"""仅清理过期未绑定附件。默认预览，显式 --apply 才删除；不运行应用初始化。"""

import argparse
import asyncio
import os


async def run(apply: bool) -> None:
    from app.core.base_model import MappedBase
    from app.core.database import async_db_session, async_engine
    from app.modules.common.file.private_service import PrivateFileService
    from app.utils.import_util import ImportUtil

    # 独立CLI没有应用路由导入过程，先解析完整ORM注册表；不初始化数据或执行迁移。
    ImportUtil.find_models(MappedBase)
    try:
        async with async_db_session() as db, db.begin():
            print(await PrivateFileService(None, db).cleanup(apply=apply))
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.environ["ENVIRONMENT"] = args.env
    asyncio.run(run(args.apply))
