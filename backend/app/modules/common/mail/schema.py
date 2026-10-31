from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MailSendSchema(BaseModel):
    """第一版仅支持单收件人、纯文本；SMTP 配置不允许由请求传入。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient: EmailStr = Field(max_length=254, description="收件人邮箱，测试时请填写自己的邮箱")
    subject: str = Field(min_length=1, max_length=200, description="邮件标题")
    text: str = Field(min_length=1, max_length=10000, description="纯文本正文，不解析 HTML")

    @field_validator("recipient", "subject", mode="before")
    @classmethod
    def reject_header_newlines(cls, value: object) -> object:
        if isinstance(value, str) and ("\r" in value or "\n" in value):
            raise ValueError("邮件地址和标题不能包含换行符")
        return value


class MailSendResultSchema(BaseModel):
    message_id: str = Field(description="本次邮件的 Message-ID，不表示已经送达或已读")
    status: Literal["ACCEPTED"] = Field(default="ACCEPTED", description="SMTP 服务已接受邮件，不代表已进入收件箱")
