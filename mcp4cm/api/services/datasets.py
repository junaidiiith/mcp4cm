from __future__ import annotations

from typing import Any

from mcp4cm.api.state import AFTER_DUMMY_STATISTICS_JOBS, AFTER_DUMMY_STATISTICS_LOCK, DATASETS
from mcp4cm.core import Dataset
from mcp4cm.dummy import default_filter_configs
from mcp4cm.runtime_store import (
    RuntimeDataset,
    get_dataset_meta,
    json_safe,
    load_dataset_after_dummy_retained_model_ids,
    load_dataset_after_dummy_statistics,
    load_dataset_statistics,
    load_model_from_runtime,
    resolve_dataset,
)
from mcp4cm.statistics import model_summary_fields


def default_dummy_filter_configs(language: str) -> list[dict[str, Any]]:
    _ = language
    return default_filter_configs()


def get_dataset(body: dict[str, Any]) -> Dataset | RuntimeDataset:
    dataset_id = str(body.get("datasetId") or "")
    if dataset_id in DATASETS:
        return DATASETS[dataset_id]
    dataset = resolve_dataset(dataset_id)
    DATASETS[dataset_id] = dataset
    return dataset


def get_dataset_by_id(dataset_id: str) -> Dataset | RuntimeDataset:
    dataset_id = str(dataset_id)
    if dataset_id in DATASETS:
        return DATASETS[dataset_id]
    dataset = resolve_dataset(dataset_id)
    DATASETS[dataset_id] = dataset
    return dataset


def get_duplicate_detection_dataset(body: dict[str, Any]) -> Dataset | RuntimeDataset:
    dataset = get_dataset(body)
    dataset_id = str(body.get("datasetId") or "")
    retained_model_ids = load_dataset_after_dummy_retained_model_ids(dataset_id)
    if retained_model_ids is None:
        return dataset
    records = [record for record in dataset if str(record.model_id) in retained_model_ids]
    return Dataset(
        records=records,
        dataset_type=getattr(dataset, "dataset_type", "runtime"),
        root=getattr(dataset, "root", None),
        diagnostics=getattr(dataset, "diagnostics", {}),
    )


def serialize_statistics(dataset: Dataset | RuntimeDataset) -> dict[str, Any]:
    if isinstance(dataset, RuntimeDataset):
        statistics = load_dataset_statistics(dataset.dataset_id)
        if statistics is None:
            raise ValueError("Statistics are unavailable for this runtime dataset.")
        return statistics
    return build_statistics_payload(dataset)


def build_statistics_payload(
    records, *, skip_topic_model: bool = False, topic_model_skip_reason: str = ""
) -> dict[str, Any]:
    from mcp4cm.statistics import CorpusStatisticsAccumulator

    accumulator = CorpusStatisticsAccumulator()
    for record in records:
        accumulator.add(record)
    return accumulator.build_payload(skip_topic_model=skip_topic_model, topic_model_skip_reason=topic_model_skip_reason)


def get_dataset_statistics(dataset_id: str) -> dict[str, Any]:
    if get_dataset_meta(dataset_id) is None:
        raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")
    statistics = load_dataset_statistics(dataset_id)
    if statistics is None:
        raise ValueError("Statistics are unavailable for this dataset.")
    return statistics


def get_dataset_status(dataset_id: str) -> dict[str, Any]:
    dataset_id = str(dataset_id or "")
    meta = get_dataset_meta(dataset_id)
    if meta is None:
        return {
            "datasetId": dataset_id,
            "available": False,
            "statisticsAvailable": False,
            "recordCount": 0,
        }
    return {
        "datasetId": dataset_id,
        "available": True,
        "statisticsAvailable": load_dataset_statistics(dataset_id) is not None,
        "recordCount": int(meta.get("recordCount") or 0),
        "datasetType": str(meta.get("datasetType") or "runtime"),
    }


def get_dataset_after_dummy_statistics(dataset_id: str) -> dict[str, Any]:
    if get_dataset_meta(dataset_id) is None:
        raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")
    statistics = load_dataset_after_dummy_statistics(dataset_id)
    if statistics is None:
        raise ValueError("After-cleansing statistics are unavailable for this dataset.")
    return statistics


def get_dataset_after_dummy_statistics_response(dataset_id: str) -> dict[str, Any]:
    if get_dataset_meta(dataset_id) is None:
        raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")
    statistics = load_dataset_after_dummy_statistics(dataset_id)
    if statistics is not None:
        return statistics
    with AFTER_DUMMY_STATISTICS_LOCK:
        job = dict(AFTER_DUMMY_STATISTICS_JOBS.get(str(dataset_id)) or {})
    return {
        "status": job.get("status") or "pending",
        "jobId": job.get("jobId") or "",
        "error": job.get("error") or "",
    }


def top_items(counter, limit: int | None = None) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def model_summary_lookup(dataset: Dataset | RuntimeDataset) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for record in dataset:
        try:
            summary = model_summary_fields(record)
        except Exception:
            summary = {
                "modelId": str(record.model_id),
                "nodeCount": int(record.node_count),
                "edgeCount": int(record.edge_count),
                "namedElements": 0,
            }
        summaries[str(record.model_id)] = summary
    return summaries


def inspect_dataset_model(
    *,
    dataset_id: str,
    model_id: str,
    include_attrs: bool = True,
) -> dict[str, Any]:
    loaded = load_model_from_runtime(str(dataset_id), str(model_id or ""))
    if loaded is None:
        raise ValueError("Unknown modelId for the selected dataset.")
    record, diagnostics = loaded

    nodes: list[dict[str, Any]] = []
    for node_id, attrs in record.graph.nodes(data=True):
        node_entry: dict[str, Any] = {"id": str(node_id)}
        if include_attrs:
            node_entry["attrs"] = json_safe(attrs)
        nodes.append(node_entry)

    edges: list[dict[str, Any]] = []
    if record.graph.is_multigraph():
        for source, target, key, attrs in record.graph.edges(keys=True, data=True):
            edge_entry: dict[str, Any] = {"source": str(source), "target": str(target), "key": str(key)}
            if include_attrs:
                edge_entry["attrs"] = json_safe(attrs)
            edges.append(edge_entry)
    else:
        for source, target, attrs in record.graph.edges(data=True):
            edge_entry = {"source": str(source), "target": str(target)}
            if include_attrs:
                edge_entry["attrs"] = json_safe(attrs)
            edges.append(edge_entry)

    return {
        "model": {
            "id": str(record.model_id),
            "language": str(record.language),
            "name": str(record.name or ""),
            "sourcePath": str(record.source_path or ""),
            "nodeCount": int(record.node_count),
            "edgeCount": int(record.edge_count),
            "metadata": json_safe(record.metadata),
        },
        "diagnostics": json_safe(diagnostics.to_dict()),
        "nodes": nodes,
        "edges": edges,
    }
