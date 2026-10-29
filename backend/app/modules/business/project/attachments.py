"""仅管理项目文件关联及业务下载权限，通用层负责文件上传和存储。"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.common.enums import RET
from app.core.exceptions import CustomException
from app.modules.common.file.private_service import PrivateFileService
from app.modules.workflow.model import WorkflowInstanceModel, WorkflowTaskModel

from .model import ProjectAttachmentModel, ProjectModel, ProjectRevisionModel


class ProjectAttachmentService:
    def __init__(self, auth, db):
        self.auth, self.db = auth, db

    async def bind(self, project, ids: list[int]) -> list[dict]:
        if len(ids) > 20:
            raise CustomException(msg="每张项目最多20个附件")
        links = (await self.db.execute(select(ProjectAttachmentModel).where(ProjectAttachmentModel.project_id == project.id))).scalars().all()
        existing = {link.file_id: link for link in links}
        files = await PrivateFileService(self.auth, self.db).accept(ids, set(existing))
        for link in links:
            link.removed_time = None if link.file_id in ids else link.removed_time or datetime.now(UTC)
        for file_id in ids:
            if file_id not in existing:
                self.db.add(ProjectAttachmentModel(project_id=project.id, file_id=file_id))
        return files

    async def validate_snapshot(self, project, snapshot: dict) -> None:
        ids = snapshot.get("attachment_ids", [])
        links = (await self.db.execute(select(ProjectAttachmentModel.file_id).where(ProjectAttachmentModel.project_id == project.id, ProjectAttachmentModel.removed_time.is_(None)))).scalars().all()
        if set(ids) != set(links):
            raise CustomException(msg="项目附件关联已变化，请重新保存资料")
        await PrivateFileService(self.auth, self.db).validate_files(ids)


async def authorize_file_download(auth, db, file_id: int, project_id: int, revision_id: int | None, task_id: int | None) -> None:
    from .service import ProjectService

    actor = await ProjectService(auth, db).actor()
    link = await db.get(ProjectAttachmentModel, (project_id, file_id))
    if link is None:
        raise CustomException(msg="附件不属于该项目", code=RET.NOT_FOUND.code)
    if task_id is not None:
        task = await db.scalar(select(WorkflowTaskModel).where(WorkflowTaskModel.id == task_id, WorkflowTaskModel.assignee_id == actor.id))
        instance = await db.get(WorkflowInstanceModel, task.instance_id) if task else None
        if not instance or instance.business_key != "project" or instance.business_id != project_id:
            raise CustomException(msg="附件不属于本人的审批任务", code=RET.NOT_FOUND.code)
        project = await db.get(ProjectModel, project_id)
    else:
        if not actor.is_superuser and "module_business:project:detail" not in auth.permissions:
            raise CustomException(msg="无项目详情权限，请从本人的审批任务下载", code=RET.FORBIDDEN.code)
        project = await ProjectService(auth, db).get_visible(project_id)
    revision = await db.get(ProjectRevisionModel, revision_id or project.current_revision_id)
    if not revision or revision.project_id != project.id or file_id not in revision.payload.get("attachment_ids", []):
        raise CustomException(msg="该资料版本不包含此附件", code=RET.NOT_FOUND.code)
