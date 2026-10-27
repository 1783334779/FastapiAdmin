"""数据库事务内执行的审批状态机。调用者必须先锁定业务单据及实例。

state 是执行路径、并行作用域及返回栈的唯一事实；任务和本次节点执行独立存表。
所有嵌套 JSON 修改在 persist 时整体赋回，避免 ORM 漏掉原地变更。
"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .graph import ancestors, evaluate
from .model import WorkflowActionModel, WorkflowInstanceModel, WorkflowTaskModel, WorkflowVisitModel
from .resolvers import AssigneeResolver


class WorkflowRuntime:
    def __init__(self, db: AsyncSession, instance: WorkflowInstanceModel, graph: dict, role_rules: dict, context: dict, actor_id: int) -> None:
        self.db, self.instance, self.graph, self.rules, self.context, self.actor_id = db, instance, graph, role_rules, context, actor_id
        self.nodes = {node["id"]: node for node in graph["nodes"]}
        self.edges = {key: [edge for edge in graph["edges"] if edge["source"] == key] for key in self.nodes}
        self.state = deepcopy(instance.state or {"tokens": {}, "scopes": {}, "returns": [], "blocked": None, "routes": []})

    async def log(self, action: str, visit_id: int | None = None, opinion: str = "", **details) -> None:
        self.db.add(
            WorkflowActionModel(
                instance_id=self.instance.id,
                actor_id=self.actor_id,
                action=action,
                visit_id=visit_id,
                revision_id=self.context["revision_id"],
                opinion=opinion,
                details={"round_no": self.instance.round_no, **details},
            )
        )

    async def persist(self) -> None:
        self.instance.state = deepcopy(self.state)
        self.instance.lock_version += 1
        await self.db.flush()

    async def start(self) -> None:
        history = deepcopy(self.state.get("history_rounds", []))
        if self.state.get("tokens"):
            history.append({"round_no": self.instance.round_no - 1, **{key: deepcopy(value) for key, value in self.state.items() if key != "history_rounds"}})
        self.state = {"tokens": {}, "scopes": {}, "returns": [], "blocked": None, "routes": [], "history_rounds": history, "submitted_revision_id": self.context["revision_id"]}
        self.instance.status = "RUNNING"
        start = next(node["id"] for node in self.nodes.values() if node["type"] == "START")
        await self.log("SUBMIT", round_no=self.instance.round_no)
        await self.spawn(start, [])

    async def spawn(self, node_key: str, lane: list, mode: str = "NORMAL", return_id: str | None = None) -> None:
        key = uuid4().hex
        token = {"id": key, "node": node_key, "lane": deepcopy(lane), "mode": mode, "return_id": return_id, "status": "WAITING"}
        self.state["tokens"][key] = token
        await self.activate(token)

    async def activate(self, token: dict) -> None:
        if self.instance.status == "BLOCKED":
            token["status"] = "WAITING"
            return
        token["status"] = "ACTIVE"
        node = self.nodes[token["node"]]
        kind = node["type"]
        if kind in {"START", "MERGE"}:
            await self.forward(token)
        elif kind == "END":
            token["status"] = "COMPLETED"
            if not self.state["returns"] and all(item["status"] == "COMPLETED" for item in self.state["tokens"].values()):
                self.instance.status = "APPROVED"
                await self.log("FINISH")
        elif kind == "EXCLUSIVE":
            edges = self.edges[node["id"]]
            default = next(edge for edge in edges if edge.get("is_default") is True)
            chosen = next(
                (edge for edge in sorted((item for item in edges if not item.get("is_default")), key=lambda item: item["priority"]) if evaluate(edge["condition"], self.context["snapshot"])), default
            )
            self.state["routes"].append({"node_key": node["id"], "edge_id": chosen["id"], "revision_id": self.context["revision_id"]})
            await self.log("ROUTE", node_key=node["id"], edge_id=chosen["id"], target_node=chosen["target"])
            token["status"] = "COMPLETED"
            await self.spawn(chosen["target"], token["lane"])
        elif kind == "PARALLEL":
            scope_id = uuid4().hex
            self.state["scopes"][scope_id] = {"join": node["data"]["join_key"], "expected": [edge["id"] for edge in self.edges[node["id"]]], "arrivals": [], "closed": False}
            await self.log("FORK", node_key=node["id"], scope_id=scope_id)
            token["status"] = "COMPLETED"
            for edge in self.edges[node["id"]]:
                await self.spawn(edge["target"], [*token["lane"], {"scope": scope_id, "branch": edge["id"]}])
        elif kind == "JOIN":
            if not token["lane"]:
                raise ValueError("汇合缺少并行作用域")
            current = token["lane"][-1]
            scope = self.state["scopes"][current["scope"]]
            if scope["join"] != node["id"]:
                raise ValueError("汇合与当前分支作用域不匹配")
            token["status"] = "COMPLETED"
            if current["branch"] not in scope["arrivals"]:
                scope["arrivals"].append(current["branch"])
            if not scope["closed"] and set(scope["expected"]) == set(scope["arrivals"]):
                scope["closed"] = True
                await self.log("JOIN", node_key=node["id"], scope_id=current["scope"])
                await self.spawn(self.edges[node["id"]][0]["target"], token["lane"][:-1])
        else:
            try:
                people, explanations = await AssigneeResolver(self.db).resolve(node, self.rules, self.context)
                reason = "未找到有效审批人" if not people else ""
            except ValueError as exc:
                people, explanations, reason = [], [], str(exc)
            if not people:
                await self.block(token, reason, "ACTIVATION", sources=explanations)
                return
            visit = WorkflowVisitModel(
                instance_id=self.instance.id,
                round_no=self.instance.round_no,
                token_id=token["id"],
                node_key=node["id"],
                node_name=node["data"]["label"],
                lane=deepcopy(token["lane"]),
                approval_mode=node["data"]["approval_mode"],
                revision_id=self.context["revision_id"],
                status="ACTIVE",
                candidates=people,
                resolution=explanations,
            )
            self.db.add(visit)
            await self.db.flush()
            token["visit_id"] = visit.id
            self.db.add_all([WorkflowTaskModel(instance_id=self.instance.id, visit_id=visit.id, assignee_id=person["id"], status="PENDING") for person in people])
            await self.log("ENTER", visit.id, candidates=people)

    async def forward(self, token: dict) -> None:
        token["status"] = "COMPLETED"
        await self.spawn(self.edges[token["node"]][0]["target"], token["lane"])

    async def suspend(self) -> list[int]:
        # 项目会话关闭 autoflush；状态过滤查询前必须落下本事务的状态变更，
        # 否则刚通过的人仍会被 SQL 的旧 PENDING 条件选中并错误改成暂停。
        await self.db.flush()
        visits = (
            (
                await self.db.execute(
                    select(WorkflowVisitModel).where(WorkflowVisitModel.instance_id == self.instance.id, WorkflowVisitModel.round_no == self.instance.round_no, WorkflowVisitModel.status == "ACTIVE")
                )
            )
            .scalars()
            .all()
        )
        ids = [visit.id for visit in visits]
        for visit in visits:
            visit.status = "SUSPENDED"
        if ids:
            tasks = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.visit_id.in_(ids), WorkflowTaskModel.status == "PENDING"))).scalars().all()
            for task in tasks:
                task.status = "SUSPENDED"
        return ids

    async def resume(self, ids: list[int]) -> None:
        if not ids:
            return
        visits = (await self.db.execute(select(WorkflowVisitModel).where(WorkflowVisitModel.id.in_(ids), WorkflowVisitModel.status == "SUSPENDED"))).scalars().all()
        for visit in visits:
            visit.status = "ACTIVE"
        active = [visit.id for visit in visits]
        if active:
            tasks = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.visit_id.in_(active), WorkflowTaskModel.status == "SUSPENDED"))).scalars().all()
            for task in tasks:
                task.status = "PENDING"

    async def block(self, token: dict, reason: str, kind: str, **details) -> None:
        ids = await self.suspend()
        self.instance.status = "BLOCKED"
        token["status"] = "BLOCKED"
        self.state["blocked"] = {"kind": kind, "token_id": token["id"], "node_key": token["node"], "reason": reason, "paused_visit_ids": ids, **details}
        await self.log("BLOCKED", reason=reason, node_key=token["node"], kind=kind)

    async def retry(self) -> None:
        blocked = self.state.get("blocked")
        if self.instance.status != "BLOCKED" or not blocked:
            raise ValueError("当前没有可恢复的阻塞")
        token = self.state["tokens"][blocked["token_id"]]
        if blocked["kind"] == "FIXED_MEMBERS":
            users = await AssigneeResolver(self.db).users(blocked["user_ids"])
            if {person["id"] for person in users} != set(blocked["user_ids"]):
                raise ValueError("既有待办人员仍然失效；请恢复原账号，不能静默换人或减少会签人数")
            token["status"] = "ACTIVE"
        else:
            node = self.nodes[token["node"]]
            people, _ = await AssigneeResolver(self.db).resolve(node, self.rules, self.context)
            if not people:
                raise ValueError("仍未找到审批人，请先补齐配置")
        self.instance.status = "RUNNING"
        self.state["blocked"] = None
        await self.resume(blocked["paused_visit_ids"])
        if blocked["kind"] == "ACTIVATION":
            await self.activate(token)
        for waiting in list(self.state["tokens"].values()):
            if waiting["status"] == "WAITING":
                await self.activate(waiting)
        await self.log("RECOVER")

    async def approve(self, task: WorkflowTaskModel, visit: WorkflowVisitModel, opinion: str) -> None:
        task.status, task.opinion, task.decision_revision_id, task.completed_time = "APPROVED", opinion, self.context["revision_id"], datetime.now(UTC)
        self.instance.has_approval_action = True
        await self.log("APPROVE", visit.id, opinion)
        await self.db.flush()
        tasks = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.visit_id == visit.id))).scalars().all()
        if visit.approval_mode == "ANY" or all(item.status == "APPROVED" for item in tasks):
            visit.status = "APPROVED"
            for item in tasks:
                if item.status == "PENDING":
                    item.status, item.completed_time = "CLOSED", datetime.now(UTC)
            token = self.state["tokens"][visit.token_id]
            token["status"] = "COMPLETED"
            await self.complete_mode(token)
        else:
            remaining = [item.assignee_id for item in tasks if item.status == "PENDING"]
            valid = await AssigneeResolver(self.db).users(remaining)
            if {person["id"] for person in valid} != set(remaining):
                await self.block(self.state["tokens"][visit.token_id], "本次会签名单有停用或删除账号，请恢复原账号后重试", "FIXED_MEMBERS", user_ids=remaining)

    async def targets(self, visit: WorkflowVisitModel) -> list[dict]:
        possible = ancestors(self.graph, visit.node_key)
        history = (
            (
                await self.db.execute(
                    select(WorkflowVisitModel).where(WorkflowVisitModel.instance_id == self.instance.id, WorkflowVisitModel.round_no == self.instance.round_no).order_by(WorkflowVisitModel.id.desc())
                )
            )
            .scalars()
            .all()
        )
        result, seen = [{"id": "DRAFT", "name": "起草"}], set()
        for previous in history:
            if previous.node_key in possible and previous.node_key not in seen and visit.lane[: len(previous.lane)] == previous.lane:
                seen.add(previous.node_key)
                result.append({"id": previous.node_key, "name": previous.node_name, "visit_id": previous.id})
        return result

    async def reject(self, task: WorkflowTaskModel, visit: WorkflowVisitModel, mode: str, target: str | None, opinion: str) -> None:
        if not opinion.strip():
            raise ValueError("驳回请填写原因")
        if mode == "RESTART" and target is not None:
            raise ValueError("驳回重走不能选择目标")
        if mode == "TARGETED" and target not in {item["id"] for item in await self.targets(visit)}:
            raise ValueError("目标不是当前同分支/公共祖先已到达节点，不能跨并行分支或选择未来节点")
        task.status, task.opinion, task.decision_revision_id, task.completed_time = "REJECTED", opinion, self.context["revision_id"], datetime.now(UTC)
        visit.status = "REJECTED"
        self.instance.has_approval_action = True
        await self.db.flush()
        siblings = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.visit_id == visit.id, WorkflowTaskModel.status == "PENDING"))).scalars().all()
        for sibling in siblings:
            sibling.status, sibling.completed_time = "CLOSED", datetime.now(UTC)
        paused = await self.suspend()
        token = self.state["tokens"][visit.token_id]
        token["status"] = "WAIT_RETURN"
        await self.log("REJECT", visit.id, opinion, mode=mode, target=target, abandoned_returns=deepcopy(self.state["returns"]) if mode == "RESTART" else [])
        if mode == "RESTART":
            self.instance.status = "RETURNED"
            self.state["returns"] = []
            self.state["restart_required"] = True
            return
        context = {
            "id": uuid4().hex,
            "origin_token_id": token["id"],
            "origin_node": token["node"],
            "origin_lane": deepcopy(token["lane"]),
            "paused_visit_ids": paused,
            "target": target,
            "phase": "TARGET",
        }
        self.state["returns"].append(context)
        if target == "DRAFT":
            self.instance.status = "RETURNED"
            return
        selected = next(item for item in await self.targets(visit) if item["id"] == target)
        previous = await self.db.get(WorkflowVisitModel, selected["visit_id"])
        await self.spawn(target, previous.lane, "RETURN_TARGET", context["id"])

    async def complete_mode(self, token: dict) -> None:
        if token["mode"] == "NORMAL":
            await self.forward(token)
            return
        context = next(item for item in self.state["returns"] if item["id"] == token["return_id"])
        if token["mode"] == "RETURN_TARGET":
            context["phase"] = "ORIGIN"
            await self.spawn(context["origin_node"], context["origin_lane"], "RETURN_ORIGIN", context["id"])
            return
        if self.state["returns"][-1]["id"] != context["id"]:
            raise ValueError("返回链尚有未完成的内层处理")
        self.state["returns"].pop()
        await self.resume(context["paused_visit_ids"])
        origin = self.state["tokens"][context["origin_token_id"]]
        origin["status"] = "COMPLETED"
        await self.complete_mode(origin)

    async def resubmit_targeted(self) -> None:
        context = self.state["returns"][-1]
        if context["target"] != "DRAFT" or context["phase"] != "TARGET":
            raise ValueError("当前不在可重新提交的起草环节")
        self.instance.status = "RUNNING"
        context["phase"] = "ORIGIN"
        await self.log("RESUBMIT_TARGETED")
        await self.spawn(context["origin_node"], context["origin_lane"], "RETURN_ORIGIN", context["id"])

    async def cancel_open(self, action: str) -> None:
        tasks = (await self.db.execute(select(WorkflowTaskModel).where(WorkflowTaskModel.instance_id == self.instance.id, WorkflowTaskModel.status.in_(["PENDING", "SUSPENDED"])))).scalars().all()
        for task in tasks:
            task.status, task.completed_time = "CANCELLED", datetime.now(UTC)
        visits = (await self.db.execute(select(WorkflowVisitModel).where(WorkflowVisitModel.instance_id == self.instance.id, WorkflowVisitModel.status.in_(["ACTIVE", "SUSPENDED"])))).scalars().all()
        for visit in visits:
            visit.status = "CANCELLED"
        for token in self.state.get("tokens", {}).values():
            if token["status"] != "COMPLETED":
                token["status"] = "CANCELLED"
        self.state["closed_by"] = action
        await self.log(action)
