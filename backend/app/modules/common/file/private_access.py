"""业务注册资料下载规则和既有写入权限；通用层不导入业务代码。"""

from collections.abc import Awaitable, Callable

from app.common.enums import RET
from app.core.exceptions import CustomException

FileAccess = Callable[..., Awaitable[None]]
FILE_ACCESS_POLICIES: dict[str, FileAccess] = {}
FILE_UPLOAD_PERMISSIONS: dict[str, tuple[str, ...]] = {}


def register_file_access(business_key: str, policy: FileAccess, *, upload_permissions: tuple[str, ...] = ()) -> None:
    FILE_ACCESS_POLICIES[business_key] = policy
    FILE_UPLOAD_PERMISSIONS[business_key] = upload_permissions


def require_upload_access(auth) -> None:
    """沿用业务的创建/编辑权限，不额外配置文件上传权限。"""
    allowed = {permission for permissions in FILE_UPLOAD_PERMISSIONS.values() for permission in permissions}
    if not auth.user.is_superuser and not allowed.intersection(auth.permissions):
        raise CustomException(msg="当前账号没有可上传附件的业务创建或编辑权限", code=RET.FORBIDDEN.code)
