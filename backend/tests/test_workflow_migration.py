"""在临时内存库真实执行增量迁移，避免只验证 create_all 路径。"""

import asyncio
import importlib.util

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.path_conf import ALEMBIC_VERSION_DIR
from app.core.base_model import MappedBase
from app.utils.import_util import ImportUtil


def test_workflow_incremental_upgrade_and_downgrade_leave_existing_tables_intact():
    ImportUtil.find_models(MappedBase)
    spec = importlib.util.spec_from_file_location("workflow_migration", ALEMBIC_VERSION_DIR / "2026_10_25_1533_d6849f0dd210.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    new_names = {name for name in MappedBase.metadata.tables if name.startswith(("wf_", "biz_project")) or name == "sys_user_role_managed_dept"}
    assert len(new_names) == 13

    def run(connection):
        existing = [table for name, table in MappedBase.metadata.tables.items() if name not in new_names]
        MappedBase.metadata.create_all(connection, tables=existing)
        connection.execute(text("create table workflow_migration_sentinel (id integer primary key, note varchar(40))"))
        connection.execute(text("insert into workflow_migration_sentinel values (1, 'keep-existing-data')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        assert new_names <= set(inspect(connection).get_table_names())
        differences = compare_metadata(
            MigrationContext.configure(connection, opts={"include_name": lambda name, kind, parents: kind != "table" or name != "workflow_migration_sentinel"}), MappedBase.metadata
        )
        assert not differences, differences
        with Operations.context(context):
            migration.downgrade()
        assert new_names.isdisjoint(inspect(connection).get_table_names())
        assert connection.scalar(text("select note from workflow_migration_sentinel where id=1")) == "keep-existing-data"
        assert {table.name for table in existing} <= set(inspect(connection).get_table_names())

    async def check():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(run)
        finally:
            await engine.dispose()

    asyncio.run(check())
