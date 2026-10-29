"""拆分通用文件与项目关联，保留文件ID、历史快照引用及原元数据。"""

import sqlalchemy as sa
from alembic import op

revision = "a7c13f2d9560"
down_revision = "f52ed530d1b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 上一条本地自动迁移已建立通用表，本条仅搬迁旧元数据，避免改写已应用版本。
    conflicts = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM biz_project_attachment p JOIN common_file f ON f.id=p.id OR f.storage_key=p.storage_key"))
    if conflicts:
        raise RuntimeError("新旧文件记录存在ID或存储标识冲突，请先人工核对，禁止覆盖")
    op.execute(sa.text("""INSERT INTO common_file (id, original_name, storage_key, size_bytes, content_type, sha256, uploader_id, created_time, discarded_time, expires_at, attached_time)
        SELECT id, original_name, storage_key, size_bytes, content_type, sha256, uploader_id, created_time,
        CASE WHEN project_id IS NULL THEN removed_time ELSE NULL END, expires_at,
        CASE WHEN project_id IS NOT NULL THEN created_time ELSE NULL END FROM biz_project_attachment"""))
    op.execute(sa.text("INSERT INTO biz_project_file (project_id, file_id, removed_time) SELECT project_id, id, removed_time FROM biz_project_attachment WHERE project_id IS NOT NULL"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("SELECT setval(pg_get_serial_sequence('common_file', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM common_file), 0), 1), EXISTS(SELECT 1 FROM common_file))"))
    # 上一迁移新建的旧表已完整搬迁；旧资料快照引用的文件ID未改变。
    op.drop_table("biz_project_attachment")


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM (SELECT file_id FROM biz_project_file GROUP BY file_id HAVING COUNT(*) > 1) AS shared_files"))
    if count:
        raise RuntimeError("已有跨项目复用文件，不能无损降级为单项目附件")
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
    op.execute(sa.text("""INSERT INTO biz_project_attachment (id, project_id, original_name, storage_key, size_bytes, content_type, sha256, uploader_id, created_time, removed_time, expires_at)
        SELECT f.id, p.project_id, f.original_name, f.storage_key, f.size_bytes, f.content_type, f.sha256, f.uploader_id, f.created_time,
        CASE WHEN p.project_id IS NULL THEN f.discarded_time ELSE p.removed_time END, f.expires_at
        FROM common_file f LEFT JOIN biz_project_file p ON p.file_id=f.id"""))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("SELECT setval(pg_get_serial_sequence('biz_project_attachment', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM biz_project_attachment), 0), 1), EXISTS(SELECT 1 FROM biz_project_attachment))"))
    # 返回上一迁移的状态：通用表仍存在，数据已完整复制回旧表。
    op.execute(sa.text("DELETE FROM biz_project_file"))
    op.execute(sa.text("DELETE FROM common_file"))
