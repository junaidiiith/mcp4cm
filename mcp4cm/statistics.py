from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from mcp4cm.core import Dataset, ModelRecord


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    node_counts = [record.node_count for record in dataset]
    edge_counts = [record.edge_count for record in dataset]
    model_name_counts = [len(node_names(record)) for record in dataset]
    return {
        "models": len(dataset),
        "languages": dict(Counter(record.language for record in dataset)),
        "labels": dict(Counter(label for record in dataset for label in record.labels)),
        "nodes": _distribution(node_counts),
        "edges": _distribution(edge_counts),
        "names": _distribution(model_name_counts),
    }


def type_counts(dataset: Dataset) -> Counter[str]:
    return Counter(type_name for record in dataset for type_name in record.types if type_name)


def name_counts(dataset: Dataset) -> Counter[str]:
    return Counter(name.strip() for record in dataset for name in node_names(record) if name.strip())


def model_statistics(record: ModelRecord) -> dict[str, Any]:
    return {
        "id": record.model_id,
        "language": record.language,
        "labels": record.labels,
        "nodes": record.node_count,
        "edges": record.edge_count,
        "names": len(node_names(record)),
        "types": dict(Counter(record.types)),
    }


def node_names(record: ModelRecord) -> list[str]:
    return [str(attrs.get("name")) for _, attrs in record.graph.nodes(data=True) if attrs.get("name")]


def _distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "median": median(values),
    }
