from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import SuccessResponse, UploadFileResponse
from app.core.base_schema import AuthSchema
from app.core.dependencies import db_getter, get_current_user
from app.core.router_class import OperationLogRoute

from .private_access import require_upload_access
from .private_service import PrivateFileService

PrivateFileRouter = APIRouter(prefix="/private", tags=["通用私有文件"], route_class=OperationLogRoute)
DB = Annotated[AsyncSession, Depends(db_getter)]
CurrentUser = Annotated[AuthSchema, Depends(get_current_user)]


@PrivateFileRouter.get("/options", summary="私有文件上传限制")
async def private_file_options(db: DB, auth: CurrentUser):
    from app.config.setting import settings

    await PrivateFileService(auth, db).actor()
    return SuccessResponse(data={"max_file_size": settings.MAX_FILE_SIZE, "extensions": settings.PRIVATE_FILE_EXTENSIONS, "temporary_hours": 24})


@PrivateFileRouter.post("/upload", summary="上传通用私有临时文件，24小时内由业务接纳")
async def private_file_upload(db: DB, auth: CurrentUser, file: Annotated[UploadFile, File()]):
    require_upload_access(auth)
    return SuccessResponse(data=await PrivateFileService(auth, db).upload(file))


@PrivateFileRouter.post("/{attachment_id}/discard", summary="废弃本人未被业务使用的临时文件")
async def private_file_discard(attachment_id: int, db: DB, auth: CurrentUser):
    return SuccessResponse(data=await PrivateFileService(auth, db).discard(attachment_id))


@PrivateFileRouter.get("/{attachment_id}/download", summary="按业务模块注册的鉴权策略下载私有文件")
async def private_file_download(
    attachment_id: int,
    db: DB,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    business_key: Annotated[str | None, Query(max_length=64)] = None,
    business_id: Annotated[int | None, Query(gt=0)] = None,
    revision_id: Annotated[int | None, Query(gt=0)] = None,
    task_id: Annotated[int | None, Query(gt=0)] = None,
):
    path, name = await PrivateFileService(auth, db).download(attachment_id, business_key, business_id, revision_id, task_id)
    return UploadFileResponse(str(path), name, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
