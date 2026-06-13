from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from mcp4cm.api.state import (
    AFTER_DUMMY_STATISTICS_JOBS,
    AFTER_DUMMY_STATISTICS_LOCK,
    DATASETS,
    LABEL_PIPELINE_CACHE,
    LABEL_PIPELINE_CACHE_LOCK,
)
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
from mcp4cm.statistics import label_pipeline_items, model_summary_fields, typed_name_entries

LABEL_PIPELINE_SORT_KEYS = {
    "rawName",
    "normalizedName",
    "rawType",
    "normalizedType",
    "classification",
    "occurrences",
    "documentFrequency",
}


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


def get_label_pipeline_page(
    dataset_id: str,
    *,
    snapshot: str = "before",
    page: int = 1,
    page_size: int = 50,
    query: str = "",
    classification: str = "all",
    sort: str = "documentFrequency",
    order: str = "desc",
) -> dict[str, Any]:
    dataset_id = str(dataset_id or "")
    if get_dataset_meta(dataset_id) is None:
        raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")

    snapshot = "after" if str(snapshot or "").strip().lower() == "after" else "before"
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 250))
    sort = sort if sort in LABEL_PIPELINE_SORT_KEYS else "documentFrequency"
    reverse = str(order or "desc").lower() != "asc"

    rows = _label_pipeline_rows_for_snapshot(dataset_id, snapshot)
    rows = _filter_label_pipeline_rows(rows, query=query, classification=classification)
    _sort_label_pipeline_rows(rows, sort=sort, reverse=reverse)

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    page = min(page, total_pages) if total_pages else 1
    start = (page - 1) * page_size
    return {
        "datasetId": dataset_id,
        "snapshot": snapshot,
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
        "rows": rows[start : start + page_size],
    }


def _label_pipeline_rows_for_snapshot(dataset_id: str, snapshot: str) -> list[dict[str, Any]]:
    retained_model_ids = None
    cache_snapshot = snapshot
    if snapshot == "after":
        if load_dataset_after_dummy_statistics(dataset_id) is None:
            raise ValueError("After-cleansing statistics are unavailable for this dataset.")
        retained_model_ids = load_dataset_after_dummy_retained_model_ids(dataset_id)
        if retained_model_ids is None:
            raise ValueError("After-cleansing retained model IDs are unavailable for this dataset.")
        cache_snapshot = f"after:{_retained_model_ids_signature(retained_model_ids)}"

    cache_key = f"{dataset_id}:{cache_snapshot}"
    with LABEL_PIPELINE_CACHE_LOCK:
        cached = LABEL_PIPELINE_CACHE.get(cache_key)
    if cached is not None:
        return [dict(row) for row in cached]

    dataset = get_dataset_by_id(dataset_id)
    rows = _build_label_pipeline_rows(dataset, retained_model_ids=retained_model_ids)
    with LABEL_PIPELINE_CACHE_LOCK:
        LABEL_PIPELINE_CACHE[cache_key] = [dict(row) for row in rows]
    return rows


def _build_label_pipeline_rows(
    dataset: Dataset | RuntimeDataset,
    *,
    retained_model_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    occurrence_counter: Counter[tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str]] = Counter()
    document_frequency_counter: Counter[tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str]] = Counter()

    for record in dataset:
        if retained_model_ids is not None and str(record.model_id) not in retained_model_ids:
            continue
        model_label_rows = set()
        for entry in typed_name_entries(record):
            key = (
                str(entry.get("rawName", "")),
                str(entry.get("normalizedName", entry.get("name", ""))),
                str(entry.get("rawType", "")),
                str(entry.get("normalizedType", "")),
                tuple(str(token) for token in entry.get("nameTokens", ())),
                tuple(str(token) for token in entry.get("typeTokens", ())),
                str(entry.get("classification", "")),
            )
            occurrence_counter[key] += 1
            model_label_rows.add(key)
        document_frequency_counter.update(model_label_rows)

    return label_pipeline_items(occurrence_counter, document_frequency_counter, limit=len(occurrence_counter))


def _filter_label_pipeline_rows(
    rows: list[dict[str, Any]],
    *,
    query: str,
    classification: str,
) -> list[dict[str, Any]]:
    classification = str(classification or "all").strip().lower()
    if classification in {"semantic", "placeholder", "missing"}:
        rows = [row for row in rows if str(row.get("classification") or "") == classification]

    lowered_query = str(query or "").strip().lower()
    if not lowered_query:
        return rows
    return [row for row in rows if lowered_query in _label_pipeline_search_text(row)]


def _label_pipeline_search_text(row: dict[str, Any]) -> str:
    tokens = [*row.get("nameTokens", []), *row.get("typeTokens", [])]
    return " ".join(
        [
            str(row.get("rawName") or ""),
            str(row.get("normalizedName") or ""),
            str(row.get("rawType") or ""),
            str(row.get("normalizedType") or ""),
            str(row.get("classification") or ""),
            " ".join(str(token) for token in tokens),
        ]
    ).lower()


def _sort_label_pipeline_rows(rows: list[dict[str, Any]], *, sort: str, reverse: bool) -> None:
    def tie_breakers(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(row.get("normalizedName") or "").lower(),
            str(row.get("rawName") or "").lower(),
            str(row.get("normalizedType") or "").lower(),
            str(row.get("rawType") or "").lower(),
            str(row.get("classification") or "").lower(),
        )

    if sort in {"occurrences", "documentFrequency"}:
        rows.sort(
            key=lambda row: (
                -int(row.get(sort) or 0) if reverse else int(row.get(sort) or 0),
                *tie_breakers(row),
            )
        )
        return

    rows.sort(key=lambda row: (str(row.get(sort) or "").lower(), *tie_breakers(row)), reverse=reverse)


def _retained_model_ids_signature(model_ids: set[str]) -> str:
    digest = hashlib.sha1()
    for model_id in sorted(model_ids):
        digest.update(model_id.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
    return f"{len(model_ids)}:{digest.hexdigest()}"


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
