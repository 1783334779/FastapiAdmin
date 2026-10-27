from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DefinitionSave(StrictRequest):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    graph: dict[str, Any]
    enabled: bool = True
    expected_version: int | None = Field(default=None, ge=1)


class BindingSave(StrictRequest):
    definition_id: int | None = Field(default=None, gt=0)
    manager_role_id: int | None = Field(default=None, gt=0)


class BusinessRoleSave(StrictRequest):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)
    strategy: Literal["FIELD_USERS", "DEPT_MANAGER"]
    config: dict[str, Any]
    enabled: bool = True


class ScopeSave(StrictRequest):
    dept_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(max_length=200)


class CommandRequest(StrictRequest):
    command_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)


class TaskDecision(CommandRequest):
    expected_revision_id: int = Field(gt=0)
    opinion: str = Field(default="", max_length=2000)
    mode: Literal["RESTART", "TARGETED"] | None = None
    target: str | None = Field(default=None, max_length=64)
