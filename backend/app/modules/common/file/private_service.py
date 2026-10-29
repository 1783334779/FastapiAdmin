"""通用私有文件服务：上传、临时归属、文件校验和清理，不依赖业务表。"""

import asyncio
import hashlib
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile
from sqlalchemy import func, select

from app.common.enums import RET
from app.config.path_conf import BASE_DIR, STATIC_DIR
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.modules.system.user.model import UserModel
from app.utils.upload_util import UploadUtil

from .model import PrivateFileModel
from .private_access import FILE_ACCESS_POLICIES


def private_root() -> Path:
    configured = settings.PRIVATE_FILE_ROOT
    root = (configured if configured.is_absolute() else BASE_DIR / configured).resolve()
    public_roots = (STATIC_DIR.resolve(), settings.UPLOAD_FILE_PATH.resolve())
    if root == BASE_DIR or any(root.is_relative_to(public_root) or public_root.is_relative_to(root) for public_root in public_roots):
        raise CustomException(msg="文件目录必须为 static 和公开上传目录以外的独立私有目录")
    return root


def attachment_path(key: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}\.[a-z0-9]{1,10}", key):
        raise CustomException(msg="附件存储标识无效")
    root = private_root()
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise CustomException(msg="附件存储路径无效")
    return path


def is_expired(value: datetime | None) -> bool:
    return value is not None and value.replace(tzinfo=value.tzinfo or UTC) <= datetime.now(UTC)


def public_attachment(item: PrivateFileModel) -> dict:
    return {"id": item.id, "original_name": item.original_name, "size_bytes": item.size_bytes, "content_type": item.content_type}


