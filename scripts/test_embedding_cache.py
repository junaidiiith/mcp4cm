#!/usr/bin/env python3
"""Exercise embedding persistence by computing and then reloading a prepared dataset.

Example:
    python scripts/test_embedding_cache.py eamodelset-json --data-dir data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from run_duplicate_detection import DEFAULT_DATA_DIR, load_prepared_dataset  # noqa: E402

from mcp4cm.duplicates import bert_semantic_similarity_pairs, graph_embedding_pairs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute and reload Node2Vec and BERT embedding caches.")
    parser.add_argument("dataset", help="Prepared dataset directory name below --data-dir.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, help="Cache root (default: <data-dir>/.mcp4cm_embeddings).")
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--bert-model", default="sentence-transformers/all-MiniLM-L6-v2")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = load_prepared_dataset(args.data_dir, args.dataset)
    cache_dir = args.cache_dir or (args.data_dir / ".mcp4cm_embeddings")

    first_node2vec = graph_embedding_pairs(dataset, threshold=args.threshold, embedding_cache_dir=cache_dir)
    first_bert = bert_semantic_similarity_pairs(
        dataset,
        threshold=args.threshold,
        model_name=args.bert_model,
        embedding_cache_dir=cache_dir,
    )
    expected = [
        cache_dir / str(dataset.dataset_type) / record.model_id / technique
        for record in dataset
        for technique in ("node2vec.npz", "bert.npz")
    ]
    missing = [path for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Embedding cache files were not written: {', '.join(map(str, missing))}")

    second_node2vec = graph_embedding_pairs(dataset, threshold=args.threshold, embedding_cache_dir=cache_dir)
    second_bert = bert_semantic_similarity_pairs(
        dataset,
        threshold=args.threshold,
        model_name=args.bert_model,
        embedding_cache_dir=cache_dir,
    )
    if first_node2vec != second_node2vec or first_bert != second_bert:
        raise RuntimeError("Reloaded embedding results differ from the initial computation.")

    print(f"Embedding cache verified: {cache_dir / str(dataset.dataset_type)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
