"""项目主表、当前经理关联及不可覆写的资料版本。审批实例位于 workflow 模块。"""

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import JSONType, MappedBase, ModelMixin, UserMixin


class ProjectModel(ModelMixin, UserMixin):
    """一行代表一个项目，创建身份和业务状态由后端控制。"""

    __tablename__: str = "biz_project"
    __table_args__ = (
        CheckConstraint("planned_end_date >= planned_start_date", name="project_planned_period"),
        Index("ix_biz_project_creator_status_deleted", "creator_user_id", "status", "is_deleted"),
        Index("ix_biz_project_dept_status_deleted", "creator_dept_id", "status", "is_deleted"),
        Index("ix_biz_project_status_deleted", "status", "is_deleted"),
        Index("ix_biz_project_created_deleted", "created_time", "is_deleted"),
        {"comment": "项目主表"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="项目名称")
    initiation_type: Mapped[str] = mapped_column(String(255), nullable=False, comment="立项类型字典值")
    category: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目类别字典值")
    external_purchase: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否对外采购")
    business_dept_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_dept.id", ondelete="RESTRICT"),
        nullable=False,
        comment="表单选择的业务部门ID",
    )
    planned_start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划开始日期")
    planned_end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划结束日期")
    currency: Mapped[str] = mapped_column(String(255), nullable=False, comment="币种字典值")

    # Service 从认证用户读取；更新 Schema 不接收创建身份，防止客户端改写。
    creator_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        nullable=False,
        comment="业务创建人ID，创建时固定",
    )
    creator_dept_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_dept.id", ondelete="RESTRICT"),
        nullable=False,
        comment="创建人部门ID快照，不跟随调岗或业务部门修改变化",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        comment="项目业务状态，DRAFT表示起草，不是启用/停用",
    )
    current_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="当前资料版本ID")
    revision_no: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False, comment="资料版本号")
    lock_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False, comment="并发版本号")

class ProjectMemberModel(MappedBase):
    """当前经理关系；三个字段共同组成主键，历史名单由资料版本保留。"""

    __tablename__: str = "biz_project_member"
    __table_args__ = (
        CheckConstraint("member_type IN ('IT_MANAGER', 'BUSINESS_MANAGER')", name="project_member_type"),
        Index("ix_biz_project_member_project_type", "project_id", "member_type"),
        Index("ix_biz_project_member_user_id", "user_id"),
        {"comment": "项目经理关联表"},
    )

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("biz_project.id", ondelete="CASCADE"),
        primary_key=True,
        comment="项目ID",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        primary_key=True,
        comment="担任经理的用户ID",
    )
    member_type: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        comment="单据成员类别：IT_MANAGER（IT项目经理）、BUSINESS_MANAGER（业务项目经理）",
    )


class ProjectRevisionModel(MappedBase):
    """不可覆写的资料快照，审批记录引用自己实际审阅的版本。"""

    __tablename__ = "biz_project_revision"
    __table_args__ = (UniqueConstraint("project_id", "revision_no", name="uq_project_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("biz_project.id", ondelete="RESTRICT"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    editor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ProjectAttachmentModel(MappedBase):
    """项目只保存文件关联；文件元数据和临时生命周期位于 common_file。"""

    __tablename__ = "biz_project_file"
    __table_args__ = (Index("ix_project_file_project_removed", "project_id", "removed_time"),)
    project_id: Mapped[int] = mapped_column(ForeignKey("biz_project.id", ondelete="RESTRICT"), primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("common_file.id", ondelete="RESTRICT"), primary_key=True)
    removed_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ProjectMilestoneModel(MappedBase):
    """项目里程碑：一行代表一个里程碑节点，责任人多对多存于成员表。"""

    __tablename__ = "biz_project_milestone"
    __table_args__ = (
        CheckConstraint("planned_end_time >= planned_start_time", name="project_milestone_period"),
        Index("ix_biz_project_milestone_project", "project_id"),
        {"comment": "项目里程碑表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("biz_project.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属项目ID",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="里程碑名称")
    delivery_standard: Mapped[str] = mapped_column(String(1000), nullable=False, comment="交付标准")
    planned_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="计划开始时间")
    planned_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="计划结束时间")
    owner_users: Mapped[list["ProjectMilestoneMemberModel"]] = relationship(
        "ProjectMilestoneMemberModel",
        back_populates="milestone",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class ProjectMilestoneMemberModel(MappedBase):
    """里程碑责任人关系表；多个字段共同组成主键，与项目经理关联表同构。"""

    __tablename__ = "biz_project_milestone_member"
    __table_args__ = (
        Index("ix_biz_project_milestone_member_milestone", "milestone_id"),
        Index("ix_biz_project_milestone_member_user", "user_id"),
        {"comment": "里程碑责任人关联表"},
    )

    milestone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("biz_project_milestone.id", ondelete="CASCADE"),
        primary_key=True,
        comment="里程碑ID",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="RESTRICT"),
        primary_key=True,
        comment="责任人用户ID",
    )
    milestone: Mapped["ProjectMilestoneModel"] = relationship(
        "ProjectMilestoneModel",
        back_populates="owner_users",
        passive_deletes=True,
    )