class PrivateFileService:
    def __init__(self, auth, db):
        self.auth, self.db = auth, db

    async def actor(self, lock=False):
        query = select(UserModel).where(UserModel.id == self.auth.user.id, UserModel.status == 0, UserModel.is_deleted.is_(False))
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        actor = await self.db.scalar(query)
        if actor is None:
            raise CustomException(msg="当前账号已失效", code=RET.FORBIDDEN.code)
        return actor

    async def upload(self, file: UploadFile) -> dict:
        # 同一用户的临时上传串行校验配额；业务接纳在各自的保存事务中完成。
        await self.actor(lock=True)
        count = await self.db.scalar(
            select(func.count())
            .select_from(PrivateFileModel)
            .where(
                PrivateFileModel.uploader_id == self.auth.user.id,
                PrivateFileModel.attached_time.is_(None),
                PrivateFileModel.discarded_time.is_(None),
                PrivateFileModel.expires_at > datetime.now(UTC),
            )
        )
        if count >= 50:
            raise CustomException(msg="未绑定的临时文件过多，请先保存业务表单或移除不需要的文件")
        raw_name = file.filename or ""
        if not raw_name or not UploadUtil.check_path_traversal(raw_name):
            raise CustomException(msg="请选择文件，且文件名不能包含路径")
        name = UploadUtil.sanitize_filename(raw_name)
        extension = UploadUtil.get_extension_from_filename(name)
        if extension not in settings.PRIVATE_FILE_EXTENSIONS or UploadUtil.is_dangerous_extension(extension):
            raise CustomException(msg="不支持该文件类型，允许：" + "、".join(settings.PRIVATE_FILE_EXTENSIONS))
        if len(name) > 255:
            raise CustomException(msg="附件名称不能超过255个字符")
        UploadUtil.check_file_size(file)
        root = private_root()
        await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True, mode=0o700)
        key = uuid4().hex + extension
        path = attachment_path(key)
        size, digest, head = 0, hashlib.sha256(), b""
        try:
            async with aiofiles.open(path, "xb") as output:
                await asyncio.to_thread(path.chmod, 0o600)
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.MAX_FILE_SIZE:
                        raise CustomException(msg=f"附件超过大小限制：{settings.MAX_FILE_SIZE // (1024 * 1024)}MB")
                    if len(head) < 4096:
                        head = (head + chunk)[:4096]
                    digest.update(chunk)
                    await output.write(chunk)
            if not size:
                raise CustomException(msg="不能上传空文件")
            item = PrivateFileModel(
                original_name=name,
                storage_key=key,
                size_bytes=size,
                sha256=digest.hexdigest(),
                content_type=UploadUtil.detect_file_type(head) or "application/octet-stream",
                uploader_id=self.auth.user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            self.db.add(item)
            await self.db.flush()
            return public_attachment(item)
        except BaseException:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        finally:
            await file.close()

    async def accept(self, ids: list[int], existing_ids: set[int]) -> list[dict]:
        """业务完成对象鉴权后调用，仅接纳文件，不处理任何业务关联。"""
        rows = (
            (await self.db.execute(select(PrivateFileModel).where(PrivateFileModel.id.in_(ids)).order_by(PrivateFileModel.id).with_for_update().execution_options(populate_existing=True)))
            .scalars()
            .all()
        )
        if {row.id for row in rows} != set(ids):
            raise CustomException(msg="部分附件不存在，请重新上传")
        now = datetime.now(UTC)
        for item in rows:
            if item.discarded_time is not None or (item.attached_time is None and is_expired(item.expires_at)):
                raise CustomException(msg="文件已移除或已过期")
            if item.id not in existing_ids and item.uploader_id != self.auth.user.id:
                raise CustomException(msg="不能关联他人上传的文件")
            if not await asyncio.to_thread(attachment_path(item.storage_key).is_file):
                raise CustomException(msg="附件文件已丢失，请重新上传")
        for item in rows:
            item.attached_time, item.expires_at = item.attached_time or now, None
        by_id = {row.id: row for row in rows}
        return [public_attachment(by_id[item_id]) for item_id in ids]

    async def validate_files(self, ids: list[int]) -> None:
        rows = (await self.db.execute(select(PrivateFileModel).where(PrivateFileModel.id.in_(ids)))).scalars().all()
        if {row.id for row in rows} != set(ids):
            raise CustomException(msg="文件关联无效，请保存资料后重新提交")
        for item in rows:
            if item.discarded_time is not None or not await asyncio.to_thread(attachment_path(item.storage_key).is_file):
                raise CustomException(msg="文件已移除或丢失，请重新上传并保存")

    async def discard(self, attachment_id: int) -> dict:
        await self.actor()
        item = await self.db.scalar(select(PrivateFileModel).where(PrivateFileModel.id == attachment_id).with_for_update().execution_options(populate_existing=True))
        if item is None or item.uploader_id != self.auth.user.id or item.attached_time is not None:
            raise CustomException(msg="只能移除本人尚未被业务使用的临时文件", code=RET.FORBIDDEN.code)
        item.discarded_time = item.expires_at = datetime.now(UTC)
        return {"id": item.id}

    async def download(self, attachment_id: int, business_key: str | None = None, business_id: int | None = None, revision_id: int | None = None, task_id: int | None = None):
        actor = await self.actor()
        item = await self.db.get(PrivateFileModel, attachment_id)
        if item is None:
            raise CustomException(msg="附件不存在或无权下载", code=RET.NOT_FOUND.code)
        if item.attached_time is None:
            if item.uploader_id != actor.id or item.discarded_time is not None or is_expired(item.expires_at):
                raise CustomException(msg="附件不存在或无权下载", code=RET.NOT_FOUND.code)
        else:
            policy = FILE_ACCESS_POLICIES.get(business_key or "")
            if policy is None or business_id is None:
                raise CustomException(msg="请从有权限的业务资料中下载文件", code=RET.FORBIDDEN.code)
            await policy(self.auth, self.db, item.id, business_id, revision_id, task_id)
        path = attachment_path(item.storage_key)
        if not await asyncio.to_thread(path.is_file):
            raise CustomException(msg="附件文件不存在", code=RET.NOT_FOUND.code)
        return path, item.original_name

    async def cleanup(self, *, apply: bool = False) -> dict:
        """仅维护命令调用：有历史归属的附件永不清理，默认只预览。"""
        rows = (
            (
                await self.db.execute(
                    select(PrivateFileModel)
                    .where(PrivateFileModel.attached_time.is_(None), PrivateFileModel.expires_at <= datetime.now(UTC))
                    .order_by(PrivateFileModel.id)
                    .limit(500)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if apply:
            for item in rows:
                await asyncio.to_thread(attachment_path(item.storage_key).unlink, missing_ok=True)
                await self.db.delete(item)

        # 文件写入与数据库提交无法原子化：仅补偿清理两天前、库中无记录的文件。
        # 不跟随符号链接，不扫描子目录，也不触碰非本服务随机命名的文件。
        def candidates():
            root = private_root()
            if not root.exists():
                return []
            found = []
            with os.scandir(root) as entries:
                for entry in entries:
                    if re.fullmatch(r"[a-f0-9]{32}\.[a-z0-9]{1,10}", entry.name) and entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < time.time() - 48 * 3600:
                        found.append(entry.name)
            return found

        names = await asyncio.to_thread(candidates)
        orphans = set()
        for start in range(0, len(names), 500):
            batch = names[start : start + 500]
            known = set((await self.db.execute(select(PrivateFileModel.storage_key).where(PrivateFileModel.storage_key.in_(batch)))).scalars().all())
            orphans.update(set(batch) - known)
            if len(orphans) >= 500:
                orphans = set(sorted(orphans)[:500])
                break
        if apply:
            for key in orphans:
                await asyncio.to_thread(attachment_path(key).unlink, missing_ok=True)
        return {"expired_temporary_files": len(rows), "orphan_files": len(orphans), "applied": apply}
