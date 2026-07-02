#!/usr/bin/env python3
"""Plot duplicate-model counts for BERT, graph similarity, TF-IDF, and GNN.

Each selected technique is computed exactly once at a zero threshold. The
resulting pair scores are filtered in memory for every requested threshold.

Example:
    python3 scripts/plot_embedding_thresholds.py eamodelset-json --data-dir data
    python3 scripts/plot_embedding_thresholds.py sap-sam-bpmn --data-dir data
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (REPOSITORY_ROOT, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_duplicate_detection import (  # noqa: E402
    DEFAULT_DATA_DIR,
    TechniqueProgressBar,
    duplicate_models_removed_from_pairs,
    load_prepared_dataset,
    tqdm,
)

from mcp4cm.duplicates import (  # noqa: E402
    bert_semantic_similarity_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs  # noqa: E402

THRESHOLDS = tuple(round(index * 0.05, 2) for index in range(1, 21))
TECHNIQUES = ("bert", "graph-similarity", "tfidf", "gnn")
DEFAULT_DATASETS = ("modelset-uml-xmi", "modelset-ecore-xmi", "eamodelset-archimate", "sap-sam-bpmn")
DATASET_ALIASES = {
    "sap-sam": "sap-sam-bpmn",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot BERT, graph-similarity, TF-IDF, and GNN duplicate counts by threshold."
    )
    parser.add_argument(
        "dataset",
        nargs="?",
        help=(
            "Prepared dataset directory name below --data-dir. "
            f"If omitted, all default datasets are processed: {', '.join(DEFAULT_DATASETS)}."
        ),
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help=(
            "Dataset directory or alias to process. Repeat to select multiple datasets. "
            f"Default when no positional dataset is given: {', '.join(DEFAULT_DATASETS)}."
        ),
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--technique",
        action="append",
        nargs="+",
        choices=TECHNIQUES,
        default=None,
        help=(
            f"Technique(s) to plot. Repeat the option or provide several names (default: all: {', '.join(TECHNIQUES)})."
        ),
    )
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        help="Embedding cache root (default: <data-dir>/.mcp4cm_embeddings).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for CSV, JSON, and PNG output (default: thresholds-results/<dataset>).",
    )
    parser.add_argument("--bert-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--bert-batch-size", type=int, default=8)
    parser.add_argument("--bert-max-length", type=int, default=256)
    parser.add_argument(
        "--tfidf-token-mode",
        choices=("names", "names_types_bag", "typed_name_pairs"),
        default="names_types_bag",
        help="TF-IDF text representation (default: names_types_bag).",
    )
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


def selected_datasets(args: argparse.Namespace) -> list[str]:
    if args.datasets:
        return [canonical_dataset(dataset) for dataset in args.datasets]
    if args.dataset:
        return [canonical_dataset(args.dataset)]
    return list(DEFAULT_DATASETS)


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


def rows_for_thresholds(
    pairs: list[Any], model_count: int, technique: str, *, progress_enabled: bool
) -> list[dict[str, int | float]]:
    rows: list[dict[str, int | float]] = []
    progress = (
        tqdm(total=len(THRESHOLDS), desc=f"{technique}: thresholds", unit="threshold", dynamic_ncols=True)
        if (progress_enabled and tqdm is not None)
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


def write_csv(path: Path, technique_rows: dict[str, list[dict[str, int | float]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("technique", "threshold", "duplicates", "unique", "matchingPairs"))
        writer.writeheader()
        for technique, rows in technique_rows.items():
            for row in rows:
                writer.writerow({"technique": technique, **row})


def plot(path: Path, technique: str, rows: list[dict[str, int | float]], model_count: int) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install it with `pip install -e '.[plot]'`.") from exc

    thresholds = [float(row["threshold"]) for row in rows]
    duplicates = [int(row["duplicates"]) / model_count * 100.0 for row in rows]
    unique = [int(row["unique"]) / model_count * 100.0 for row in rows]
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.plot(thresholds, duplicates, marker="o", label="Duplicate models (removed)")
    axis.plot(thresholds, unique, marker="o", label="Unique models")
    axis.set_xlabel("Similarity threshold")
    axis.set_ylabel("Models (%)")
    axis.set_title(f"{technique} duplicate detection")
    axis.set_xlim(0.05, 1.0)
    axis.set_ylim(0, 100)
    axis.set_xticks(THRESHOLDS)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def output_dir_for_dataset(args: argparse.Namespace, dataset_name: str, dataset_count: int) -> Path:
    if args.output_dir is None:
        return REPOSITORY_ROOT / "thresholds-results" / dataset_name
    if dataset_count == 1:
        return args.output_dir
    return args.output_dir / dataset_name


def run_dataset(
    args: argparse.Namespace, dataset_name: str, selected_techniques: list[str], dataset_count: int
) -> Path:
    dataset = load_prepared_dataset(args.data_dir, dataset_name)
    cache_dir = args.embedding_cache_dir or (args.data_dir / ".mcp4cm_embeddings")
    output_dir = output_dir_for_dataset(args, dataset_name, dataset_count)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Threshold zero computes each representation once. All requested
    # thresholds are positive, so filtering is equivalent to rerunning a
    # detector without repeating vectorization or contrastive training.
    technique_pairs: dict[str, list[Any]] = {}
    if "bert" in selected_techniques:
        progress = TechniqueProgressBar("bert", enabled=not args.no_progress)
        try:
            technique_pairs["bert"] = bert_semantic_similarity_pairs(
                dataset,
                threshold=0.0,
                model_name=args.bert_model,
                batch_size=args.bert_batch_size,
                max_length=args.bert_max_length,
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
        finally:
            progress.close()
    if "graph-similarity" in selected_techniques:
        progress = TechniqueProgressBar("graph-similarity", enabled=not args.no_progress)
        try:
            technique_pairs["graph-similarity"] = graph_similarity_pairs(dataset, threshold=0.0, progress=progress)
        finally:
            progress.close()
    if "tfidf" in selected_techniques:
        progress = TechniqueProgressBar("tfidf", enabled=not args.no_progress)
        try:
            technique_pairs["tfidf"] = tfidf_duplicate_pairs(
                dataset,
                threshold=0.0,
                token_mode=args.tfidf_token_mode,
                technique="tfidf",
                progress=progress,
            )
        finally:
            progress.close()
    if "gnn" in selected_techniques:
        progress = TechniqueProgressBar("gnn", enabled=not args.no_progress)
        try:
            gnn_triples = gnn_duplicate_pairs(
                dataset,
                threshold=0.0,
                config=gnn_training_config(args),
                embedding_cache_dir=cache_dir,
                progress=progress,
            )
        finally:
            progress.close()
        technique_pairs["gnn"] = [
            SimpleNamespace(left_id=left_id, right_id=right_id, score=score) for left_id, right_id, score in gnn_triples
        ]

    technique_rows = {
        technique: rows_for_thresholds(
            technique_pairs[technique], len(dataset), technique, progress_enabled=not args.no_progress
        )
        for technique in selected_techniques
    }

    for technique, rows in technique_rows.items():
        filename_prefix = technique
        payload: dict[str, Any] = {
            "technique": technique,
            "dataset": str(dataset.dataset_type),
            "modelCount": len(dataset),
            "thresholds": list(THRESHOLDS),
            "results": rows,
        }
        if technique == "tfidf":
            payload["tfidfTokenMode"] = args.tfidf_token_mode
        elif technique == "gnn":
            payload["gnnTrainingConfig"] = asdict(gnn_training_config(args))
        elif technique == "bert":
            payload["bertModel"] = args.bert_model
        elif technique == "graph-similarity":
            payload["graphSimilarity"] = {"threshold": 0.0}
        (output_dir / f"{filename_prefix}.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        write_csv(output_dir / f"{filename_prefix}.csv", {technique: rows})
        plot(output_dir / f"{filename_prefix}.png", technique, rows, len(dataset))

    print(f"Saved results to {output_dir}")
    return output_dir


def main() -> int:
    args = parse_args()
    datasets = selected_datasets(args)
    selected_techniques = (
        [technique for group in args.technique for technique in group] if args.technique else list(TECHNIQUES)
    )

    for dataset_name in datasets:
        run_dataset(args, dataset_name, selected_techniques, len(datasets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
