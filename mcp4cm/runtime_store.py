from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from mcp4cm._deps import require_networkx
from mcp4cm.core import Dataset, ModelDiagnostics, ModelRecord
from mcp4cm.statistics import model_summary_fields

RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
RUNTIME_LOCK = threading.RLock()


def runtime_dataset_dir(dataset_id: str) -> Path:
    return RUNTIME_DIR / str(dataset_id)


def runtime_dataset_ir_dir(dataset_id: str) -> Path:
    return runtime_dataset_dir(dataset_id) / "ir"


def runtime_dataset_index_path(dataset_id: str) -> Path:
    return runtime_dataset_dir(dataset_id) / "index.json"


def runtime_dataset_statistics_path(dataset_id: str) -> Path:
    return runtime_dataset_dir(dataset_id) / "statistics.json"


def runtime_dataset_after_dummy_statistics_path(dataset_id: str) -> Path:
    return runtime_dataset_dir(dataset_id) / "statistics-after-dummy.json"


def runtime_dataset_after_dummy_retained_models_path(dataset_id: str) -> Path:
    return runtime_dataset_dir(dataset_id) / "retained-models-after-dummy.json"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:  # pragma: no cover - best effort only
            return str(value)
    return str(value)


def runtime_index_template(
    *,
    dataset_id: str = "",
    dataset_type: str = "",
    model_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": time.time(),
        "datasetId": str(dataset_id),
        "datasetType": str(dataset_type),
        "createdAt": time.time(),
        "recordCount": len(model_entries or []),
        "models": model_entries or [],
    }


def ensure_runtime_store(dataset_id: str | None = None) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if dataset_id:
        runtime_dataset_ir_dir(dataset_id).mkdir(parents=True, exist_ok=True)


def load_runtime_index(dataset_id: str) -> dict[str, Any] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return None
    index_path = runtime_dataset_index_path(dataset_id)
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    payload.setdefault("version", 1)
    payload.setdefault("updatedAt", time.time())
    payload.setdefault("datasetId", dataset_id)
    payload.setdefault("datasetType", "runtime")
    payload.setdefault("createdAt", payload.get("updatedAt") or time.time())
    payload.setdefault("recordCount", len(payload.get("models") or []))
    payload.setdefault("models", [])
    if not isinstance(payload["models"], list):
        payload["models"] = []
    return payload


def save_runtime_index(dataset_id: str, index_payload: dict[str, Any]) -> None:
    index_payload["updatedAt"] = time.time()
    ensure_runtime_store(dataset_id)
    index_path = runtime_dataset_index_path(dataset_id)
    temp_path = index_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(index_path)


def runtime_model_filename(model_id: str, index: int, seen: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(model_id or "").strip()) or f"model_{index + 1}"
    candidate = f"{base}.json"
    counter = 1
    while candidate in seen:
        candidate = f"{base}_{counter}.json"
        counter += 1
    seen.add(candidate)
    return candidate


def _flatten_runtime_attrs(attrs: Any, *, skip_keys: set[str]) -> dict[str, Any]:
    if not isinstance(attrs, dict):
        return {}
    flattened: dict[str, Any] = {}
    for raw_key, raw_value in attrs.items():
        key = str(raw_key)
        if key == "attrs" or key in skip_keys:
            continue
        flattened[key] = json_safe(raw_value)
    return flattened


