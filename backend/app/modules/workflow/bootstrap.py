"""新增功能的幂等配置补齐：不覆盖原菜单、字典或已编辑的流程。"""

from sqlalchemy import inspect, select

from app.core.logger import logger
from app.modules.system.dict.model import DictTypeModel
from app.modules.system.menu.model import MenuModel

from .graph import default_graph
from .model import BusinessRoleModel, WorkflowBindingModel, WorkflowDefinitionModel


async def bootstrap_workflow(db) -> None:
    connection = await db.connection()
    if not await connection.run_sync(lambda conn: inspect(conn).has_table("wf_definition")):
        logger.warning("审批模块尚未执行迁移，暂不补齐其菜单配置")
        return

    async def menu(route_name, title, path, component=None, parent_id=None, permission=None, hidden=False, kind=2, icon="ri:git-branch-line", redirect=None):
        existing = await db.scalar(select(MenuModel).where(MenuModel.route_name == route_name))
        if existing:
            return existing
        item = MenuModel(
            name=title,
            title=title,
            type=kind,
            order=70,
            status=0,
            route_name=route_name,
            route_path=path,
            component_path=component,
            redirect=redirect,
            parent_id=parent_id,
            permission=permission,
            hidden=hidden,
            keep_alive=False,
            icon=icon,
            scope="web",
        )
        db.add(item)
        await db.flush()
        return item

    system = await db.scalar(select(MenuModel).where(MenuModel.route_name == "System"))
    if not system:
        system = await menu("System", "系统管理", "/system", kind=1, redirect="/system/approval-flows")
    config = await menu("ApprovalFlowConfig", "审批流程配置", "approval-flows", "module_system/approval_flow/index", system.id, "module_system:workflow:query")
    await menu("ApprovalFlowDesigner", "设计审批流程", "approval-flows/:id/design", "module_system/approval_flow/designer", system.id, "module_system:workflow:query", True)
    for action, label in (("configure", "配置审批流程"), ("publish", "发布审批流程"), ("recover", "恢复阻塞流程")):
        await menu(f"ApprovalFlow_{action}", label, "", parent_id=config.id, permission=f"module_system:workflow:{action}", hidden=True, kind=3)
    business = await menu("BusinessProjects", "项目管理", "/business", kind=1, icon="ri:briefcase-3-line", redirect="/business/projects")
    # 补齐本模块初次开发时遗漏的目录重定向，不覆盖管理员自定义值。
    if not business.redirect:
        business.redirect = "/business/projects"
    project = await menu("ProjectList", "项目列表", "projects", "module_business/project/index", business.id, "module_business:project:query", icon="ri:folder-2-line")
    for name, path, component, permission in (
        ("ProjectCreate", "projects/new", "create", "create"),
        ("ProjectEdit", "projects/:id/edit", "edit", "update"),
        ("ProjectDetail", "projects/:id", "detail", "detail"),
    ):
        await menu(
            name, {"create": "新建项目", "edit": "编辑项目", "detail": "项目详情"}[component], path, f"module_business/project/{component}", business.id, f"module_business:project:{permission}", True
        )
    for action, label in (("create", "创建项目"), ("detail", "查看项目"), ("update", "编辑草稿"), ("submit", "提交项目"), ("withdraw", "撤回项目"), ("delete", "删除草稿")):
        await menu(f"Project_{action}", label, "", parent_id=project.id, permission=f"module_business:project:{action}", hidden=True, kind=3)
    await menu("WorkflowTasks", "我的审批", "/workflow/tasks", "module_workflow/tasks/index", icon="ri:task-line")

    for code, name in (("project_initiation_type", "项目立项类型"), ("project_category", "项目类别"), ("project_currency", "项目币种")):
        if not await db.scalar(select(DictTypeModel.id).where(DictTypeModel.dict_type == code)):
            db.add(DictTypeModel(dict_type=code, dict_name=name, status=0))
    defaults = [
        ("PROJECT_IT_MANAGER", "当前项目IT经理", "FIELD_USERS", {"field": "it_manager_ids"}),
        ("PROJECT_BUSINESS_MANAGER", "当前项目业务经理", "FIELD_USERS", {"field": "business_manager_ids"}),
        ("CREATOR_DEPT_MANAGER", "创建部门负责人", "DEPT_MANAGER", {}),
    ]
    for code, name, strategy, config_value in defaults:
        if not await db.scalar(select(BusinessRoleModel.id).where(BusinessRoleModel.code == code)):
            db.add(BusinessRoleModel(code=code, name=name, business_key="project", strategy=strategy, config=config_value, enabled=True))
    if not await db.scalar(select(WorkflowBindingModel.id).where(WorkflowBindingModel.business_key == "project")):
        db.add(WorkflowBindingModel(business_key="project"))
    if not await db.scalar(select(WorkflowDefinitionModel.id).where(WorkflowDefinitionModel.code == "project_approval")):
        db.add(WorkflowDefinitionModel(code="project_approval", name="项目审批流程", business_key="project", enabled=True, draft_graph=default_graph(), updated_by=0))
    await db.flush()
