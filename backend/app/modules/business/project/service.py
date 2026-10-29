from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select

from app.common.enums import RET
from app.common.response import jsonable_response_content
from app.core.exceptions import CustomException
from app.modules.system.dept.model import DeptModel
from app.modules.system.dict.model import DictDataModel, DictTypeModel
from app.modules.system.user.model import UserModel
from app.modules.workflow.model import WorkflowInstanceModel
from app.modules.workflow.resolvers import managed_department_ids
from app.utils.excel_util import ExcelUtil

from .adapter import ProjectWorkflowAdapter
from .crud import ProjectCRUD
from .model import ProjectMemberModel, ProjectModel, ProjectRevisionModel
from .schema import ProjectCreateSchema, ProjectUpdateSchema

EDITABLE = {"DRAFT", "RETURNED", "WITHDRAWN"}
DICTIONARIES = {"initiation_type": "project_initiation_type", "category": "project_category", "currency": "project_currency"}
PROJECT_STATUS_LABELS = {"DRAFT": "起草", "IN_REVIEW": "审批中", "RETURNED": "退回起草", "BLOCKED": "流程阻塞", "APPROVED": "已通过", "WITHDRAWN": "已撤回"}
EXPORT_COLUMNS = {"name": "项目名称", "initiation_type": "立项类型", "business_dept_id": "业务部门", "status": "状态", "creator_name": "创建人", "created_date": "创建日期"}


