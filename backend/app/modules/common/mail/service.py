import asyncio
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.common.enums import RET
from app.config.setting import Settings
from app.core.exceptions import CustomException
from app.core.logger import logger

from .schema import MailSendResultSchema, MailSendSchema


class MailService:
    """可复用的 SMTP 发送服务；不依赖项目或流程模块，不自动重试。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_configured(self) -> None:
        if not self.settings.MAIL_ENABLED:
            raise CustomException(msg="邮件功能未开启，请配置 MAIL_* 并设置 MAIL_ENABLED=True 后重启后端", code=RET.SERVICE_UNAVAILABLE.code)
        required = {
            "MAIL_HOST": self.settings.MAIL_HOST.strip(),
            "MAIL_USERNAME": self.settings.MAIL_USERNAME.strip(),
            "MAIL_PASSWORD": self.settings.MAIL_PASSWORD.get_secret_value().strip(),
            "MAIL_FROM": self.settings.MAIL_FROM,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise CustomException(msg=f"邮件配置不完整，缺少：{', '.join(missing)}", code=RET.SERVICE_UNAVAILABLE.code)
        if "\r" in self.settings.MAIL_FROM_NAME or "\n" in self.settings.MAIL_FROM_NAME:
            raise CustomException(msg="MAIL_FROM_NAME 不能包含换行符", code=RET.SERVICE_UNAVAILABLE.code)

    async def send(self, data: MailSendSchema) -> MailSendResultSchema:
        self.ensure_configured()
        sender = str(self.settings.MAIL_FROM)
        message = EmailMessage()
        message["From"] = Address(display_name=self.settings.MAIL_FROM_NAME, addr_spec=sender)
        message["To"] = str(data.recipient)
        message["Subject"] = data.subject
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message_id = make_msgid()
        message["Message-ID"] = message_id
        message.set_content(data.text)

        try:
            # smtplib 是阻塞 I/O：交给线程执行，但仍等待结果，非“返回后后台发送”。
            await asyncio.to_thread(self._deliver, message, sender, str(data.recipient))
        except smtplib.SMTPAuthenticationError:
            raise CustomException(msg="SMTP 认证失败，请检查邮箱账号、客户端授权码和 SMTP 开通状态", code=RET.SERVICE_UNAVAILABLE.code) from None
        except ssl.SSLCertVerificationError:
            raise CustomException(msg="SMTP 证书校验失败，请检查邮件服务地址与服务器证书，不要关闭证书校验", code=RET.BAD_GATEWAY.code) from None
        except TimeoutError:
            raise CustomException(msg="邮件服务超时，投递结果未确认，请先检查收件箱，勿立即重复发送", code=RET.GATEWAY_TIMEOUT.code) from None
        except smtplib.SMTPRecipientsRefused:
            raise CustomException(msg="邮件服务拒绝了收件人，请检查邮箱地址及发信限制", code=RET.BAD_GATEWAY.code) from None
        except smtplib.SMTPSenderRefused:
            raise CustomException(msg="邮件服务拒绝了发件人，请检查 MAIL_FROM 是否与发信账号匹配", code=RET.BAD_GATEWAY.code) from None
        except (OSError, smtplib.SMTPException, UnicodeError) as exc:
            # 不记录 SMTP 响应原文、堆栈局部变量或邮件正文，防止凭据与业务数据泄露。
            logger.warning("SMTP 发送未确认，异常类型={}", type(exc).__name__)
            raise CustomException(msg="邮件发送未确认，请检查 SMTP 地址、端口、加密方式及网络；重试前先检查收件箱", code=RET.BAD_GATEWAY.code) from None
        return MailSendResultSchema(message_id=message_id)

    def _deliver(self, message: EmailMessage, sender: str, recipient: str) -> None:
        context = ssl.create_default_context()
        client: smtplib.SMTP | None = None
        try:
            if self.settings.MAIL_SECURITY == "SSL":
                client = smtplib.SMTP_SSL(self.settings.MAIL_HOST.strip(), self.settings.MAIL_PORT, timeout=self.settings.MAIL_TIMEOUT_SECONDS, context=context)
            else:
                client = smtplib.SMTP(self.settings.MAIL_HOST.strip(), self.settings.MAIL_PORT, timeout=self.settings.MAIL_TIMEOUT_SECONDS)
                client.ehlo()
                client.starttls(context=context)  # 不支持 STARTTLS 时直接失败，绝不降级为明文认证
                client.ehlo()
            client.login(self.settings.MAIL_USERNAME.strip(), self.settings.MAIL_PASSWORD.get_secret_value())
            refused = client.send_message(message, from_addr=sender, to_addrs=[recipient])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        finally:
            if client is not None:
                try:
                    client.quit()
                except OSError:
                    # DATA 已被接受后，QUIT 断连不能被误报成发送失败，否则人工重试会重复发送。
                    pass
                finally:
                    client.close()
