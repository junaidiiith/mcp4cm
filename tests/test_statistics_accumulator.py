from io import BytesIO
import json
import shutil
import time

import networkx as nx

from mcp4cm import api_server
from mcp4cm.api_server import DATASETS, UPLOAD_PARSE_JOBS, UPLOAD_SESSIONS, create_app
from mcp4cm.core import ModelRecord
from mcp4cm.statistics import CorpusStatisticsAccumulator


def clear_runtime():
    shutil.rmtree(api_server.RUNTIME_DIR, ignore_errors=True)


def test_corpus_statistics_accumulator_builds_without_graph_reload():
    accumulator = CorpusStatisticsAccumulator()
    for index in range(1200):
        accumulator.node_counts.append(index)
        accumulator.edge_counts.append(index + 1)
        accumulator.name_count_values.append(3)
        accumulator.name_slot_counts.append(4)
        accumulator.languages["uml"] += 1
        accumulator.scatter_rows.append(
            {
                "id": f"m{index}",
                "namedElements": 2,
                "uniqueNames": 2,
                "tokens": 3,
                "uniqueTokens": 3,
                "nameSlots": 4,
                "missingNames": 0,
                "missingNameRatio": 0.0,
            }
        )

    payload = accumulator.build_payload()

    assert payload["summary"]["models"] == 1200
    assert payload["visualizations"]["topicModel"]["available"] is False
    assert len(payload["visualizations"]["modelVocabularyScatter"]) == 1200


def test_corpus_statistics_accumulator_builds_quality_visualizations():
    graph = nx.DiGraph()
    graph.add_node("semantic", type="Task", name="Approve invoice")
    graph.add_node("missing", type="Task", name="")
    graph.add_node("type_like", type="Class", name="Class1")
    graph.add_node("placeholder", type="Package", name="todo")
    graph.add_node("repeated_a", type="Task", name="Review")
    graph.add_node("repeated_b", type="Task", name="Review")

    accumulator = CorpusStatisticsAccumulator()
    accumulator.add(ModelRecord(model_id="m1", language="bpmn", graph=graph))
    visualizations = accumulator.build_payload()["visualizations"]

    classification_counts = {item["key"]: item["count"] for item in visualizations["nameClassificationOverview"]}
    assert classification_counts == {"semantic": 3, "missing": 1, "placeholder": 1, "type_like": 1}
    assert visualizations["missingNameRatioSummary"]["above30"] == 0
    assert visualizations["semanticNameCountHistogram"][1]["count"] == 1
    assert visualizations["elementTypeQualityMatrix"][0]["total"] == 4
    task_row = next(row for row in visualizations["elementTypeQualityMatrix"] if row["type"] == "task")
    assert task_row["total"] == 4
    assert task_row["missing"] == 1
    assert visualizations["modelQualityWatchlists"]["fewSemanticNames"][0]["id"] == "m1"
    assert visualizations["modelQualityWatchlists"]["highMissingRatio"][0]["id"] == "m1"
    assert visualizations["modelQualityWatchlists"]["highNameDominance"][0]["dominantName"] == "review"


def test_upload_parse_uses_accumulator_for_statistics():
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
        for index in range(20)
    ]
    files = [
        (BytesIO(json.dumps(model).encode("utf-8")), f"models/model-{index}.json")
        for index, model in enumerate(models)
    ]

    started = client.post("/api/uploads/start", json={"language": "archimate", "format": "json"}).get_json()
    upload_id = started["uploadId"]
    client.post(
        f"/api/uploads/{upload_id}/chunks",
        data={"files": files},
        content_type="multipart/form-data",
    )
    job = client.post(f"/api/uploads/{upload_id}/parse", json={}).get_json()
    job_id = job["jobId"]

    finished = {}
    for _ in range(100):
        finished = client.get(f"/api/uploads/{upload_id}/jobs/{job_id}").get_json()
        if finished["status"] in {"complete", "error"}:
            break
        time.sleep(0.05)

    assert finished["status"] == "complete"
    assert finished["statistics"]["summary"]["models"] == 20
    assert finished["statistics"]["visualizations"]["languageDistribution"][0]["count"] == 20
    assert (api_server.RUNTIME_DIR / finished["datasetId"] / "statistics.json").exists()
