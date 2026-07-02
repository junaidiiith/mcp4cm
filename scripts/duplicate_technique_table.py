#!/usr/bin/env python3
"""Generate a LaTeX duplicate-detection result table at a fixed threshold."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (REPOSITORY_ROOT, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_duplicate_detection import DEFAULT_DATA_DIR, TechniqueProgressBar, load_prepared_dataset  # noqa: E402

from mcp4cm.duplicates import (  # noqa: E402
    bert_semantic_similarity_pairs,
    detect_duplicates_by_name_hash,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs  # noqa: E402

DEFAULT_DATASETS = ("modelset-uml-xmi", "modelset-ecore-xmi", "eamodelset-archimate", "sap-sam-bpmn")
DEFAULT_TECHNIQUES = ("hash", "tfidf", "graph-similarity", "bert-similarity", "gnn")
TECHNIQUE_LABELS = {
    "hash": "Hash",
    "tfidf": "TF--IDF",
    "graph-similarity": "Graph metrics",
    "bert-similarity": "BERT",
    "gnn": "GNN",
}
DATASET_LABELS = {
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "eamodelset-archimate": "EAModelSet",
    "sap-sam-bpmn": "SAP-SAM BPMN",
    "sap-sam": "SAP-SAM BPMN",
}
DATASET_ALIASES = {
    "sap-sam": "sap-sam-bpmn",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute duplicate-detection table rows and write LaTeX/CSV/JSON outputs."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help=f"Dataset to include. Repeatable. Default: {', '.join(DEFAULT_DATASETS)}.",
    )
    parser.add_argument(
        "--technique",
        action="append",
        nargs="+",
        choices=DEFAULT_TECHNIQUES,
        help=f"Technique(s) to include. Default: {', '.join(DEFAULT_TECHNIQUES)}.",
    )
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("threshold-results_v1/duplicate_technique_table.tex"),
        help="LaTeX table output path.",
    )
    parser.add_argument("--csv-output", type=Path, help="Optional CSV output path.")
    parser.add_argument("--json-output", type=Path, help="Optional JSON output path.")
    parser.add_argument("--embedding-cache-dir", type=Path, help="Default: <data-dir>/.mcp4cm_embeddings.")
    parser.add_argument(
        "--tfidf-token-mode",
        default="names_types_bag",
        choices=("names", "names_types_bag", "typed_name_pairs"),
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
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args()


def canonical_dataset(name: str) -> str:
    return DATASET_ALIASES.get(name, name)


def selected_techniques(args: argparse.Namespace) -> list[str]:
    if args.technique:
        return [technique for group in args.technique for technique in group]
    return list(DEFAULT_TECHNIQUES)


def gnn_config(args: argparse.Namespace) -> GNNTrainingConfig:
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


def summarize_pairs(
    *, dataset_name: str, technique: str, total_models: int, pairs: list[Any], runtime_seconds: float
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


def summarize_hash_groups(
    *, dataset_name: str, total_models: int, groups: list[Any], runtime_seconds: float
) -> TableRow:
    participating_models = len({model_id for group in groups for model_id in group.model_ids})
    pair_count = sum((len(group.model_ids) * (len(group.model_ids) - 1)) // 2 for group in groups)
    return TableRow(
        dataset=dataset_name,
        technique="hash",
        models=participating_models,
        model_percent=(participating_models / total_models * 100.0) if total_models else 0.0,
        pairs=pair_count,
        groups=len(groups),
        largest_group=max((len(group.model_ids) for group in groups), default=0),
        runtime_seconds=runtime_seconds,
        total_models=total_models,
    )


def run_technique(dataset: Any, dataset_name: str, technique: str, args: argparse.Namespace) -> TableRow:
    cache_dir = args.embedding_cache_dir or (args.data_dir / ".mcp4cm_embeddings")
    progress = TechniqueProgressBar(technique, enabled=not args.no_progress)
    started = time.perf_counter()
    try:
        if technique == "hash":
            groups = detect_duplicates_by_name_hash(dataset, include_types=False, progress=progress)
            elapsed = time.perf_counter() - started
            return summarize_hash_groups(
                dataset_name=dataset_name, total_models=len(dataset), groups=groups, runtime_seconds=elapsed
            )
        if technique == "tfidf":
            pairs = tfidf_duplicate_pairs(
                dataset,
                threshold=args.threshold,
                token_mode=args.tfidf_token_mode,
                technique="tfidf",
                progress=progress,
            )
        elif technique == "graph-similarity":
            pairs = graph_similarity_pairs(dataset, threshold=args.threshold, progress=progress)
        elif technique == "bert-similarity":
            pairs = bert_semantic_similarity_pairs(
                dataset,
                threshold=args.threshold,
                model_name=args.bert_model,
                batch_size=args.bert_batch_size,
                max_length=args.bert_max_length,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
        elif technique == "gnn":
            triples = gnn_duplicate_pairs(
                dataset,
                threshold=args.threshold,
                config=gnn_config(args),
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
            pairs = [SimpleNamespace(left_id=left_id, right_id=right_id) for left_id, right_id, _score in triples]
        else:
            raise ValueError(f"Unsupported technique: {technique}")
        elapsed = time.perf_counter() - started
        return summarize_pairs(
            dataset_name=dataset_name,
            technique=technique,
            total_models=len(dataset),
            pairs=list(pairs),
            runtime_seconds=elapsed,
        )
    finally:
        progress.close()


def format_int(value: int) -> str:
    return f"{value:,}"


def latex_escape(value: str) -> str:
    return value.replace("_", r"\_").replace("%", r"\%")


def runtime_label(seconds: float) -> str:
    return f"{seconds:.2f} s"


def latex_table(rows: list[TableRow], *, threshold: float, techniques: list[str]) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"    \centering",
        (
            r"    \caption{Duplicate candidates produced independently by each duplicate detector at "
            f"threshold {threshold:g}. ``Models'' counts distinct models that participate in at least one "
            r"candidate duplicate relation.}"
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
                f"& {runtime_label(row.runtime_seconds)} \\\\"
            )

    lines.extend(
        [
            r"        \bottomrule",
            r"    \end{tabular}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[TableRow]) -> None:
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


def write_json(path: Path, rows: list[TableRow], *, threshold: float) -> None:
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


def main() -> int:
    args = parse_args()
    datasets = [canonical_dataset(dataset) for dataset in (args.datasets or list(DEFAULT_DATASETS))]
    techniques = selected_techniques(args)

    rows: list[TableRow] = []
    for dataset_name in datasets:
        dataset = load_prepared_dataset(args.data_dir, dataset_name)
        for technique in techniques:
            print("Running technique", technique, "on dataset", dataset_name)
            rows.append(run_technique(dataset, dataset_name, technique, args))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(latex_table(rows, threshold=args.threshold, techniques=techniques), encoding="utf-8")
    if args.csv_output:
        write_csv(args.csv_output, rows)
    if args.json_output:
        write_json(args.json_output, rows, threshold=args.threshold)

    print(args.output)
    if args.csv_output:
        print(args.csv_output)
    if args.json_output:
        print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
