from copy import deepcopy

from sqlalchemy import select

from app.common.enums import RET
from app.core.exceptions import CustomException

from .model import ProjectModel, ProjectRevisionModel


class ProjectWorkflowAdapter:
    def __init__(self, db) -> None:
        self.db = db

    async def load(self, business_id: int, lock: bool = False, include_deleted: bool = False) -> ProjectModel:
        query = select(ProjectModel).where(ProjectModel.id == business_id)
        if not include_deleted:
            query = query.where(ProjectModel.is_deleted.is_(False))
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        project = await self.db.scalar(query)
        if project is None:
            raise CustomException(msg="项目不存在或已删除", code=RET.NOT_FOUND.code)
        return project

    async def context(self, project: ProjectModel) -> dict:
        revision = await self.db.get(ProjectRevisionModel, project.current_revision_id) if project.current_revision_id else None
        if revision is None:
            raise CustomException(msg="项目尚无完整资料版本，请先保存草稿")
        return {"revision_id": revision.id, "revision_no": revision.revision_no, "snapshot": deepcopy(revision.payload), "creator_dept_id": project.creator_dept_id}

    async def sync_status(self, project: ProjectModel, instance) -> None:
        states = {"RUNNING": "IN_REVIEW", "RETURNED": "RETURNED", "BLOCKED": "BLOCKED", "APPROVED": "APPROVED", "WITHDRAWN": "WITHDRAWN", "TERMINATED": "DELETED"}
        project.status = states[instance.status]
        project.lock_version += 1
