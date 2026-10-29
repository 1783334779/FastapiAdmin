"""通用文件与项目适配集成测试：临时 SQLite 和临时私有磁盘，不连接服务器。"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_project_workflow as workflow_tests
from fastapi import UploadFile

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.modules.business.project.model import ProjectModel, ProjectRevisionModel
from app.modules.common.file.model import PrivateFileModel
from app.modules.common.file.private_access import FILE_ACCESS_POLICIES, FILE_UPLOAD_PERMISSIONS, register_file_access
from app.modules.common.file.private_service import PrivateFileService, attachment_path, private_root


@pytest.fixture
def case(test_client, monkeypatch):
    yield from workflow_tests.case.__wrapped__(test_client, monkeypatch)


@pytest.fixture(autouse=True)
def private_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PRIVATE_FILE_ROOT", tmp_path / "files")


def upload(case, name="说明.txt", content=b"private attachment", expected=200):
    result = case.client.post("/common/file/private/upload", files={"file": (name, content, "text/plain")})
    assert result.status_code == expected, result.text
    return result.json().get("data")


def download(case, file_id, expected=200, **params):
    result = case.client.get(f"/common/file/private/{file_id}/download", params=params)
    assert result.status_code == expected, result.text
    return result


def run_db(action):
    async def run():
        async with async_db_session() as db, db.begin():
            return await action(db)

    return asyncio.run(run())


def test_upload_is_generic_private_and_temporary_owner_only(case):
    case.as_user("creator")
    item = upload(case)
    assert set(item) == {"id", "original_name", "size_bytes", "content_type"}
    assert download(case, item["id"]).content == b"private attachment"

    async def inspect(db):
        row = await db.get(PrivateFileModel, item["id"])
        assert row.attached_time is None and row.expires_at is not None
        assert not hasattr(row, "project_id")
        path = attachment_path(row.storage_key)
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.name != item["original_name"]

    run_db(inspect)
    case.as_user("outsider")
    download(case, item["id"], 404)
    case.call("POST", f"/common/file/private/{item['id']}/discard", expected=403)


@pytest.mark.parametrize("name,content", [("virus.exe", b"bad"), ("empty.txt", b""), ("../secret.txt", b"bad")])
def test_reject_invalid_upload_without_leaving_files(case, name, content):
    upload(case.as_user("creator"), name, content, 400)
    assert not list(settings.PRIVATE_FILE_ROOT.glob("*"))


def test_upload_follows_business_create_or_edit_permission_and_size_limit(case, monkeypatch):
    case.as_user("creator")
    case.permissions = ["module_business:project:create"]
    item = upload(case)
    case.permissions = ["module_business:project:update"]
    upload(case)
    case.permissions = ["module_business:project:detail"]
    result = case.client.post("/common/file/private/upload", files={"file": ("test.txt", b"hello")})
    assert result.status_code == 403
    # 查询限制和清理本人临时文件不要求额外授权，也不因写权限撤销而无法清理。
    case.call("GET", "/common/file/private/options")
    case.call("POST", f"/common/file/private/{item['id']}/discard")
    case.permissions = ["module_business:project:create"]
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 4)
    before = list(settings.PRIVATE_FILE_ROOT.glob("*"))
    upload(case, content=b"too large", expected=400)
    assert list(settings.PRIVATE_FILE_ROOT.glob("*")) == before


def test_stream_without_reported_size_still_enforces_limit(case, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 4)
    auth = SimpleNamespace(user=SimpleNamespace(id=case.data["people"]["creator"]["id"]))

    async def attempt(db):
        file = UploadFile(filename="large.txt", file=BytesIO(b"actual size is large"), size=None)
        with pytest.raises(CustomException, match="超过大小限制"):
            await PrivateFileService(auth, db).upload(file)
        assert file.file.closed

    run_db(attempt)
    assert not list(settings.PRIVATE_FILE_ROOT.glob("*"))


def test_private_paths_reject_public_root_and_symlink_escape(tmp_path, monkeypatch):
    public = tmp_path / "public"
    monkeypatch.setattr(settings, "UPLOAD_FILE_PATH", public)
    monkeypatch.setattr(settings, "PRIVATE_FILE_ROOT", public / "private")
    with pytest.raises(CustomException):
        private_root()
    monkeypatch.setattr(settings, "PRIVATE_FILE_ROOT", tmp_path / "files")
    settings.PRIVATE_FILE_ROOT.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"must never be served")
    (settings.PRIVATE_FILE_ROOT / ("c" * 32 + ".txt")).symlink_to(outside)
    with pytest.raises(CustomException):
        attachment_path("c" * 32 + ".txt")
    with pytest.raises(CustomException):
        attachment_path("../secret.txt")


def test_bind_files_to_project_and_keep_historical_revision_readable(case):
    item = upload(case.as_user("creator"))
    project = case.create(attachment_ids=[item["id"]])
    first = case.detail(project["id"])
    assert first["attachments"] == [item]
    params = {"business_key": "project", "business_id": project["id"]}
    download(case, item["id"], **params)
    download(case, item["id"], 403)  # 已绑定文件必须走业务权限
    case.call("POST", f"/common/file/private/{item['id']}/discard", expected=403)
    case.update(project["id"], attachment_ids=[])
    download(case, item["id"], 404, **params)
    download(case, item["id"], **params, revision_id=first["revision_id"])
    case.as_user("outsider")
    download(case, item["id"], 404, **params, revision_id=first["revision_id"])


def test_foreign_files_cannot_be_attached_and_ids_can_be_reused_by_owner(case):
    item = upload(case.as_user("outsider"))
    case.as_user("creator").call("POST", "/business/project/create", case.body(attachment_ids=[item["id"]]), expected=400)
    first = case.create(user="outsider", attachment_ids=[item["id"]])
    second = case.create(user="outsider", attachment_ids=[item["id"]])
    assert first["id"] != second["id"]
    assert case.detail(second["id"], "outsider")["attachments"] == [item]


def test_direct_submit_is_atomic_and_idempotent_with_uploaded_files(case):
    item = upload(case.as_user("creator"))
    body = {**case.body(attachment_ids=[item["id"]]), "command_key": uuid4().hex}
    case.call("POST", "/business/project/create-and-submit", body, expected=400)

    async def check_rollback(db):
        file = await db.get(PrivateFileModel, item["id"])
        assert file.attached_time is None and file.expires_at is not None

    run_db(check_rollback)
    case.configure()
    case.as_user("creator")
    created = case.call("POST", "/business/project/create-and-submit", body)
    assert created["status"] == "IN_REVIEW" and created["attachments"] == [item]
    retried = case.call("POST", "/business/project/create-and-submit", body)
    assert retried == created


def test_only_own_approval_task_grants_attachment_access(case):
    case.configure()
    item = upload(case.as_user("creator"))
    project = case.create(attachment_ids=[item["id"]])
    case.submit(project)
    task = case.task("it1")["task"]
    params = {"business_key": "project", "business_id": project["id"], "task_id": task["id"]}
    case.permissions = []
    download(case, item["id"], **params)
    download(case, item["id"], 403, business_key="project", business_id=project["id"])
    case.as_user("it2")
    download(case, item["id"], 404, **params)


def test_expired_files_and_missing_disk_block_binding_or_submission(case):
    item = upload(case.as_user("creator"))

    async def expire(db):
        row = await db.get(PrivateFileModel, item["id"])
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    run_db(expire)
    case.call("POST", "/business/project/create", case.body(attachment_ids=[item["id"]]), expected=400)
    download(case, item["id"], 404)

    case.configure()
    second = upload(case.as_user("creator"))
    project = case.create(attachment_ids=[second["id"]])

    async def lose_file(db):
        row = await db.get(PrivateFileModel, second["id"])
        attachment_path(row.storage_key).unlink()

    run_db(lose_file)
    case.as_user("creator").call("POST", f"/business/project/{project['id']}/submit", {"command_key": "missing-file-test", "expected_version": project["lock_version"]}, expected=400)


def test_other_business_can_register_access_policy_without_project_dependency(case):
    item = upload(case.as_user("creator"))

    async def accept(db):
        await PrivateFileService(type("Auth", (), {"user": type("User", (), {"id": case.data["people"]["creator"]["id"]})()})(), db).accept([item["id"]], set())

    run_db(accept)
    calls = []

    async def policy(auth, db, file_id, business_id, revision_id, task_id):
        calls.append((auth.user.id, file_id, business_id))

    register_file_access("attachment_test_business", policy, upload_permissions=("example:create",))
    try:
        case.permissions = ["example:create"]
        upload(case)  # 其他模块只需声明自己的既有业务权限，无项目权限也能上传。
        download(case, item["id"], business_key="attachment_test_business", business_id=42)
        assert calls == [(case.data["people"]["creator"]["id"], item["id"], 42)]
        download(case, item["id"], 403, business_key="unknown", business_id=42)
    finally:
        FILE_ACCESS_POLICIES.pop("attachment_test_business", None)
        FILE_UPLOAD_PERMISSIONS.pop("attachment_test_business", None)


def test_cleanup_preview_and_apply_preserve_all_bound_historical_files(case):
    expired = upload(case.as_user("creator"))
    bound = upload(case)
    project = case.create(attachment_ids=[bound["id"]])
    first = case.detail(project["id"])
    case.update(project["id"], attachment_ids=[])
    case.call("POST", f"/common/file/private/{expired['id']}/discard")
    orphan = settings.PRIVATE_FILE_ROOT / ("a" * 32 + ".txt")
    orphan.write_bytes(b"orphan")  # 测试夹具数据，不修改源码
    old = (datetime.now(UTC) - timedelta(days=3)).timestamp()
    os.utime(orphan, (old, old))

    async def clean(db):
        service = PrivateFileService(None, db)
        preview = await service.cleanup()
        assert preview["expired_temporary_files"] >= 1  # 会话隔离库保留前面用例的过期元数据
        assert preview["orphan_files"] == 1 and not preview["applied"]
        assert orphan.exists() and await db.get(PrivateFileModel, expired["id"]) is not None
        return await service.cleanup(apply=True)

    result = run_db(clean)
    assert result["applied"] and not orphan.exists()
    download(case, expired["id"], 404)
    download(case, bound["id"], business_key="project", business_id=project["id"], revision_id=first["revision_id"])


def test_legacy_snapshot_without_attachment_fields_still_submits(case):
    case.configure()
    project = case.create()

    async def legacy(db):
        row = await db.get(ProjectModel, project["id"])
        revision = await db.get(ProjectRevisionModel, row.current_revision_id)
        revision.payload = {key: value for key, value in revision.payload.items() if key not in {"attachment_ids", "attachments"}}

    run_db(legacy)
    assert case.submit(project)["status"] == "RUNNING"