def _drop_runtime_data_duplicates(payload: dict[str, Any], *, protected_keys: set[str]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload
    for key in list(payload.keys()):
        if key == "data" or key in protected_keys:
            continue
        if key in data and payload.get(key) == data.get(key):
            payload.pop(key, None)
    return payload


def serialize_graph_for_runtime(graph) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "directed": bool(graph.is_directed()),
        "multigraph": bool(graph.is_multigraph()),
        "graphAttrs": json_safe(dict(graph.graph)),
        "nodes": [],
        "edges": [],
    }
    for node_id, attrs in graph.nodes(data=True):
        node_entry: dict[str, Any] = {"id": json_safe(node_id)}
        node_entry.update(_flatten_runtime_attrs(attrs, skip_keys={"id"}))
        payload["nodes"].append(
            _drop_runtime_data_duplicates(
                node_entry,
                protected_keys={"id", "type", "name"},
            )
        )
    if graph.is_multigraph():
        for source, target, key, attrs in graph.edges(keys=True, data=True):
            edge_entry: dict[str, Any] = {
                "source": json_safe(source),
                "target": json_safe(target),
                "key": json_safe(key),
            }
            edge_entry.update(_flatten_runtime_attrs(attrs, skip_keys=set()))
            if "id" not in edge_entry and edge_entry.get("key") is not None:
                edge_entry["id"] = edge_entry["key"]
            payload["edges"].append(
                _drop_runtime_data_duplicates(
                    edge_entry,
                    protected_keys={"source", "target", "key", "id", "type"},
                )
            )
    else:
        for source, target, attrs in graph.edges(data=True):
            edge_entry = {"source": json_safe(source), "target": json_safe(target)}
            edge_entry.update(_flatten_runtime_attrs(attrs, skip_keys=set()))
            payload["edges"].append(
                _drop_runtime_data_duplicates(
                    edge_entry,
                    protected_keys={"source", "target", "id", "type"},
                )
            )
    return payload


def serialize_model_for_runtime(record: ModelRecord, diagnostics: ModelDiagnostics | None = None) -> dict[str, Any]:
    return {
        "modelId": str(record.model_id),
        "language": str(record.language),
        "labels": [str(label) for label in record.labels],
        "name": str(record.name or ""),
        "sourcePath": str(record.source_path or ""),
        "rawText": str(record.raw_text or ""),
        "rawXmi": str(record.raw_xmi or ""),
        "metadata": json_safe(record.metadata if isinstance(record.metadata, dict) else {}),
        "parseDiagnostics": json_safe(diagnostics.to_dict() if diagnostics else {}),
        "graph": serialize_graph_for_runtime(record.graph),
    }


def deserialize_graph_from_runtime(payload: dict[str, Any]):
    nx = require_networkx()
    directed = bool(payload.get("directed", True))
    multigraph = bool(payload.get("multigraph", False))
    graph_cls = (
        nx.MultiDiGraph
        if directed and multigraph
        else nx.DiGraph
        if directed
        else nx.MultiGraph
        if multigraph
        else nx.Graph
    )
    graph = graph_cls()
    graph.graph.update(payload.get("graphAttrs") or {})
    for node in payload.get("nodes") or []:
        node_id = node.get("id")
        attrs: dict[str, Any] = {}
        legacy_attrs = node.get("attrs")
        if isinstance(legacy_attrs, dict):
            attrs.update(legacy_attrs)
        for key, value in (node or {}).items():
            if key in {"id", "attrs"}:
                continue
            attrs[str(key)] = value
        graph.add_node(node_id, **attrs)
    for edge in payload.get("edges") or []:
        source = edge.get("source")
        target = edge.get("target")
        attrs: dict[str, Any] = {}
        legacy_attrs = edge.get("attrs")
        if isinstance(legacy_attrs, dict):
            attrs.update(legacy_attrs)
        for key, value in (edge or {}).items():
            if key in {"source", "target", "key", "attrs"}:
                continue
            attrs[str(key)] = value
        if multigraph:
            edge_key = edge.get("key")
            if edge_key is None:
                edge_key = attrs.get("id")
            graph.add_edge(source, target, key=edge_key, **attrs)
        else:
            graph.add_edge(source, target, **attrs)
    return graph


