"""仅供浏览器冒烟测试的临时 SQLite 服务，不能作为业务服务部署。

运行：.venv/bin/python -B tests/workflow_preview.py
前端临时代理指向 127.0.0.1:18001；访问 /api/v1/__test/session。
复用 conftest 的独立临时文件库和模拟 Redis，不读取或修改开发 MySQL。
"""

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import uvicorn
from fastapi.responses import HTMLResponse
from sqlalchemy import select


def create_preview():
    spec = importlib.util.spec_from_file_location("preview_conftest", Path(__file__).with_name("conftest.py"))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    from app.config.setting import settings
    from app.core.database import async_db_session
    from app.modules.system.dept.model import DeptModel
    from app.modules.system.dict.model import DictDataModel, DictTypeModel
    from app.modules.system.role.model import RoleModel
    from app.modules.system.user.model import UserModel, UserRolesModel
    from app.modules.workflow.model import RoleManagedDeptModel, WorkflowBindingModel

    assert settings.DATABASE_TYPE == "sqlite" and settings.DATABASE_NAME == fixture._TEST_DB_PATH
    settings.OPERATION_RECORD_METHOD = []  # 不测试独立后台日志写库，避开 SQLite 单写锁。
    patch("app.modules.system.auth.service._write_login_log", new=AsyncMock(return_value=None)).start()
    app = fixture._app

    @asynccontextmanager
    async def lifespan(app):
        async with fixture._test_lifespan(app):
            async with async_db_session() as db, db.begin():
                dept = DeptModel(name="冒烟测试财务部", code="wf_preview_finance", status=0)
                role = RoleModel(name="冒烟测试部门负责人", code="wf_preview_head", status=0)
                db.add_all([dept, role])
                await db.flush()
                user = await db.scalar(select(UserModel).where(UserModel.username == "admin"))
                user.dept_id, user.is_superuser = dept.id, True
                db.add(UserRolesModel(user_id=user.id, role_id=role.id))
                await db.flush()
                db.add(RoleManagedDeptModel(user_id=user.id, role_id=role.id, dept_id=dept.id))
                binding = await db.scalar(select(WorkflowBindingModel).where(WorkflowBindingModel.business_key == "project"))
                binding.manager_role_id = role.id
                for code, label, value in (("project_initiation_type", "演示立项", "PREVIEW"), ("project_category", "演示类别", "PREVIEW"), ("project_currency", "人民币（演示）", "CNY")):
                    dictionary = await db.scalar(select(DictTypeModel).where(DictTypeModel.dict_type == code))
                    db.add(DictDataModel(dict_type_id=dictionary.id, dict_type=code, dict_label=label, dict_value=value, dict_sort=1, status=0))
            yield

    app.router.lifespan_context = lifespan

    @app.get("/__test/session", include_in_schema=False)
    async def test_session():
        # 测试服务专用登录表单，经真实登录 API 获取 JWT；不修改生产登录组件。
        return HTMLResponse("""<!doctype html><html lang="zh"><meta charset="utf-8">
        <h1>临时库浏览器测试</h1><p>仅连接本次启动的 SQLite，测试账号 admin。</p>
        <form id="form"><label>测试账号<input name="username" value="admin"></label>
        <label>测试密码<input name="password" type="password" value="admin123"></label>
        <button>进入临时测试系统</button></form><pre id="result"></pre>
        <script>document.querySelector('#form').onsubmit=async(e)=>{
        e.preventDefault();const response=await fetch('/api/v1/system/auth/login',{
          method:'POST',body:new FormData(e.target)});const payload=await response.json();
        const data=payload.data;if(!data?.access_token){document.querySelector('#result').textContent=payload.msg;return;}
        localStorage.setItem('remember_me','false');sessionStorage.setItem('access_token',data.access_token);
        sessionStorage.setItem('refresh_token',data.refresh_token);location.href='/web#/system/approval-flows';
        };</script></html>""")

    app.router.routes.insert(0, app.router.routes.pop())  # 排在已有前端 catch-all 前。
    return app


if __name__ == "__main__":
    uvicorn.run(create_preview(), host="127.0.0.1", port=18001, log_level="warning")
