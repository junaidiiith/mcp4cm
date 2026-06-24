import json

from mcp4cm.parsers.bpmn_signavio.parser import BPMNSignavioJSONParser


def write_model(tmp_path, payload):
    path = tmp_path / "model.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def simple_signavio_model(*child_shapes):
    return {
        "resourceId": "diagram-1",
        "stencil": {"id": "BPMNDiagram"},
        "properties": {"name": "Order flow"},
        "childShapes": list(child_shapes),
    }


def shape(shape_id, stencil_id, *, name="", outgoing=None, target=None):
    payload = {
        "resourceId": shape_id,
        "stencil": {"id": stencil_id},
        "properties": {"name": name},
        "outgoing": [{"resourceId": ref} for ref in (outgoing or [])],
        "childShapes": [],
    }
    if target is not None:
        payload["target"] = {"resourceId": target}
    return payload


def edge_by_id(ir, edge_id):
    return next(edge for edge in ir.edges if edge.id == edge_id)


def test_bpmn_signavio_parser_materializes_connector_nodes_by_default(tmp_path):
    model_path = write_model(
        tmp_path,
        simple_signavio_model(
            shape("task-1", "Task", name="Create order", outgoing=["flow-1"]),
            shape("task-2", "Task", name="Send invoice"),
            shape("flow-1", "SequenceFlow", target="task-2", outgoing=["task-2"]),
        ),
    )

    ir, stats = BPMNSignavioJSONParser().parse(str(model_path))

    assert stats.elements_skipped == 0
    assert {node.id for node in ir.nodes} == {"diagram-1", "task-1", "task-2", "flow-1"}
    assert edge_by_id(ir, "outgoing:task-1->flow-1").type == "bpmnConnectorSource"
    assert edge_by_id(ir, "target:flow-1->task-2").type == "bpmnConnectorTarget"

    derived = edge_by_id(ir, "flow-1")
    assert derived.sourceId == "task-1"
    assert derived.targetId == "task-2"
    assert derived.type == "SequenceFlow"
    assert derived.data["derived"] is True
    assert derived.data["connectorId"] == "flow-1"


def test_bpmn_signavio_parser_preserves_connector_to_connector_relationships(tmp_path):
    model_path = write_model(
        tmp_path,
        simple_signavio_model(
            shape("data-1", "DataObject", name="Invoice", outgoing=["assoc-1"]),
            shape("task-1", "Task", name="Create order", outgoing=["flow-1"]),
            shape("task-2", "Task", name="Send invoice"),
            shape("flow-1", "SequenceFlow", target="task-2", outgoing=["task-2"]),
            shape("assoc-1", "Association_Undirected", target="flow-1", outgoing=["flow-1"]),
        ),
    )

    ir, stats = BPMNSignavioJSONParser().parse(str(model_path))

    assert stats.elements_skipped == 0
    assert "assoc-1" in {node.id for node in ir.nodes}
    assert "flow-1" in {node.id for node in ir.nodes}

    source_ref = edge_by_id(ir, "outgoing:data-1->assoc-1")
    assert source_ref.sourceId == "data-1"
    assert source_ref.targetId == "assoc-1"
    assert source_ref.type == "bpmnConnectorSource"

    target_ref = edge_by_id(ir, "target:assoc-1->flow-1")
    assert target_ref.sourceId == "assoc-1"
    assert target_ref.targetId == "flow-1"
    assert target_ref.type == "bpmnConnectorTarget"


def test_bpmn_signavio_parser_can_use_legacy_edge_only_connector_mode(tmp_path):
    model_path = write_model(
        tmp_path,
        simple_signavio_model(
            shape("task-1", "Task", name="Create order", outgoing=["flow-1"]),
            shape("task-2", "Task", name="Send invoice"),
            shape("flow-1", "SequenceFlow", target="task-2", outgoing=["task-2"]),
        ),
    )

    ir, stats = BPMNSignavioJSONParser(materialize_connector_nodes=False).parse(str(model_path))

    assert stats.elements_skipped == 0
    assert {node.id for node in ir.nodes} == {"diagram-1", "task-1", "task-2"}

    edge = edge_by_id(ir, "flow-1")
    assert edge.sourceId == "task-1"
    assert edge.targetId == "task-2"
    assert edge.type == "SequenceFlow"
    assert "derived" not in edge.data
