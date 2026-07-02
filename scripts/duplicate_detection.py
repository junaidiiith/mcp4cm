#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Run duplicate detection across prepared datasets and write analysis artifacts.

The script produces per-technique threshold CSV/JSON/PNG files below one
directory per dataset, writes a combined technique plot for each dataset, and
emits a LaTeX/CSV/JSON table summary at the selected reporting threshold.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (REPOSITORY_ROOT, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from mcp4cm.duplicates import (  # noqa: E402
    bert_semantic_similarity_pairs,
    detect_duplicates_by_name_hash,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs  # noqa: E402
from mcp4cm.utils import pair_count  # noqa: E402
from run_duplicate_detection import (  # noqa: E402
    DEFAULT_DATA_DIR,
    TechniqueProgressBar,
    duplicate_models_removed_from_groups,
    duplicate_models_removed_from_pairs,
    load_prepared_dataset,
    tqdm,
)

DEFAULT_DATASETS = ("modelset-uml-xmi", "modelset-ecore-xmi", "eamodelset-archimate", "sap-sam-bpmn")
DATASET_ALIASES = {"sap-sam": "sap-sam-bpmn"}
DATASET_LABELS = {
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "eamodelset-archimate": "EAModelSet",
    "sap-sam-bpmn": "SAP-SAM BPMN",
}

THRESHOLDS = tuple(round(index * 0.05, 2) for index in range(1, 21))
PAIR_TECHNIQUES = ("tfidf", "graph-similarity", "bert", "gnn")
TECHNIQUES = ("hash", *PAIR_TECHNIQUES)
TECHNIQUE_ALIASES = {
    "bert-similarity": "bert",
}
TECHNIQUE_LABELS = {
    "hash": "Hash",
    "tfidf": "TF-IDF",
    "graph-similarity": "Graph metrics",
    "bert": "BERT",
    "gnn": "GNN",
}
TECHNIQUE_COLORS = {
    "tfidf": "#1f77b4",
    "graph-similarity": "#ff7f0e",
    "bert": "#d62728",
    "gnn": "#9467bd",
    "hash": "#2ca02c",
}


@dataclass(frozen=True)
class TableRow:
    dataset: str
    technique: str
    models: int
    model_percent: float
    pairs: int
    groups: int
    largest_group: int
    runtime_seconds: float
    total_models: int


@dataclass(frozen=True)
class TechniqueArtifacts:
    technique: str
    rows: list[dict[str, int | float]]
    table_row: TableRow
    json_path: Path
    csv_path: Path
    png_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run duplicate detection and generate per-technique artifacts plus summary tables."
    )
    parser.add_argument(
        "dataset",
        nargs="?",
        help=(
            "Prepared dataset directory below --data-dir. If omitted and --dataset is not used, "
            f"all default datasets are processed: {', '.join(DEFAULT_DATASETS)}."
        ),
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="Dataset directory or alias to process. Repeat to select multiple datasets.",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--evaluation-dir",
        dest="data_dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Deprecated alias for --data-dir.",
    )
    parser.add_argument(
        "--technique",
        action="append",
        nargs="+",
        choices=(*TECHNIQUES, "bert-similarity"),
        default=None,
        help=(
            "Technique(s) to run. Repeat the option or provide several names "
            f"(default: all: {', '.join(TECHNIQUES)})."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Reporting threshold for table rows. Threshold plots always use 0.05..1.0.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation-results"),
        help="Root directory for generated artifacts.",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        help="Embedding cache root (default: <data-dir>/.mcp4cm_embeddings).",
    )
    parser.add_argument(
        "--tfidf-token-mode",
        choices=("names", "names_types_bag", "typed_name_pairs"),
        default="names_types_bag",
    )
    parser.add_argument("--bert-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--bert-batch-size", type=int, default=8)
    parser.add_argument("--bert-max-length", type=int, default=256)
    parser.add_argument("--gnn-model-name", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--gnn-dimensions", type=int, default=128)
    parser.add_argument("--gnn-layers", type=int, default=2)
    parser.add_argument("--gnn-epochs", type=int, default=20)
    parser.add_argument("--gnn-learning-rate", type=float, default=1e-3)
    parser.add_argument("--gnn-temperature", type=float, default=0.2)
    parser.add_argument("--gnn-edge-dropout", type=float, default=0.15)
    parser.add_argument("--gnn-feature-mask-rate", type=float, default=0.10)
    parser.add_argument("--gnn-batch-size", type=int, default=32)
    parser.add_argument("--gnn-seed", type=int, default=42)
    parser.add_argument("--gnn-device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bars.")
    return parser.parse_args(argv)


def canonical_dataset(name: str) -> str:
    return DATASET_ALIASES.get(name, name)


def canonical_technique(name: str) -> str:
    return TECHNIQUE_ALIASES.get(name, name)


def selected_datasets(args: argparse.Namespace) -> list[str]:
    if args.datasets:
        datasets = [canonical_dataset(dataset) for dataset in args.datasets]
    elif args.dataset:
        datasets = [canonical_dataset(args.dataset)]
    else:
        datasets = list(DEFAULT_DATASETS)
    return list(dict.fromkeys(datasets))


def selected_techniques(args: argparse.Namespace) -> list[str]:
    if not args.technique:
        return list(TECHNIQUES)
    techniques = [canonical_technique(technique) for group in args.technique for technique in group]
    return list(dict.fromkeys(techniques))


def gnn_training_config(args: argparse.Namespace) -> GNNTrainingConfig:
    return GNNTrainingConfig(
        model_name=args.gnn_model_name,
        embedding_dim=args.gnn_dimensions,
        layers=args.gnn_layers,
        epochs=args.gnn_epochs,
        learning_rate=args.gnn_learning_rate,
        temperature=args.gnn_temperature,
        edge_dropout=args.gnn_edge_dropout,
        feature_mask_rate=args.gnn_feature_mask_rate,
        batch_size=args.gnn_batch_size,
        seed=args.gnn_seed,
        device=args.gnn_device,
    )


def pair_endpoints(pair: Any) -> tuple[str, str]:
    return str(pair.left_id), str(pair.right_id)


def connected_components_from_pairs(pairs: list[Any]) -> list[set[str]]:
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        left_id, right_id = pair_endpoints(pair)
        adjacency.setdefault(left_id, set()).add(right_id)
        adjacency.setdefault(right_id, set()).add(left_id)

    components: list[set[str]] = []
    visited: set[str] = set()
    for model_id in sorted(adjacency):
        if model_id in visited:
            continue
        component: set[str] = set()
        stack = [model_id]
        visited.add(model_id)
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component) > 1:
            components.append(component)
    return components


def table_row_from_pairs(
    *,
    dataset_name: str,
    technique: str,
    total_models: int,
    pairs: list[Any],
    runtime_seconds: float,
) -> TableRow:
    components = connected_components_from_pairs(pairs)
    participating_models = len({model_id for component in components for model_id in component})
    return TableRow(
        dataset=dataset_name,
        technique=technique,
        models=participating_models,
        model_percent=(participating_models / total_models * 100.0) if total_models else 0.0,
        pairs=len(pairs),
        groups=len(components),
        largest_group=max((len(component) for component in components), default=0),
        runtime_seconds=runtime_seconds,
        total_models=total_models,
    )


def table_row_from_hash_groups(
    *,
    dataset_name: str,
    total_models: int,
    groups: list[Any],
    runtime_seconds: float,
) -> TableRow:
    participating_models = len({model_id for group in groups for model_id in group.model_ids})
    hash_pair_count = sum(pair_count(len(group.model_ids)) for group in groups)
    return TableRow(
        dataset=dataset_name,
        technique="hash",
        models=participating_models,
        model_percent=(participating_models / total_models * 100.0) if total_models else 0.0,
        pairs=hash_pair_count,
        groups=len(groups),
        largest_group=max((len(group.model_ids) for group in groups), default=0),
        runtime_seconds=runtime_seconds,
        total_models=total_models,
    )


def rows_for_thresholds(
    pairs: list[Any],
    model_count: int,
    technique: str,
    *,
    progress_enabled: bool,
) -> list[dict[str, int | float]]:
    rows: list[dict[str, int | float]] = []
    progress = (
        tqdm(total=len(THRESHOLDS), desc=f"{technique}: thresholds", unit="threshold", dynamic_ncols=True)
        if progress_enabled and tqdm is not None
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


def hash_threshold_rows(groups: list[Any], model_count: int) -> list[dict[str, int | float]]:
    duplicates = duplicate_models_removed_from_groups(groups)
    return [
        {
            "threshold": 1.0,
            "duplicates": duplicates,
            "unique": model_count - duplicates,
            "matchingPairs": sum(pair_count(len(group.model_ids)) for group in groups),
        }
    ]


def matched_pairs_at_threshold(pairs: list[Any], threshold: float) -> list[Any]:
    return [pair for pair in pairs if pair.score >= threshold]


def write_technique_csv(path: Path, technique: str, rows: list[dict[str, int | float]]) -> None:
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
    rows: list[dict[str, int | float]],
    runtime_seconds: float,
    config: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": dataset_name,
        "technique": technique,
        "modelCount": model_count,
        "thresholds": [row["threshold"] for row in rows],
        "runtimeSeconds": runtime_seconds,
        "config": config,
        "results": rows,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def plot_technique(path: Path, technique: str, rows: list[dict[str, int | float]], model_count: int) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install it with `pip install -e '.[plot]'`.") from exc

    thresholds = [float(row["threshold"]) for row in rows]
    duplicates = [int(row["duplicates"]) / model_count * 100.0 for row in rows]
    unique = [int(row["unique"]) / model_count * 100.0 for row in rows]
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.plot(thresholds, duplicates, marker="o", color=TECHNIQUE_COLORS[technique], label="Duplicate models")
    axis.plot(thresholds, unique, marker="s", color="#333333", linestyle="--", label="Unique models")
    axis.set_xlabel("Similarity threshold")
    axis.set_ylabel("Models (%)")
    axis.set_title(f"{TECHNIQUE_LABELS[technique]} duplicate detection")
    axis.set_ylim(0, 100)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    if len(thresholds) > 1:
        axis.set_xlim(0.05, 1.0)
        axis.set_xticks(THRESHOLDS)
    else:
        axis.set_xlim(0.95, 1.05)
        axis.set_xticks([thresholds[0]])
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def load_pair_rows_from_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def technique_artifact_path(dataset_dir: Path, technique: str, suffix: str) -> Path:
    return dataset_dir / technique / f"{technique}.{suffix}"


def plot_combined_dataset(dataset_dir: Path, output_name: str = "combined_duplicate_techniques.png") -> Path | None:
    technique_rows: dict[str, list[dict[str, str]]] = {}
    model_counts: dict[str, int] = {}
    for technique in PAIR_TECHNIQUES:
        csv_path = technique_artifact_path(dataset_dir, technique, "csv")
        json_path = technique_artifact_path(dataset_dir, technique, "json")
        if not csv_path.exists() or not json_path.exists():
            continue
        technique_rows[technique] = load_pair_rows_from_csv(csv_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        model_count = payload.get("modelCount")
        if isinstance(model_count, int):
            model_counts[technique] = model_count

    if not technique_rows:
        return None

    try:
        import matplotlib.lines as mlines
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install it with `pip install -e '.[plot]'`.") from exc

    figure, axis = plt.subplots(figsize=(12, 7))
    for technique in PAIR_TECHNIQUES:
        rows = sorted(technique_rows.get(technique, []), key=lambda row: float(row["threshold"]))
        model_count = model_counts.get(technique)
        if not rows or not model_count:
            continue
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

    axis.set_title(f"{DATASET_LABELS.get(dataset_dir.name, dataset_dir.name)}: duplicate and unique models")
    axis.set_xlabel("Similarity threshold")
    axis.set_ylabel("Models (%)")
    axis.set_xlim(0.05, 1.0)
    axis.set_ylim(0, 100)
    axis.set_xticks(THRESHOLDS)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    axis.grid(True, alpha=0.3)

    technique_handles = [
        mlines.Line2D(
            [],
            [],
            color=TECHNIQUE_COLORS[technique],
            marker="o",
            linestyle="-",
            label=TECHNIQUE_LABELS[technique],
        )
        for technique in PAIR_TECHNIQUES
        if technique in technique_rows
    ]
    metric_handles = [
        mlines.Line2D([], [], color="black", marker="o", linestyle="-", label="Duplicate models"),
        mlines.Line2D([], [], color="black", marker="s", linestyle="--", label="Unique models"),
    ]
    figure.legend(handles=technique_handles, title="Technique", loc="lower center", ncol=4, bbox_to_anchor=(0.40, 0.0))
    figure.legend(handles=metric_handles, title="Metric", loc="lower center", ncol=2, bbox_to_anchor=(0.80, 0.0))
    figure.tight_layout(rect=(0, 0.12, 1, 1))
    output_path = dataset_dir / output_name
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def compute_pair_technique(
    args: argparse.Namespace,
    dataset: Any,
    technique: str,
    cache_dir: Path,
) -> tuple[list[Any], dict[str, Any]]:
    progress = TechniqueProgressBar(technique, enabled=not args.no_progress)
    try:
        if technique == "tfidf":
            pairs = tfidf_duplicate_pairs(
                dataset,
                threshold=0.0,
                token_mode=args.tfidf_token_mode,
                technique="tfidf",
                progress=progress,
            )
            config = {"thresholdScanStart": 0.0, "tokenMode": args.tfidf_token_mode}
        elif technique == "graph-similarity":
            pairs = graph_similarity_pairs(dataset, threshold=0.0, progress=progress)
            config = {"thresholdScanStart": 0.0}
        elif technique == "bert":
            pairs = bert_semantic_similarity_pairs(
                dataset,
                threshold=0.0,
                model_name=args.bert_model,
                batch_size=args.bert_batch_size,
                max_length=args.bert_max_length,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
            config = {
                "thresholdScanStart": 0.0,
                "model": args.bert_model,
                "batchSize": args.bert_batch_size,
                "maxLength": args.bert_max_length,
            }
        elif technique == "gnn":
            config_object = gnn_training_config(args)
            triples = gnn_duplicate_pairs(
                dataset,
                threshold=0.0,
                config=config_object,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
            pairs = [
                SimpleNamespace(left_id=left_id, right_id=right_id, score=score)
                for left_id, right_id, score in triples
            ]
            config = {"thresholdScanStart": 0.0, "trainingConfig": asdict(config_object)}
        else:
            raise ValueError(f"Unsupported pair technique: {technique}")
        return list(pairs), config
    finally:
        progress.close()


def run_hash_artifacts(
    args: argparse.Namespace,
    dataset: Any,
    dataset_name: str,
    output_dir: Path,
) -> TechniqueArtifacts:
    started = time.perf_counter()
    progress = TechniqueProgressBar("hash", enabled=not args.no_progress)
    try:
        groups = detect_duplicates_by_name_hash(dataset, include_types=False, progress=progress)
    finally:
        progress.close()
    runtime_seconds = time.perf_counter() - started
    rows = hash_threshold_rows(groups, len(dataset))
    table_row = table_row_from_hash_groups(
        dataset_name=dataset_name,
        total_models=len(dataset),
        groups=groups,
        runtime_seconds=runtime_seconds,
    )
    json_path = technique_artifact_path(output_dir, "hash", "json")
    csv_path = technique_artifact_path(output_dir, "hash", "csv")
    png_path = technique_artifact_path(output_dir, "hash", "png")
    write_technique_json(
        json_path,
        dataset_name=dataset_name,
        technique="hash",
        model_count=len(dataset),
        rows=rows,
        runtime_seconds=runtime_seconds,
        config={"includeTypes": False},
    )
    write_technique_csv(csv_path, "hash", rows)
    plot_technique(png_path, "hash", rows, len(dataset))
    return TechniqueArtifacts("hash", rows, table_row, json_path, csv_path, png_path)


def run_pair_artifacts(
    args: argparse.Namespace,
    dataset: Any,
    dataset_name: str,
    technique: str,
    output_dir: Path,
    cache_dir: Path,
) -> TechniqueArtifacts:
    started = time.perf_counter()
    pairs, config = compute_pair_technique(args, dataset, technique, cache_dir)
    runtime_seconds = time.perf_counter() - started
    rows = rows_for_thresholds(pairs, len(dataset), technique, progress_enabled=not args.no_progress)
    table_pairs = matched_pairs_at_threshold(pairs, args.threshold)
    table_row = table_row_from_pairs(
        dataset_name=dataset_name,
        technique=technique,
        total_models=len(dataset),
        pairs=table_pairs,
        runtime_seconds=runtime_seconds,
    )
    json_path = technique_artifact_path(output_dir, technique, "json")
    csv_path = technique_artifact_path(output_dir, technique, "csv")
    png_path = technique_artifact_path(output_dir, technique, "png")
    write_technique_json(
        json_path,
        dataset_name=dataset_name,
        technique=technique,
        model_count=len(dataset),
        rows=rows,
        runtime_seconds=runtime_seconds,
        config=config,
    )
    write_technique_csv(csv_path, technique, rows)
    plot_technique(png_path, technique, rows, len(dataset))
    return TechniqueArtifacts(technique, rows, table_row, json_path, csv_path, png_path)


def run_dataset(args: argparse.Namespace, dataset_name: str, techniques: list[str]) -> list[TechniqueArtifacts]:
    dataset = load_prepared_dataset(args.data_dir, dataset_name)
    dataset_output_dir = args.output_dir / dataset_name
    dataset_output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.embedding_cache_dir or (args.data_dir / ".mcp4cm_embeddings")

    artifacts: list[TechniqueArtifacts] = []
    for technique in techniques:
        print(f"Running {technique} on {dataset_name}")
        if technique == "hash":
            artifacts.append(run_hash_artifacts(args, dataset, dataset_name, dataset_output_dir))
        else:
            artifacts.append(run_pair_artifacts(args, dataset, dataset_name, technique, dataset_output_dir, cache_dir))

    combined_path = plot_combined_dataset(dataset_output_dir)
    if combined_path is not None:
        print(combined_path)
    return artifacts


def format_int(value: int) -> str:
    return f"{value:,}"


def latex_escape(value: str) -> str:
    return value.replace("_", r"\_").replace("%", r"\%")


def latex_table(rows: list[TableRow], *, threshold: float) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"    \centering",
        (
            r"    \caption{Duplicate candidates produced independently by each duplicate detector at "
            f"threshold {threshold:g}. ``Models'' counts distinct models that participate in at least one "
            r"candidate duplicate relation. Hash is exact and does not use the threshold.}"
        ),
        r"    \label{tab:duplicate-results}",
        r"    \begin{tabular}{llrrrrrr}",
        r"        \toprule",
        r"        Dataset & Technique & Models & Models (\%) & Pairs & Groups & Largest group & Runtime \\",
        r"        \midrule",
    ]
    rows_by_dataset: dict[str, list[TableRow]] = {}
    for row in rows:
        rows_by_dataset.setdefault(row.dataset, []).append(row)

    for dataset_index, (dataset, dataset_rows) in enumerate(rows_by_dataset.items()):
        if dataset_index:
            lines.append(r"        \midrule")
        first = True
        for row in dataset_rows:
            dataset_cell = (
                rf"\multirow{{{len(dataset_rows)}}}{{*}}{{{latex_escape(DATASET_LABELS.get(dataset, dataset))}}}"
                if first
                else ""
            )
            first = False
            lines.append(
                "        "
                f"{dataset_cell} & {TECHNIQUE_LABELS[row.technique]} "
                f"& {format_int(row.models)} "
                f"& {row.model_percent:.2f} "
                f"& {format_int(row.pairs)} "
                f"& {format_int(row.groups)} "
                f"& {format_int(row.largest_group)} "
                f"& {row.runtime_seconds:.2f} s \\\\"
            )

    lines.extend([r"        \bottomrule", r"    \end{tabular}", r"\end{table*}", ""])
    return "\n".join(lines)


def write_table_csv(path: Path, rows: list[TableRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "dataset",
                "technique",
                "models",
                "modelsPercent",
                "pairs",
                "groups",
                "largestGroup",
                "runtimeSeconds",
                "totalModels",
            ),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "dataset": row.dataset,
                    "technique": row.technique,
                    "models": row.models,
                    "modelsPercent": f"{row.model_percent:.4f}",
                    "pairs": row.pairs,
                    "groups": row.groups,
                    "largestGroup": row.largest_group,
                    "runtimeSeconds": f"{row.runtime_seconds:.6f}",
                    "totalModels": row.total_models,
                }
            )


def write_table_json(path: Path, rows: list[TableRow], *, threshold: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "threshold": threshold,
        "rows": [
            {
                "dataset": row.dataset,
                "technique": row.technique,
                "models": row.models,
                "modelsPercent": row.model_percent,
                "pairs": row.pairs,
                "groups": row.groups,
                "largestGroup": row.largest_group,
                "runtimeSeconds": row.runtime_seconds,
                "totalModels": row.total_models,
            }
            for row in rows
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_table_outputs(output_dir: Path, rows: list[TableRow], *, threshold: float) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / "duplicate_technique_table.tex"
    csv_path = output_dir / "duplicate_technique_table.csv"
    json_path = output_dir / "duplicate_technique_table.json"
    tex_path.write_text(latex_table(rows, threshold=threshold), encoding="utf-8")
    write_table_csv(csv_path, rows)
    write_table_json(json_path, rows, threshold=threshold)
    return [tex_path, csv_path, json_path]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    datasets = selected_datasets(args)
    techniques = selected_techniques(args)
    invalid = [technique for technique in techniques if technique not in TECHNIQUES]
    if invalid:
        raise ValueError(f"Unsupported technique(s): {', '.join(invalid)}")

    all_artifacts: list[TechniqueArtifacts] = []
    for dataset_name in datasets:
        all_artifacts.extend(run_dataset(args, dataset_name, techniques))

    table_rows = [artifact.table_row for artifact in all_artifacts]
    table_paths = write_table_outputs(args.output_dir, table_rows, threshold=args.threshold)
    for path in table_paths:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
