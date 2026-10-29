"""项目写入层：只组织数据库写入，不接管登录、业务校验或事务提交。"""

from sqlalchemy.ext.asyncio import AsyncSession

from .model import ProjectMemberModel, ProjectModel
from .schema import ProjectCreateSchema


class ProjectCRUD:
    """项目专用数据层，不套用通用 CRUD 对单一主键和数据范围的假设。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_draft(
        self,
        data: ProjectCreateSchema,
        *,
        creator_user_id: int,
        creator_dept_id: int,
    ) -> ProjectModel:
        """写入主表和两类经理，调用方负责整个事务的提交或回滚。

        data 必须经过 Schema 校验；创建身份由 Service 从认证用户取得。
        人员/部门启用状态、字典有效性及创建权限不由这一层判断。
        """
        # 经理与附件ID数组都不是主表列，先从主表数据中排除。
        project_data = data.model_dump(exclude={"it_manager_ids", "business_manager_ids", "attachment_ids"})
        project = ProjectModel(
            **project_data,
            creator_user_id=creator_user_id,
            creator_dept_id=creator_dept_id,
            created_id=creator_user_id,
            updated_id=creator_user_id,
            status="DRAFT",
        )
        self.db.add(project)
        await self.db.flush()  # 执行主表 INSERT，取得数据库生成的 project.id；还没有提交事务。

        members = []
        for member_type, user_ids in (
            ("IT_MANAGER", data.it_manager_ids),
            ("BUSINESS_MANAGER", data.business_manager_ids),
        ):
            for user_id in user_ids:
                members.append(ProjectMemberModel(project_id=project.id, user_id=user_id, member_type=member_type))

        self.db.add_all(members)
        await self.db.flush()  # 让关联写入错误在同一事务中暴露；失败交给外层回滚。
        return project
