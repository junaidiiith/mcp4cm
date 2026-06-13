import json
import shutil
import time
from io import BytesIO

import networkx as nx

from mcp4cm.api import create_app
from mcp4cm.api.state import DATASETS, LABEL_PIPELINE_CACHE, UPLOAD_PARSE_JOBS, UPLOAD_SESSIONS
from mcp4cm.core import ModelRecord
from mcp4cm.dummy import derive_nodes
from mcp4cm.runtime_store import RUNTIME_DIR
from mcp4cm.statistics import CorpusStatisticsAccumulator, typed_name_entries


def clear_runtime():
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    LABEL_PIPELINE_CACHE.clear()


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
    graph.add_node("type_derived", type="Class", name="Class1")
    graph.add_node("placeholder", type="Package", name="todo")
    graph.add_node("actor_placeholder", type="Actor", name="Actor")
    graph.add_node("actor_semantic", type="Task", name="Actor")
    graph.add_node("repeated_a", type="Task", name="Review")
    graph.add_node("repeated_b", type="Task", name="Review")
    graph.add_edge("semantic", "repeated_a", type="ControlFlow")

    accumulator = CorpusStatisticsAccumulator()
    accumulator.add(ModelRecord(model_id="m1", language="bpmn", graph=graph))
    payload = accumulator.build_payload()
    visualizations = payload["visualizations"]

    classification_counts = {item["key"]: item["count"] for item in visualizations["nameClassificationOverview"]}
    assert classification_counts == {"semantic": 4, "missing": 1, "placeholder": 3}
    assert payload["topTypes"][0] == {"label": "Task", "count": 5}
    assert {"label": "ControlFlow", "count": 1} in payload["topTypes"]
    assert "control flow" not in {item["label"] for item in payload["topNames"]}
    assert visualizations["missingNameRatioSummary"]["above30"] == 0
    assert visualizations["semanticNameCountHistogram"][1]["count"] == 1
    assert visualizations["elementTypeQualityMatrix"][0]["total"] == 5
    task_row = next(row for row in visualizations["elementTypeQualityMatrix"] if row["type"] == "task")
    assert task_row["total"] == 5
    assert task_row["missing"] == 1
    vocabulary_summary = visualizations["vocabularySummary"]
    assert vocabulary_summary["uniqueNames"] == 5
    assert vocabulary_summary["totalOccurrences"] == 7
    assert vocabulary_summary["semanticNames"] == 3
    assert vocabulary_summary["placeholderNames"] == 3
    assert vocabulary_summary["singletonNames"] == 4
    review_row = next(row for row in visualizations["vocabularyRanking"] if row["name"] == "review")
    assert review_row["occurrences"] == 2
    assert review_row["documentFrequency"] == 1
    assert review_row["occurrencesPerUsedModel"] == 2
    assert review_row["classification"] == "semantic"
    task_vocabulary = next(row for row in visualizations["typeVocabularyTable"] if row["type"] == "task")
    assert task_vocabulary["namedOccurrences"] == 4
    assert task_vocabulary["names"][0]["name"] == "review"
    assert task_vocabulary["names"][0]["occurrences"] == 2
    assert task_vocabulary["names"][0]["share"] == 0.5
    actor_type_vocabulary = next(row for row in visualizations["typeVocabularyTable"] if row["type"] == "actor")
    actor_type_name = next(name for name in actor_type_vocabulary["names"] if name["name"] == "actor")
    assert actor_type_name["classification"] == "placeholder"
    task_actor_name = next(name for name in task_vocabulary["names"] if name["name"] == "actor")
    assert task_actor_name["classification"] == "semantic"
    actor_row = next(row for row in visualizations["vocabularyRanking"] if row["name"] == "actor")
    assert actor_row["classification"] == "mixed"
    class_row = next(row for row in visualizations["vocabularyRanking"] if row["name"] == "class1")
    assert class_row["classification"] == "placeholder"
    assert visualizations["nameReuseDistribution"][0] == {"label": "1", "count": 4}
    pipeline_row = next(row for row in visualizations["labelPipelineRows"] if row["rawName"] == "Approve invoice")
    assert pipeline_row["normalizedName"] == "approve invoice"
    assert pipeline_row["nameTokens"] == ["approve", "invoice"]
    assert pipeline_row["rawType"] == "Task"
    assert pipeline_row["normalizedType"] == "task"
    assert pipeline_row["typeTokens"] == ["task"]
    assert pipeline_row["classification"] == "semantic"
    assert visualizations["modelQualityWatchlists"]["fewSemanticNames"][0]["id"] == "m1"
    assert visualizations["modelQualityWatchlists"]["highMissingRatio"][0]["id"] == "m1"
    placeholder_watchlist_row = visualizations["modelQualityWatchlists"]["highPlaceholderRatio"][0]
    assert placeholder_watchlist_row["id"] == "m1"
    assert placeholder_watchlist_row["placeholderNames"] == 3
    assert placeholder_watchlist_row["placeholderRatio"] == 0.4286
    assert visualizations["modelQualityWatchlists"]["highNameDominance"][0]["dominantName"] == "review"
    assert len(visualizations["typeVocabularyTable"]) == len(visualizations["elementTypeQualityMatrix"])
    assert {row["type"] for row in visualizations["typeVocabularyTable"]} == {
        row["type"] for row in visualizations["elementTypeQualityMatrix"]
    }


