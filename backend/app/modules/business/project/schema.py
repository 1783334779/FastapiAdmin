"""项目请求的数据结构；不访问数据库，也不创建数据库表。"""

from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PositiveId = Annotated[int, Field(strict=True, gt=0)]


class ProjectCreateSchema(BaseModel):
    """创建项目的输入，只校验格式；关联数据的有效性由 Service 校验。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    initiation_type: str = Field(..., min_length=1, max_length=255, description="立项类型的字典值")
    category: str = Field(..., min_length=1, max_length=255, description="项目类别的字典值")
    it_manager_ids: list[PositiveId] = Field(..., min_length=1, description="IT 项目经理用户 ID 列表")
    external_purchase: bool = Field(..., strict=True, description="是否对外采购，必须传 true 或 false")
    business_manager_ids: list[PositiveId] = Field(..., min_length=1, description="业务项目经理用户 ID 列表")
    business_dept_id: PositiveId = Field(..., description="业务部门 ID；不代表创建人部门快照")
    planned_start_date: date = Field(..., description="计划开始日期，格式 YYYY-MM-DD")
    planned_end_date: date = Field(..., description="计划结束日期，格式 YYYY-MM-DD")
    currency: str = Field(..., min_length=1, max_length=255, description="币种的字典值")

    @field_validator("it_manager_ids", "business_manager_ids")
    @classmethod
    def deduplicate_manager_ids(cls, value: list[int]) -> list[int]:
        """每类经理按用户 ID 去重，保留首次出现的顺序。"""
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_project_period(self) -> Self:
        """单个日期合法之后，再校验两个日期之间的关系。"""
        if self.planned_end_date < self.planned_start_date:
            raise ValueError("计划结束日期不能早于计划开始日期")
        return self


class ProjectUpdateSchema(ProjectCreateSchema):
    expected_version: PositiveId = Field(..., description="页面读取到的项目并发版本号")


class ProjectCreateSubmitSchema(ProjectCreateSchema):
    command_key: str = Field(min_length=8, max_length=100, description="创建并提交的幂等键，重试同一请求时保持不变")


class ProjectUpdateSubmitSchema(ProjectUpdateSchema):
    command_key: str = Field(min_length=8, max_length=100, description="修改并提交的幂等键，重试同一请求时保持不变")
