from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DUPLICATE_DETECTION_PATH = REPOSITORY_ROOT / "evaluation" / "duplicate_detection.py"
SPEC = importlib.util.spec_from_file_location("duplicate_detection", DUPLICATE_DETECTION_PATH)
assert SPEC is not None and SPEC.loader is not None
duplicate_detection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = duplicate_detection
SPEC.loader.exec_module(duplicate_detection)


def test_defaults_select_all_targets_and_runtime_techniques() -> None:
    args = duplicate_detection.parse_args([])

    assert duplicate_detection.resolve_targets(args.only) == list(duplicate_detection.DEFAULT_TARGETS)
    technique_ids = [technique.id for technique in duplicate_detection.DUPLICATE_TECHNIQUES]
    assert technique_ids == ["hash", "tfidf", "graph_similarity", "bert_semantic", "gnn"]
    assert duplicate_detection.IGNORED_TECHNIQUES == ("graph_embedding", "graph_isomorphism")


def test_resolves_target_groups_without_duplicates() -> None:
    args = duplicate_detection.parse_args(["--only", "modelset", "--only", "modelset-uml-xmi"])

    assert duplicate_detection.resolve_targets(args.only) == ["modelset-uml-xmi", "modelset-ecore-xmi"]


def test_evaluation_dir_argument_is_preserved(tmp_path: Path) -> None:
    args = duplicate_detection.parse_args(["--evaluation-dir", str(tmp_path)])

    assert args.evaluation_dir == tmp_path


def test_evaluate_dataset_writes_runtime_artifacts(monkeypatch, tmp_path: Path) -> None:
    runtime_dir = tmp_path / "sap-sam-bpmn-runtime"
    runtime_dir.mkdir()

    monkeypatch.setattr(
        duplicate_detection,
        "load_runtime_index",
        lambda _runtime_dir: {"datasetType": "fake", "models": []},
    )
    monkeypatch.setattr(duplicate_detection, "load_records", lambda _runtime_dir, _index_payload: [])
    monkeypatch.setattr(
        duplicate_detection,
        "run_technique",
        lambda _dataset, technique: {
            "techniqueId": technique.id,
            "label": technique.label,
            "status": "ok",
            "pairCount": 0,
            "detectedModelCount": 0,
            "groupCount": 0,
            "largestGroupSize": 0,
            "elapsedMs": 0,
            "pairs": [],
            "groups": [],
        },
    )

    summary = duplicate_detection.evaluate_dataset(dataset_name="sap-sam-bpmn", evaluation_dir=tmp_path)

    assert summary["dataset"] == "sap-sam-bpmn"
    assert len(summary["rows"]) == len(duplicate_detection.DUPLICATE_TECHNIQUES)
    result_path = runtime_dir / "duplicate_detection.json"
    summary_path = runtime_dir / "duplicate_detection_summary.json"
    assert result_path.is_file()
    assert summary_path.is_file()
    assert '"bert_semantic"' in result_path.read_text(encoding="utf-8")
    assert '"gnn"' in result_path.read_text(encoding="utf-8")
