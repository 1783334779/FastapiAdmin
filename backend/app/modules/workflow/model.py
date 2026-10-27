"""流程版本不可变；节点执行、个人任务及业务轨迹独立持久化。"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import JSONType, MappedBase


class WorkflowRecord(MappedBase):
    __abstract__ = True
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class WorkflowDefinitionModel(WorkflowRecord):
    __tablename__ = "wf_definition"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    business_key: Mapped[str] = mapped_column(String(64), default="project")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    draft_graph: Mapped[dict] = mapped_column(JSONType)
    published_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int] = mapped_column(Integer)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class WorkflowVersionModel(WorkflowRecord):
    __tablename__ = "wf_version"
    __table_args__ = (UniqueConstraint("definition_id", "version_no", name="uq_wf_version"),)
    definition_id: Mapped[int] = mapped_column(ForeignKey("wf_definition.id", ondelete="RESTRICT"))
    version_no: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict] = mapped_column(JSONType)
    role_rules: Mapped[dict] = mapped_column(JSONType)
    published_by: Mapped[int] = mapped_column(Integer)


class WorkflowBindingModel(WorkflowRecord):
    __tablename__ = "wf_binding"
    business_key: Mapped[str] = mapped_column(String(64), unique=True, default="project")
    definition_id: Mapped[int | None] = mapped_column(ForeignKey("wf_definition.id", ondelete="RESTRICT"), nullable=True)
    manager_role_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BusinessRoleModel(WorkflowRecord):
    __tablename__ = "wf_business_role"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    business_key: Mapped[str] = mapped_column(String(64), default="project")
    strategy: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RoleManagedDeptModel(MappedBase):
    __tablename__ = "sys_user_role_managed_dept"
    __table_args__ = (ForeignKeyConstraint(["user_id", "role_id"], ["sys_user_roles.user_id", "sys_user_roles.role_id"], ondelete="CASCADE"), Index("ix_managed_dept_user_role", "user_id", "role_id"))
    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dept_id: Mapped[int] = mapped_column(ForeignKey("sys_dept.id", ondelete="CASCADE"), primary_key=True)


class WorkflowInstanceModel(WorkflowRecord):
    __tablename__ = "wf_instance"
    __table_args__ = (UniqueConstraint("business_key", "business_id", name="uq_wf_business_instance"),)
    business_key: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("wf_version.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    has_approval_action: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[dict] = mapped_column(JSONType, default=dict)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class WorkflowVisitModel(WorkflowRecord):
    __tablename__ = "wf_visit"
    instance_id: Mapped[int] = mapped_column(ForeignKey("wf_instance.id", ondelete="RESTRICT"), index=True)
    round_no: Mapped[int] = mapped_column(Integer)
    token_id: Mapped[str] = mapped_column(String(64))
    node_key: Mapped[str] = mapped_column(String(64))
    node_name: Mapped[str] = mapped_column(String(200))
    lane: Mapped[list] = mapped_column(JSONType, default=list)
    approval_mode: Mapped[str] = mapped_column(String(8))
    revision_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    candidates: Mapped[list] = mapped_column(JSONType)
    resolution: Mapped[list] = mapped_column(JSONType)


class WorkflowTaskModel(WorkflowRecord):
    __tablename__ = "wf_task"
    __table_args__ = (UniqueConstraint("visit_id", "assignee_id", name="uq_wf_visit_assignee"), Index("ix_wf_task_assignee_status", "assignee_id", "status"))
    instance_id: Mapped[int] = mapped_column(ForeignKey("wf_instance.id", ondelete="RESTRICT"), index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("wf_visit.id", ondelete="RESTRICT"), index=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    opinion: Mapped[str] = mapped_column(Text, default="")
    decision_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowActionModel(WorkflowRecord):
    __tablename__ = "wf_action"
    instance_id: Mapped[int] = mapped_column(ForeignKey("wf_instance.id", ondelete="RESTRICT"), index=True)
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    visit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opinion: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSONType, default=dict)


class WorkflowCommandModel(WorkflowRecord):
    __tablename__ = "wf_command"
    __table_args__ = (UniqueConstraint("actor_id", "scope", "command_key", name="uq_wf_command"),)
    actor_id: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(100))
    command_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONType)
