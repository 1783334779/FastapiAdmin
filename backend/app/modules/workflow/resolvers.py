"""按稳定规则找人；人员在每次节点激活时解析，本次待办随后冻结。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.system.dept.model import DeptModel
from app.modules.system.role.model import RoleModel
from app.modules.system.user.model import UserModel, UserRolesModel

from .model import RoleManagedDeptModel, WorkflowBindingModel

USER_FIELDS = {"it_manager_ids", "business_manager_ids", "creator_user_id"}


def validate_business_rule(strategy: str, config: dict) -> None:
    if strategy == "FIELD_USERS":
        if not isinstance(config.get("field"), str) or config["field"] not in USER_FIELDS:
            raise ValueError("人员字段仅支持IT经理、业务经理或创建人")
    elif strategy == "DEPT_MANAGER":
        if type(config.get("role_id")) is not int or config["role_id"] <= 0:
            raise ValueError("部门负责人规则必须选择一个系统角色")
    else:
        raise ValueError("不支持该找人策略，不能配置任意脚本")


class AssigneeResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def users(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        rows = (await self.db.execute(select(UserModel.id, UserModel.name).where(UserModel.id.in_(ids), UserModel.status == 0, UserModel.is_deleted.is_(False)))).all()
        return [{"id": row.id, "name": row.name} for row in rows]

    async def role_users(self, role_id: int, dept_id: int | None = None) -> list[dict]:
        role = await self.db.scalar(select(RoleModel.id).where(RoleModel.id == role_id, RoleModel.status == 0, RoleModel.is_deleted.is_(False)))
        if role is None:
            raise ValueError(f"系统角色 {role_id} 不存在、被停用或已删除")
        query = (
            select(UserModel.id, UserModel.name)
            .join(UserRolesModel, UserRolesModel.user_id == UserModel.id)
            .where(
                UserRolesModel.role_id == role_id,
                UserModel.status == 0,
                UserModel.is_deleted.is_(False),
            )
        )
        if dept_id is not None:
            query = query.join(RoleManagedDeptModel, (RoleManagedDeptModel.user_id == UserModel.id) & (RoleManagedDeptModel.role_id == role_id)).where(RoleManagedDeptModel.dept_id == dept_id)
        rows = (await self.db.execute(query)).all()
        return [{"id": row.id, "name": row.name} for row in rows]

    async def department_managers(self, role_id: int, department_id: int) -> tuple[list[dict], list[int]]:
        checked = []
        while department_id:
            if department_id in checked:
                raise ValueError("部门树存在回环，请管理员修复")
            checked.append(department_id)
            department = await self.db.scalar(select(DeptModel).where(DeptModel.id == department_id, DeptModel.status == 0, DeptModel.is_deleted.is_(False)))
            if department is None:
                raise ValueError(f"创建部门或上级部门 {department_id} 已失效")
            people = await self.role_users(role_id, department_id)
            if people:
                return people, checked
            department_id = department.parent_id
        return [], checked

    async def resolve(self, node: dict, role_rules: dict, context: dict) -> tuple[list[dict], list[dict]]:
        people, explanations = {}, []
        for rule in node["data"]["assignees"]:
            checked = []
            if rule["type"] == "SYSTEM_ROLE":
                found = await self.role_users(rule["role_id"])
                label = f"系统角色:{rule['role_id']}"
            else:
                code = rule["code"]
                if code not in role_rules:
                    raise ValueError(f"发布版缺少业务角色规则 {code}")
                saved = role_rules[code]
                strategy, config = saved["strategy"], saved["config"]
                validate_business_rule(strategy, config)
                label = saved.get("name", code)
                if strategy == "FIELD_USERS":
                    ids = context["snapshot"].get(config["field"], [])
                    ids = ids if isinstance(ids, list) else [ids]
                    found = await self.users(ids)
                else:
                    found, checked = await self.department_managers(config["role_id"], context["creator_dept_id"])
            people.update({person["id"]: person for person in found})
            explanations.append({"source": label, "user_ids": [person["id"] for person in found], "departments_checked": checked})
        return sorted(people.values(), key=lambda person: person["id"]), explanations

    async def precheck(self, graph: dict, role_rules: dict, context: dict) -> list[dict]:
        issues = []
        for node in graph["nodes"]:
            if node["type"] != "APPROVAL":
                continue
            try:
                people, explanation = await self.resolve(node, role_rules, context)
                if not people:
                    issues.append({"node_key": node["id"], "node_name": node["data"]["label"], "reason": "未找到有效审批人", "sources": explanation})
            except ValueError as exc:
                issues.append({"node_key": node["id"], "node_name": node["data"]["label"], "reason": str(exc)})
        return issues


async def managed_department_ids(db: AsyncSession, user_id: int) -> set[int]:
    binding = await db.scalar(select(WorkflowBindingModel).where(WorkflowBindingModel.business_key == "project"))
    if not binding or not binding.manager_role_id:
        return set()
    query = (
        select(RoleManagedDeptModel.dept_id)
        .join(
            UserRolesModel,
            (UserRolesModel.user_id == RoleManagedDeptModel.user_id) & (UserRolesModel.role_id == RoleManagedDeptModel.role_id),
        )
        .join(RoleModel, RoleModel.id == RoleManagedDeptModel.role_id)
        .where(
            RoleManagedDeptModel.user_id == user_id,
            RoleManagedDeptModel.role_id == binding.manager_role_id,
            RoleModel.status == 0,
            RoleModel.is_deleted.is_(False),
        )
    )
    found = set((await db.execute(query)).scalars().all())
    rows = (await db.execute(select(DeptModel.id, DeptModel.parent_id).where(DeptModel.status == 0, DeptModel.is_deleted.is_(False)))).all()
    valid_ids = {row.id for row in rows}
    found &= valid_ids
    while True:
        expanded = found | {row.id for row in rows if row.parent_id in found}
        if expanded == found:
            return found
        found = expanded
