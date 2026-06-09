from io import BytesIO
from collections import Counter
import os
import time
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from mcp4cm import api_server
from mcp4cm.api_server import (
    DATASETS,
    DUPLICATE_JOBS,
    UPLOAD_PARSE_JOBS,
    UPLOAD_SESSIONS,
    create_app,
)
from mcp4cm.core import Dataset
from mcp4cm.parsers.archimate_json.parser import ArchimateJsonParser
from mcp4cm.parsers.graph import normalize_graph_attributes


def test_top_items_returns_all_values_when_limit_is_omitted():
    items = api_server.top_items(Counter({f"type-{index}": index for index in range(20)}))

    assert len(items) == 20


def clear_runtime():
    shutil.rmtree(api_server.RUNTIME_DIR, ignore_errors=True)


def upload_and_parse_via_job(
    client,
    *,
    language: str,
    files,
    data_format: str = "json",
    session_overrides: dict | None = None,
    poll_attempts: int = 100,
):
    payload = {"language": language, "format": data_format}
    if session_overrides:
        payload.update(session_overrides)
    started_session = client.post("/api/uploads/start", json=payload)
    assert started_session.status_code == 200
    upload_id = started_session.get_json()["uploadId"]

    uploaded = client.post(
        f"/api/uploads/{upload_id}/chunks",
        data={"files": files},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200

    started_job = client.post(f"/api/uploads/{upload_id}/parse", json={})
    assert started_job.status_code == 200
    job_id = started_job.get_json()["jobId"]

    job_data = {}
    for _ in range(poll_attempts):
        response = client.get(f"/api/uploads/{upload_id}/jobs/{job_id}")
        assert response.status_code == 200
        job_data = response.get_json()
        if job_data["status"] in {"complete", "error"}:
            break
        time.sleep(0.05)
    return upload_id, job_id, job_data


def run_duplicate_job(client, payload: dict, poll_attempts: int = 40):
    started = client.post("/api/duplicates/jobs", json=payload)
    assert started.status_code == 200
    job_id = started.get_json()["jobId"]

    data = {}
    for _ in range(poll_attempts):
        response = client.get(f"/api/duplicates/jobs/{job_id}")
        assert response.status_code == 200
        data = response.get_json()
        if data["status"] in {"complete", "error"}:
            break
        time.sleep(0.05)
    return data


def test_flask_health_route():
    client = create_app().test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_legacy_sync_endpoints_are_removed():
    client = create_app().test_client()

    upload_response = client.post("/api/datasets", json={})
    duplicate_response = client.post("/api/duplicates", json={})

    assert upload_response.status_code == 404
    assert duplicate_response.status_code == 404
    assert upload_response.get_json()["error"] == "Not found"
    assert duplicate_response.get_json()["error"] == "Not found"


def test_upload_session_chunked_parse_job():
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    clear_runtime()
    client = create_app().test_client()

    session = client.post("/api/uploads/start", json={"language": "bpmn", "format": "signavio"}).get_json()
    upload_id = session["uploadId"]
    stage_dir = Path(UPLOAD_SESSIONS[upload_id]["stageDir"])

    valid_signavio = {
        "resourceId": "diagram-1",
        "stencil": {"id": "BPMNDiagram"},
        "properties": {"name": "Order flow"},
        "childShapes": [],
    }

    chunk = client.post(
        f"/api/uploads/{upload_id}/chunks",
        data={
            "files": [
                (BytesIO(json.dumps(valid_signavio).encode("utf-8")), "models/model-a.json"),
                (BytesIO(b"ignored"), "models/README.txt"),
            ]
        },
        content_type="multipart/form-data",
    ).get_json()
    assert chunk["totalFiles"] == 2

    started_job = client.post(f"/api/uploads/{upload_id}/parse", json={}).get_json()
    job_id = started_job["jobId"]

    job_data = {}
    for _ in range(30):
        response = client.get(f"/api/uploads/{upload_id}/jobs/{job_id}")
        job_data = response.get_json()
        if job_data["status"] == "complete":
            break
        time.sleep(0.05)

    assert job_data["status"] == "complete"
    assert job_data["processedFiles"] == 2
    assert job_data["uploadSummary"]["records"] == 1
    assert job_data["uploadSummary"]["errors"] == 0
    assert job_data["uploadSummary"]["warnings"] >= 1
    assert job_data["datasetId"]
    assert job_data["statistics"]["summary"]["models"] == 1
    assert not stage_dir.exists()
    assert UPLOAD_SESSIONS[upload_id]["stageDir"] == ""


def test_upload_start_resets_previous_pipeline_state_and_runtime(tmp_path):
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    DUPLICATE_JOBS.clear()
    clear_runtime()

    DATASETS["old"] = Dataset([], "archimate")
    old_stage = tmp_path / "old-stage"
    old_stage.mkdir()
    (old_stage / "tmp.bin").write_bytes(b"1")
    UPLOAD_SESSIONS["old"] = {"status": "ready", "stageDir": str(old_stage), "files": []}
    UPLOAD_PARSE_JOBS["old"] = {"status": "complete"}
    DUPLICATE_JOBS["old"] = {"status": "complete"}

    runtime_dummy = api_server.RUNTIME_DIR / "index.json"
    runtime_dummy.parent.mkdir(parents=True, exist_ok=True)
    runtime_dummy.write_text("{}", encoding="utf-8")

    client = create_app().test_client()
    response = client.post("/api/uploads/start", json={"language": "bpmn", "format": "signavio"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["uploadId"] in UPLOAD_SESSIONS
    assert len(UPLOAD_SESSIONS) == 1
    assert "old" not in DATASETS
    assert "old" not in UPLOAD_PARSE_JOBS
    assert "old" not in DUPLICATE_JOBS
    assert not old_stage.exists()
    assert not api_server.RUNTIME_DIR.exists()


def test_upload_start_rejects_when_pipeline_run_is_active():
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    DUPLICATE_JOBS.clear()
    clear_runtime()

    UPLOAD_SESSIONS["active"] = {"status": "collecting", "stageDir": "", "files": []}
    client = create_app().test_client()
    response = client.post("/api/uploads/start", json={"language": "bpmn", "format": "signavio"})
    data = response.get_json()

    assert response.status_code == 400
    assert "already active" in data["error"]


def test_runtime_dataset_persistence_supports_reload_when_memory_is_cleared():
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    DUPLICATE_JOBS.clear()
    clear_runtime()

    client = create_app().test_client()
    _, _, job = upload_and_parse_via_job(
        client,
        language="archimate",
        files=(
            BytesIO(
                json.dumps(
                    {
                        "archimateId": "m-runtime",
                        "name": "Runtime model",
                        "elements": [{"id": "a", "name": "App", "type": "ApplicationComponent"}],
                        "relationships": [],
                    }
                ).encode("utf-8")
            ),
            "model.json",
        ),
    )
    assert job["status"] == "complete"
    dataset_id = job["datasetId"]
    assert (api_server.RUNTIME_DIR / "index.json").exists()
    assert (api_server.RUNTIME_DIR / "ir" / dataset_id).exists()

    DATASETS.clear()
    inspect = client.get(f"/api/datasets/{dataset_id}/models/m-runtime/inspect")
    inspect_data = inspect.get_json()

    assert inspect.status_code == 200
    assert inspect_data["model"]["id"] == "m-runtime"


def test_serialize_graph_for_runtime_flattens_attrs_and_deduplicates_data_fields():
    nx = api_server.require_networkx()
    graph = nx.MultiDiGraph()
    graph.add_node(
        "n1",
        id="n1",
        type="Class",
        name="B",
        data={"attributes": [{"id": "att1", "name": "x"}]},
        attributes=[{"id": "att1", "name": "x"}],
    )
    graph.add_node("n2", id="n2", type="Class", name="A", data={})
    graph.add_edge(
        "n1",
        "n2",
        key="e1",
        id="e1",
        type="Generalization",
        data={"general": "n2", "specific": "n1"},
        general="n2",
        specific="n1",
    )

    payload = api_server.serialize_graph_for_runtime(graph)

    node = next(item for item in payload["nodes"] if item["id"] == "n1")
    assert "attrs" not in node
    assert node["type"] == "Class"
    assert node["name"] == "B"
    assert node["data"]["attributes"][0]["id"] == "att1"
    assert "attributes" not in node

    edge = next(item for item in payload["edges"] if item["id"] == "e1")
    assert "attrs" not in edge
    assert edge["source"] == "n1"
    assert edge["target"] == "n2"
    assert edge["key"] == "e1"
    assert edge["type"] == "Generalization"
    assert edge["data"]["general"] == "n2"
    assert edge["data"]["specific"] == "n1"
    assert "general" not in edge
    assert "specific" not in edge


def test_deserialize_graph_from_runtime_supports_flat_and_legacy_attrs_shapes():
    legacy_payload = {
        "directed": True,
        "multigraph": True,
        "graphAttrs": {},
        "nodes": [{"id": "n1", "attrs": {"id": "n1", "type": "Class", "name": "Legacy", "data": {}}}],
        "edges": [
            {
                "source": "n1",
                "target": "n1",
                "key": "e-legacy",
                "attrs": {"id": "e-legacy", "type": "Association", "data": {"k": "v"}},
            }
        ],
    }
    flat_payload = {
        "directed": True,
        "multigraph": True,
        "graphAttrs": {},
        "nodes": [{"id": "n2", "type": "Class", "name": "Flat", "data": {}}],
        "edges": [{"source": "n2", "target": "n2", "key": "e-flat", "id": "e-flat", "type": "Association", "data": {}}],
    }

    legacy_graph = api_server.deserialize_graph_from_runtime(legacy_payload)
    flat_graph = api_server.deserialize_graph_from_runtime(flat_payload)

    assert legacy_graph.nodes["n1"]["type"] == "Class"
    assert legacy_graph.nodes["n1"]["name"] == "Legacy"
    assert legacy_graph.edges["n1", "n1", "e-legacy"]["id"] == "e-legacy"
    assert legacy_graph.edges["n1", "n1", "e-legacy"]["type"] == "Association"

    assert flat_graph.nodes["n2"]["type"] == "Class"
    assert flat_graph.nodes["n2"]["name"] == "Flat"
    assert flat_graph.edges["n2", "n2", "e-flat"]["id"] == "e-flat"
    assert flat_graph.edges["n2", "n2", "e-flat"]["type"] == "Association"


def test_normalize_graph_attributes_keeps_data_nested_without_top_level_duplicates():
    nx = api_server.require_networkx()
    graph = nx.MultiDiGraph()
    graph.add_node("n1", type="Class", name="B", data={"attributes": [{"id": "att1"}]})
    graph.add_node("n2", type="Class", name="A", data={})
    graph.add_edge("n1", "n2", id="e1", type="Generalization", data={"general": "n2", "specific": "n1"})

    normalize_graph_attributes(graph)

    node_attrs = graph.nodes["n1"]
    edge_attrs = graph.edges["n1", "n2", 0]

    assert "attributes" not in node_attrs
    assert node_attrs["data"]["attributes"][0]["id"] == "att1"
    assert "general" not in edge_attrs
    assert "specific" not in edge_attrs
    assert edge_attrs["data"]["general"] == "n2"
    assert edge_attrs["data"]["specific"] == "n1"


def test_upload_start_rejects_options_not_supported_by_parser_descriptor():
    DATASETS.clear()
    client = create_app().test_client()

    response = client.post(
        "/api/uploads/start",
        json={
            "language": "archimate",
            "format": "json",
            "includeAttributes": False,
        },
    )

    assert response.status_code == 400
    assert "Unsupported option" in response.get_json()["error"]


def test_pids_on_port_uses_lsof(monkeypatch):
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="123\n456\n", stderr="")

    monkeypatch.setattr(api_server.subprocess, "run", fake_run)

    assert api_server.pids_on_port(8765) == [123, 456]
    assert calls == [["lsof", "-ti", ":8765"]]


def test_kill_processes_on_port_skips_current_pid(monkeypatch):
    killed = []
    monkeypatch.setattr(api_server, "pids_on_port", lambda port: [111, os.getpid(), 222])
    monkeypatch.setattr(api_server.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    result = api_server.kill_processes_on_port(8765)

    assert result == [111, 222]
    assert [pid for pid, _ in killed] == [111, 222]


def test_selected_duplicate_techniques_accepts_ml_aliases():
    selected = api_server.selected_duplicate_techniques(
        {"techniques": ["Graph embeddings", "BERT semantic", "node2vec", "bert_similarity"]}
    )

    assert selected == ["graph_embedding", "bert_semantic"]


def test_selected_duplicate_techniques_accepts_cached_payload_shapes():
    assert api_server.selected_duplicate_techniques({"techniques": "graph_embeddings, BERT semantic"}) == [
        "graph_embedding",
        "bert_semantic",
    ]
    assert api_server.selected_duplicate_techniques({"selectedTechniques": {"graph_embedding": True, "hash_names": False}}) == [
        "graph_embedding"
    ]
    assert api_server.selected_duplicate_techniques({"selected": [{"id": "bert_semantic"}]}) == ["bert_semantic"]


def test_flask_upload_dataset_route():
    DATASETS.clear()
    client = create_app().test_client()
    _, _, job = upload_and_parse_via_job(
        client,
        language="archimate",
        files=(
            BytesIO(
                b"""{
                    "archimateId": "m1",
                    "name": "Example",
                    "elements": [
                        {"id": "a", "name": "App", "type": "ApplicationComponent"},
                        {"id": "b", "name": "DB", "type": "DataObject"}
                    ],
                    "relationships": [
                        {"id": "r1", "sourceId": "a", "targetId": "b", "type": "Access"}
                    ]
                }"""
            ),
            "model.json",
        ),
    )

    assert job["status"] == "complete"
    assert job["datasetId"] in DATASETS
    assert job["statistics"]["summary"]["models"] == 1


def test_flask_upload_dataset_route_rejects_jsonl():
    DATASETS.clear()
    client = create_app().test_client()
    content = b"""
{"archimateId":"m1","name":"One","elements":[{"id":"a","name":"App","type":"ApplicationComponent"}],"relationships":[]}
{"archimateId":"m2","name":"Two","elements":[{"id":"b","name":"DB","type":"DataObject"}],"relationships":[]}
""".strip()

    _, _, job = upload_and_parse_via_job(
        client,
        language="archimate",
        files=(BytesIO(content), "models.jsonl"),
    )

    assert job["status"] == "error"
    assert job["uploadSummary"]["records"] == 0
    assert job["uploadSummary"]["ignoredFiles"] == ["models.jsonl"]
    assert "SKIPPED_UNSUPPORTED_EXTENSION" in job["uploadSummary"]["warningsByType"]


def test_flask_xmi_upload_reports_empty_and_invalid_files_separately():
    DATASETS.clear()
    client = create_app().test_client()

    _, _, job = upload_and_parse_via_job(
        client,
        language="uml",
        data_format="xmi",
        files=[
            (BytesIO(b""), "models/empty.xmi"),
            (BytesIO(b"<uml:Model>"), "models/invalid.xmi"),
        ],
    )

    assert job["status"] == "error"
    assert job["uploadSummary"]["records"] == 0
    assert job["uploadSummary"]["errors"] == 2
    assert job["uploadSummary"]["emptyFiles"] == ["models/empty.xmi"]
    assert job["uploadSummary"]["invalidFiles"] == ["models/invalid.xmi"]
    assert job["uploadSummary"]["warningsByType"] == {"EMPTY_FILE": 1, "PARSE_ERROR": 1}


def test_directory_upload_does_not_infer_archimate_and_ignores_macos_metadata():
    DATASETS.clear()
    client = create_app().test_client()
    archimate = b"""<?xml version="1.0" encoding="UTF-8"?>
<archimate:model xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xmlns:archimate="http://www.archimatetool.com/archimate" name="Example" id="m1" version="4.0.0">
 <folder name="Application" id="f1" type="application">
  <element xsi:type="archimate:ApplicationComponent" name="App" id="a1"/>
 </folder>
</archimate:model>"""

    _, _, job = upload_and_parse_via_job(
        client,
        language="uml",
        data_format="xmi",
        files=[
            (BytesIO(archimate), "eamodelset/model.archimate"),
            (BytesIO(b"AppleDouble"), "__MACOSX/eamodelset/._model.archimate"),
        ],
    )

    assert job["status"] == "error"
    assert job["uploadSummary"]["format"] == "xmi"
    assert job["uploadSummary"]["language"] == "uml"
    assert job["uploadSummary"]["records"] == 0
    assert job["uploadSummary"]["errors"] == 0
    assert job["uploadSummary"]["ignoredFiles"] == [
        "__MACOSX/eamodelset/._model.archimate",
        "eamodelset/model.archimate",
    ]


def test_flask_upload_dataset_route_accepts_signavio_bpmn_format():
    DATASETS.clear()
    client = create_app().test_client()
    signavio = {
        "resourceId": "diagram-1",
        "stencil": {"id": "BPMNDiagram"},
        "properties": {"name": "Order flow"},
        "childShapes": [
            {
                "resourceId": "task-1",
                "stencil": {"id": "Task"},
                "properties": {"name": "Create order"},
                "outgoing": [{"resourceId": "flow-1"}],
                "childShapes": [],
            },
            {
                "resourceId": "task-2",
                "stencil": {"id": "Task"},
                "properties": {"name": "Send invoice"},
                "outgoing": [],
                "childShapes": [],
            },
            {
                "resourceId": "flow-1",
                "stencil": {"id": "SequenceFlow"},
                "target": {"resourceId": "task-2"},
                "outgoing": [{"resourceId": "task-2"}],
                "childShapes": [],
            },
        ],
    }

    _, _, job = upload_and_parse_via_job(
        client,
        language="bpmn",
        data_format="signavio",
        files=(BytesIO(json.dumps(signavio).encode("utf-8")), "model.json"),
    )

    assert job["status"] == "complete"
    assert job["datasetId"] in DATASETS
    assert job["statistics"]["summary"]["models"] == 1
    assert job["uploadSummary"]["format"] == "signavio"


def test_flask_signavio_upload_reports_parse_error_for_non_json_files():
    DATASETS.clear()
    client = create_app().test_client()
    signavio = {
        "resourceId": "diagram-1",
        "stencil": {"id": "BPMNDiagram"},
        "properties": {"name": "Order flow"},
        "childShapes": [],
    }

    _, _, job = upload_and_parse_via_job(
        client,
        language="bpmn",
        data_format="signavio",
        files=[
            (BytesIO(json.dumps(signavio).encode("utf-8")), "valid/model.json"),
            (BytesIO(b"not signavio"), "ignored/readme.txt"),
        ],
    )
    assert job["status"] == "complete"
    assert job["statistics"]["summary"]["models"] == 1
    assert job["uploadSummary"]["errors"] == 0
    assert job["uploadSummary"]["warnings"] >= 1
    assert "SKIPPED_UNSUPPORTED_EXTENSION" in job["uploadSummary"]["warningsByType"]
    assert job["uploadSummary"]["warningsList"]
    first_warning = job["uploadSummary"]["warningsList"][0]
    assert first_warning["type"] == "SKIPPED_UNSUPPORTED_EXTENSION"
    assert first_warning["path"] == "ignored/readme.txt"
    assert "message" in first_warning
    assert job["uploadSummary"]["warningFiles"][0]["hasDetails"] is True
    assert "modelId" in job["uploadSummary"]["warningFiles"][0]


def test_flask_upload_dataset_jsonl_is_not_supported():
    DATASETS.clear()
    client = create_app().test_client()
    lines = "\n".join(
        json.dumps(
            {
                "ids": f"model-{index}",
                "nodes": [{"id": f"n{index}", "name": f"Class {index}", "type": "Class"}],
                "edges": [],
            }
        )
        for index in range(12)
    )

    _, _, job = upload_and_parse_via_job(
        client,
        language="uml",
        files=(BytesIO(lines.encode("utf-8")), "models.jsonl"),
    )

    assert job["status"] == "error"
    assert job["uploadSummary"]["records"] == 0
    assert "SKIPPED_UNSUPPORTED_EXTENSION" in job["uploadSummary"]["warningsByType"]


def test_flask_upload_dataset_route_rejects_jsonl_array_lines():
    DATASETS.clear()
    client = create_app().test_client()
    content = b"""
[{"archimateId":"m1","name":"One","elements":[{"id":"a","name":"App","type":"ApplicationComponent"}],"relationships":[]},{"archimateId":"m2","name":"Two","elements":[{"id":"b","name":"DB","type":"DataObject"}],"relationships":[]}]
""".strip()

    _, _, job = upload_and_parse_via_job(
        client,
        language="archimate",
        files=(BytesIO(content), "models.jsonl"),
    )

    assert job["status"] == "error"
    assert job["uploadSummary"]["records"] == 0


def test_merge_model_diagnostics_does_not_add_parse_warning_when_typed_warnings_exist():
    summary = api_server.empty_upload_summary()
    diagnostics = api_server.ModelDiagnostics(
        parse_status="warning",
        warning_count=1,
        warnings_by_type={"INVALID_TYPE_REFERENCE": 1},
        warning_messages_by_type={
            "INVALID_TYPE_REFERENCE": [
                "Association end end-1 has no resolvable type reference.",
            ],
        },
        source_path="modelset-uml/f51fd8af-292f-44c7-8a63-b9fc80cb4ab7.xmi",
    )

    api_server.merge_model_diagnostics(summary, "f51fd8af-292f-44c7-8a63-b9fc80cb4ab7", diagnostics)

    assert summary["warnings"] == 1
    assert summary["warningsByType"] == {"INVALID_TYPE_REFERENCE": 1}
    assert len(summary["warningFiles"]) == 1
    warning_file = summary["warningFiles"][0]
    assert warning_file["warnings"] == 1
    assert warning_file["types"] == {"INVALID_TYPE_REFERENCE": 1}


def test_flask_upload_dataset_route_rejects_zero_parsed_models():
    DATASETS.clear()
    client = create_app().test_client()

    _, _, job = upload_and_parse_via_job(
        client,
        language="uml",
        files=(BytesIO(b'["not a model"]'), "uml.jsonl"),
    )

    assert job["status"] == "error"
    assert "0 models" in job["error"]


def test_flask_upload_dataset_route_reports_parsed_models():
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    clear_runtime()
    client = create_app().test_client()
    models = [
        {
            "archimateId": f"m{index}",
            "name": f"Model {index}",
            "elements": [{"id": "a", "name": f"App {index}", "type": "ApplicationComponent"}],
            "relationships": [],
        }
        for index in range(12)
    ]

    files = [
        (BytesIO(json.dumps(model).encode("utf-8")), f"models/model-{index}.json")
        for index, model in enumerate(models)
    ]

    _, _, job = upload_and_parse_via_job(client, language="archimate", files=files)

    assert job["status"] == "complete"
    assert job["uploadSummary"]["records"] == 12
    assert job["statistics"]["summary"]["models"] == 12
    assert len(DATASETS[job["datasetId"]]) == 12
    models_page = client.get(f"/api/datasets/{job['datasetId']}/models?page=1&pageSize=50").get_json()
    assert models_page["total"] == 12
    assert len(models_page["models"]) == 12
    assert "parsedModels" not in job["uploadSummary"]


def test_flask_model_inspect_route_returns_nodes_and_edges():
    DATASETS.clear()
    UPLOAD_SESSIONS.clear()
    UPLOAD_PARSE_JOBS.clear()
    clear_runtime()
    client = create_app().test_client()
    payload = {
        "archimateId": "inspect-model",
        "name": "Inspect me",
        "elements": [
            {"id": "a", "name": "App", "type": "ApplicationComponent"},
            {"id": "b", "name": "DB", "type": "DataObject"},
        ],
        "relationships": [
            {"id": "r1", "sourceId": "a", "targetId": "b", "type": "Access"},
        ],
    }

    _, _, job = upload_and_parse_via_job(
        client,
        language="archimate",
        files=(BytesIO(json.dumps(payload).encode("utf-8")), "model.json"),
    )
    assert job["status"] == "complete"
    dataset_id = job["datasetId"]

    response = client.get(f"/api/datasets/{dataset_id}/models/inspect-model/inspect?includeAttrs=false")
    data = response.get_json()

    assert response.status_code == 200
    assert data["model"]["id"] == "inspect-model"
    assert data["model"]["nodeCount"] == 2
    assert data["model"]["edgeCount"] == 1
    assert len(data["nodes"]) == 2
    assert "attrs" not in data["nodes"][0]

    models_page = client.get(f"/api/datasets/{dataset_id}/models?page=1&pageSize=10").get_json()
    assert models_page["total"] == 1
    assert models_page["models"][0]["nodeCount"] == 2
    assert models_page["models"][0]["edgeCount"] == 1


def test_flask_duplicates_returns_model_counts_for_pie_charts():
    DATASETS.clear()
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [{"id": "a", "name": "Order", "type": "BusinessObject"}],
            "relationships": [],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [{"id": "b", "name": "Order", "type": "BusinessObject"}],
            "relationships": [],
        },
        model_id="second",
    )
    third = parser.parse(
        {
            "elements": [{"id": "c", "name": "Invoice", "type": "BusinessObject"}],
            "relationships": [],
        },
        model_id="third",
    )
    DATASETS["dataset"] = Dataset([first, second, third], "archimate")
    client = create_app().test_client()

    job = run_duplicate_job(
        client,
        {
            "datasetId": "dataset",
            "techniques": ["hash_names"],
            "mandatoryTechniques": [],
            "minVotes": 1,
            "thresholds": {},
        },
    )

    assert job["status"] == "complete"
    data = job["result"]
    assert data["modelCounts"]["hash"] | {"elapsedMs": 0} == {
        "duplicateModels": 2,
        "uniqueModels": 1,
        "totalModels": 3,
        "pairCount": 1,
        "elapsedMs": 0,
    }
    assert data["modelCounts"]["hash"]["elapsedMs"] >= 0
    assert data["elapsedMs"] >= 0


def test_flask_duplicate_pairs_counts_candidate_pairs_not_only_vote_approved_pairs():
    DATASETS.clear()
    parser = ArchimateJsonParser()
    first = parser.parse(
        {"elements": [{"id": "a", "name": "Order", "type": "BusinessObject"}], "relationships": []},
        model_id="first",
    )
    second = parser.parse(
        {"elements": [{"id": "b", "name": "Order", "type": "BusinessObject"}], "relationships": []},
        model_id="second",
    )
    DATASETS["dataset"] = Dataset([first, second], "archimate")
    client = create_app().test_client()

    job = run_duplicate_job(
        client,
        {
            "datasetId": "dataset",
            "techniques": ["hash_names"],
            "mandatoryTechniques": [],
            "minVotes": 2,
            "thresholds": {},
        },
    )
    assert job["status"] == "complete"
    data = job["result"]

    assert data["duplicatePairs"] == 1
    assert data["votedDuplicatePairs"] == 0
    assert data["candidatePairs"] == 1
    assert data["approvedPairs"] == 0
    assert data["totalDecisions"] == 1
    assert data["returnedDecisions"] == 1
    assert data["truncated"] is False
    assert data["decisions"][0]["isDuplicate"] is False


def test_flask_duplicate_detection_job_reports_progress_and_result():
    DATASETS.clear()
    parser = ArchimateJsonParser()
    first = parser.parse(
        {"elements": [{"id": "a", "name": "Order", "type": "BusinessObject"}], "relationships": []},
        model_id="first",
    )
    second = parser.parse(
        {"elements": [{"id": "b", "name": "Order", "type": "BusinessObject"}], "relationships": []},
        model_id="second",
    )
    DATASETS["dataset"] = Dataset([first, second], "archimate")
    client = create_app().test_client()

    start = client.post(
        "/api/duplicates/jobs",
        json={
            "datasetId": "dataset",
            "techniques": ["hash_names"],
            "mandatoryTechniques": [],
            "minVotes": 1,
            "thresholds": {},
        },
    )
    job_id = start.get_json()["jobId"]

    data = {}
    for _ in range(20):
        response = client.get(f"/api/duplicates/jobs/{job_id}")
        data = response.get_json()
        if data["status"] == "complete":
            break
        time.sleep(0.05)

    assert data["status"] == "complete"
    assert data["progress"] == 100
    assert data["completedTechniques"] == ["hash"]
    assert data["result"]["duplicatePairs"] == 1
    assert data["elapsedMs"] >= 0
    assert data["result"]["elapsedMs"] >= 0
    assert data["result"]["modelCounts"]["hash"]["elapsedMs"] >= 0
