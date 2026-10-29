"""在临时内存库真实执行增量迁移，避免只验证 create_all 路径。"""

import asyncio
import importlib.util

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.path_conf import ALEMBIC_VERSION_DIR
from app.core.base_model import MappedBase
from app.utils.import_util import ImportUtil


def test_workflow_incremental_upgrade_and_downgrade_leave_existing_tables_intact():
    ImportUtil.find_models(MappedBase)
    migrations = []
    for filename in ("2026_10_25_1533_d6849f0dd210.py", "2026_10_29_1200_f3c91d72a604.py", "2026_10_29_0627_f52ed530d1b6.py", "2026_10_29_1300_a7c13f2d9560.py"):
        spec = importlib.util.spec_from_file_location("workflow_migration", ALEMBIC_VERSION_DIR / filename)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migrations.append(migration)
    new_names = {name for name in MappedBase.metadata.tables if name.startswith(("wf_", "biz_project")) or name in {"sys_user_role_managed_dept", "common_file"}}
    assert len(new_names) == 15

    def run(connection):
        existing = [table for name, table in MappedBase.metadata.tables.items() if name not in new_names]
        MappedBase.metadata.create_all(connection, tables=existing)
        connection.execute(text("create table workflow_migration_sentinel (id integer primary key, note varchar(40))"))
        connection.execute(text("insert into workflow_migration_sentinel values (1, 'keep-existing-data')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            for migration in migrations:
                migration.upgrade()
        assert new_names <= set(inspect(connection).get_table_names())
        differences = compare_metadata(
            MigrationContext.configure(connection, opts={"include_name": lambda name, kind, parents: kind != "table" or name != "workflow_migration_sentinel"}), MappedBase.metadata
        )
        assert not differences, differences
        with Operations.context(context):
            for migration in reversed(migrations):
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


def test_file_refactor_preserves_ids_metadata_and_removed_history():
    """有数据的旧附件表搬迁，不以空表通过作为迁移正确的证据。"""
    migrations = []
    for filename in ("2026_10_29_1200_f3c91d72a604.py", "2026_10_29_0627_f52ed530d1b6.py", "2026_10_29_1300_a7c13f2d9560.py"):
        spec = importlib.util.spec_from_file_location("file_migration", ALEMBIC_VERSION_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        migrations.append(module)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE sys_user (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE biz_project (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO sys_user VALUES (1)"))
            connection.execute(text("INSERT INTO biz_project VALUES (47)"))
            with Operations.context(MigrationContext.configure(connection)):
                migrations[0].upgrade()
                connection.execute(
                    text("""INSERT INTO biz_project_attachment
                    (id, project_id, original_name, storage_key, size_bytes, content_type, sha256, uploader_id, created_time, removed_time, expires_at)
                    VALUES (:id, :project, 'history.txt', :key, 16, 'text/plain', :sha, 1, '2026-10-28 08:00:00', '2026-10-29 08:00:00', :expires)"""),
                    [
                        {"id": 12, "project": None, "key": "a" * 32 + ".txt", "sha": "c" * 64, "expires": "2026-10-29 08:00:00"},
                        {"id": 13, "project": 47, "key": "b" * 32 + ".txt", "sha": "d" * 64, "expires": None},
                    ],
                )
                migrations[1].upgrade()
                migrations[2].upgrade()
                rows = connection.execute(text("SELECT id, discarded_time, attached_time, sha256 FROM common_file ORDER BY id")).all()
                assert rows[0].id == 12 and rows[0].discarded_time and rows[0].attached_time is None
                assert rows[1].id == 13 and rows[1].discarded_time is None and rows[1].attached_time and rows[1].sha256 == "d" * 64
                assert connection.execute(text("SELECT project_id, file_id, removed_time FROM biz_project_file")).one()[:2] == (47, 13)
                migrations[2].downgrade()
                assert connection.scalar(text("SELECT COUNT(*) FROM biz_project_attachment")) == 2
                assert connection.scalar(text("SELECT removed_time FROM biz_project_attachment WHERE id=13"))
                assert connection.scalar(text("SELECT COUNT(*) FROM common_file")) == 0
                migrations[1].downgrade()
                migrations[0].downgrade()
                assert set(inspect(connection).get_table_names()) == {"sys_user", "biz_project"}
    finally:
        engine.dispose()
