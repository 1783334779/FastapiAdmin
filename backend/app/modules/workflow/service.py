import hashlib
import json
from copy import deepcopy

from sqlalchemy import delete, func, select

from app.common.enums import RET
from app.common.response import jsonable_response_content
from app.core.exceptions import CustomException
from app.modules.system.dept.model import DeptModel
from app.modules.system.user.model import UserModel, UserRolesModel

from .adapters import adapter_for
from .engine import WorkflowRuntime
from .graph import validate_graph
from .model import (
    BusinessRoleModel,
    RoleManagedDeptModel,
    WorkflowActionModel,
    WorkflowBindingModel,
    WorkflowCommandModel,
    WorkflowDefinitionModel,
    WorkflowInstanceModel,
    WorkflowTaskModel,
    WorkflowVersionModel,
    WorkflowVisitModel,
)
from .resolvers import AssigneeResolver, validate_business_rule


def conflict(message="数据已发生变化，请刷新后重试"):
    raise CustomException(msg=message, code=RET.CONFLICT.code)


class WorkflowService:
    def __init__(self, auth, db) -> None:
        self.auth, self.db = auth, db

    async def actor(self):
        actor = await self.db.scalar(select(UserModel).where(UserModel.id == self.auth.user.id, UserModel.status == 0, UserModel.is_deleted.is_(False)))
        if actor is None:
            raise CustomException(msg="当前账号已失效", code=RET.FORBIDDEN.code)
        return actor

    async def binding(self, lock=False):
        await self.actor()
        query = select(WorkflowBindingModel).where(WorkflowBindingModel.business_key == "project")
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.db.scalar(query)
        if result is None:
            result = WorkflowBindingModel(business_key="project")
            self.db.add(result)
            await self.db.flush()
        return result

    async def list_definitions(self):
        await self.actor()
        definitions = (await self.db.execute(select(WorkflowDefinitionModel).order_by(WorkflowDefinitionModel.id.desc()))).scalars().all()
        return [
            {"id": item.id, "code": item.code, "name": item.name, "enabled": item.enabled, "published_version_id": item.published_version_id, "lock_version": item.lock_version} for item in definitions
        ]

    async def definition_detail(self, definition_id: int, version_id: int | None = None):
        await self.actor()
        definition = await self.db.get(WorkflowDefinitionModel, definition_id)
        if not definition:
            raise CustomException(msg="流程不存在", code=RET.NOT_FOUND.code)
        versions = (await self.db.execute(select(WorkflowVersionModel).where(WorkflowVersionModel.definition_id == definition_id).order_by(WorkflowVersionModel.version_no.desc()))).scalars().all()
        selected = next((version for version in versions if version.id == version_id), None)
        if version_id is not None and selected is None:
            raise CustomException(msg="此版本不属于当前流程", code=RET.NOT_FOUND.code)
        return {
            "id": definition.id,
            "code": definition.code,
            "name": definition.name,
            "enabled": definition.enabled,
            "lock_version": definition.lock_version,
            "published_version_id": definition.published_version_id,
            "graph": selected.graph if selected else definition.draft_graph,
            "read_only": selected is not None,
            "versions": [{"id": version.id, "version_no": version.version_no, "created_time": version.created_time} for version in versions],
        }

    async def save_definition(self, body, definition_id=None):
        await self.actor()
        if (
            len(json.dumps(body.graph)) > 250000
            or not isinstance(body.graph.get("nodes"), list)
            or not isinstance(body.graph.get("edges"), list)
            or len(body.graph["nodes"]) > 100
            or len(body.graph["edges"]) > 300
        ):
            raise CustomException(msg="流程草稿需包含 nodes/edges，且不超过100节点、300连线及250KB")
        duplicate = await self.db.scalar(select(WorkflowDefinitionModel.id).where(WorkflowDefinitionModel.code == body.code))
        if duplicate is not None and duplicate != definition_id:
            raise CustomException(msg="流程编码已存在")
        if definition_id:
            definition = await self.db.scalar(select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.id == definition_id).with_for_update().execution_options(populate_existing=True))
            if not definition:
                raise CustomException(msg="流程不存在", code=RET.NOT_FOUND.code)
            if definition.lock_version != body.expected_version:
                conflict()
            if definition.code != body.code:
                raise CustomException(msg="已有流程的稳定编码不能修改")
            definition.name, definition.draft_graph, definition.enabled = body.name, deepcopy(body.graph), body.enabled
            definition.updated_by, definition.lock_version = self.auth.user.id, definition.lock_version + 1
        else:
            definition = WorkflowDefinitionModel(code=body.code, name=body.name, business_key="project", draft_graph=deepcopy(body.graph), enabled=body.enabled, updated_by=self.auth.user.id)
            self.db.add(definition)
        await self.db.flush()
        return await self.definition_detail(definition.id)

    async def frozen_rules(self, graph):
        rules = {}
        binding = await self.binding()
        for node in graph["nodes"]:
            if node["type"] != "APPROVAL":
                continue
            for source in node["data"]["assignees"]:
                if source["type"] == "SYSTEM_ROLE":
                    await AssigneeResolver(self.db).role_users(source["role_id"])
                    continue
                code = source["code"]
                role = await self.db.scalar(select(BusinessRoleModel).where(BusinessRoleModel.code == code, BusinessRoleModel.enabled.is_(True), BusinessRoleModel.business_key == "project"))
                if not role:
                    raise ValueError(f"业务角色 {code} 不存在或已停用")
                config = deepcopy(role.config)
                if role.strategy == "DEPT_MANAGER" and not config.get("role_id"):
                    config["role_id"] = binding.manager_role_id
                validate_business_rule(role.strategy, config)
                if role.strategy == "DEPT_MANAGER":
                    await AssigneeResolver(self.db).role_users(config["role_id"])
                rules[code] = {"name": role.name, "strategy": role.strategy, "config": config}
        return rules

    async def validate_definition(self, graph):
        try:
            normalized = validate_graph(graph)
            await self.frozen_rules(normalized)
            return {"valid": True, "issues": []}
        except ValueError as exc:
            return {"valid": False, "issues": [str(exc)]}

    async def publish(self, definition_id, body):
        await self.actor()
        definition = await self.db.scalar(select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.id == definition_id).with_for_update().execution_options(populate_existing=True))
        if not definition:
            raise CustomException(msg="流程不存在", code=RET.NOT_FOUND.code)
        scope = f"publish:{definition.id}"
        cached, digest = await self.cached_command(scope, body)
        if cached:
            return cached.result
        if definition.lock_version != body.expected_version:
            conflict()
        try:
            graph = validate_graph(definition.draft_graph)
            rules = await self.frozen_rules(graph)
        except ValueError as exc:
            raise CustomException(msg=str(exc)) from exc
        number = (await self.db.scalar(select(func.max(WorkflowVersionModel.version_no)).where(WorkflowVersionModel.definition_id == definition.id))) or 0
        version = WorkflowVersionModel(definition_id=definition.id, version_no=number + 1, graph=graph, role_rules=rules, published_by=self.auth.user.id)
        self.db.add(version)
        await self.db.flush()
        definition.published_version_id, definition.lock_version = version.id, definition.lock_version + 1
        # result 里的时间会经 JSON 存储，统一为字符串以便幂等命中时响应一致。
        result = await self.definition_detail(definition.id)
        result = jsonable_response_content(result)
        return await self.remember(scope, body, digest, result)

    async def set_binding(self, body):
        await self.actor()
        binding = await self.binding(lock=True)
        if body.definition_id is not None:
            definition = await self.db.get(WorkflowDefinitionModel, body.definition_id)
            if not definition or not definition.enabled or not definition.published_version_id:
                raise CustomException(msg="只能绑定已启用且已发布的流程")
        if body.manager_role_id is not None:
            try:
                await AssigneeResolver(self.db).role_users(body.manager_role_id)
            except ValueError as exc:
                raise CustomException(msg=str(exc)) from exc
        binding.definition_id, binding.manager_role_id = body.definition_id, body.manager_role_id
        return {"definition_id": binding.definition_id, "manager_role_id": binding.manager_role_id}

    async def business_roles(self):
        await self.actor()
        roles = (await self.db.execute(select(BusinessRoleModel).order_by(BusinessRoleModel.id))).scalars().all()
        return [{"id": item.id, "code": item.code, "name": item.name, "strategy": item.strategy, "config": item.config, "enabled": item.enabled} for item in roles]

    async def save_business_role(self, body, role_id=None):
        await self.actor()
        try:
            validate_business_rule(body.strategy, body.config)
            if body.strategy == "DEPT_MANAGER":
                await AssigneeResolver(self.db).role_users(body.config["role_id"])
        except ValueError as exc:
            raise CustomException(msg=str(exc)) from exc
        existing = await self.db.scalar(select(BusinessRoleModel).where(BusinessRoleModel.code == body.code))
        if role_id:
            role = await self.db.get(BusinessRoleModel, role_id)
            if not role or role.code != body.code:
                raise CustomException(msg="业务角色不存在或试图修改稳定编码")
        else:
            if existing:
                raise CustomException(msg="业务角色编码已存在")
            role = BusinessRoleModel(code=body.code, business_key="project")
            self.db.add(role)
        role.name, role.strategy, role.config, role.enabled = body.name, body.strategy, deepcopy(body.config), body.enabled
        await self.db.flush()
        return {"id": role.id}

    async def role_members(self, role_id):
        await self.actor()
        rows = (
            await self.db.execute(
                select(UserModel.id, UserModel.name, UserModel.dept_id)
                .join(UserRolesModel, UserRolesModel.user_id == UserModel.id)
                .where(UserRolesModel.role_id == role_id, UserModel.is_deleted.is_(False))
                .order_by(UserModel.id)
            )
        ).all()
        scopes = (await self.db.execute(select(RoleManagedDeptModel).where(RoleManagedDeptModel.role_id == role_id))).scalars().all()
        return [{"id": row.id, "name": row.name, "dept_id": row.dept_id, "managed_dept_ids": [scope.dept_id for scope in scopes if scope.user_id == row.id]} for row in rows]

    async def save_scope(self, role_id, user_id, dept_ids):
        await self.actor()
        member = await self.db.scalar(select(UserRolesModel.user_id).where(UserRolesModel.role_id == role_id, UserRolesModel.user_id == user_id))
        if member is None:
            raise CustomException(msg="该人员不属于所选角色，请先在用户管理分配角色")
        ids = set(dept_ids)
        valid = set((await self.db.execute(select(DeptModel.id).where(DeptModel.id.in_(ids), DeptModel.status == 0, DeptModel.is_deleted.is_(False)))).scalars().all())
        if valid != ids:
            raise CustomException(msg="管理部门包含无效部门")
        await self.db.execute(delete(RoleManagedDeptModel).where(RoleManagedDeptModel.role_id == role_id, RoleManagedDeptModel.user_id == user_id))
        self.db.add_all([RoleManagedDeptModel(role_id=role_id, user_id=user_id, dept_id=value) for value in sorted(ids)])
        return {"saved": True}

    async def version_for_project(self, project, lock=False):
        query = select(WorkflowInstanceModel).where(WorkflowInstanceModel.business_key == "project", WorkflowInstanceModel.business_id == project.id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        instance = await self.db.scalar(query)
        if instance:
            return await self.db.get(WorkflowVersionModel, instance.version_id), instance
        binding = await self.binding(lock=lock)
        definition = await self.db.get(WorkflowDefinitionModel, binding.definition_id) if binding.definition_id else None
        if not definition or not definition.enabled or not definition.published_version_id:
            raise CustomException(msg="项目模块尚未绑定已发布流程，请联系管理员配置")
        if lock:
            definition = await self.db.scalar(select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.id == definition.id).with_for_update().execution_options(populate_existing=True))
        return await self.db.get(WorkflowVersionModel, definition.published_version_id), None

    async def precheck(self, project_id):
        await self.actor()
        adapter = adapter_for("project", self.db)
        project = await adapter.load(project_id)
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以提交预检查", code=RET.FORBIDDEN.code)
        version, _ = await self.version_for_project(project)
        context = await adapter.context(project)
        issues = await AssigneeResolver(self.db).precheck(version.graph, version.role_rules, context)
        return {"valid": not issues, "issues": issues, "version_id": version.id, "version_no": version.version_no}

    async def cached_command(self, scope, body, lock=False):
        digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        query = select(WorkflowCommandModel).where(WorkflowCommandModel.actor_id == self.auth.user.id, WorkflowCommandModel.scope == scope, WorkflowCommandModel.command_key == body.command_key)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        command = await self.db.scalar(query)
        if command and command.request_hash != digest:
            conflict("同一幂等键不能用于不同请求内容")
        return command, digest

    async def remember(self, scope, body, digest, result):
        self.db.add(WorkflowCommandModel(actor_id=self.auth.user.id, scope=scope, command_key=body.command_key, request_hash=digest, result=deepcopy(result)))
        await self.db.flush()
        return result

    def summary(self, instance):
        return {
            "id": instance.id,
            "status": instance.status,
            "round_no": instance.round_no,
            "version_id": instance.version_id,
            "lock_version": instance.lock_version,
            "has_approval_action": instance.has_approval_action,
            "blocked": instance.state.get("blocked"),
            "returns": instance.state.get("returns", []),
            "routes": instance.state.get("routes", []),
            "rounds": [
                {"round_no": item["round_no"], "submitted_revision_id": item.get("submitted_revision_id"), "routes": item.get("routes", []), "closed_by": item.get("closed_by")}
                for item in instance.state.get("history_rounds", [])
            ]
            + [{"round_no": instance.round_no, "submitted_revision_id": instance.state.get("submitted_revision_id"), "routes": instance.state.get("routes", [])}],
        }

    async def submit(self, project_id, body):
        await self.actor()
        adapter = adapter_for("project", self.db)
        project = await adapter.load(project_id, lock=True)
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以提交", code=RET.FORBIDDEN.code)
        scope = f"submit:{project.id}"
        cached, digest = await self.cached_command(scope, body)
        if cached:
            return cached.result
        from app.modules.business.project.schema import ProjectCreateSchema
        from app.modules.business.project.service import ProjectService

        business = ProjectService(self.auth, self.db)
        business.require_owner_edit(project, body.expected_version)
        context = await adapter.context(project)
        data = ProjectCreateSchema.model_validate({key: context["snapshot"][key] for key in ProjectCreateSchema.model_fields if key in context["snapshot"]})
        await business.validate_input(data)
        from app.modules.business.project.attachments import ProjectAttachmentService

        await ProjectAttachmentService(self.auth, self.db).validate_snapshot(project, context["snapshot"])
        version, instance = await self.version_for_project(project, lock=True)
        issues = await AssigneeResolver(self.db).precheck(version.graph, version.role_rules, context)
        if issues:
            raise CustomException(msg="提交失败：" + "；".join(f"{issue['node_name']}：{issue['reason']}" for issue in issues))
        if instance is None:
            instance = WorkflowInstanceModel(business_key="project", business_id=project.id, version_id=version.id, status="RUNNING", round_no=1, has_approval_action=False, state={}, lock_version=1)
            self.db.add(instance)
            await self.db.flush()
        runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, context, self.auth.user.id)
        if instance.status == "RETURNED" and instance.state.get("returns") and not instance.state.get("restart_required"):
            await runtime.resubmit_targeted()
        else:
            if instance.state:
                await runtime.cancel_open("NEW_ROUND")
                instance.round_no += 1
            await runtime.start()
        await runtime.persist()
        await adapter.sync_status(project, instance)
        return await self.remember(scope, body, digest, self.summary(instance))

    async def locked_task(self, task_id):
        task = await self.db.scalar(select(WorkflowTaskModel).where(WorkflowTaskModel.id == task_id, WorkflowTaskModel.assignee_id == self.auth.user.id))
        if task is None:
            raise CustomException(msg="任务不存在或不属于当前用户", code=RET.NOT_FOUND.code)
        instance = await self.db.get(WorkflowInstanceModel, task.instance_id)
        adapter = adapter_for(instance.business_key, self.db)
        project = await adapter.load(instance.business_id, lock=True)
        instance = await self.db.scalar(select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == instance.id).with_for_update().execution_options(populate_existing=True))
        task = await self.db.scalar(select(WorkflowTaskModel).where(WorkflowTaskModel.id == task_id).with_for_update().execution_options(populate_existing=True))
        return task, instance, project, adapter

    async def decide(self, task_id, body, action):
        await self.actor()
        task, instance, project, adapter = await self.locked_task(task_id)
        scope = f"{action}:{task.id}"
        cached, digest = await self.cached_command(scope, body)
        if cached:
            return cached.result
        if instance.status != "RUNNING" or task.status != "PENDING":
            conflict("任务已完成、暂停或流程不允许操作，请刷新")
        if instance.lock_version != body.expected_version:
            conflict()
        context = await adapter.context(project)
        if context["revision_id"] != body.expected_revision_id:
            conflict("项目资料已经变化，请刷新并审阅最新资料后再处理")
        visit = await self.db.get(WorkflowVisitModel, task.visit_id)
        if visit.status != "ACTIVE":
            conflict("当前节点不在可审批状态")
        version = await self.db.get(WorkflowVersionModel, instance.version_id)
        runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, context, self.auth.user.id)
        try:
            if action == "approve":
                if body.mode is not None or body.target is not None:
                    raise ValueError("同意操作不能携带驳回参数")
                await runtime.approve(task, visit, body.opinion)
            else:
                if body.mode not in {"RESTART", "TARGETED"}:
                    raise ValueError("请选择驳回模式")
                await runtime.reject(task, visit, body.mode, body.target, body.opinion)
        except ValueError as exc:
            raise CustomException(msg=str(exc)) from exc
        await runtime.persist()
        await adapter.sync_status(project, instance)
        return await self.remember(scope, body, digest, self.summary(instance))

    async def withdraw(self, project_id, body):
        await self.actor()
        adapter = adapter_for("project", self.db)
        project = await adapter.load(project_id, lock=True)
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以撤回", code=RET.FORBIDDEN.code)
        cached, digest = await self.cached_command(f"withdraw:{project.id}", body)
        if cached:
            return cached.result
        if project.lock_version != body.expected_version:
            conflict()
        version, instance = await self.version_for_project(project, lock=True)
        if not instance or instance.status not in {"RUNNING", "BLOCKED"} or instance.has_approval_action:
            raise CustomException(msg="只有尚无人作出审批操作的审批中项目才能撤回")
        runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, await adapter.context(project), self.auth.user.id)
        await runtime.cancel_open("WITHDRAW")
        instance.status = "WITHDRAWN"
        await runtime.persist()
        await adapter.sync_status(project, instance)
        return await self.remember(f"withdraw:{project.id}", body, digest, self.summary(instance))

    async def terminate_for_delete(self, project):
        instance = await self.db.scalar(select(WorkflowInstanceModel).where(WorkflowInstanceModel.business_key == "project", WorkflowInstanceModel.business_id == project.id).with_for_update())
        if instance:
            version = await self.db.get(WorkflowVersionModel, instance.version_id)
            adapter = adapter_for("project", self.db)
            runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, await adapter.context(project), self.auth.user.id)
            await runtime.cancel_open("DELETE_DRAFT")
            instance.status = "TERMINATED"
            await runtime.persist()

    async def recover(self, instance_id, body):
        await self.actor()
        instance = await self.db.get(WorkflowInstanceModel, instance_id)
        if not instance:
            raise CustomException(msg="流程实例不存在", code=RET.NOT_FOUND.code)
        adapter = adapter_for(instance.business_key, self.db)
        project = await adapter.load(instance.business_id, lock=True)
        instance = await self.db.scalar(select(WorkflowInstanceModel).where(WorkflowInstanceModel.id == instance_id).with_for_update().execution_options(populate_existing=True))
        cached, digest = await self.cached_command(f"recover:{instance.id}", body)
        if cached:
            return cached.result
        if instance.lock_version != body.expected_version:
            conflict()
        version = await self.db.get(WorkflowVersionModel, instance.version_id)
        runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, await adapter.context(project), self.auth.user.id)
        try:
            await runtime.retry()
        except ValueError as exc:
            raise CustomException(msg=str(exc)) from exc
        await runtime.persist()
        await adapter.sync_status(project, instance)
        return await self.remember(f"recover:{instance.id}", body, digest, self.summary(instance))

    async def business_history(self, business_key, business_id):
        instance = await self.db.scalar(select(WorkflowInstanceModel).where(WorkflowInstanceModel.business_key == business_key, WorkflowInstanceModel.business_id == business_id))
        if not instance:
            return None
        version = await self.db.get(WorkflowVersionModel, instance.version_id)
        visits = (await self.db.execute(select(WorkflowVisitModel).where(WorkflowVisitModel.instance_id == instance.id).order_by(WorkflowVisitModel.id))).scalars().all()
        tasks = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.instance_id == instance.id).order_by(WorkflowTaskModel.id))).scalars().all()
        logs = (await self.db.execute(select(WorkflowActionModel).where(WorkflowActionModel.instance_id == instance.id).order_by(WorkflowActionModel.id))).scalars().all()
        actor_ids = {log.actor_id for log in logs}
        names = {row.id: row.name for row in (await self.db.execute(select(UserModel.id, UserModel.name).where(UserModel.id.in_(actor_ids)))).all()}
        return {
            **self.summary(instance),
            "version_no": version.version_no,
            "graph": version.graph,
            "visits": [
                {
                    "id": visit.id,
                    "node_key": visit.node_key,
                    "node_name": visit.node_name,
                    "round_no": visit.round_no,
                    "status": visit.status,
                    "approval_mode": visit.approval_mode,
                    "revision_id": visit.revision_id,
                    "candidates": visit.candidates,
                    "resolution": visit.resolution,
                    "tasks": [
                        {
                            "id": task.id,
                            "assignee_id": task.assignee_id,
                            "status": task.status,
                            "opinion": task.opinion,
                            "decision_revision_id": task.decision_revision_id,
                            "completed_time": task.completed_time,
                        }
                        for task in tasks
                        if task.visit_id == visit.id
                    ],
                }
                for visit in visits
            ],
            "actions": [
                {
                    "id": log.id,
                    "actor_id": log.actor_id,
                    "actor_name": names.get(log.actor_id, "历史用户"),
                    "action": log.action,
                    "visit_id": log.visit_id,
                    "revision_id": log.revision_id,
                    "opinion": log.opinion,
                    "details": log.details,
                    "created_time": log.created_time,
                }
                for log in logs
            ],
        }

    async def task_detail(self, task_id):
        await self.actor()
        task = await self.db.scalar(select(WorkflowTaskModel).where(WorkflowTaskModel.id == task_id, WorkflowTaskModel.assignee_id == self.auth.user.id))
        if not task:
            raise CustomException(msg="任务不存在或不属于当前用户", code=RET.NOT_FOUND.code)
        instance = await self.db.get(WorkflowInstanceModel, task.instance_id)
        adapter = adapter_for(instance.business_key, self.db)
        project = await adapter.load(instance.business_id, include_deleted=True)
        context = await adapter.context(project)
        version = await self.db.get(WorkflowVersionModel, instance.version_id)
        visit = await self.db.get(WorkflowVisitModel, task.visit_id)
        runtime = WorkflowRuntime(self.db, instance, version.graph, version.role_rules, context, self.auth.user.id)
        from app.modules.business.project.model import ProjectRevisionModel

        revisions = (await self.db.execute(select(ProjectRevisionModel).where(ProjectRevisionModel.project_id == project.id).order_by(ProjectRevisionModel.revision_no.desc()))).scalars().all()
        allowed = task.status == "PENDING" and instance.status == "RUNNING" and not project.is_deleted and visit.status == "ACTIVE"
        return {
            "task": {"id": task.id, "status": task.status, "node_name": visit.node_name, "activation_revision_id": visit.revision_id},
            "project": {
                **context["snapshot"],
                "id": project.id,
                "status": project.status,
                "revision_id": context["revision_id"],
                "revision_no": project.revision_no,
                "lock_version": project.lock_version,
            },
            "workflow": await self.business_history(instance.business_key, instance.business_id),
            "allowed_actions": {"approve": allowed, "reject": allowed},
            "reject_targets": await runtime.targets(visit) if allowed else [],
            "revisions": [{"id": revision.id, "revision_no": revision.revision_no, "payload": revision.payload, "created_time": revision.created_time} for revision in revisions],
        }

    async def task_page(self, bucket, page_no, page_size):
        await self.actor()
        states = ["PENDING", "SUSPENDED"] if bucket == "todo" else ["APPROVED", "REJECTED", "CLOSED", "CANCELLED"]
        condition = (WorkflowTaskModel.assignee_id == self.auth.user.id) & WorkflowTaskModel.status.in_(states)
        total = await self.db.scalar(select(func.count()).select_from(WorkflowTaskModel).where(condition))
        rows = (
            await self.db.execute(
                select(WorkflowTaskModel, WorkflowVisitModel, WorkflowInstanceModel)
                .join(WorkflowVisitModel, WorkflowVisitModel.id == WorkflowTaskModel.visit_id)
                .join(WorkflowInstanceModel, WorkflowInstanceModel.id == WorkflowTaskModel.instance_id)
                .where(condition)
                .order_by(WorkflowTaskModel.id.desc())
                .offset((page_no - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = []
        for task, visit, instance in rows:
            adapter = adapter_for(instance.business_key, self.db)
            project = await adapter.load(instance.business_id, include_deleted=True)
            items.append(
                {
                    "id": task.id,
                    "project_id": project.id,
                    "project_name": project.name,
                    "node_name": visit.node_name,
                    "status": task.status,
                    "workflow_status": instance.status,
                    "round_no": visit.round_no,
                    "created_time": task.created_time,
                    "completed_time": task.completed_time,
                }
            )
        return {"items": items, "total": total, "page_no": page_no, "page_size": page_size}
