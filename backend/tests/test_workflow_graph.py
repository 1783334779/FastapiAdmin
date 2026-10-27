"""纯流程图校验：无脚本执行，畸形 JSON 不应产生服务端 TypeError。"""

from copy import deepcopy

import pytest

from app.modules.workflow.graph import default_graph, evaluate, validate_condition, validate_graph


@pytest.mark.parametrize("bad", [None, [], {}, 1, True])
@pytest.mark.parametrize("path", ["node_type", "mode", "source_type", "edge_source", "edge_target"])
def test_unhashable_and_wrong_typed_graph_values_are_rejected(bad, path):
    graph = default_graph()
    if path == "node_type":
        graph["nodes"][1]["type"] = bad
    elif path == "mode":
        graph["nodes"][1]["data"]["approval_mode"] = bad
    elif path == "source_type":
        graph["nodes"][1]["data"]["assignees"][0]["type"] = bad
    else:
        graph["edges"][0]["source" if path == "edge_source" else "target"] = bad
    with pytest.raises(ValueError):
        validate_graph(graph)


@pytest.mark.parametrize("field", ["field", "op", "logic"])
def test_condition_does_not_accept_objects_as_keywords(field):
    condition = {"field": "external_purchase", "op": "eq", "value": True}
    condition[field] = {}
    with pytest.raises(ValueError):
        validate_condition(condition)


def test_condition_types_and_groups():
    condition = {"logic": "AND", "items": [{"field": "external_purchase", "op": "eq", "value": True}, {"field": "currency", "op": "in", "value": ["CNY", "USD"]}]}
    assert evaluate(condition, {"external_purchase": True, "currency": "CNY"})
    assert not evaluate(condition, {"external_purchase": False, "currency": "CNY"})
    with pytest.raises(ValueError):
        validate_condition({"field": "external_purchase", "op": "eq", "value": "true"})
    with pytest.raises(ValueError):
        validate_condition({"field": "planned_start_date", "op": "gt", "value": "20261001"})


def test_duplicate_edges_and_cycles_are_rejected():
    graph = default_graph()
    graph["edges"].append({**deepcopy(graph["edges"][0]), "id": "duplicate"})
    with pytest.raises(ValueError):
        validate_graph(graph)
    graph = default_graph()
    graph["edges"][-1]["target"] = "it"
    with pytest.raises(ValueError):
        validate_graph(graph)
