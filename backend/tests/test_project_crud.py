"""直接运行本文件，只用 SQLite 内存库验证正式项目模型与写入层。

命令：backend/.venv/bin/python -B backend/tests/test_project_crud.py

不启动应用、不加载连接配置或迁移。公共模型基类使用真实源码，
用户/部门使用最小引用模型；因此不是整个应用或目标数据库的集成验收。
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import Integer, event, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载测试目标：{relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_components_without_application_startup():
    """在临时包上下文加载正式源码，退出后恢复已有模块，不覆盖运行配置。"""
    packages = {}
    for name in ("app", "app.core", "app.utils", "app.modules", "app.modules.business", "app.modules.business.project"):
        package = types.ModuleType(name)
        package.__path__ = [str(BACKEND_ROOT / name.replace(".", "/"))]
        packages[name] = package
    uuid_utility = types.ModuleType("app.utils.common_util")
    uuid_utility.uuid4_str = lambda: str(uuid4())
    packages[uuid_utility.__name__] = uuid_utility

    with patch.dict(sys.modules, packages):
        base = _load_module("app.core.base_model", "app/core/base_model.py")
        schema = _load_module("app.modules.business.project.schema", "app/modules/business/project/schema.py")
        model = _load_module("app.modules.business.project.model", "app/modules/business/project/model.py")
        crud = _load_module("app.modules.business.project.crud", "app/modules/business/project/crud.py")

        class UserModel(base.MappedBase):
            __tablename__ = "sys_user"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        class DeptModel(base.MappedBase):
            __tablename__ = "sys_dept"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        base.MappedBase.registry.configure()
        return types.SimpleNamespace(base=base, schema=schema, model=model, crud=crud, user=UserModel, dept=DeptModel)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def valid_payload() -> dict:
    return {
        "name": "写入层测试项目",
        "initiation_type": "test_initiation",
        "category": "test_category",
        "it_manager_ids": [11, 12],
        "external_purchase": False,
        "business_manager_ids": [12, 21],
        "business_dept_id": 31,
        "planned_start_date": "2026-11-01",
        "planned_end_date": "2027-04-30",
        "currency": "test_currency",
    }


class TestProjectCRUD(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.components = _load_components_without_application_startup()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.components.base.MappedBase.registry.dispose()

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(self.components.base.MappedBase.metadata.create_all)
            await connection.execute(insert(self.components.user.__table__), [{"id": value} for value in (1, 11, 12, 21, 22)])
            await connection.execute(insert(self.components.dept.__table__), [{"id": 9}, {"id": 31}])

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def create_data(self, **changes):
        return self.components.schema.ProjectCreateSchema.model_validate({**valid_payload(), **changes})

    async def assert_row_counts(self, projects: int, members: int) -> None:
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(self.components.model.ProjectModel)), projects)
            self.assertEqual(await db.scalar(select(func.count()).select_from(self.components.model.ProjectMemberModel)), members)

    async def test_create_writes_project_and_four_member_rows(self) -> None:
        async with self.sessions() as db, db.begin():
            project = await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            project_id = project.id
            self.assertIsNotNone(project_id)

        async with self.sessions() as db:
            model = self.components.model
            project = await db.get(model.ProjectModel, project_id)
            self.assertEqual(project.name, "写入层测试项目")
            self.assertIs(project.external_purchase, False)
            rows = (await db.execute(select(model.ProjectMemberModel.project_id, model.ProjectMemberModel.user_id, model.ProjectMemberModel.member_type))).all()
            self.assertEqual(set(rows), {(project_id, 11, "IT_MANAGER"), (project_id, 12, "IT_MANAGER"), (project_id, 12, "BUSINESS_MANAGER"), (project_id, 21, "BUSINESS_MANAGER")})

    async def test_creator_snapshot_audit_and_draft_status(self) -> None:
        async with self.sessions() as db, db.begin():
            project = await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            self.assertEqual(project.creator_user_id, 1)
            self.assertEqual(project.creator_dept_id, 9)
            self.assertEqual(project.business_dept_id, 31)
            self.assertEqual(project.created_id, 1)
            self.assertEqual(project.updated_id, 1)
            self.assertEqual(project.status, "DRAFT")

    async def test_caller_can_roll_back_because_crud_does_not_commit(self) -> None:
        async with self.sessions() as db:
            await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            await db.rollback()
        await self.assert_row_counts(0, 0)

    async def test_member_failure_rolls_back_the_already_flushed_project(self) -> None:
        # 999 在格式上合法，但内存库没有这个用户，第二次 flush 会违反外键。
        with self.assertRaises(IntegrityError):
            async with self.sessions() as db, db.begin():
                await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(business_manager_ids=[999]), creator_user_id=1, creator_dept_id=9)
        await self.assert_row_counts(0, 0)

    async def test_missing_creator_department_rolls_back(self) -> None:
        with self.assertRaises(IntegrityError):
            async with self.sessions() as db, db.begin():
                await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=999)
        await self.assert_row_counts(0, 0)

    async def test_schema_deduplication_preserves_two_distinct_manager_types(self) -> None:
        async with self.sessions() as db, db.begin():
            await self.components.crud.ProjectCRUD(db).create_draft(
                self.create_data(it_manager_ids=[11, 11, 12], business_manager_ids=[12, 21, 12]),
                creator_user_id=1,
                creator_dept_id=9,
            )
        await self.assert_row_counts(1, 4)

    async def test_one_user_can_participate_in_two_projects(self) -> None:
        async with self.sessions() as db, db.begin():
            first = await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            second = await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            self.assertNotEqual(first.id, second.id)
        await self.assert_row_counts(2, 8)

    async def test_composite_primary_key_rejects_duplicate_members(self) -> None:
        async with self.sessions() as db, db.begin():
            project = await self.components.crud.ProjectCRUD(db).create_draft(self.create_data(), creator_user_id=1, creator_dept_id=9)
            project_id = project.id
        with self.assertRaises(IntegrityError):
            async with self.sessions() as db, db.begin():
                db.add(self.components.model.ProjectMemberModel(project_id=project_id, user_id=11, member_type="IT_MANAGER"))
                await db.flush()
        await self.assert_row_counts(1, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
