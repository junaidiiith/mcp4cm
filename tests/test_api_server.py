from io import BytesIO
import os
import time
import json
from types import SimpleNamespace

from mcp4cm import api_server
from mcp4cm.api_server import DATASETS, PREPROCESSED_UPLOADS, create_app
from mcp4cm.core import Dataset
from mcp4cm.parsers.archimate import ArchimateParser


def test_flask_health_route():
    client = create_app().test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


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
    payload = {
        "language": "archimate",
        "files": [
            {
                "name": "model.json",
                "content": """{
                    "archimateId": "m1",
                    "name": "Example",
                    "elements": [
                        {"id": "a", "name": "App", "type": "ApplicationComponent"},
                        {"id": "b", "name": "DB", "type": "DataObject"}
                    ],
                    "relationships": [
                        {"id": "r1", "sourceId": "a", "targetId": "b", "type": "Access"}
                    ]
                }""",
            }
        ],
    }

    response = client.post("/api/datasets", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert data["datasetId"] in DATASETS
    assert data["statistics"]["summary"]["models"] == 1


def test_flask_upload_dataset_route_accepts_multipart_jsonl():
    DATASETS.clear()
    client = create_app().test_client()
    content = b"""
{"archimateId":"m1","name":"One","elements":[{"id":"a","name":"App","type":"ApplicationComponent"}],"relationships":[]}
{"archimateId":"m2","name":"Two","elements":[{"id":"b","name":"DB","type":"DataObject"}],"relationships":[]}
""".strip()

    response = client.post(
        "/api/datasets",
        data={
            "language": "archimate",
            "files": (BytesIO(content), "models.jsonl"),
        },
        content_type="multipart/form-data",
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["datasetId"] in DATASETS
    assert data["statistics"]["summary"]["models"] == 2
    assert data["uploadSummary"]["records"] == 2


def test_flask_preprocess_then_processes_selected_model_limit():
    DATASETS.clear()
    PREPROCESSED_UPLOADS.clear()
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

    preprocess = client.post(
        "/api/datasets/preprocess",
        data={"language": "uml", "files": (BytesIO(lines.encode("utf-8")), "models.jsonl")},
        content_type="multipart/form-data",
    )
    preprocess_data = preprocess.get_json()

    assert preprocess.status_code == 200
    assert preprocess_data["uploadSummary"]["totalRecords"] == 12
    assert preprocess_data["uploadSummary"]["usedRecords"] == 0

    process = client.post(
        "/api/datasets",
        data={
            "language": "uml",
            "preprocessId": preprocess_data["preprocessId"],
            "modelLimit": "10",
        },
        content_type="multipart/form-data",
    )
    process_data = process.get_json()

    assert process.status_code == 200
    assert process_data["statistics"]["summary"]["models"] == 10
    assert process_data["uploadSummary"]["totalRecords"] == 12
    assert process_data["uploadSummary"]["usedRecords"] == 10


def test_flask_upload_dataset_route_flattens_jsonl_array_lines():
    DATASETS.clear()
    client = create_app().test_client()
    content = b"""
[{"archimateId":"m1","name":"One","elements":[{"id":"a","name":"App","type":"ApplicationComponent"}],"relationships":[]},{"archimateId":"m2","name":"Two","elements":[{"id":"b","name":"DB","type":"DataObject"}],"relationships":[]}]
""".strip()

    response = client.post(
        "/api/datasets",
        data={
            "language": "archimate",
            "files": (BytesIO(content), "models.jsonl"),
        },
        content_type="multipart/form-data",
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["statistics"]["summary"]["models"] == 2


def test_flask_upload_dataset_route_rejects_zero_parsed_models():
    DATASETS.clear()
    client = create_app().test_client()

    response = client.post(
        "/api/datasets",
        data={
            "language": "uml",
            "files": (BytesIO(b'["not a model"]'), "uml.jsonl"),
        },
        content_type="multipart/form-data",
    )
    data = response.get_json()

    assert response.status_code == 400
    assert "parsed 0 models" in data["error"]


def test_flask_upload_dataset_route_applies_model_limit():
    DATASETS.clear()
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

    response = client.post(
        "/api/datasets",
        json={
            "language": "archimate",
            "modelLimit": 9,
            "files": [{"name": "models.json", "content": json.dumps(models)}],
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["uploadSummary"]["totalRecords"] == 12
    assert data["uploadSummary"]["modelLimit"] == 10
    assert data["uploadSummary"]["usedRecords"] == 10
    assert data["statistics"]["summary"]["models"] == 10
    assert len(DATASETS[data["datasetId"]]) == 10


def test_flask_duplicates_returns_model_counts_for_pie_charts():
    DATASETS.clear()
    parser = ArchimateParser()
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

    response = client.post(
        "/api/duplicates",
        json={
            "datasetId": "dataset",
            "techniques": ["hash_names"],
            "mandatoryTechniques": [],
            "minVotes": 1,
            "thresholds": {},
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["modelCounts"]["hash_names"] | {"elapsedMs": 0} == {
        "duplicateModels": 2,
        "uniqueModels": 1,
        "totalModels": 3,
        "pairCount": 1,
        "elapsedMs": 0,
    }
    assert data["modelCounts"]["hash_names"]["elapsedMs"] >= 0
    assert data["elapsedMs"] >= 0


def test_flask_duplicate_pairs_counts_candidate_pairs_not_only_vote_approved_pairs():
    DATASETS.clear()
    parser = ArchimateParser()
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

    response = client.post(
        "/api/duplicates",
        json={
            "datasetId": "dataset",
            "techniques": ["hash_names"],
            "mandatoryTechniques": [],
            "minVotes": 2,
            "thresholds": {},
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["duplicatePairs"] == 1
    assert data["votedDuplicatePairs"] == 0
    assert data["decisions"][0]["isDuplicate"] is False


def test_flask_duplicate_detection_job_reports_progress_and_result():
    DATASETS.clear()
    parser = ArchimateParser()
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
    assert data["completedTechniques"] == ["hash_names"]
    assert data["result"]["duplicatePairs"] == 1
    assert data["elapsedMs"] >= 0
    assert data["result"]["elapsedMs"] >= 0
    assert data["result"]["modelCounts"]["hash_names"]["elapsedMs"] >= 0
