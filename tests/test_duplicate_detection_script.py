from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DUPLICATE_DETECTION_PATH = REPOSITORY_ROOT / "scripts" / "duplicate_detection.py"
SPEC = importlib.util.spec_from_file_location("duplicate_detection", DUPLICATE_DETECTION_PATH)
assert SPEC is not None and SPEC.loader is not None
duplicate_detection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = duplicate_detection
SPEC.loader.exec_module(duplicate_detection)


class FakeDataset:
    dataset_type = "fake-dataset"

    def __init__(self, size: int) -> None:
        self.records = [SimpleNamespace(model_id=f"model-{index}") for index in range(size)]

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)


def test_defaults_select_all_datasets_and_techniques() -> None:
    args = duplicate_detection.parse_args([])

    assert duplicate_detection.selected_datasets(args) == list(duplicate_detection.DEFAULT_DATASETS)
    assert duplicate_detection.selected_techniques(args) == list(duplicate_detection.TECHNIQUES)
    assert "node2vec" not in duplicate_detection.TECHNIQUES
    assert "isomorphism" not in duplicate_detection.TECHNIQUES
    assert {"bert", "gnn"} <= set(duplicate_detection.TECHNIQUES)


def test_selects_multiple_datasets_and_techniques_with_aliases() -> None:
    args = duplicate_detection.parse_args(
        [
            "--dataset",
            "sap-sam",
            "--dataset",
            "modelset-uml-xmi",
            "--technique",
            "tfidf",
            "bert-similarity",
            "--technique",
            "gnn",
        ]
    )

    assert duplicate_detection.selected_datasets(args) == ["sap-sam-bpmn", "modelset-uml-xmi"]
    assert duplicate_detection.selected_techniques(args) == ["tfidf", "bert", "gnn"]


def test_evaluation_dir_alias_sets_data_dir(tmp_path: Path) -> None:
    args = duplicate_detection.parse_args(["--evaluation-dir", str(tmp_path)])

    assert args.data_dir == tmp_path


def test_run_dataset_writes_artifacts_under_dataset_and_technique(monkeypatch, tmp_path: Path) -> None:
    def fake_plot(path: Path, technique: str, rows, model_count: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{technique}:{model_count}:{len(rows)}\n", encoding="utf-8")

    monkeypatch.setattr(duplicate_detection, "load_prepared_dataset", lambda data_dir, dataset_name: FakeDataset(3))
    monkeypatch.setattr(
        duplicate_detection,
        "detect_duplicates_by_name_hash",
        lambda dataset, include_types, progress: [SimpleNamespace(model_ids=["model-0", "model-1"])],
    )
    monkeypatch.setattr(
        duplicate_detection,
        "compute_pair_technique",
        lambda args, dataset, technique, cache_dir: (
            [SimpleNamespace(left_id="model-0", right_id="model-2", score=0.95)],
            {"thresholdScanStart": 0.0},
        ),
    )
    monkeypatch.setattr(duplicate_detection, "plot_technique", fake_plot)
    monkeypatch.setattr(
        duplicate_detection,
        "plot_combined_dataset",
        lambda dataset_dir: (dataset_dir / "combined_duplicate_techniques.png"),
    )

    args = duplicate_detection.parse_args(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "--output-dir",
            str(tmp_path / "results"),
            "--threshold",
            "0.9",
            "--no-progress",
        ]
    )

    artifacts = duplicate_detection.run_dataset(args, "sap-sam-bpmn", ["hash", "bert"])

    assert len(artifacts) == 2
    assert (tmp_path / "results" / "sap-sam-bpmn" / "hash" / "hash.csv").is_file()
    assert (tmp_path / "results" / "sap-sam-bpmn" / "hash" / "hash.json").is_file()
    assert (tmp_path / "results" / "sap-sam-bpmn" / "hash" / "hash.png").is_file()
    assert (tmp_path / "results" / "sap-sam-bpmn" / "bert" / "bert.csv").is_file()
    assert (tmp_path / "results" / "sap-sam-bpmn" / "bert" / "bert.json").is_file()
    assert (tmp_path / "results" / "sap-sam-bpmn" / "bert" / "bert.png").is_file()
    assert artifacts[1].table_row.technique == "bert"
    assert artifacts[1].table_row.models == 2


def test_write_table_outputs_matches_table_script_artifacts(tmp_path: Path) -> None:
    row = duplicate_detection.TableRow(
        dataset="sap-sam-bpmn",
        technique="gnn",
        models=2,
        model_percent=50.0,
        pairs=1,
        groups=1,
        largest_group=2,
        runtime_seconds=0.25,
        total_models=4,
    )

    paths = duplicate_detection.write_table_outputs(tmp_path, [row], threshold=0.9)

    assert {path.name for path in paths} == {
        "duplicate_technique_table.tex",
        "duplicate_technique_table.csv",
        "duplicate_technique_table.json",
    }
    assert "SAP-SAM BPMN" in (tmp_path / "duplicate_technique_table.tex").read_text(encoding="utf-8")
    assert '"threshold": 0.9' in (tmp_path / "duplicate_technique_table.json").read_text(encoding="utf-8")
