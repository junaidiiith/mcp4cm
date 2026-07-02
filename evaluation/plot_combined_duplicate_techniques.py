#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tqdm import tqdm

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs
from mcp4cm.runtime_store import deserialize_model_from_runtime

DEFAULT_TARGETS = (
    "modelset-uml-xmi",
    "modelset-ecore-xmi",
    "eamodelset-archimate",
    "sap-sam-bpmn",
)

TARGET_GROUPS: dict[str, tuple[str, ...]] = {
    "all": DEFAULT_TARGETS,
    "modelset": ("modelset-uml-xmi", "modelset-ecore-xmi"),
}

TARGET_CHOICES = tuple(TARGET_GROUPS) + DEFAULT_TARGETS
THRESHOLDS = tuple(round(index * 0.05, 2) for index in range(1, 21))
TECHNIQUES = ("tfidf", "graph_similarity", "bert_semantic", "gnn")

TECHNIQUE_LABELS = {
    "tfidf": "TF-IDF",
    "graph_similarity": "Graph similarity",
    "bert_semantic": "BERT similarity",
    "gnn": "GNN",
}

TECHNIQUE_COLORS = {
    "tfidf": "#1f77b4",
    "graph_similarity": "#ff7f0e",
    "bert_semantic": "#d62728",
    "gnn": "#9467bd",
}

DATASET_LABELS = {
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "eamodelset-archimate": "EAModelSet",
    "sap-sam-bpmn": "SAP-SAM BPMN",
}


