from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import SuccessResponse
from app.core.base_schema import AuthSchema
from app.core.dependencies import AuthPermission, db_getter, get_current_user
from app.core.router_class import OperationLogRoute
from app.modules.business.project.service import ProjectService
from app.modules.system.role.model import RoleModel

from .schema import BindingSave, BusinessRoleSave, CommandRequest, DefinitionSave, ScopeSave, TaskDecision
from .service import WorkflowService

WorkflowRouter = APIRouter(prefix="/workflow", tags=["审批流程配置"], route_class=OperationLogRoute)
TaskRouter = APIRouter(prefix="/task", tags=["我的审批"], route_class=OperationLogRoute)
DB = Annotated[AsyncSession, Depends(db_getter)]
ConfigReader = Annotated[AuthSchema, Security(AuthPermission(["module_system:workflow:query", "module_system:workflow:configure"]))]
ConfigWriter = Annotated[AuthSchema, Security(AuthPermission(["module_system:workflow:configure"]))]
Participant = Annotated[AuthSchema, Depends(get_current_user)]


@WorkflowRouter.get("/list")
async def flow_list(auth: ConfigReader, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).list_definitions())


@WorkflowRouter.get("/detail/{definition_id}")
async def flow_detail(definition_id: int, auth: ConfigReader, db: DB, version_id: Annotated[int | None, Query(gt=0)] = None):
    return SuccessResponse(data=await WorkflowService(auth, db).definition_detail(definition_id, version_id))


@WorkflowRouter.post("/create")
async def flow_create(data: DefinitionSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).save_definition(data))


@WorkflowRouter.put("/update/{definition_id}")
async def flow_update(definition_id: int, data: DefinitionSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).save_definition(data, definition_id))


@WorkflowRouter.post("/validate")
async def flow_validate(data: DefinitionSave, auth: ConfigReader, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).validate_definition(data.graph))


@WorkflowRouter.post("/publish/{definition_id}")
async def flow_publish(definition_id: int, data: CommandRequest, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:workflow:publish"]))]):
    return SuccessResponse(data=await WorkflowService(auth, db).publish(definition_id, data))


@WorkflowRouter.get("/binding")
async def flow_binding(auth: ConfigReader, db: DB):
    binding = await WorkflowService(auth, db).binding()
    return SuccessResponse(data={"definition_id": binding.definition_id, "manager_role_id": binding.manager_role_id})


@WorkflowRouter.put("/binding")
async def flow_bind(data: BindingSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).set_binding(data))


@WorkflowRouter.get("/options")
async def flow_options(auth: ConfigReader, db: DB):
    options = await ProjectService(auth, db).options()
    roles = (await db.execute(select(RoleModel.id, RoleModel.name, RoleModel.code).where(RoleModel.status == 0, RoleModel.is_deleted.is_(False)).order_by(RoleModel.order))).all()
    options["roles"] = [{"id": row.id, "name": row.name, "code": row.code} for row in roles]
    options["business_roles"] = await WorkflowService(auth, db).business_roles()
    return SuccessResponse(data=options)


@WorkflowRouter.get("/business-roles")
async def business_roles(auth: ConfigReader, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).business_roles())


@WorkflowRouter.post("/business-roles")
async def business_role_create(data: BusinessRoleSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).save_business_role(data))


@WorkflowRouter.put("/business-roles/{role_id}")
async def business_role_update(role_id: int, data: BusinessRoleSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).save_business_role(data, role_id))


@WorkflowRouter.get("/role-members/{role_id}")
async def role_members(role_id: int, auth: ConfigReader, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).role_members(role_id))


@WorkflowRouter.put("/role-members/{role_id}/{user_id}")
async def role_scope(role_id: int, user_id: int, data: ScopeSave, auth: ConfigWriter, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).save_scope(role_id, user_id, data.dept_ids))


# 个人任务入口只要求登录；能读/能操作仍由任务归属与状态校验，不授予项目列表权限。
@TaskRouter.get("/todo")
async def my_todo(auth: Participant, db: DB, page_no: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 10):
    return SuccessResponse(data=await WorkflowService(auth, db).task_page("todo", page_no, page_size))


@TaskRouter.get("/done")
async def my_done(auth: Participant, db: DB, page_no: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 10):
    return SuccessResponse(data=await WorkflowService(auth, db).task_page("done", page_no, page_size))


@TaskRouter.get("/{task_id}/detail")
async def my_task_detail(task_id: int, auth: Participant, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).task_detail(task_id))


@TaskRouter.post("/{task_id}/approve")
async def task_approve(task_id: int, data: TaskDecision, auth: Participant, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).decide(task_id, data, "approve"))


@TaskRouter.post("/{task_id}/reject")
async def task_reject(task_id: int, data: TaskDecision, auth: Participant, db: DB):
    return SuccessResponse(data=await WorkflowService(auth, db).decide(task_id, data, "reject"))


@TaskRouter.post("/instances/{instance_id}/recover")
async def instance_recover(instance_id: int, data: CommandRequest, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:workflow:recover"]))]):
    return SuccessResponse(data=await WorkflowService(auth, db).recover(instance_id, data))
