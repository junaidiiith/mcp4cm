from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from mcp4cm.core import Dataset, ModelRecord


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    node_counts = [record.node_count for record in dataset]
    edge_counts = [record.edge_count for record in dataset]
    name_counts = [len(record.names) for record in dataset]
    return {
        "models": len(dataset),
        "languages": dict(Counter(record.language for record in dataset)),
        "labels": dict(Counter(label for record in dataset for label in record.labels)),
        "nodes": _distribution(node_counts),
        "edges": _distribution(edge_counts),
        "names": _distribution(name_counts),
    }


def type_counts(dataset: Dataset) -> Counter[str]:
    return Counter(type_name for record in dataset for type_name in record.types if type_name)


def name_counts(dataset: Dataset) -> Counter[str]:
    return Counter(name.strip() for record in dataset for name in record.names if name.strip())


def word_counts(dataset: Dataset, *, min_length: int = 2) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in dataset:
        for token in _tokens(record):
            if len(token) >= min_length:
                counter[token] += 1
    return counter


def model_statistics(record: ModelRecord) -> dict[str, Any]:
    return {
        "id": record.model_id,
        "language": record.language,
        "labels": record.labels,
        "nodes": record.node_count,
        "edges": record.edge_count,
        "names": len(record.names),
        "types": dict(Counter(record.types)),
    }


def _distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "median": median(values),
    }


def _tokens(record: ModelRecord) -> list[str]:
    import re

    return [match.group(0).lower() for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", record.text_for_similarity())]

