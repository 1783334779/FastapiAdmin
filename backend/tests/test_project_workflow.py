"""业务接口集成测试：现有 conftest 的临时 SQLite/模拟 Redis，不连接业务库。

认证上下文按测试用户替换，仍执行接口权限、对象权限、真实模型与完整请求事务。
这不替代目标 MySQL 的并发/迁移验证或真实登录测试。
"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.base_schema import AuthSchema, CoreUserSchema
from app.core.database import async_db_session
from app.core.dependencies import get_current_user
from app.modules.system.dept.model import DeptModel
from app.modules.system.dict.model import DictDataModel, DictTypeModel
from app.modules.system.role.model import RoleModel
from app.modules.system.user.model import UserModel, UserRolesModel
from app.modules.workflow.graph import default_graph
from app.modules.workflow.model import RoleManagedDeptModel

PERMISSIONS = [f"module_business:project:{action}" for action in ("query", "detail", "create", "update", "submit", "withdraw", "delete")] + [
    f"module_system:workflow:{action}" for action in ("query", "configure", "publish", "recover")
]


@pytest.fixture
def case(test_client, monkeypatch):
    # SQLite 仅允许一个写事务；响应后台日志早于 request-scope 事务提交，
    # 因而会等待业务事务持有的写锁。日志模块不在本组业务测试范围内。
    monkeypatch.setattr("app.core.router_class._write_operation_log_async", AsyncMock())

    async def seed():
        prefix = uuid4().hex[:12]
        async with async_db_session() as db, db.begin():
            corp = DeptModel(name=f"集团-{prefix}", code=f"corp_{prefix}", status=0)
            db.add(corp)
            await db.flush()
            finance = DeptModel(name=f"财务-{prefix}", code=f"finance_{prefix}", parent_id=corp.id, status=0)
            tech = DeptModel(name=f"技术-{prefix}", code=f"tech_{prefix}", parent_id=corp.id, status=0)
            db.add_all([finance, tech])
            await db.flush()
            child = DeptModel(name=f"核算-{prefix}", code=f"child_{prefix}", parent_id=finance.id, status=0)
            db.add(child)
            await db.flush()
            people = {}
            for key in ("creator", "child_creator", "it1", "it2", "business", "head", "parent_head", "outsider", "admin"):
                person = UserModel(
                    username=f"wf_{key}_{prefix}",
                    name=f"{key}-{prefix}",
                    password="unused-in-auth-override-test",
                    dept_id=child.id if key == "child_creator" else finance.id if key == "creator" else tech.id,
                    status=0,
                    is_superuser=key == "admin",
                )
                db.add(person)
                await db.flush()
                people[key] = {"id": person.id, "name": person.name, "dept_id": person.dept_id, "is_superuser": person.is_superuser}
            role = RoleModel(name=f"负责人-{prefix}", code=f"head_{prefix}", status=0)
            db.add(role)
            await db.flush()
            db.add_all([UserRolesModel(user_id=people[key]["id"], role_id=role.id) for key in ("head", "parent_head")])
            await db.flush()
            db.add_all(
                [RoleManagedDeptModel(role_id=role.id, user_id=people["head"]["id"], dept_id=finance.id), RoleManagedDeptModel(role_id=role.id, user_id=people["parent_head"]["id"], dept_id=corp.id)]
            )
            values = {}
            for field, code in (("initiation_type", "project_initiation_type"), ("category", "project_category"), ("currency", "project_currency")):
                dictionary = await db.scalar(select(DictTypeModel).where(DictTypeModel.dict_type == code))
                value = f"test_{field}_{prefix}"
                db.add(DictDataModel(dict_type_id=dictionary.id, dict_type=code, dict_label=f"测试-{field}", dict_value=value, dict_sort=1, status=0))
                values[field] = value
            return {"people": people, "role_id": role.id, "finance": finance.id, "tech": tech.id, "child": child.id, "values": values, "prefix": prefix}

    seeded = asyncio.run(seed())
    harness = Harness(test_client, seeded)
    previous = test_client.app.dependency_overrides.get(get_current_user)
    test_client.app.dependency_overrides[get_current_user] = lambda: AuthSchema(user=CoreUserSchema(**seeded["people"][harness.current]), permissions=harness.permissions)
    yield harness
    if previous is None:
        test_client.app.dependency_overrides.pop(get_current_user, None)
    else:
        test_client.app.dependency_overrides[get_current_user] = previous


class Harness:
    def __init__(self, client, data):
        self.client, self.data, self.current = client, data, "admin"
        self.permissions = PERMISSIONS

    def as_user(self, key):
        self.current = key
        return self

    def call(self, method, path, data=None, expected=200):
        response = self.client.request(method, path, json=data) if data is not None else self.client.request(method, path)
        assert response.status_code == expected, response.text
        return response.json().get("data") if expected == 200 else response.json()

    def body(self, **changes):
        return {
            "name": f"项目-{self.data['prefix']}",
            **self.data["values"],
            "it_manager_ids": [self.data["people"]["it1"]["id"], self.data["people"]["it2"]["id"]],
            "business_manager_ids": [self.data["people"]["business"]["id"]],
            "external_purchase": False,
            "business_dept_id": self.data["tech"],
            "planned_start_date": "2026-11-01",
            "planned_end_date": "2027-04-30",
            **changes,
        }

    def configure(self, graph=None):
        self.as_user("admin").call("PUT", "/system/workflow/binding", {"definition_id": None, "manager_role_id": self.data["role_id"]})
        definition = self.call("POST", "/system/workflow/create", {"name": "接口验收流程", "code": f"test_{uuid4().hex}", "enabled": True, "graph": graph or default_graph()})
        definition = self.call("POST", f"/system/workflow/publish/{definition['id']}", {"command_key": uuid4().hex, "expected_version": definition["lock_version"]})
        self.call("PUT", "/system/workflow/binding", {"definition_id": definition["id"], "manager_role_id": self.data["role_id"]})
        self.definition = definition
        return definition

    def create(self, user="creator", **changes):
        return self.as_user(user).call("POST", "/business/project/create", self.body(**changes))

    def detail(self, project_id, user="creator"):
        return self.as_user(user).call("GET", f"/business/project/detail/{project_id}")

    def submit(self, project, user="creator"):
        return self.as_user(user).call("POST", f"/business/project/{project['id']}/submit", {"command_key": uuid4().hex, "expected_version": project["lock_version"]})

    def task(self, user, node=None):
        rows = self.as_user(user).call("GET", "/workflow/task/todo?page_size=100")["items"]
        matching = [item for item in rows if item["status"] == "PENDING" and (node is None or item["node_name"] == node)]
        assert matching, rows
        return self.call("GET", f"/workflow/task/{matching[0]['id']}/detail")

    def decide(self, user, action="approve", node=None, mode=None, target=None):
        task = self.task(user, node)
        body = {"command_key": uuid4().hex, "expected_version": task["workflow"]["lock_version"], "expected_revision_id": task["project"]["revision_id"], "opinion": "测试意见"}
        if mode:
            body["mode"] = mode
        if target:
            body["target"] = target
        return self.call("POST", f"/workflow/task/{task['task']['id']}/{action}", body)

    def update(self, project_id, **changes):
        project = self.detail(project_id)
        return self.call("PUT", f"/business/project/update/{project_id}", {**self.body(), **changes, "expected_version": project["lock_version"]})


def parallel_graph():
    graph = default_graph()
    graph["nodes"] = [node for node in graph["nodes"] if node["id"] in {"start", "it", "business", "manager", "end"}]
    graph["nodes"] += [
        {"id": "fork", "type": "PARALLEL", "position": {"x": 0, "y": 0}, "data": {"label": "并行", "join_key": "join"}},
        {"id": "join", "type": "JOIN", "position": {"x": 0, "y": 0}, "data": {"label": "汇合"}},
    ]
    pairs = [("start", "fork"), ("fork", "it"), ("fork", "business"), ("it", "join"), ("business", "join"), ("join", "manager"), ("manager", "end")]
    graph["edges"] = [{"id": f"edge_{index}", "source": source, "target": target} for index, (source, target) in enumerate(pairs)]
    return graph


def test_serial_any_and_nearest_department_manager(case):
    case.configure()
    project = case.create()
    check = case.call("POST", f"/business/project/{project['id']}/precheck")
    assert check["valid"]
    case.submit(project)
    case.decide("it1")
    closed = case.as_user("it2").call("GET", "/workflow/task/done")["items"]
    assert closed[0]["status"] == "CLOSED"
    case.decide("business")
    task = case.task("head")
    assert task["task"]["node_name"] == "部门负责人审核"
    assert task["workflow"]["visits"][-1]["candidates"] == [{"id": case.data["people"]["head"]["id"], "name": case.data["people"]["head"]["name"]}]
    assert case.decide("head")["status"] == "APPROVED"
    assert case.detail(project["id"])["status"] == "APPROVED"


def test_project_visibility_and_task_only_access(case):
    case.configure()
    project = case.create()
    case.submit(project)
    assert case.as_user("it1").call("GET", "/business/project/list")["total"] == 0
    case.call("GET", f"/business/project/detail/{project['id']}", expected=404)
    assert case.task("it1")["project"]["id"] == project["id"]
    task = case.task("it1")
    case.as_user("outsider").call("GET", f"/workflow/task/{task['task']['id']}/detail", expected=404)
    assert case.as_user("head").call("GET", "/business/project/list")["total"] == 1
    case.call("PUT", f"/business/project/update/{project['id']}", {**case.body(), "expected_version": project["lock_version"]}, expected=403)


def test_child_department_visibility_and_creator_department_snapshot(case):
    case.configure()
    project = case.create(user="child_creator")
    assert case.as_user("head").call("GET", "/business/project/list")["total"] == 1

    async def transfer():
        async with async_db_session() as db, db.begin():
            user = await db.get(UserModel, case.data["people"]["child_creator"]["id"])
            user.dept_id = case.data["tech"]

    asyncio.run(transfer())
    result = case.detail(project["id"], "child_creator")
    assert result["creator_dept_id"] == case.data["child"]
    assert case.as_user("head").call("GET", "/business/project/list")["total"] == 1


def test_full_graph_precheck_rejects_missing_people(case):
    case.configure()
    project = case.create()

    async def remove_scope():
        from sqlalchemy import delete

        async with async_db_session() as db, db.begin():
            await db.execute(delete(RoleManagedDeptModel).where(RoleManagedDeptModel.role_id == case.data["role_id"]))

    asyncio.run(remove_scope())
    result = case.call("POST", f"/business/project/{project['id']}/precheck")
    assert not result["valid"] and result["issues"][0]["node_key"] == "manager"
    case.call("POST", f"/business/project/{project['id']}/submit", {"command_key": uuid4().hex, "expected_version": project["lock_version"]}, expected=400)
    assert case.detail(project["id"])["workflow"] is None


def test_all_mode_and_restart_preserve_old_history(case):
    graph = default_graph()
    next(node for node in graph["nodes"] if node["id"] == "it")["data"]["approval_mode"] = "ALL"
    case.configure(graph)
    project = case.create()
    case.submit(project)
    case.decide("it1")
    assert not case.as_user("business").call("GET", "/workflow/task/todo")["items"]
    result = case.decide("it2", "reject", mode="RESTART")
    assert result["status"] == "RETURNED"
    project = case.update(project["id"], name="重走后的项目")
    assert case.submit(project)["round_no"] == 2
    history = case.task("it1")["workflow"]
    assert history["visits"][0]["round_no"] == 1
    assert [item["round_no"] for item in history["rounds"]] == [1, 2]
    assert history["rounds"][0]["closed_by"] == "NEW_ROUND"


def test_parallel_join_and_targeted_return_preserve_completed_branch(case):
    case.configure(parallel_graph())
    project = case.create()
    case.submit(project)
    case.decide("it1")
    assert not case.as_user("head").call("GET", "/workflow/task/todo")["items"]
    case.decide("business", "reject", mode="TARGETED", target="DRAFT")
    project = case.update(project["id"], external_purchase=True)
    case.submit(project)
    case.decide("business")
    task = case.task("head")
    it_visits = [visit for visit in task["workflow"]["visits"] if visit["node_key"] == "it"]
    assert len(it_visits) == 1 and it_visits[0]["status"] == "APPROVED"
    assert it_visits[0]["revision_id"] != task["project"]["revision_id"]
    assert case.decide("head")["status"] == "APPROVED"


def test_parallel_cross_branch_return_is_forbidden_and_other_tasks_pause(case):
    case.configure(parallel_graph())
    project = case.create()
    case.submit(project)
    task = case.task("it1")
    business = case.task("business")
    assert "it" not in {item["id"] for item in business["reject_targets"]}
    body = {
        "command_key": uuid4().hex,
        "expected_version": business["workflow"]["lock_version"],
        "expected_revision_id": business["project"]["revision_id"],
        "opinion": "不允许跨分支",
        "mode": "TARGETED",
        "target": "it",
    }
    case.call("POST", f"/workflow/task/{business['task']['id']}/reject", body, expected=400)
    case.decide("business", "reject", mode="TARGETED", target="DRAFT")
    paused = case.as_user("it1").call("GET", f"/workflow/task/{task['task']['id']}/detail")
    assert paused["task"]["status"] == "SUSPENDED" and not paused["allowed_actions"]["approve"]


def test_nested_targeted_returns_go_draft_then_b_then_d(case):
    case.configure()
    project = case.create()
    case.submit(project)
    case.decide("it1")
    case.decide("business")
    case.decide("head", "reject", mode="TARGETED", target="business")
    case.decide("business", "reject", mode="TARGETED", target="DRAFT")
    project = case.update(project["id"], external_purchase=True)
    case.submit(project)
    assert case.task("business")["task"]["node_name"] == "业务项目经理审核"
    case.decide("business")
    assert case.task("head")["task"]["node_name"] == "部门负责人审核"
    assert case.decide("head")["status"] == "APPROVED"


def test_existing_project_pins_version_and_dynamic_people_freeze_per_visit(case):
    definition = case.configure()
    project = case.create()
    first = case.submit(project)
    case.as_user("admin").call("POST", f"/system/workflow/publish/{definition['id']}", {"command_key": uuid4().hex, "expected_version": definition["lock_version"]})
    case.decide("it1")
    case.decide("business")
    task = case.task("head")
    assert task["workflow"]["version_id"] == first["version_id"]

    async def remove_member():
        from sqlalchemy import delete

        async with async_db_session() as db, db.begin():
            await db.execute(delete(UserRolesModel).where(UserRolesModel.user_id == case.data["people"]["head"]["id"], UserRolesModel.role_id == case.data["role_id"]))

    asyncio.run(remove_member())
    assert case.decide("head")["status"] == "APPROVED"


def test_approve_idempotency_rejects_changed_payload(case):
    case.configure()
    project = case.create()
    case.submit(project)
    task = case.task("it1")
    body = {"command_key": uuid4().hex, "expected_version": task["workflow"]["lock_version"], "expected_revision_id": task["project"]["revision_id"], "opinion": "同意"}
    path = f"/workflow/task/{task['task']['id']}/approve"
    first = case.call("POST", path, body)
    assert case.call("POST", path, body) == first
    case.call("POST", path, {**body, "opinion": "不同请求"}, expected=409)
    assert len(case.as_user("business").call("GET", "/workflow/task/todo")["items"]) == 1


def test_withdraw_before_approval_and_refuse_after_action(case):
    case.configure()
    project = case.create()
    case.submit(project)
    current = case.detail(project["id"])
    result = case.call("POST", f"/business/project/{project['id']}/withdraw", {"command_key": uuid4().hex, "expected_version": current["lock_version"]})
    assert result["status"] == "WITHDRAWN"
    case.submit(case.detail(project["id"]))
    case.decide("it1")
    current = case.detail(project["id"])
    case.call("POST", f"/business/project/{project['id']}/withdraw", {"command_key": uuid4().hex, "expected_version": current["lock_version"]}, expected=400)


def test_returned_draft_delete_terminates_tasks_and_preserves_history(case):
    case.configure(parallel_graph())
    project = case.create()
    case.submit(project)
    task = case.task("it1")
    case.decide("business", "reject", mode="TARGETED", target="DRAFT")
    current = case.detail(project["id"])
    case.call("POST", f"/business/project/{project['id']}/delete", {"command_key": uuid4().hex, "expected_version": current["lock_version"]})
    result = case.as_user("it1").call("GET", f"/workflow/task/{task['task']['id']}/detail")
    assert result["workflow"]["status"] == "TERMINATED"
    assert result["task"]["status"] == "CANCELLED" and not result["allowed_actions"]["approve"]


def conditional_graph():
    graph = default_graph()
    graph["nodes"] += [
        {"id": "choice", "type": "EXCLUSIVE", "data": {"label": "采购判断"}},
        {"id": "merge", "type": "MERGE", "data": {"label": "条件合并"}},
    ]
    graph["edges"] = [
        {"id": "s", "source": "start", "target": "choice"},
        {"id": "first", "source": "choice", "target": "it", "priority": 0, "condition": {"field": "external_purchase", "op": "eq", "value": True}},
        {"id": "second", "source": "choice", "target": "business", "priority": 1, "condition": {"field": "external_purchase", "op": "eq", "value": True}},
        {"id": "fallback", "source": "choice", "target": "manager", "is_default": True},
        *[{"id": f"merge_{key}", "source": key, "target": "merge"} for key in ("it", "business", "manager")],
        {"id": "e", "source": "merge", "target": "end"},
    ]
    return graph


@pytest.mark.parametrize(("purchase", "user", "edge"), [(True, "it1", "first"), (False, "head", "fallback")])
def test_exclusive_first_match_and_default(case, purchase, user, edge):
    case.configure(conditional_graph())
    project = case.create(external_purchase=purchase)
    case.submit(project)
    task = case.task(user)
    assert task["workflow"]["routes"][0]["edge_id"] == edge
    assert len(task["workflow"]["visits"]) == 1
    assert case.decide(user)["status"] == "APPROVED"


def test_precheck_checks_even_the_unselected_conditional_branch(case):
    case.configure(conditional_graph())
    project = case.create(external_purchase=True)

    async def remove_scopes():
        from sqlalchemy import delete

        async with async_db_session() as db, db.begin():
            await db.execute(delete(RoleManagedDeptModel).where(RoleManagedDeptModel.role_id == case.data["role_id"]))

    asyncio.run(remove_scopes())
    result = case.call("POST", f"/business/project/{project['id']}/precheck")
    assert not result["valid"] and result["issues"][0]["node_key"] == "manager"


def test_missing_people_at_activation_block_then_recover(case):
    case.configure()
    project = case.create()
    case.submit(project)
    case.decide("it1")
    for key in ("head", "parent_head"):
        case.as_user("admin").call("PUT", f"/system/workflow/role-members/{case.data['role_id']}/{case.data['people'][key]['id']}", {"dept_ids": []})
    blocked = case.decide("business")
    assert blocked["status"] == "BLOCKED" and blocked["blocked"]["kind"] == "ACTIVATION"
    case.as_user("admin").call("POST", f"/workflow/task/instances/{blocked['id']}/recover", {"command_key": uuid4().hex, "expected_version": blocked["lock_version"]}, expected=400)
    case.call("PUT", f"/system/workflow/role-members/{case.data['role_id']}/{case.data['people']['head']['id']}", {"dept_ids": [case.data["finance"]]})
    recovered = case.call("POST", f"/workflow/task/instances/{blocked['id']}/recover", {"command_key": uuid4().hex, "expected_version": blocked["lock_version"]})
    assert recovered["status"] == "RUNNING"
    assert case.decide("head")["status"] == "APPROVED"


def test_inactive_frozen_all_member_cannot_be_silently_removed(case):
    graph = default_graph()
    next(node for node in graph["nodes"] if node["id"] == "it")["data"]["approval_mode"] = "ALL"
    case.configure(graph)
    project = case.create()
    case.submit(project)

    async def set_status(status):
        async with async_db_session() as db, db.begin():
            user = await db.get(UserModel, case.data["people"]["it2"]["id"])
            user.status = status

    asyncio.run(set_status(1))
    blocked = case.decide("it1")
    assert blocked["status"] == "BLOCKED" and blocked["blocked"]["kind"] == "FIXED_MEMBERS"
    case.as_user("it2").call("GET", "/workflow/task/todo", expected=403)
    case.as_user("admin").call("POST", f"/workflow/task/instances/{blocked['id']}/recover", {"command_key": uuid4().hex, "expected_version": blocked["lock_version"]}, expected=400)
    asyncio.run(set_status(0))
    case.call("POST", f"/workflow/task/instances/{blocked['id']}/recover", {"command_key": uuid4().hex, "expected_version": blocked["lock_version"]})
    assert case.decide("it2")["status"] == "RUNNING"
    assert case.task("business")["task"]["node_name"] == "业务项目经理审核"


def test_next_node_reresolves_and_uses_nearest_available_parent(case):
    case.configure()
    project = case.create()
    case.submit(project)
    case.decide("it1")
    case.as_user("admin").call("PUT", f"/system/workflow/role-members/{case.data['role_id']}/{case.data['people']['head']['id']}", {"dept_ids": []})
    case.decide("business")
    task = case.task("parent_head")
    assert task["workflow"]["visits"][-1]["resolution"][0]["departments_checked"][0] == case.data["finance"]
    assert case.decide("parent_head")["status"] == "APPROVED"


def test_union_deduplicates_and_creator_must_manually_approve(case):
    graph = default_graph()
    it = next(node for node in graph["nodes"] if node["id"] == "it")
    it["data"]["approval_mode"] = "ALL"
    it["data"]["assignees"].append({"type": "SYSTEM_ROLE", "role_id": case.data["role_id"]})
    case.configure(graph)
    project = case.create(it_manager_ids=[case.data["people"]["creator"]["id"], case.data["people"]["head"]["id"]])
    case.submit(project)
    task = case.task("creator")
    candidates = task["workflow"]["visits"][0]["candidates"]
    assert len(candidates) == 3 and len({item["id"] for item in candidates}) == 3
    assert not task["workflow"]["has_approval_action"]
    case.decide("creator")
    case.decide("head")
    assert case.decide("parent_head")["status"] == "RUNNING"
    assert case.task("business")


def test_targeted_return_to_draft_keeps_original_route_after_field_change(case):
    case.configure(conditional_graph())
    project = case.create(external_purchase=True)
    case.submit(project)
    case.decide("it1", "reject", mode="TARGETED", target="DRAFT")
    project = case.update(project["id"], external_purchase=False)
    case.submit(project)
    task = case.task("it1")
    assert len(task["workflow"]["routes"]) == 1
    assert not case.as_user("head").call("GET", "/workflow/task/todo")["items"]
    assert case.decide("it1")["status"] == "APPROVED"


def test_stale_revision_and_workflow_version_are_rejected(case):
    case.configure()
    project = case.create()
    case.submit(project)
    task = case.task("it1")
    body = {"command_key": uuid4().hex, "expected_version": task["workflow"]["lock_version"], "expected_revision_id": task["project"]["revision_id"] + 10000, "opinion": "旧资料"}
    path = f"/workflow/task/{task['task']['id']}/approve"
    case.call("POST", path, body, expected=409)
    case.call("POST", path, {**body, "expected_revision_id": task["project"]["revision_id"], "expected_version": task["workflow"]["lock_version"] + 1}, expected=409)
    assert case.task("it1")["task"]["status"] == "PENDING"


def test_publish_is_idempotent_and_old_graph_is_immutable(case):
    definition = case.configure()
    body = {"command_key": uuid4().hex, "expected_version": definition["lock_version"]}
    path = f"/system/workflow/publish/{definition['id']}"
    first = case.call("POST", path, body)
    assert case.call("POST", path, body) == first
    old_id = first["versions"][-1]["id"]
    graph = default_graph()
    graph["nodes"][1]["data"]["label"] = "新草稿名称"
    case.call(
        "PUT", f"/system/workflow/update/{definition['id']}", {"code": definition["code"], "name": definition["name"], "enabled": True, "graph": graph, "expected_version": first["lock_version"]}
    )
    old = case.call("GET", f"/system/workflow/detail/{definition['id']}?version_id={old_id}")
    assert old["read_only"] and old["graph"]["nodes"][1]["data"]["label"] != "新草稿名称"


def test_bootstrapped_menus_obey_current_project_menu_schema(case):
    from app.modules.system.menu.model import MenuModel
    from app.modules.system.menu.schema import MenuOutSchema

    async def validate():
        async with async_db_session() as db:
            menus = (
                (
                    await db.execute(
                        select(MenuModel).where(MenuModel.route_name.in_(["BusinessProjects", "ProjectList", "ApprovalFlowConfig", "WorkflowTasks", "ProjectCreate", "ApprovalFlowDesigner"]))
                    )
                )
                .scalars()
                .all()
            )
            assert len(menus) == 6
            for menu in menus:
                MenuOutSchema.model_validate(menu)

    asyncio.run(validate())


def test_task_owner_needs_no_project_or_configuration_permission(case):
    case.configure()
    project = case.create()
    case.submit(project)
    case.permissions = []
    case.as_user("it1").call("GET", "/business/project/list", expected=403)
    case.call("GET", "/system/workflow/list", expected=403)
    assert case.task("it1")["project"]["id"] == project["id"]
    case.decide("it1")


def test_rejection_record_is_not_overwritten_by_closing_sibling_tasks(case):
    case.configure()
    project = case.create()
    case.submit(project)
    case.decide("it1", "reject", mode="RESTART")
    history = case.detail(project["id"])["workflow"]
    tasks = history["visits"][0]["tasks"]
    assert next(item for item in tasks if item["assignee_id"] == case.data["people"]["it1"]["id"])["status"] == "REJECTED"
    assert next(item for item in tasks if item["assignee_id"] == case.data["people"]["it2"]["id"])["status"] == "CLOSED"


def test_nested_parallel_joins_wait_for_every_branch(case):
    graph = parallel_graph()
    graph["nodes"] += [
        {"id": "inner", "type": "PARALLEL", "data": {"label": "内层并行", "join_key": "inner_join"}},
        {"id": "inner_join", "type": "JOIN", "data": {"label": "内层汇合"}},
        {"id": "extra", "type": "APPROVAL", "data": {"label": "内层额外审核", "approval_mode": "ANY", "assignees": [{"type": "BUSINESS_ROLE", "code": "PROJECT_IT_MANAGER"}]}},
    ]
    graph["edges"] = [edge for edge in graph["edges"] if (edge["source"], edge["target"]) not in {("fork", "business"), ("business", "join")}]
    graph["edges"] += [
        {"id": f"inner_{index}", "source": source, "target": target}
        for index, (source, target) in enumerate([("fork", "inner"), ("inner", "business"), ("inner", "extra"), ("business", "inner_join"), ("extra", "inner_join"), ("inner_join", "join")])
    ]
    case.configure(graph)
    project = case.create()
    case.submit(project)
    case.decide("it1", node="IT项目经理审核")
    case.decide("business")
    assert not case.as_user("head").call("GET", "/workflow/task/todo")["items"]
    case.decide("it1", node="内层额外审核")
    assert case.decide("head")["status"] == "APPROVED"


def test_soft_delete_is_idempotent_and_preserves_revision(case):
    project = case.create()
    body = {"command_key": uuid4().hex, "expected_version": project["lock_version"]}
    path = f"/business/project/{project['id']}/delete"
    first = case.call("POST", path, body)
    assert case.call("POST", path, body) == first
    assert case.call("GET", "/business/project/list")["total"] == 0
    case.call("POST", path, {**body, "expected_version": project["lock_version"] + 1}, expected=409)


def test_child_project_approves_at_nearest_parent_with_people(case):
    case.configure()
    project = case.create(user="child_creator")
    case.submit(project, user="child_creator")
    case.decide("it1")
    case.decide("business")
    resolution = case.task("head")["workflow"]["visits"][-1]["resolution"][0]
    assert resolution["departments_checked"] == [case.data["child"], case.data["finance"]]
    assert resolution["user_ids"] == [case.data["people"]["head"]["id"]]
    assert case.decide("head")["status"] == "APPROVED"


def test_restart_recalculates_condition_but_archives_previous_round_route(case):
    case.configure(conditional_graph())
    project = case.create(external_purchase=True)
    case.submit(project)
    case.decide("it1", "reject", mode="RESTART")
    project = case.update(project["id"], external_purchase=False)
    result = case.submit(project)
    assert result["round_no"] == 2
    assert result["rounds"][0]["routes"][0]["edge_id"] == "first"
    assert result["rounds"][1]["routes"][0]["edge_id"] == "fallback"
    assert case.decide("head")["status"] == "APPROVED"


def test_project_people_options_search_accounts_and_return_user_ids(case):
    account = f"wf_it1_{case.data['prefix']}"
    options = case.as_user("creator").call("GET", f"/business/project/options?search={account}")
    assert len(options["users"]) == 1
    person = options["users"][0]
    assert person["id"] == case.data["people"]["it1"]["id"]
    assert person["username"] == account
    assert person["dept_id"] == case.data["tech"]
    assert set(person) == {"id", "name", "username", "dept_id"}


def test_project_people_options_exclude_disabled_accounts(case):
    async def disable():
        async with async_db_session() as db, db.begin():
            person = await db.get(UserModel, case.data["people"]["it1"]["id"])
            person.status = 1

    asyncio.run(disable())
    options = case.as_user("creator").call("GET", f"/business/project/options?search=wf_it1_{case.data['prefix']}")
    assert options["users"] == []


def test_create_and_submit_directly_creates_running_project(case):
    case.configure()
    body = {**case.body(), "command_key": uuid4().hex}
    result = case.as_user("creator").call("POST", "/business/project/create-and-submit", body)
    assert result["status"] == "IN_REVIEW" and result["revision_no"] == 1
    assert not result["allowed_actions"]["edit"]
    task = case.task("it1")
    assert task["project"]["id"] == result["id"]
    assert task["workflow"]["version_id"] == case.definition["published_version_id"]


def test_create_and_submit_is_idempotent_and_conflicts_on_changed_body(case):
    case.configure()
    body = {**case.body(), "command_key": uuid4().hex}
    first = case.as_user("creator").call("POST", "/business/project/create-and-submit", body)
    assert case.call("POST", "/business/project/create-and-submit", body) == first
    case.call("POST", "/business/project/create-and-submit", {**body, "name": "另一份内容"}, expected=409)
    assert case.call("GET", "/business/project/list")["total"] == 1
    assert len(case.detail(first["id"])["workflow"]["visits"]) == 1


@pytest.mark.parametrize("permissions", [["module_business:project:create"], ["module_business:project:submit"], []])
def test_create_and_submit_requires_both_permissions(case, permissions):
    case.configure()
    case.permissions = permissions
    case.as_user("creator").call("POST", "/business/project/create-and-submit", {**case.body(), "command_key": uuid4().hex}, expected=403)


def test_create_and_submit_missing_binding_leaves_no_project(case):
    case.as_user("admin").call("PUT", "/system/workflow/binding", {"definition_id": None, "manager_role_id": case.data["role_id"]})
    case.as_user("creator").call("POST", "/business/project/create-and-submit", {**case.body(), "command_key": uuid4().hex}, expected=400)
    assert case.call("GET", "/business/project/list")["total"] == 0
    # 单独保存草稿不依赖流程已绑定。
    assert case.create()["status"] == "DRAFT"


def test_create_and_submit_precheck_failure_rolls_back_all_rows_and_can_retry(case):
    from sqlalchemy import func

    from app.modules.business.project.model import ProjectMemberModel, ProjectModel, ProjectRevisionModel
    from app.modules.workflow.model import WorkflowCommandModel, WorkflowInstanceModel, WorkflowTaskModel, WorkflowVisitModel

    tables = [ProjectModel, ProjectMemberModel, ProjectRevisionModel, WorkflowInstanceModel, WorkflowVisitModel, WorkflowTaskModel, WorkflowCommandModel]

    async def counts():
        async with async_db_session() as db:
            return [await db.scalar(select(func.count()).select_from(table)) for table in tables]

    case.configure()
    for key in ("head", "parent_head"):
        case.call("PUT", f"/system/workflow/role-members/{case.data['role_id']}/{case.data['people'][key]['id']}", {"dept_ids": []})
    before = asyncio.run(counts())
    body = {**case.body(), "command_key": uuid4().hex}
    case.as_user("creator").call("POST", "/business/project/create-and-submit", body, expected=400)
    assert asyncio.run(counts()) == before
    case.as_user("admin").call("PUT", f"/system/workflow/role-members/{case.data['role_id']}/{case.data['people']['head']['id']}", {"dept_ids": [case.data["finance"]]})
    assert case.as_user("creator").call("POST", "/business/project/create-and-submit", body)["status"] == "IN_REVIEW"


def test_update_and_submit_saves_once_and_is_idempotent(case):
    case.configure()
    project = case.create()
    body = {**case.body(name="编辑后直接提交"), "expected_version": project["lock_version"], "command_key": uuid4().hex}
    path = f"/business/project/update-and-submit/{project['id']}"
    result = case.call("PUT", path, body)
    assert result["status"] == "IN_REVIEW" and result["revision_no"] == 2
    assert result["name"] == "编辑后直接提交"
    assert case.call("PUT", path, body) == result
    assert len(case.detail(project["id"])["revisions"]) == 2
    assert case.task("it1")["project"]["name"] == "编辑后直接提交"


def test_update_and_submit_failure_rolls_back_edits_and_revision(case):
    case.as_user("admin").call("PUT", "/system/workflow/binding", {"definition_id": None, "manager_role_id": case.data["role_id"]})
    project = case.create()
    body = {**case.body(name="不应保存的修改", it_manager_ids=[case.data["people"]["outsider"]["id"]]), "expected_version": project["lock_version"], "command_key": uuid4().hex}
    case.call("PUT", f"/business/project/update-and-submit/{project['id']}", body, expected=400)
    restored = case.detail(project["id"])
    assert restored["status"] == "DRAFT" and restored["name"] == project["name"]
    assert restored["lock_version"] == project["lock_version"]
    assert restored["it_manager_ids"] == project["it_manager_ids"]
    assert len(restored["revisions"]) == 1 and restored["workflow"] is None


@pytest.mark.parametrize("permissions", [["module_business:project:update"], ["module_business:project:submit"]])
def test_update_and_submit_requires_both_permissions(case, permissions):
    case.configure()
    project = case.create()
    case.permissions = permissions
    case.call("PUT", f"/business/project/update-and-submit/{project['id']}", {**case.body(), "expected_version": project["lock_version"], "command_key": uuid4().hex}, expected=403)


def test_update_and_submit_keeps_owner_and_version_checks(case):
    case.configure()
    project = case.create()
    body = {**case.body(), "expected_version": project["lock_version"], "command_key": uuid4().hex}
    path = f"/business/project/update-and-submit/{project['id']}"
    case.as_user("admin").call("PUT", path, body, expected=403)
    case.as_user("creator").call("PUT", path, {**body, "expected_version": project["lock_version"] + 1}, expected=409)
    assert case.detail(project["id"])["status"] == "DRAFT"


def test_update_and_submit_after_restart_uses_pinned_version(case):
    case.configure()
    project = case.create()
    first = case.submit(project)
    case.decide("it1", "reject", mode="RESTART")
    returned = case.detail(project["id"])
    result = case.call("PUT", f"/business/project/update-and-submit/{project['id']}", {**case.body(), "expected_version": returned["lock_version"], "command_key": uuid4().hex})
    assert result["status"] == "IN_REVIEW"
    history = case.detail(project["id"])["workflow"]
    assert history["round_no"] == 2 and history["version_id"] == first["version_id"]
