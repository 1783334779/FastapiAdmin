"""里程碑表兜底重建：清理旧版遗留结构，使库内结构对齐当前模型。

背景：biz_project_milestone 曾以旧形态（主键 (project_id, name)、name 指向
common_file、含 removed_time/owner_user_id 列）被建表；改版后的 08:21 迁移
直接按最终模型建表。本迁移兜底处理「库内仍是旧形态」的情况（含本机 08:21 旧版
已应用、08:22 首版加列失败遗留的中间态）：旧形态主键结构与最终形态不同，无法
通过 ALTER 无损收敛，且该表为新增功能表（无业务数据），核对无数据后重建为
最终形态；已为最终形态时跳过。

Revision ID: 2c9934f399e6
Revises: 92d939deb155
Create Date: 2026-10-29 08:22:33.383033

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2c9934f399e6'
down_revision: Union[str, None] = '92d939deb155'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_milestone_table() -> None:
    """按当前模型创建 biz_project_milestone（与模型 metadata 逐字段一致，避免 autogen 漂移）。"""
    op.create_table(
        'biz_project_milestone',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), nullable=False, comment='所属项目ID'),
        sa.Column('name', sa.String(length=200), nullable=False, comment='里程碑名称'),
        sa.Column('delivery_standard', sa.String(length=1000), nullable=False, comment='交付标准'),
        sa.Column('planned_start_time', sa.DateTime(timezone=True), nullable=False, comment='计划开始时间'),
        sa.Column('planned_end_time', sa.DateTime(timezone=True), nullable=False, comment='计划结束时间'),
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.CheckConstraint('planned_end_time >= planned_start_time', name=op.f('ck_biz_project_milestone_project_milestone_period')),
        sa.ForeignKeyConstraint(['project_id'], ['biz_project.id'], name=op.f('fk_biz_project_milestone_project_id_biz_project'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_biz_project_milestone')),
        comment='项目里程碑表',
    )
    op.create_index('ix_biz_project_milestone_project', 'biz_project_milestone', ['project_id'], unique=False)


def _create_member_table() -> None:
    """按当前模型创建 biz_project_milestone_member。"""
    op.create_table(
        'biz_project_milestone_member',
        sa.Column('milestone_id', sa.Integer(), nullable=False, comment='里程碑ID'),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='责任人用户ID'),
        sa.ForeignKeyConstraint(['milestone_id'], ['biz_project_milestone.id'], name=op.f('fk_biz_project_milestone_member_milestone_id_biz_project_milestone'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['sys_user.id'], name=op.f('fk_biz_project_milestone_member_user_id_sys_user'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('milestone_id', 'user_id', name=op.f('pk_biz_project_milestone_member')),
        comment='里程碑责任人关联表',
    )
    op.create_index('ix_biz_project_milestone_member_milestone', 'biz_project_milestone_member', ['milestone_id'], unique=False)
    op.create_index('ix_biz_project_milestone_member_user', 'biz_project_milestone_member', ['user_id'], unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 旧形态特征列 removed_time：命中即需重建（主键结构不同，无法 ALTER 收敛）
    if inspector.has_table('biz_project_milestone'):
        cols = {c['name'] for c in inspector.get_columns('biz_project_milestone')}
        if 'removed_time' in cols:
            rows = bind.scalar(sa.text('SELECT COUNT(*) FROM biz_project_milestone'))
            if rows:
                raise RuntimeError(f'biz_project_milestone 旧形态仍有 {rows} 行数据，禁止重建，请先人工迁移')
            op.drop_table('biz_project_milestone')
            inspector = sa.inspect(bind)  # 重新反射，反映删除后的状态

    if not inspector.has_table('biz_project_milestone'):
        _create_milestone_table()
    if not inspector.has_table('biz_project_milestone_member'):
        _create_member_table()


def downgrade() -> None:
    # 重建后的最终形态无法恢复旧形态；按链式语义回滚：先删成员表，再删里程碑表
    # （08:21 的 downgrade 会继续处理前置结构）。旧形态遗留结构在 upgrade 中已不可恢复。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('biz_project_milestone_member'):
        op.drop_table('biz_project_milestone_member')
    if inspector.has_table('biz_project_milestone'):
        op.drop_table('biz_project_milestone')
