from typing import Annotated

from fastapi import APIRouter, Body, Depends, Security
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis
from redis.exceptions import RedisError

from app.common.enums import RET
from app.common.response import ResponseSchema, SuccessResponse
from app.config.setting import Settings, get_settings
from app.core.base_schema import AuthSchema
from app.core.dependencies import get_current_user, redis_getter
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .schema import MailSendResultSchema, MailSendSchema
from .service import MailService

MailRouter = APIRouter(route_class=OperationLogRoute, prefix="/mail", tags=["邮件发送"])


async def require_mail_admin(auth: Annotated[AuthSchema, Security(get_current_user)]) -> AuthSchema:
    if not auth.user.id or not auth.user.is_superuser:
        raise CustomException(msg="仅超级管理员可发送测试邮件", code=RET.FORBIDDEN.code)
    return auth


@MailRouter.post("/test", summary="手动发送测试邮件（仅超级管理员）", response_model=ResponseSchema[MailSendResultSchema])
async def send_test_mail_controller(
    auth: Annotated[AuthSchema, Depends(require_mail_admin)],
    redis: Annotated[Redis, Depends(redis_getter)],
    settings: Annotated[Settings, Depends(get_settings)],
    data: Annotated[MailSendSchema, Body(description="请使用自己的邮箱作为测试收件人；不要传入授权码")],
) -> JSONResponse:
    service = MailService(settings)
    service.ensure_configured()
    try:
        # Redis 原子占位，多 worker 也不能绕过；失败仍保留冷却，避免反复认证触发邮箱风控。
        allowed = await redis.set(f"common:mail:test:cooldown:{auth.user.id}", "1", ex=60, nx=True)
    except RedisError:
        raise CustomException(msg="邮件测试限流服务不可用，暂不发送", code=RET.SERVICE_UNAVAILABLE.code) from None
    if not allowed:
        raise CustomException(msg="测试邮件每位管理员每 60 秒最多发送一次，请稍后再试", code=RET.TOO_MANY_REQUESTS.code)
    result = await service.send(data)
    return SuccessResponse(data=result, msg="SMTP 服务已接受邮件，请检查收件箱或垃圾邮件，不代表已送达或已读")
