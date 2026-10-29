"""通用私有文件元数据，不依赖项目或审批流程。"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class PrivateFileModel(MappedBase):
    __tablename__ = "common_file"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="private_file_size"),
        Index("ix_common_file_temporary_expiry", "attached_time", "expires_at"),
        Index("ix_common_file_uploader", "uploader_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    discarded_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 曾被业务接纳的文件不再作为临时文件清理，保护历史引用。
    attached_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
