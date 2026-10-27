"""受限条件语言和结构化有向无环流程图，不执行用户脚本。"""

import re
from collections import deque
from copy import deepcopy
from datetime import date
from math import isfinite

NODE_TYPES = {"START", "APPROVAL", "EXCLUSIVE", "MERGE", "PARALLEL", "JOIN", "END"}
FIELDS = {
    "name": "string",
    "initiation_type": "string",
    "category": "string",
    "external_purchase": "boolean",
    "business_dept_id": "number",
    "planned_start_date": "date",
    "planned_end_date": "date",
    "currency": "string",
    "it_manager_ids": "users",
    "business_manager_ids": "users",
}
OPERATORS = {"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "contains"}


def validate_condition(condition: dict, depth: int = 0) -> None:
    if not isinstance(condition, dict) or depth > 5:
        raise ValueError("条件必须为对象，嵌套不能超过5层")
    if "logic" in condition:
        items = condition.get("items")
        if not isinstance(condition["logic"], str) or condition["logic"] not in {"AND", "OR"} or not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ValueError("条件组需要 AND/OR 和1至20项子条件")
        for item in items:
            validate_condition(item, depth + 1)
        return
    field, op, value = condition.get("field"), condition.get("op"), condition.get("value")
    if not isinstance(field, str) or not isinstance(op, str) or field not in FIELDS or op not in OPERATORS:
        raise ValueError("条件字段或操作符不受支持")
    kind = FIELDS[field]
    if kind == "users":
        if op != "contains" or type(value) is not int or value <= 0:
            raise ValueError("经理集合只能用 contains 判断一个正整数用户ID")
        return
    if op == "contains" or (op in {"gt", "gte", "lt", "lte"} and kind not in {"number", "date"}):
        raise ValueError("条件操作符与字段类型不匹配")
    values = value if op in {"in", "not_in"} else [value]
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError("集合条件需要非空数组，最多100项")
    for item in values:
        if kind == "boolean" and type(item) is not bool:
            raise ValueError("是否采购条件必须使用布尔值")
        if kind == "number" and (type(item) is not int or item <= 0):
            raise ValueError("部门条件必须使用正整数ID")
        if kind in {"date", "string"} and (not isinstance(item, str) or not item.strip() or len(item) > 255):
            raise ValueError("文字/日期条件值不合法")
        if kind == "date":
            if date.fromisoformat(item).isoformat() != item:
                raise ValueError("日期条件需要 YYYY-MM-DD 格式")


def evaluate(condition: dict, snapshot: dict) -> bool:
    validate_condition(condition)
    if "logic" in condition:
        results = [evaluate(item, snapshot) for item in condition["items"]]
        return all(results) if condition["logic"] == "AND" else any(results)
    actual, expected, op = snapshot.get(condition["field"]), condition["value"], condition["op"]
    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "contains":
        return expected in actual
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    return actual <= expected


def validate_graph(value: dict) -> dict:
    graph = deepcopy(value)
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise ValueError("流程图需要 nodes 和 edges 数组")
    if not 3 <= len(graph["nodes"]) <= 100 or len(graph["edges"]) > 300:
        raise ValueError("流程需要3至100个节点、最多300条连线")
    nodes, outgoing, incoming = {}, {}, {}
    for node in graph["nodes"]:
        key = node.get("id") if isinstance(node, dict) else None
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) or key in nodes:
            raise ValueError("节点ID必须唯一，仅包含字母数字、下划线或横线")
        if not isinstance(node.get("type"), str) or node["type"] not in NODE_TYPES:
            raise ValueError(f"节点 {key} 类型不合法")
        data = node.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("label"), str) or not 1 <= len(data["label"].strip()) <= 100:
            raise ValueError(f"节点 {key} 需要1至100字名称")
        position = node.get("position", {"x": 0, "y": 0})
        if not isinstance(position, dict) or any(type(position.get(axis)) not in (int, float) or not isfinite(position[axis]) or abs(position[axis]) > 100000 for axis in ("x", "y")):
            raise ValueError("节点坐标不合法")
        node["position"] = position
        if node["type"] == "APPROVAL":
            rules = data.get("assignees")
            if not isinstance(data.get("approval_mode"), str) or data["approval_mode"] not in {"ANY", "ALL"} or not isinstance(rules, list) or not 1 <= len(rules) <= 20:
                raise ValueError(f"{data['label']} 需要审批模式及1至20个人员来源")
            for rule in rules:
                if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or rule["type"] not in {"SYSTEM_ROLE", "BUSINESS_ROLE"}:
                    raise ValueError("审批来源必须为系统角色或业务角色")
                if rule["type"] == "SYSTEM_ROLE" and (type(rule.get("role_id")) is not int or rule["role_id"] <= 0):
                    raise ValueError("系统角色ID不合法")
                if rule["type"] == "BUSINESS_ROLE" and (not isinstance(rule.get("code"), str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", rule["code"])):
                    raise ValueError("业务角色编码不合法")
        nodes[key], outgoing[key], incoming[key] = node, [], []
    edge_ids, edge_pairs = set(), set()
    for edge in graph["edges"]:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str) or edge["id"] in edge_ids or not 1 <= len(edge["id"]) <= 64:
            raise ValueError("连线ID必须存在且唯一")
        if not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str) or edge["source"] not in nodes or edge["target"] not in nodes or edge["source"] == edge["target"]:
            raise ValueError("连线端点不存在或指向自身")
        pair = (edge["source"], edge["target"])
        if pair in edge_pairs:
            raise ValueError("同一对节点不能重复连线")
        edge_pairs.add(pair)
        if "is_default" in edge and type(edge["is_default"]) is not bool:
            raise ValueError("默认路线标记必须为布尔值")
        edge_ids.add(edge["id"])
        outgoing[edge["source"]].append(edge)
        incoming[edge["target"]].append(edge)
    starts = [node["id"] for node in nodes.values() if node["type"] == "START"]
    ends = [node["id"] for node in nodes.values() if node["type"] == "END"]
    if len(starts) != 1 or len(ends) != 1 or not any(node["type"] == "APPROVAL" for node in nodes.values()):
        raise ValueError("流程必须有一个开始、一个结束和至少一个审核节点")
    for key, node in nodes.items():
        kind, out, inc = node["type"], outgoing[key], incoming[key]
        if (kind == "START" and inc) or (kind == "END" and out) or (kind != "START" and not inc) or (kind != "END" and not out):
            raise ValueError(f"{node['data']['label']} 的入口或出口不完整")
        if kind not in {"END", "EXCLUSIVE", "PARALLEL"} and len(out) != 1:
            raise ValueError(f"{node['data']['label']} 只能有一条后续连线")
        if kind in {"EXCLUSIVE", "PARALLEL"} and len(out) < 2:
            raise ValueError("分支节点至少需要两条出口")
        if kind == "EXCLUSIVE":
            if sum(edge.get("is_default") is True for edge in out) != 1:
                raise ValueError("每个条件分支必须且只能配置一条默认路线")
            priorities = []
            for edge in out:
                if edge.get("is_default") is True:
                    if edge.get("condition") is not None:
                        raise ValueError("默认路线不能同时配置条件")
                    continue
                if type(edge.get("priority")) is not int or edge["priority"] < 0:
                    raise ValueError("条件分支需要非负整数优先级")
                priorities.append(edge["priority"])
                validate_condition(edge.get("condition"))
            if len(priorities) != len(set(priorities)):
                raise ValueError("同一条件分支的优先级不能重复")
        elif any(edge.get("condition") or edge.get("is_default") for edge in out):
            raise ValueError("只有条件分支节点的出口可以配置条件或默认路线")
    indegree = {key: len(edges) for key, edges in incoming.items()}
    queue, visited = deque(starts), set()
    while queue:
        key = queue.popleft()
        visited.add(key)
        for edge in outgoing[key]:
            indegree[edge["target"]] -= 1
            if indegree[edge["target"]] == 0:
                queue.append(edge["target"])
    if len(visited) != len(nodes):
        raise ValueError("流程存在回环或不可达节点；反向处理请使用驳回，不要画循环边")
    paired_joins = set()
    for key, node in nodes.items():
        if node["type"] != "PARALLEL":
            continue
        join_key = node["data"].get("join_key")
        if not isinstance(join_key, str) or join_key not in nodes or nodes[join_key]["type"] != "JOIN" or join_key in paired_joins:
            raise ValueError("每个并行分叉必须指定独立的并行汇合节点")
        paired_joins.add(join_key)
        branch_sets = []
        for edge in outgoing[key]:
            stack, members = [edge["target"]], set()
            while stack:
                target = stack.pop()
                if target == join_key or target in members:
                    continue
                if target == key or nodes[target]["type"] == "END":
                    raise ValueError("并行分支必须先到达配对汇合，不能直接结束")
                members.add(target)
                stack.extend(item["target"] for item in outgoing[target])
            if any(members & other for other in branch_sets):
                raise ValueError("并行分支不能在配对汇合前交叉")
            branch_sets.append(members)
    if {key for key, node in nodes.items() if node["type"] == "JOIN"} != paired_joins:
        raise ValueError("存在没有配对分叉的并行汇合")
    # 每条路径都必须遵循相同的并行作用域，避免从条件旁路直接进入 JOIN，
    # 或嵌套并行尚未汇合就越过外层汇合；不能等到运行时才发现图不可执行。
    contexts, pending = {}, [(starts[0], ())]
    while pending:
        key, stack = pending.pop()
        node = nodes[key]
        if node["type"] == "JOIN":
            if not stack or nodes[stack[-1][0]]["data"]["join_key"] != key:
                raise ValueError("并行汇合存在越级或非并行入口")
            stack = stack[:-1]
        if key in contexts:
            if contexts[key] != stack:
                raise ValueError("节点存在不同并行作用域的非法交叉入口")
            continue
        contexts[key] = stack
        if node["type"] == "END" and stack:
            raise ValueError("并行分支尚未汇合，不能结束")
        for edge in outgoing[key]:
            next_stack = (*stack, (key, edge["id"])) if node["type"] == "PARALLEL" else stack
            pending.append((edge["target"], next_stack))
    return graph