class TechniqueProgressBar:
    def __init__(self, technique: str, *, enabled: bool) -> None:
        self.technique = technique
        self.enabled = enabled
        self.bar: tqdm | None = None
        self.phase = ""

    def __call__(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return

        phase = str(event.get("phase") or "running")
        total = max(int(event.get("total") or 0), 1)
        current = min(max(int(event.get("current") or 0), 0), total)
        if self.bar is None:
            self.bar = tqdm(total=total, desc=f"{self.technique}: {phase}", unit="item", dynamic_ncols=True)
            self.phase = phase
        elif phase != self.phase or self.bar.total != total or current < self.bar.n:
            self.bar.reset(total=total)
            self.bar.set_description(f"{self.technique}: {phase}")
            self.phase = phase

        self.bar.update(current - self.bar.n)
        message = str(event.get("message") or "")
        if message:
            self.bar.set_postfix_str(message, refresh=False)

    def close(self) -> None:
        if self.bar is not None:
            self.bar.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot duplicate and unique model counts from parsed evaluation runtime datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python evaluation/plot_combined_duplicate_techniques.py\n"
            "  python evaluation/plot_combined_duplicate_techniques.py --only eamodelset-archimate\n"
            "  python evaluation/plot_combined_duplicate_techniques.py --technique tfidf --technique graph_similarity\n"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=TARGET_CHOICES,
        metavar="TARGET",
        help=(
            "Run only the selected dataset or group. "
            f"Groups: {', '.join(TARGET_GROUPS)}. Targets: {', '.join(DEFAULT_TARGETS)}. "
            "Repeatable. Default: all evaluation targets."
        ),
    )
    parser.add_argument(
        "--technique",
        action="append",
        choices=TECHNIQUES,
        help=f"Technique to plot. Repeatable. Default: {', '.join(TECHNIQUES)}.",
    )
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=Path("evaluation"),
        help="Directory containing <dataset>-runtime folders (default: evaluation).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for plots and threshold CSV/JSON (default: <evaluation-dir>/threshold-plots).",
    )
    parser.add_argument(
        "--combined-output",
        type=Path,
        default=None,
        help="Optional path for one multi-panel PNG containing all selected datasets.",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        default=None,
        help="Embedding cache root (default: <evaluation-dir>/.mcp4cm_embeddings).",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bars.")
    return parser.parse_args()


def resolve_targets(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(DEFAULT_TARGETS)

    resolved: list[str] = []
    for item in selected:
        if item in TARGET_GROUPS:
            resolved.extend(TARGET_GROUPS[item])
            continue
        if item not in DEFAULT_TARGETS:
            raise ValueError(f"Unknown target: {item}")
        resolved.append(item)

    return list(dict.fromkeys(resolved))


def load_runtime_index(runtime_dir: Path) -> dict[str, Any]:
    index_path = runtime_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing runtime index: {index_path}")
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Runtime index is not a JSON object: {index_path}")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError(f"Runtime index does not contain a models list: {index_path}")
    return payload


def load_records(runtime_dir: Path, index_payload: dict[str, Any], *, progress_enabled: bool) -> list[ModelRecord]:
    ir_dir = runtime_dir / "ir"
    records: list[ModelRecord] = []
    model_entries = [entry for entry in index_payload.get("models") or [] if isinstance(entry, dict)]
    iterator = tqdm(model_entries, desc=runtime_dir.name, unit="model") if progress_enabled else model_entries
    for entry in iterator:
        filename = str(entry.get("file") or "")
        if not filename:
            raise ValueError(f"Runtime index entry is missing a file value in {runtime_dir / 'index.json'}")
        model_path = ir_dir / filename
        if not model_path.exists():
            raise FileNotFoundError(f"Runtime model file is missing: {model_path}")
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Runtime model file is not a JSON object: {model_path}")
        records.append(deserialize_model_from_runtime(payload))
    return records


def load_dataset(evaluation_dir: Path, dataset_name: str, *, progress_enabled: bool) -> Dataset:
    runtime_dir = evaluation_dir / f"{dataset_name}-runtime"
    if not runtime_dir.is_dir():
        raise FileNotFoundError(f"Missing runtime directory: {runtime_dir}")
    index_payload = load_runtime_index(runtime_dir)
    records = load_records(runtime_dir, index_payload, progress_enabled=progress_enabled)
    dataset_type = str(index_payload.get("datasetType") or "runtime")
    return Dataset(records=records, dataset_type=dataset_type, root=runtime_dir / "ir")


def duplicate_models_removed_from_pairs(pairs: list[Any]) -> int:
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        left_id, right_id = str(pair.left_id), str(pair.right_id)
        adjacency.setdefault(left_id, set()).add(right_id)
        adjacency.setdefault(right_id, set()).add(left_id)

    visited: set[str] = set()
    removed = 0
    for model_id in adjacency:
        if model_id in visited:
            continue
        stack = [model_id]
        component_size = 0
        visited.add(model_id)
        while stack:
            current = stack.pop()
            component_size += 1
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        removed += max(component_size - 1, 0)
    return removed


def rows_for_thresholds(
    pairs: list[Any], model_count: int, technique: str, *, progress_enabled: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    progress = (
        tqdm(total=len(THRESHOLDS), desc=f"{technique}: thresholds", unit="threshold", dynamic_ncols=True)
        if progress_enabled
        else None
    )
    try:
        for threshold in THRESHOLDS:
            matched_pairs = [pair for pair in pairs if pair.score >= threshold]
            duplicates = duplicate_models_removed_from_pairs(matched_pairs)
            rows.append(
                {
                    "threshold": threshold,
                    "duplicates": duplicates,
                    "unique": model_count - duplicates,
                    "matchingPairs": len(matched_pairs),
                }
            )
            if progress is not None:
                progress.update(1)
    finally:
        if progress is not None:
            progress.close()
    return rows


def compute_pairs(
    dataset: Dataset,
    technique: str,
    *,
    cache_dir: Path,
    progress_enabled: bool,
) -> tuple[list[Any], dict[str, Any]]:
    progress = TechniqueProgressBar(technique, enabled=progress_enabled)
    started = time.perf_counter()
    try:
        if technique == "tfidf":
            pairs = tfidf_duplicate_pairs(
                dataset,
                threshold=0.0,
                token_mode="names",
                technique="tfidf",
                progress=progress,
            )
            config = {"thresholdScanStart": 0.0, "tokenMode": "names"}
        elif technique == "graph_similarity":
            pairs = graph_similarity_pairs(dataset, threshold=0.0, progress=progress)
            config = {"thresholdScanStart": 0.0}
        elif technique == "bert_semantic":
            pairs = bert_semantic_similarity_pairs(
                dataset,
                threshold=0.0,
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                batch_size=8,
                max_length=256,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
            config = {
                "thresholdScanStart": 0.0,
                "modelName": "sentence-transformers/all-MiniLM-L6-v2",
                "batchSize": 8,
                "maxLength": 256,
                "semanticTextMode": "names_types_bag",
            }
        elif technique == "gnn":
            config_object = GNNTrainingConfig()
            triples = gnn_duplicate_pairs(
                dataset,
                threshold=0.0,
                config=config_object,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
            pairs = [SimpleNamespace(left_id=left, right_id=right, score=score) for left, right, score in triples]
            config = {"thresholdScanStart": 0.0, "trainingConfig": asdict(config_object)}
        else:
            raise ValueError(f"Unsupported technique: {technique}")
    finally:
        progress.close()

    return list(pairs), {**config, "runtimeSeconds": time.perf_counter() - started}


def write_technique_csv(path: Path, technique: str, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("technique", "threshold", "duplicates", "unique", "matchingPairs"))
        writer.writeheader()
        for row in rows:
            writer.writerow({"technique": technique, **row})


def write_technique_json(
    path: Path,
    *,
    dataset_name: str,
    technique: str,
    model_count: int,
    rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "dataset": dataset_name,
        "technique": technique,
        "modelCount": model_count,
        "thresholds": [row["threshold"] for row in rows],
        "runtimeSeconds": config.get("runtimeSeconds", 0),
        "config": config,
        "results": rows,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_dataset(
    *,
    dataset_name: str,
    evaluation_dir: Path,
    output_dir: Path,
    techniques: list[str],
    cache_dir: Path,
    progress_enabled: bool,
) -> Path:
    print(f"Loading {dataset_name}")
    dataset = load_dataset(evaluation_dir, dataset_name, progress_enabled=progress_enabled)
    dataset_output_dir = output_dir / dataset_name
    technique_rows: dict[str, list[dict[str, Any]]] = {}
    model_counts: dict[str, int] = {}

    for technique in techniques:
        print(f"Running {technique} on {dataset_name}")
        pairs, config = compute_pairs(dataset, technique, cache_dir=cache_dir, progress_enabled=progress_enabled)
        rows = rows_for_thresholds(pairs, len(dataset), technique, progress_enabled=progress_enabled)
        technique_rows[technique] = rows
        model_counts[technique] = len(dataset)
        write_technique_csv(dataset_output_dir / technique / f"{technique}.csv", technique, rows)
        write_technique_json(
            dataset_output_dir / technique / f"{technique}.json",
            dataset_name=dataset_name,
            technique=technique,
            model_count=len(dataset),
            rows=rows,
            config=config,
        )

    return plot_dataset(dataset_output_dir, dataset_name, technique_rows, model_counts)


def plot_dataset(
    output_dir: Path,
    dataset_name: str,
    rows_by_technique: dict[str, list[dict[str, Any]]],
    model_counts: dict[str, int],
    output_name: str = "combined_duplicate_techniques.png",
) -> Path:
    try:
        import matplotlib.lines as mlines
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install the project plotting dependencies.") from exc

    figure, axis = plt.subplots(figsize=(12, 7))
    draw_dataset(axis, dataset_name, rows_by_technique, model_counts)
    axis.set_title(f"{DATASET_LABELS.get(dataset_name, dataset_name)}: duplicate and unique models by threshold")
    axis.set_xlabel("Similarity threshold")
    axis.set_ylabel("Models (%)")
    axis.set_xticks(THRESHOLDS)

    technique_handles, metric_handles = legend_handles(mlines, rows_by_technique)
    figure.legend(
        handles=technique_handles,
        title="Technique",
        loc="lower center",
        ncol=max(len(technique_handles), 1),
        frameon=True,
        bbox_to_anchor=(0.40, 0.0),
    )
    figure.legend(
        handles=metric_handles,
        title="Metric",
        loc="lower center",
        ncol=2,
        frameon=True,
        bbox_to_anchor=(0.80, 0.0),
    )
    figure.tight_layout(rect=(0, 0.12, 1, 1))
    output_path = output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def draw_dataset(
    axis,
    dataset_name: str,
    rows_by_technique: dict[str, list[dict[str, Any]]],
    model_counts: dict[str, int],
) -> None:
    from matplotlib.ticker import PercentFormatter

    for technique in TECHNIQUES:
        rows = sorted(rows_by_technique.get(technique, []), key=lambda row: float(row["threshold"]))
        if not rows:
            continue
        model_count = model_counts[technique]
        thresholds = [float(row["threshold"]) for row in rows]
        duplicates = [int(row["duplicates"]) / model_count * 100.0 for row in rows]
        unique = [int(row["unique"]) / model_count * 100.0 for row in rows]
        axis.plot(
            thresholds,
            duplicates,
            marker="o",
            linewidth=1.9,
            markersize=4.0,
            color=TECHNIQUE_COLORS[technique],
            linestyle="-",
        )
        axis.plot(
            thresholds,
            unique,
            marker="s",
            linewidth=1.9,
            markersize=3.7,
            color=TECHNIQUE_COLORS[technique],
            linestyle="--",
        )

    axis.set_title(DATASET_LABELS.get(dataset_name, dataset_name))
    axis.set_xlim(0.05, 1.0)
    axis.set_ylim(0, 100)
    axis.set_xticks([round(index * 0.1, 2) for index in range(1, 11)])
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    axis.grid(True, alpha=0.3)


def legend_handles(mlines, rows_by_technique: dict[str, list[dict[str, Any]]]):
    technique_handles = [
        mlines.Line2D(
            [],
            [],
            color=TECHNIQUE_COLORS[technique],
            marker="o",
            linestyle="-",
            label=TECHNIQUE_LABELS[technique],
        )
        for technique in TECHNIQUES
        if technique in rows_by_technique
    ]
    metric_handles = [
        mlines.Line2D([], [], color="black", marker="o", linestyle="-", label="Duplicate models"),
        mlines.Line2D([], [], color="black", marker="s", linestyle="--", label="Unique models"),
    ]
    return technique_handles, metric_handles


def load_plotted_rows(
    dataset_output_dir: Path, techniques: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    rows_by_technique: dict[str, list[dict[str, Any]]] = {}
    model_counts: dict[str, int] = {}
    for technique in techniques:
        json_path = dataset_output_dir / technique / f"{technique}.json"
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        rows_by_technique[technique] = list(payload["results"])
        model_counts[technique] = int(payload["modelCount"])
    return rows_by_technique, model_counts


def plot_all_datasets(
    *,
    dataset_names: list[str],
    output_dir: Path,
    techniques: list[str],
    output_path: Path,
) -> Path:
    try:
        import matplotlib.lines as mlines
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install the project plotting dependencies.") from exc

    figure, axes = plt.subplots(2, 2, figsize=(15, 10), sharex=True, sharey=True)
    subplot_labels = ("(a)", "(b)", "(c)", "(d)")
    for axis, dataset_name, subplot_label in zip(axes.flat, dataset_names, subplot_labels, strict=False):
        rows_by_technique, model_counts = load_plotted_rows(output_dir / dataset_name, techniques)
        draw_dataset(axis, dataset_name, rows_by_technique, model_counts)
        axis.set_title(f"{subplot_label} {DATASET_LABELS.get(dataset_name, dataset_name)}")

    for axis in axes[:, 0]:
        axis.set_ylabel("Models (%)")
    for axis in axes[-1, :]:
        axis.set_xlabel("Similarity threshold")

    technique_handles, metric_handles = legend_handles(mlines, {technique: [] for technique in techniques})
    figure.legend(
        handles=technique_handles,
        title="Technique",
        loc="lower center",
        ncol=max(len(technique_handles), 1),
        frameon=True,
        bbox_to_anchor=(0.38, 0.01),
    )
    figure.legend(
        handles=metric_handles,
        title="Metric",
        loc="lower center",
        ncol=2,
        frameon=True,
        bbox_to_anchor=(0.79, 0.01),
    )
    figure.suptitle("Duplicate and unique models by similarity threshold", y=0.98)
    figure.tight_layout(rect=(0, 0.11, 1, 0.96))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def main() -> int:
    args = parse_args()
    targets = resolve_targets(args.only)
    techniques = list(dict.fromkeys(args.technique or TECHNIQUES))
    output_dir = args.output_dir or args.evaluation_dir / "threshold-plots"
    cache_dir = args.embedding_cache_dir or args.evaluation_dir / ".mcp4cm_embeddings"
    progress_enabled = sys.stderr.isatty() and not args.no_progress

    output_paths = [
        run_dataset(
            dataset_name=target,
            evaluation_dir=args.evaluation_dir,
            output_dir=output_dir,
            techniques=techniques,
            cache_dir=cache_dir,
            progress_enabled=progress_enabled,
        )
        for target in targets
    ]
    if args.combined_output:
        output_paths.append(
            plot_all_datasets(
                dataset_names=targets,
                output_dir=output_dir,
                techniques=techniques,
                output_path=args.combined_output,
            )
        )

    for output_path in output_paths:
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
