"""项目私有附件，仅新增附件表，不修改既有业务数据。"""

import sqlalchemy as sa
from alembic import op

revision = "f3c91d72a604"
down_revision = "d6849f0dd210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_project_attachment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_biz_project_attachment_project_attachment_size")),
        sa.ForeignKeyConstraint(["project_id"], ["biz_project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploader_id"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_project_attachment_project_removed", "biz_project_attachment", ["project_id", "removed_time"])
    op.create_index("ix_project_attachment_temporary_expiry", "biz_project_attachment", ["project_id", "expires_at"])
    op.create_index("ix_project_attachment_uploader", "biz_project_attachment", ["uploader_id"])


def downgrade() -> None:
    op.drop_index("ix_project_attachment_uploader", table_name="biz_project_attachment")
    op.drop_index("ix_project_attachment_temporary_expiry", table_name="biz_project_attachment")
    op.drop_index("ix_project_attachment_project_removed", table_name="biz_project_attachment")
    op.drop_table("biz_project_attachment")