def ancestors(graph: dict, key: str) -> set[str]:
    found, stack = set(), [key]
    while stack:
        target = stack.pop()
        for edge in graph["edges"]:
            if edge["target"] == target and edge["source"] not in found:
                found.add(edge["source"])
                stack.append(edge["source"])
    return found


def default_graph() -> dict:
    labels = [("start", "START", "开始"), ("it", "APPROVAL", "IT项目经理审核"), ("business", "APPROVAL", "业务项目经理审核"), ("manager", "APPROVAL", "部门负责人审核"), ("end", "END", "结束")]
    codes = {"it": "PROJECT_IT_MANAGER", "business": "PROJECT_BUSINESS_MANAGER", "manager": "CREATOR_DEPT_MANAGER"}
    nodes = []
    for index, (key, kind, label) in enumerate(labels):
        data = {"label": label}
        if kind == "APPROVAL":
            data.update(approval_mode="ANY", assignees=[{"type": "BUSINESS_ROLE", "code": codes[key]}])
        nodes.append({"id": key, "type": kind, "position": {"x": 280, "y": 80 + index * 140}, "data": data})
    return {"nodes": nodes, "edges": [{"id": f"edge_{index}", "source": labels[index][0], "target": labels[index + 1][0]} for index in range(len(labels) - 1)]}