def deserialize_model_from_runtime(payload: dict[str, Any]) -> ModelRecord:
    graph_payload = payload.get("graph")
    if not isinstance(graph_payload, dict):
        raise ValueError("Persisted model graph payload is missing or invalid.")
    source_path = str(payload.get("sourcePath") or "")
    return ModelRecord(
        model_id=str(payload.get("modelId") or ""),
        language=str(payload.get("language") or ""),
        graph=deserialize_graph_from_runtime(graph_payload),
        labels=tuple(str(label) for label in (payload.get("labels") or [])),
        name=str(payload.get("name") or "") or None,
        source_path=Path(source_path) if source_path else None,
        raw_text=str(payload.get("rawText") or ""),
        raw_xmi=str(payload.get("rawXmi") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )


def deserialize_diagnostics_from_runtime(payload: dict[str, Any]) -> ModelDiagnostics:
    diagnostics_payload = payload.get("parseDiagnostics")
    return ModelDiagnostics.from_dict(diagnostics_payload if isinstance(diagnostics_payload, dict) else {})


def build_model_summary(record: ModelRecord, diagnostics: ModelDiagnostics | None = None) -> dict[str, Any]:
    diagnostics = diagnostics or ModelDiagnostics("success")
    summary = model_summary_fields(record)
    summary["warnings"] = int(diagnostics.warning_count)
    summary["types"] = dict(diagnostics.warnings_by_type)
    return summary


def summary_from_model_entry(model_entry: dict[str, Any]) -> dict[str, Any]:
    summary = model_entry.get("summary")
    if isinstance(summary, dict):
        return {
            "modelId": str(summary.get("modelId") or model_entry.get("modelId") or ""),
            "name": str(summary.get("name") or ""),
            "path": str(summary.get("path") or ""),
            "language": str(summary.get("language") or model_entry.get("language") or ""),
            "nodeCount": int(summary.get("nodeCount") or 0),
            "edgeCount": int(summary.get("edgeCount") or 0),
            "warnings": int(summary.get("warnings") or 0),
            "types": dict(summary.get("types") or {}),
        }
    return {
        "modelId": str(model_entry.get("modelId") or ""),
        "name": "",
        "path": "",
        "language": str(model_entry.get("language") or ""),
        "nodeCount": 0,
        "edgeCount": 0,
        "warnings": 0,
        "types": {},
    }


def spill_model_to_runtime(
    *,
    dataset_id: str,
    dataset_dir: Path,
    record: ModelRecord,
    diagnostics: ModelDiagnostics | None,
    filename: str,
) -> dict[str, Any]:
    model_payload = serialize_model_for_runtime(record, diagnostics)
    (dataset_dir / filename).write_text(json.dumps(model_payload, ensure_ascii=False), encoding="utf-8")
    return {
        "modelId": str(record.model_id),
        "file": filename,
        "language": str(record.language),
        "summary": build_model_summary(record, diagnostics),
    }


def finalize_runtime_dataset(
    *,
    dataset_id: str,
    dataset_type: str,
    model_entries: list[dict[str, Any]],
) -> None:
    with RUNTIME_LOCK:
        index_payload = runtime_index_template(
            dataset_id=dataset_id,
            dataset_type=str(dataset_type),
            model_entries=model_entries,
        )
        save_runtime_index(dataset_id, index_payload)


def save_dataset_statistics(dataset_id: str, statistics: dict[str, Any]) -> None:
    with RUNTIME_LOCK:
        ensure_runtime_store(dataset_id)
        statistics_path = runtime_dataset_statistics_path(dataset_id)
        temp_path = statistics_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(json_safe(statistics), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(statistics_path)


def save_dataset_after_dummy_statistics(dataset_id: str, statistics: dict[str, Any]) -> None:
    with RUNTIME_LOCK:
        ensure_runtime_store(dataset_id)
        statistics_path = runtime_dataset_after_dummy_statistics_path(dataset_id)
        temp_path = statistics_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(json_safe(statistics), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(statistics_path)


def delete_dataset_after_dummy_statistics(dataset_id: str) -> None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return
    with RUNTIME_LOCK:
        runtime_dataset_after_dummy_statistics_path(dataset_id).unlink(missing_ok=True)


def save_dataset_after_dummy_retained_model_ids(dataset_id: str, model_ids: set[str] | list[str] | tuple[str, ...]) -> None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return
    payload = {
        "version": 1,
        "updatedAt": time.time(),
        "datasetId": dataset_id,
        "retainedModelIds": sorted(str(model_id) for model_id in model_ids),
    }
    with RUNTIME_LOCK:
        ensure_runtime_store(dataset_id)
        retained_path = runtime_dataset_after_dummy_retained_models_path(dataset_id)
        temp_path = retained_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(retained_path)


def delete_dataset_after_dummy_retained_model_ids(dataset_id: str) -> None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return
    with RUNTIME_LOCK:
        runtime_dataset_after_dummy_retained_models_path(dataset_id).unlink(missing_ok=True)


def load_dataset_after_dummy_retained_model_ids(dataset_id: str) -> set[str] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return None
    retained_path = runtime_dataset_after_dummy_retained_models_path(dataset_id)
    if not retained_path.exists():
        return None
    with RUNTIME_LOCK:
        try:
            payload = json.loads(retained_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    raw_ids = payload.get("retainedModelIds")
    if not isinstance(raw_ids, list):
        return None
    return {str(model_id) for model_id in raw_ids}


def load_dataset_statistics(dataset_id: str) -> dict[str, Any] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return None
    statistics_path = runtime_dataset_statistics_path(dataset_id)
    if not statistics_path.exists():
        return None
    with RUNTIME_LOCK:
        try:
            payload = json.loads(statistics_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return payload if isinstance(payload, dict) else None


def load_dataset_after_dummy_statistics(dataset_id: str) -> dict[str, Any] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return None
    statistics_path = runtime_dataset_after_dummy_statistics_path(dataset_id)
    if not statistics_path.exists():
        return None
    with RUNTIME_LOCK:
        try:
            payload = json.loads(statistics_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return payload if isinstance(payload, dict) else None


def get_dataset_meta(dataset_id: str) -> dict[str, Any] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id:
        return None
    with RUNTIME_LOCK:
        dataset_meta = load_runtime_index(dataset_id)
        return dict(dataset_meta) if isinstance(dataset_meta, dict) else None


def model_entry_by_id(dataset_meta: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    model_id = str(model_id or "")
    for model_entry in dataset_meta.get("models") or []:
        if isinstance(model_entry, dict) and str(model_entry.get("modelId") or "") == model_id:
            return model_entry
    return None


def load_model_from_runtime(dataset_id: str, model_id: str) -> tuple[ModelRecord, ModelDiagnostics] | None:
    dataset_id = str(dataset_id or "")
    model_id = str(model_id or "")
    if not dataset_id or not model_id:
        return None
    with RUNTIME_LOCK:
        dataset_meta = get_dataset_meta(dataset_id)
        if dataset_meta is None:
            return None
        model_entry = model_entry_by_id(dataset_meta, model_id)
        if model_entry is None:
            return None
        filename = str(model_entry.get("file") or "")
        if not filename:
            return None
        model_path = runtime_dataset_ir_dir(dataset_id) / filename
        if not model_path.exists():
            return None
        model_payload = json.loads(model_path.read_text(encoding="utf-8"))
    record = deserialize_model_from_runtime(model_payload)
    diagnostics = deserialize_diagnostics_from_runtime(model_payload)
    return record, diagnostics


def load_model_entry_from_runtime(dataset_id: str, model_entry: dict[str, Any]) -> tuple[ModelRecord, ModelDiagnostics] | None:
    dataset_id = str(dataset_id or "")
    if not dataset_id or not isinstance(model_entry, dict):
        return None
    filename = str(model_entry.get("file") or "")
    if not filename:
        return None
    model_path = runtime_dataset_ir_dir(dataset_id) / filename
    with RUNTIME_LOCK:
        if not model_path.exists():
            return None
        try:
            model_payload = json.loads(model_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    record = deserialize_model_from_runtime(model_payload)
    diagnostics = deserialize_diagnostics_from_runtime(model_payload)
    return record, diagnostics


def iter_models_from_runtime(dataset_id: str) -> Iterator[ModelRecord]:
    dataset_meta = get_dataset_meta(dataset_id)
    if dataset_meta is None:
        return
    for model_entry in dataset_meta.get("models") or []:
        if not isinstance(model_entry, dict):
            continue
        loaded = load_model_entry_from_runtime(dataset_id, model_entry)
        if loaded is not None:
            yield loaded[0]


@dataclass(slots=True)
class RuntimeDataset:
    """Dataset backed by runtime JSON; models are loaded on demand."""

    dataset_id: str
    dataset_type: str
    record_count: int
    model_entries: list[dict[str, Any]] = field(default_factory=list)
    root: Path | None = None
    diagnostics: dict[str, ModelDiagnostics] = field(default_factory=dict)

    @classmethod
    def from_meta(cls, dataset_id: str, meta: dict[str, Any]) -> RuntimeDataset:
        model_entries = [dict(entry) for entry in (meta.get("models") or []) if isinstance(entry, dict)]
        return cls(
            dataset_id=str(dataset_id),
            dataset_type=str(meta.get("datasetType") or "runtime"),
            record_count=int(meta.get("recordCount") or len(model_entries)),
            model_entries=model_entries,
            root=runtime_dataset_ir_dir(dataset_id),
        )

    def __len__(self) -> int:
        return self.record_count

    def __iter__(self) -> Iterator[ModelRecord]:
        return iter_models_from_runtime(self.dataset_id)

    @property
    def records(self) -> list[ModelRecord]:
        return list(self)

    def summaries(self) -> list[dict[str, Any]]:
        return [summary_from_model_entry(entry) for entry in self.model_entries]


def list_dataset_models(
    dataset_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
    query: str = "",
    sort: str = "modelId",
    order: str = "asc",
    warning_type: str = "",
) -> dict[str, Any]:
    meta = get_dataset_meta(dataset_id)
    if meta is None:
        raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 500))
    summaries = [summary_from_model_entry(entry) for entry in meta.get("models") or [] if isinstance(entry, dict)]

    lowered_query = str(query or "").strip().lower()
    warning_type = str(warning_type or "").strip()
    if warning_type and warning_type != "all":
        summaries = [row for row in summaries if row.get("types", {}).get(warning_type)]
    if lowered_query:
        summaries = [
            row
            for row in summaries
            if lowered_query in str(row.get("modelId") or "").lower()
            or lowered_query in str(row.get("name") or "").lower()
            or lowered_query in str(row.get("path") or "").lower()
            or any(
                lowered_query in f"{warning_key} {warning_count}".lower()
                for warning_key, warning_count in (row.get("types") or {}).items()
            )
        ]

    sort_key = str(sort or "modelId")
    reverse = str(order or "asc").lower() == "desc"
    if sort_key in {"nodeCount", "edgeCount", "warnings"}:
        summaries.sort(key=lambda row: int(row.get(sort_key) or 0), reverse=reverse)
    elif sort_key == "path":
        summaries.sort(key=lambda row: str(row.get("path") or "").lower(), reverse=reverse)
    else:
        summaries.sort(key=lambda row: str(row.get("modelId") or "").lower(), reverse=reverse)

    total = len(summaries)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "datasetId": str(dataset_id),
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, (total + page_size - 1) // page_size) if total else 0,
        "models": summaries[start:end],
    }


def resolve_dataset(dataset_id: str) -> Dataset | RuntimeDataset:
    meta = get_dataset_meta(dataset_id)
    if meta is not None:
        return RuntimeDataset.from_meta(dataset_id, meta)
    raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")