def test_type_vocabulary_table_includes_types_without_named_vocabulary():
    graph = nx.DiGraph()
    graph.add_node("named", type="Task", name="Approve invoice")
    graph.add_node("missing_only_a", type="Event", name="")
    graph.add_node("missing_only_b", type="Event", name="")

    accumulator = CorpusStatisticsAccumulator()
    accumulator.add(ModelRecord(model_id="m1", language="bpmn", graph=graph))
    visualizations = accumulator.build_payload()["visualizations"]

    event_row = next(row for row in visualizations["typeVocabularyTable"] if row["type"] == "event")
    assert event_row["totalOccurrences"] == 2
    assert event_row["namedOccurrences"] == 0
    assert event_row["names"] == []


def test_statistics_and_dummy_use_shared_name_classification():
    graph = nx.DiGraph()
    graph.add_node("semantic", type="Task", name="ApproveInvoice")
    graph.add_node("missing", type="Task", name="")
    graph.add_node("type_derived", type="Class", name="Class1")
    graph.add_node("placeholder", type="Package", name="todo")
    record = ModelRecord(model_id="m1", language="uml", graph=graph)

    statistics_entries = {entry["name"]: entry["classification"] for entry in typed_name_entries(record)}
    dummy_nodes = {node.normalized_name: node.classification for node in derive_nodes(record)}

    assert statistics_entries == dummy_nodes
    assert statistics_entries["approve invoice"] == "semantic"
    assert statistics_entries["class1"] == "placeholder"
    assert statistics_entries["todo"] == "placeholder"
    assert statistics_entries[""] == "missing"


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
        (BytesIO(json.dumps(model).encode("utf-8")), f"models/model-{index}.json") for index, model in enumerate(models)
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
    assert finished["statistics"]["summary"]["languages"]["archimate"] == 20
    assert (RUNTIME_DIR / finished["datasetId"] / "statistics.json").exists()

    page = client.get(
        f"/api/datasets/{finished['datasetId']}/visualizations/label-pipeline?page=1&pageSize=5"
    ).get_json()
    assert page["page"] == 1
    assert page["pageSize"] == 5
    assert page["total"] >= 20
    assert len(page["rows"]) == 5

    filtered = client.get(
        f"/api/datasets/{finished['datasetId']}/visualizations/label-pipeline"
        "?query=App%2019&classification=semantic&page=1&pageSize=10"
    ).get_json()
    assert filtered["total"] == 1
    assert filtered["rows"][0]["rawName"] == "App 19"
    assert filtered["rows"][0]["normalizedName"] == "app 19"
