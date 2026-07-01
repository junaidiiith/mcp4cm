#!/usr/bin/env python3
"""Run duplicate detection for one prepared dataset in ``data/``.

Examples:
    python scripts/run_duplicate_detection.py eamodelset-json
    python scripts/run_duplicate_detection.py sap-sam-bpmn --technique tfidf graph-similarity
    python scripts/run_duplicate_detection.py modelset-uml-json --technique hash tfidf graph-similarity
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - tqdm is a project dependency
    tqdm = None

# Make the script runnable from a source checkout without requiring an editable install.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from mcp4cm.core import Dataset
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    detect_duplicates_by_name_hash,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs
from mcp4cm.parsers.parse import parse_files


DEFAULT_DATA_DIR = REPOSITORY_ROOT / "data"
LOG = logging.getLogger(__name__)

DATASET_PARSERS = {
    "eamodelset-json": ("archimate", "json"),
    "eamodelset-archimate": ("archimate", "xmi"),
    "sap-sam-bpmn": ("bpmn", "signavio"),
    "modelset-uml-json": ("uml", "json"),
    "modelset-uml-xmi": ("uml", "xmi"),
    "modelset-ecore-json": ("ecore", "json"),
    "modelset-ecore-xmi": ("ecore", "ecore"),
}


def dataset_choices(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[str, ...]:
    if not data_dir.is_dir():
        return tuple(sorted(DATASET_PARSERS))
    return tuple(
        sorted(
            path.name
            for path in data_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".") and path.name != "__MACOSX"
        )
    )


def parse_data_dir_arg(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args, _ = parser.parse_known_args(argv)
    return args.data_dir


class TechniqueProgressBar:
    """Adapt detector progress events to one terminal progress bar per technique."""

    def __init__(self, technique: str, *, enabled: bool) -> None:
        self.technique = technique
        self.enabled = enabled and tqdm is not None
        self.bar = None
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


def duplicate_models_removed_from_groups(groups: list[Any]) -> int:
    """Return models removed when one representative is retained per duplicate group."""
    return sum(max(len(group.model_ids) - 1, 0) for group in groups)


def duplicate_models_removed_from_pairs(pairs: list[Any]) -> int:
    """Return models removed when one representative is retained per connected pair component."""
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    data_dir = parse_data_dir_arg(argv)
    parser = argparse.ArgumentParser(description="Run duplicate detection on a dataset below data/.")
    parser.add_argument(
        "dataset",
        choices=dataset_choices(data_dir),
        help="Dataset directory name below --data-dir.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing datasets (default: {DEFAULT_DATA_DIR}).",
    )
    parser.add_argument(
        "--technique",
        action="append",
        nargs="+",
        choices=("hash", "tfidf", "graph-similarity", "node2vec", "gnn", "bert-similarity", "isomorphism"),
        default=None,
        help="Detection method(s) to run. Repeat the option or pass several names (default: hash).",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.9, help="Similarity threshold for TF-IDF and graph methods."
    )
    parser.add_argument(
        "--include-types", action="store_true", help="Include node types in hash and TF-IDF comparisons."
    )
    parser.add_argument("--min-named-nodes", type=int, default=0, help="Minimum names required for hash comparison.")
    parser.add_argument(
        "--deduplicate-name-tokens",
        action="store_true",
        help="Ignore repeated name tokens when hashing.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path instead of stdout.")
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        help="Directory containing dataset/graph embedding caches (default: <data-dir>/.mcp4cm_embeddings).",
    )
    parser.add_argument("--gnn-epochs", type=int, default=20, help="Contrastive GNN training epochs.")
    parser.add_argument("--gnn-dimensions", type=int, default=128, help="Contrastive GNN graph-vector dimension.")
    parser.add_argument("--gnn-layers", type=int, default=2, help="Edge-aware GNN message-passing layers.")
    parser.add_argument("--gnn-learning-rate", type=float, default=1e-3, help="Contrastive GNN learning rate.")
    parser.add_argument("--gnn-temperature", type=float, default=0.2, help="NT-Xent contrastive temperature.")
    parser.add_argument("--gnn-edge-dropout", type=float, default=0.15, help="Edge dropout used for GraphCL views.")
    parser.add_argument("--gnn-feature-mask-rate", type=float, default=0.10, help="Node feature masking used for GraphCL views.")
    parser.add_argument("--gnn-batch-size", type=int, default=32, help="Graphs per contrastive GNN batch.")
    parser.add_argument("--gnn-model-name", default="sentence-transformers/all-MiniLM-L6-v2", help="Sentence-transformer model for node and edge text.")
    parser.add_argument("--gnn-seed", type=int, default=42, help="Contrastive GNN random seed.")
    parser.add_argument("--gnn-device", choices=("auto", "cpu", "cuda"), default="auto", help="GNN training device.")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bars.")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Minimum log level written to stderr (default: INFO).",
    )
    return parser.parse_args(argv)


def dataset_parser(dataset_name: str) -> tuple[str, str]:
    try:
        return DATASET_PARSERS[dataset_name]
    except KeyError as exc:
        supported = ", ".join(sorted(DATASET_PARSERS))
        raise ValueError(f"Unsupported dataset '{dataset_name}'. Supported datasets: {supported}.") from exc


def load_prepared_dataset(data_dir: Path, dataset_name: str) -> Dataset:
    if Path(dataset_name).name != dataset_name:
        raise ValueError("dataset must be a directory name, not a path.")

    language, data_format = dataset_parser(dataset_name)
    root = data_dir / dataset_name
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {root}")

    extensions = {
        "json": "*.json",
        "signavio": "*.json",
        "xmi": "*.archimate" if language == "archimate" else "*.xmi",
        "ecore": "*.ecore",
    }
    files = sorted(root.rglob(extensions[data_format]))
    if not files:
        raise FileNotFoundError(f"No {extensions[data_format]} files found in {root}")

    LOG.info("Parsing dataset=%s files=%d parser=%s/%s", dataset_name, len(files), language, data_format)
    started = time.perf_counter()
    parsed = parse_files(files, language=language, format=data_format)
    LOG.info(
        "Parsed dataset=%s models=%d issues=%d elapsedMs=%d",
        dataset_name,
        len(parsed.records),
        len(parsed.issues),
        round((time.perf_counter() - started) * 1000),
    )
    if parsed.issues:
        print(f"Warning: {len(parsed.issues)} file(s) could not be parsed.", file=sys.stderr)
    if not parsed.records:
        raise ValueError(
            f"No models were parsed from {root}. Install project dependencies and inspect parser errors above."
        )
    return Dataset(records=parsed.records, dataset_type=dataset_name, root=root, diagnostics=parsed.diagnostics)


def run_detection(dataset: Dataset, args: argparse.Namespace) -> dict[str, object]:
    techniques = [technique for group in args.technique for technique in group] if args.technique else ["hash"]
    result: dict[str, object] = {
        "dataset": str(dataset.dataset_type),
        "techniques": techniques,
        "results": {},
        "timingsMs": {},
    }
    results: dict[str, object] = result["results"]  # type: ignore[assignment]
    timings_ms: dict[str, int] = result["timingsMs"]  # type: ignore[assignment]
    embedding_cache_dir = args.embedding_cache_dir or (args.data_dir / ".mcp4cm_embeddings")

    def run_technique(
        name: str,
        compute: Callable[[Callable[[dict[str, Any]], None]], list[Any]],
        count_removed: Callable[[list[Any]], int],
    ) -> None:
        LOG.info("Starting technique=%s models=%d", name, len(dataset))
        started = time.perf_counter()
        progress = TechniqueProgressBar(name, enabled=not args.no_progress)
        try:
            items = compute(progress)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            LOG.exception("Failed technique=%s elapsedMs=%d", name, elapsed_ms)
            raise
        finally:
            progress.close()
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        duplicate_models_removed = count_removed(items)
        results[name] = {
            "initialTotalModels": len(dataset),
            "duplicateModelsRemoved": duplicate_models_removed,
            "uniqueModelsRemaining": len(dataset) - duplicate_models_removed,
        }
        timings_ms[name] = elapsed_ms
        LOG.info(
            "Finished technique=%s duplicateModelsRemoved=%d uniqueModelsRemaining=%d elapsedMs=%d",
            name,
            duplicate_models_removed,
            len(dataset) - duplicate_models_removed,
            elapsed_ms,
        )

    if "hash" in techniques:
        run_technique(
            "hash",
            lambda progress: detect_duplicates_by_name_hash(
                dataset,
                include_types=args.include_types,
                min_named_nodes=args.min_named_nodes,
                deduplicate_name_tokens=args.deduplicate_name_tokens,
                progress=progress,
            ),
            duplicate_models_removed_from_groups,
        )
    if "tfidf" in techniques:
        run_technique(
            "tfidf",
            lambda progress: tfidf_duplicate_pairs(
                dataset,
                token_mode="names_types_bag" if args.include_types else "names",
                threshold=args.threshold,
                technique="tfidf",
                progress=progress,
            ),
            duplicate_models_removed_from_pairs,
        )
    if "graph-similarity" in techniques:
        run_technique(
            "graph-similarity",
            lambda progress: graph_similarity_pairs(dataset, threshold=args.threshold, progress=progress),
            duplicate_models_removed_from_pairs,
        )
    if "node2vec" in techniques:
        run_technique(
            "node2vec",
            lambda progress: graph_embedding_pairs(
                dataset, threshold=args.threshold, embedding_cache_dir=embedding_cache_dir, progress=progress
            ),
            duplicate_models_removed_from_pairs,
        )
    if "gnn" in techniques:
        config = GNNTrainingConfig(
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
        run_technique(
            "gnn",
            lambda progress: [
                type("GNNPair", (), {"left_id": left, "right_id": right, "score": score})
                for left, right, score in gnn_duplicate_pairs(
                    dataset, threshold=args.threshold, config=config, embedding_cache_dir=embedding_cache_dir, progress=progress
                )
            ],
            duplicate_models_removed_from_pairs,
        )
    if "bert-similarity" in techniques:
        run_technique(
            "bert-similarity",
            lambda progress: bert_semantic_similarity_pairs(
                dataset, threshold=args.threshold, embedding_cache_dir=embedding_cache_dir, progress=progress
            ),
            duplicate_models_removed_from_pairs,
        )
    if "isomorphism" in techniques:
        run_technique(
            "isomorphism",
            lambda progress: graph_isomorphism_pairs(dataset, progress=progress),
            duplicate_models_removed_from_pairs,
        )
    return result


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        report = run_detection(load_prepared_dataset(args.data_dir, args.dataset), args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{output}\n", encoding="utf-8")
        print(f"Wrote duplicate report to {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
