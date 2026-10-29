from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import StreamResponse, SuccessResponse
from app.core.base_schema import AuthSchema
from app.core.dependencies import AuthPermission, db_getter
from app.core.router_class import OperationLogRoute
from app.modules.common.file.private_access import register_file_access
from app.modules.workflow.schema import CommandRequest
from app.modules.workflow.service import WorkflowService
from app.utils.common_util import bytes2file_response

from .attachments import authorize_file_download
from .schema import ProjectCreateSchema, ProjectCreateSubmitSchema, ProjectUpdateSchema, ProjectUpdateSubmitSchema
from .service import ProjectService

ProjectRouter = APIRouter(prefix="/project", tags=["项目管理"], route_class=OperationLogRoute)
DB = Annotated[AsyncSession, Depends(db_getter)]
register_file_access("project", authorize_file_download, upload_permissions=("module_business:project:create", "module_business:project:update"))


@ProjectRouter.get("/list", summary="按创建人/管理部门快照查询项目")
async def project_list(
    db: DB,
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:query"]))],
    page_no: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    name: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str, Query(max_length=32)] = "",
):
    return SuccessResponse(data=await ProjectService(auth, db).page(page_no, page_size, name, status))


@ProjectRouter.get("/export", summary="按列表筛选与可见权限导出全部项目")
async def project_export(
    db: DB,
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:query"]))],
    name: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str, Query(max_length=32)] = "",
):
    content = await ProjectService(auth, db).export(name, status)
    return StreamResponse(
        data=bytes2file_response(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=projects.xlsx"},
    )


@ProjectRouter.get("/options", summary="项目最小人员/部门/字典目录")
async def project_options(
    db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:create", "module_business:project:update"]))], search: Annotated[str, Query(max_length=100)] = ""
):
    return SuccessResponse(data=await ProjectService(auth, db).options(search))


@ProjectRouter.get("/detail/{project_id}", summary="普通项目详情，遵守列表可见范围")
async def project_detail(project_id: int, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:detail"]))]):
    return SuccessResponse(data=await ProjectService(auth, db).detail(project_id))


@ProjectRouter.post("/create", summary="创建项目草稿")
async def project_create(data: ProjectCreateSchema, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:create"]))]):
    return SuccessResponse(data=await ProjectService(auth, db).create(data))


@ProjectRouter.post("/create-and-submit", summary="创建并直接提交审批，同一事务原子完成")
async def project_create_submit(
    data: ProjectCreateSubmitSchema,
    db: DB,
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:create"]))],
    _submit_auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:submit"]))],
):
    # AuthPermission 的列表是 OR，两个依赖分别校验才能要求 create AND submit。
    return SuccessResponse(data=await ProjectService(auth, db).create_and_submit(data))


@ProjectRouter.put("/update/{project_id}", summary="仅创建人修改起草资料")
async def project_update(project_id: int, data: ProjectUpdateSchema, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:update"]))]):
    return SuccessResponse(data=await ProjectService(auth, db).update(project_id, data))


@ProjectRouter.put("/update-and-submit/{project_id}", summary="保存编辑内容并直接提交审批，同一事务原子完成")
async def project_update_submit(
    project_id: int,
    data: ProjectUpdateSubmitSchema,
    db: DB,
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:update"]))],
    _submit_auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:submit"]))],
):
    return SuccessResponse(data=await ProjectService(auth, db).update_and_submit(project_id, data))


@ProjectRouter.post("/{project_id}/precheck", summary="提交前校验全部分支审批人，不创建待办")
async def project_precheck(project_id: int, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:submit"]))]):
    return SuccessResponse(data=await WorkflowService(auth, db).precheck(project_id))


@ProjectRouter.post("/{project_id}/submit", summary="提交或重新提交，首次绑定发布版")
async def project_submit(project_id: int, data: CommandRequest, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:submit"]))]):
    return SuccessResponse(data=await WorkflowService(auth, db).submit(project_id, data))


@ProjectRouter.post("/{project_id}/withdraw", summary="创建人在无人审批时撤回")
async def project_withdraw(project_id: int, data: CommandRequest, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:withdraw"]))]):
    return SuccessResponse(data=await WorkflowService(auth, db).withdraw(project_id, data))


@ProjectRouter.post("/{project_id}/delete", summary="创建人软删除草稿并终止挂起流程")
async def project_delete(project_id: int, data: CommandRequest, db: DB, auth: Annotated[AuthSchema, Security(AuthPermission(["module_business:project:delete"]))]):
    return SuccessResponse(data=await ProjectService(auth, db).delete(project_id, data))