class ProjectService:
    def __init__(self, auth, db) -> None:
        self.auth, self.db = auth, db
        self.adapter = ProjectWorkflowAdapter(db)

    async def actor(self, lock=False):
        query = select(UserModel).where(UserModel.id == self.auth.user.id, UserModel.status == 0, UserModel.is_deleted.is_(False))
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        user = await self.db.scalar(query)
        if user is None:
            raise CustomException(msg="当前账号已失效", code=RET.FORBIDDEN.code)
        return user

    async def visible_condition(self):
        actor = await self.actor()
        if actor.is_superuser:
            return ProjectModel.is_deleted.is_(False)
        depts = await managed_department_ids(self.db, self.auth.user.id)
        return or_(ProjectModel.creator_user_id == self.auth.user.id, ProjectModel.creator_dept_id.in_(depts))

    async def get_visible(self, project_id: int):
        project = await self.db.scalar(select(ProjectModel).where(ProjectModel.id == project_id, ProjectModel.is_deleted.is_(False), await self.visible_condition()))
        if project is None:
            raise CustomException(msg="项目不存在或无权查看", code=RET.NOT_FOUND.code)
        return project

    async def validate_input(self, data: ProjectCreateSchema) -> dict:
        ids = set(data.it_manager_ids + data.business_manager_ids)
        rows = (await self.db.execute(select(UserModel.id, UserModel.name).where(UserModel.id.in_(ids), UserModel.status == 0, UserModel.is_deleted.is_(False)))).all()
        if {row.id for row in rows} != ids:
            raise CustomException(msg="选中的项目经理有不存在、停用或已删除人员，请重新选择")
        dept = await self.db.scalar(select(DeptModel).where(DeptModel.id == data.business_dept_id, DeptModel.status == 0, DeptModel.is_deleted.is_(False)))
        if dept is None:
            raise CustomException(msg="业务部门不存在或已停用")
        labels = {"business_dept_id": dept.name}
        for field, dictionary in DICTIONARIES.items():
            label = await self.db.scalar(
                select(DictDataModel.dict_label)
                .join(DictTypeModel, DictDataModel.dict_type_id == DictTypeModel.id)
                .where(
                    DictTypeModel.dict_type == dictionary,
                    DictTypeModel.status == 0,
                    DictTypeModel.is_deleted.is_(False),
                    DictDataModel.dict_value == getattr(data, field),
                    DictDataModel.status == 0,
                    DictDataModel.is_deleted.is_(False),
                )
            )
            if label is None:
                raise CustomException(msg=f"{dictionary} 字典值无效，请先在字典管理维护有效选项")
            labels[field] = label
        return {"labels": labels, "users": [{"id": row.id, "name": row.name} for row in rows]}

    async def save_revision(self, project, data, display) -> None:
        from .attachments import ProjectAttachmentService

        attachments = await ProjectAttachmentService(self.auth, self.db).bind(project, data.attachment_ids)
        project.revision_no += 1
        payload = data.model_dump(mode="json", exclude={"expected_version"})
        payload.update(display)
        payload["attachments"] = attachments
        creator = await self.db.get(UserModel, project.creator_user_id)
        dept = await self.db.get(DeptModel, project.creator_dept_id)
        payload.update(
            creator_user_id=project.creator_user_id, creator_dept_id=project.creator_dept_id, creator_name=creator.name if creator else "历史用户", creator_dept_name=dept.name if dept else "历史部门"
        )
        revision = ProjectRevisionModel(project_id=project.id, revision_no=project.revision_no, payload=payload, editor_id=self.auth.user.id)
        self.db.add(revision)
        await self.db.flush()
        project.current_revision_id = revision.id

    async def create(self, data):
        actor = await self.actor()
        dept = await self.db.scalar(select(DeptModel.id).where(DeptModel.id == actor.dept_id, DeptModel.status == 0, DeptModel.is_deleted.is_(False)))
        if dept is None:
            raise CustomException(msg="创建人尚未配置有效部门，请先维护用户部门")
        display = await self.validate_input(data)
        project = await ProjectCRUD(self.db).create_draft(data, creator_user_id=actor.id, creator_dept_id=dept)
        await self.save_revision(project, data, display)
        return await self.serialize(project)

    async def update(self, project_id: int, data: ProjectUpdateSchema):
        await self.actor()
        project = await self.adapter.load(project_id, lock=True)
        self.require_owner_edit(project, data.expected_version)
        display = await self.validate_input(data)
        for key, value in data.model_dump(exclude={"expected_version", "it_manager_ids", "business_manager_ids", "attachment_ids"}).items():
            setattr(project, key, value)
        await self.db.execute(delete(ProjectMemberModel).where(ProjectMemberModel.project_id == project.id))
        for kind, ids in (("IT_MANAGER", data.it_manager_ids), ("BUSINESS_MANAGER", data.business_manager_ids)):
            self.db.add_all([ProjectMemberModel(project_id=project.id, user_id=user_id, member_type=kind) for user_id in ids])
        project.updated_id, project.lock_version = self.auth.user.id, project.lock_version + 1
        await self.save_revision(project, data, display)
        return await self.serialize(project)

    async def create_and_submit(self, body):
        from app.modules.workflow.schema import CommandRequest
        from app.modules.workflow.service import WorkflowService

        # 项目尚无 ID：先按创建人串行化此命令，再做当前读，避免并发重试重复建单。
        await self.actor(lock=True)
        workflow = WorkflowService(self.auth, self.db)
        scope = "project:create-and-submit"
        cached, digest = await workflow.cached_command(scope, body, lock=True)
        if cached:
            return cached.result
        data = ProjectCreateSchema.model_validate(body.model_dump(exclude={"command_key"}))
        created = await self.create(data)
        # autoflush 关闭；提交会锁定并重新读取主表，先刷新刚写入的资料指针。
        await self.db.flush()
        await workflow.submit(created["id"], CommandRequest(command_key=body.command_key, expected_version=created["lock_version"]))
        project = await self.adapter.load(created["id"])
        result = jsonable_response_content(await self.serialize(project))
        return await workflow.remember(scope, body, digest, result)

    async def update_and_submit(self, project_id, body):
        from app.modules.workflow.schema import CommandRequest
        from app.modules.workflow.service import WorkflowService

        await self.actor()
        project = await self.adapter.load(project_id, lock=True)
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以修改或提交项目", code=RET.FORBIDDEN.code)
        workflow = WorkflowService(self.auth, self.db)
        scope = f"project:update-and-submit:{project.id}"
        cached, digest = await workflow.cached_command(scope, body, lock=True)
        if cached:
            return cached.result
        data = ProjectUpdateSchema.model_validate(body.model_dump(exclude={"command_key"}))
        saved = await self.update(project.id, data)
        await self.db.flush()
        await workflow.submit(project.id, CommandRequest(command_key=body.command_key, expected_version=saved["lock_version"]))
        result = jsonable_response_content(await self.serialize(project))
        return await workflow.remember(scope, body, digest, result)

    def require_owner_edit(self, project, expected_version: int) -> None:
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以修改或提交项目", code=RET.FORBIDDEN.code)
        if project.status not in EDITABLE:
            raise CustomException(msg="只有起草、退回起草或撤回后的项目可以修改")
        if project.lock_version != expected_version:
            raise CustomException(msg="项目已发生变化，请刷新后重试", code=RET.CONFLICT.code)

    async def serialize(self, project):
        context = await self.adapter.context(project)
        instance = await self.db.scalar(select(WorkflowInstanceModel).where(WorkflowInstanceModel.business_key == "project", WorkflowInstanceModel.business_id == project.id))
        owner = project.creator_user_id == self.auth.user.id
        return {
            **context["snapshot"],
            "id": project.id,
            "status": project.status,
            "revision_id": context["revision_id"],
            "revision_no": project.revision_no,
            "lock_version": project.lock_version,
            "created_time": project.created_time,
            "updated_time": project.updated_time,
            "allowed_actions": {
                "edit": owner and project.status in EDITABLE,
                "submit": owner and project.status in EDITABLE,
                "delete": owner and project.status in EDITABLE,
                "withdraw": owner and bool(instance) and instance.status in {"RUNNING", "BLOCKED"} and not instance.has_approval_action,
            },
        }

    async def list_conditions(self, name: str = "", status: str = ""):
        """列表和全量导出共用筛选及对象可见范围，不接受客户端指定数据范围。"""
        conditions = [ProjectModel.is_deleted.is_(False), await self.visible_condition()]
        if name:
            conditions.append(ProjectModel.name.contains(name, autoescape=True))
        if status:
            conditions.append(ProjectModel.status == status)
        return conditions

    async def page(self, page_no: int, page_size: int, name: str = "", status: str = ""):
        conditions = await self.list_conditions(name, status)
        total = await self.db.scalar(select(func.count()).select_from(ProjectModel).where(*conditions))
        projects = (await self.db.execute(select(ProjectModel).where(*conditions).order_by(ProjectModel.id.desc()).offset((page_no - 1) * page_size).limit(page_size))).scalars().all()
        return {"items": [await self.serialize(project) for project in projects], "total": total, "page_no": page_no, "page_size": page_size}

    async def export(self, name: str = "", status: str = "") -> bytes:
        conditions = await self.list_conditions(name, status)
        # 与列表同序，不分页；批量取当前快照，避免逐条 serialize 额外查询审批实例。
        rows = (
            await self.db.execute(
                select(ProjectModel, ProjectRevisionModel.payload)
                .outerjoin(ProjectRevisionModel, ProjectRevisionModel.id == ProjectModel.current_revision_id)
                .where(*conditions)
                .order_by(ProjectModel.id.desc())
            )
        ).all()
        data = []
        for project, snapshot in rows:
            if snapshot is None:
                raise CustomException(msg=f"项目 {project.id} 缺少当前资料版本，请修复后重新导出")
            labels = snapshot.get("labels") or {}
            data.append(
                {
                    "name": snapshot.get("name"),
                    "initiation_type": labels.get("initiation_type") if labels.get("initiation_type") is not None else snapshot.get("initiation_type"),
                    "business_dept_id": labels.get("business_dept_id") if labels.get("business_dept_id") is not None else snapshot.get("business_dept_id"),
                    "status": PROJECT_STATUS_LABELS.get(project.status, project.status),
                    "creator_name": snapshot.get("creator_name"),
                    "created_date": project.created_time.strftime("%Y-%m-%d") if project.created_time else None,
                }
            )
        return await ExcelUtil.aexport_list2excel(data, EXPORT_COLUMNS, max_rows=None)

    async def detail(self, project_id: int):
        project = await self.get_visible(project_id)
        from app.modules.workflow.service import WorkflowService

        result = await self.serialize(project)
        result["workflow"] = await WorkflowService(self.auth, self.db).business_history("project", project.id)
        revisions = (await self.db.execute(select(ProjectRevisionModel).where(ProjectRevisionModel.project_id == project.id).order_by(ProjectRevisionModel.revision_no.desc()))).scalars().all()
        result["revisions"] = [{"id": item.id, "revision_no": item.revision_no, "editor_id": item.editor_id, "created_time": item.created_time, "payload": item.payload} for item in revisions]
        return result

    async def delete(self, project_id: int, body):
        await self.actor()
        project = await self.adapter.load(project_id, lock=True, include_deleted=True)
        if project.creator_user_id != self.auth.user.id:
            raise CustomException(msg="只有创建人可以删除草稿", code=RET.FORBIDDEN.code)
        from app.modules.workflow.service import WorkflowService

        workflow = WorkflowService(self.auth, self.db)
        scope = f"delete:{project.id}"
        cached, digest = await workflow.cached_command(scope, body)
        if cached:
            return cached.result
        if project.is_deleted:
            raise CustomException(msg="项目已删除", code=RET.NOT_FOUND.code)
        self.require_owner_edit(project, body.expected_version)
        await workflow.terminate_for_delete(project)
        project.is_deleted, project.deleted_id, project.deleted_time = True, self.auth.user.id, datetime.now(UTC)
        project.lock_version += 1
        return await workflow.remember(scope, body, digest, {"id": project.id, "deleted": True})

    async def options(self, search: str = ""):
        await self.actor()
        query = select(UserModel.id, UserModel.name, UserModel.username, UserModel.dept_id).where(UserModel.status == 0, UserModel.is_deleted.is_(False))
        if search:
            query = query.where(or_(UserModel.name.contains(search, autoescape=True), UserModel.username.contains(search, autoescape=True)))
        users = (await self.db.execute(query.order_by(UserModel.id).limit(300))).all()
        depts = (await self.db.execute(select(DeptModel.id, DeptModel.name, DeptModel.parent_id).where(DeptModel.status == 0, DeptModel.is_deleted.is_(False)))).all()
        dictionaries = {}
        for field, code in DICTIONARIES.items():
            rows = (
                await self.db.execute(
                    select(DictDataModel.dict_value, DictDataModel.dict_label)
                    .join(DictTypeModel, DictTypeModel.id == DictDataModel.dict_type_id)
                    .where(DictTypeModel.dict_type == code, DictTypeModel.status == 0, DictTypeModel.is_deleted.is_(False), DictDataModel.status == 0, DictDataModel.is_deleted.is_(False))
                    .order_by(DictDataModel.dict_sort)
                )
            ).all()
            dictionaries[field] = [{"value": row.dict_value, "label": row.dict_label} for row in rows]
        return {
            "users": [{"id": row.id, "name": row.name, "username": row.username, "dept_id": row.dept_id} for row in users],
            "departments": [{"id": row.id, "name": row.name, "parent_id": row.parent_id} for row in depts],
            "dictionaries": dictionaries,
        }
