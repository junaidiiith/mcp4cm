#!/usr/bin/env python3
"""Plot contrastive-GNN duplicate counts over fixed similarity thresholds.

The GraphCL encoder is trained (or reloaded from its corpus-scoped cache) exactly
once. Its resulting pair scores are then filtered in memory for each threshold.

Example:
    python3 scripts/plot_gnn_embedding_thresholds.py eamodelset-json --data-dir data
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (REPOSITORY_ROOT, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from plot_embedding_thresholds import THRESHOLDS, plot, rows_for_thresholds, write_csv  # noqa: E402
from run_duplicate_detection import (  # noqa: E402
    DEFAULT_DATA_DIR,
    TechniqueProgressBar,
    dataset_choices,
    load_prepared_dataset,
    parse_data_dir_arg,
)

from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    data_dir = parse_data_dir_arg(argv)
    parser = argparse.ArgumentParser(description="Plot contrastive-GNN duplicate counts by threshold.")
    parser.add_argument(
        "dataset",
        choices=dataset_choices(data_dir),
        help="Prepared dataset directory name below --data-dir.",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        help="Embedding cache root (default: <data-dir>/.mcp4cm_embeddings).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for CSV, JSON, and PNG output (default: gnn-threshold-results/<dataset>).",
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


def training_config(args: argparse.Namespace) -> GNNTrainingConfig:
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


def main() -> int:
    args = parse_args()
    dataset = load_prepared_dataset(args.data_dir, args.dataset)
    cache_dir = args.embedding_cache_dir or (args.data_dir / ".mcp4cm_embeddings")
    output_dir = args.output_dir or (REPOSITORY_ROOT / "gnn-threshold-results" / args.dataset)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Threshold zero trains/reloads exactly once. Every requested threshold is
    # positive, so filtering this result is equivalent to rerunning the detector.
    progress = TechniqueProgressBar("gnn", enabled=not args.no_progress)
    try:
        triples = gnn_duplicate_pairs(
            dataset,
            threshold=0.0,
            config=training_config(args),
            embedding_cache_dir=cache_dir,
            progress=progress,
        )
    finally:
        progress.close()
    pairs = [SimpleNamespace(left_id=left_id, right_id=right_id, score=score) for left_id, right_id, score in triples]
    rows = rows_for_thresholds(pairs, len(dataset), "gnn", progress_enabled=not args.no_progress)
    results = {"gnn": rows}

    filename_prefix = f"gnn_{args.dataset}"
    (output_dir / f"{filename_prefix}.json").write_text(
        json.dumps(
            {
                "dataset": str(dataset.dataset_type),
                "modelCount": len(dataset),
                "thresholds": list(THRESHOLDS),
                "trainingConfig": asdict(training_config(args)),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / f"{filename_prefix}.csv", results)
    plot(output_dir / f"{filename_prefix}.png", "Contrastive GNN", rows)
    print(f"Saved GNN threshold results to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
