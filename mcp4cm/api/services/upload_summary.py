from __future__ import annotations

from typing import Any

from mcp4cm.core import ModelDiagnostics, ModelRecord


def merge_model_diagnostics(summary: dict[str, Any], model_id: str, diagnostics: ModelDiagnostics) -> None:
    warning_total = int(diagnostics.warning_count or 0)
    if warning_total <= 0:
        return
    warning_types = diagnostics.warnings_by_type or {}
    warning_messages_by_type = diagnostics.warning_messages_by_type or {}
    source_path = str(diagnostics.source_path or "")
    warning_entries_added = 0
    typed_warning_total = 0
    typed_warning_names: list[str] = []
    for warning_type, count in warning_types.items():
        warning_type = str(warning_type)
        warning_count = int(count or 0)
        if warning_count <= 0:
            continue
        typed_warning_total += warning_count
        typed_warning_names.append(warning_type)
        summary["warningsByType"][warning_type] = summary["warningsByType"].get(warning_type, 0) + warning_count
        register_warning_file(summary, source_path, warning_type, warning_count, model_id=model_id)
        type_messages = warning_messages_by_type.get(warning_type) or []
        for message in type_messages:
            append_warning_entry(summary, warning_type, str(message), path=source_path, model_id=model_id)
            warning_entries_added += 1
    summary["warnings"] += warning_total
    fallback_type = typed_warning_names[0] if typed_warning_names else "PARSE_WARNING"
    if warning_entries_added == 0:
        append_warning_entry(
            summary,
            fallback_type,
            "Warning emitted without a detailed parser message.",
            path=source_path,
            model_id=model_id,
        )
        warning_entries_added += 1
    if warning_entries_added < warning_total:
        for _ in range(warning_total - warning_entries_added):
            append_warning_entry(
                summary,
                fallback_type,
                "Warning emitted without a detailed parser message.",
                path=source_path,
                model_id=model_id,
            )
    if typed_warning_total <= 0:
        summary["warningsByType"]["PARSE_WARNING"] = summary["warningsByType"].get("PARSE_WARNING", 0) + warning_total
        register_warning_file(
            summary,
            source_path,
            "PARSE_WARNING",
            warning_total,
            model_id=model_id,
        )


def add_upload_warning(
    summary: dict[str, Any],
    warning_type: str,
    message: str,
    *,
    path: str = "",
    model_id: str = "",
) -> None:
    summary["warnings"] += 1
    summary["warningsByType"][warning_type] = summary["warningsByType"].get(warning_type, 0) + 1
    append_warning_entry(summary, warning_type, message, path=path, model_id=model_id)
    if path:
        register_warning_file(summary, path, warning_type, 1, model_id=model_id)


def empty_upload_summary() -> dict[str, Any]:
    return {
        "files": 0,
        "payloads": 0,
        "records": 0,
        "errors": 0,
        "emptyFiles": [],
        "invalidFiles": [],
        "ignoredFiles": [],
        "warnings": 0,
        "warningsByType": {},
        "warningsList": [],
        "warningFiles": [],
        "parsedModels": [],
        "_warningFileIndex": {},
    }


def append_warning_entry(
    summary: dict[str, Any],
    warning_type: str,
    message: str,
    *,
    path: str = "",
    model_id: str = "",
) -> None:
    entry = {
        "type": str(warning_type),
        "message": str(message),
        "path": str(path or ""),
    }
    if model_id:
        entry["modelId"] = str(model_id)
    summary["warningsList"].append(entry)


def register_warning_file(
    summary: dict[str, Any],
    path: str,
    warning_type: str,
    count: int,
    *,
    model_id: str = "",
) -> None:
    if not path:
        return
    warning_file_index = summary.setdefault("_warningFileIndex", {})
    existing_index = warning_file_index.get(path)
    if existing_index is None:
        entry = {
            "path": path,
            "warnings": 0,
            "types": {},
            "modelId": str(model_id or ""),
            "hasDetails": True,
        }
        summary["warningFiles"].append(entry)
        existing_index = len(summary["warningFiles"]) - 1
        warning_file_index[path] = existing_index
    entry = summary["warningFiles"][existing_index]
    if model_id:
        existing_model_id = str(entry.get("modelId") or "")
        if existing_model_id and existing_model_id != model_id:
            entry["modelId"] = ""
        elif not existing_model_id:
            entry["modelId"] = str(model_id)
    entry["warnings"] = int(entry.get("warnings", 0)) + int(count)
    types = entry.setdefault("types", {})
    types[warning_type] = int(types.get(warning_type, 0)) + int(count)


def build_parsed_models_summary(summary: dict[str, Any], records: list[ModelRecord]) -> list[dict[str, Any]]:
    warnings_by_model: dict[str, dict[str, Any]] = {}
    for warning in summary.get("warningsList") or []:
        if not isinstance(warning, dict):
            continue
        model_id = str(warning.get("modelId") or "")
        if not model_id:
            continue
        warning_type = str(warning.get("type") or "PARSE_WARNING")
        row = warnings_by_model.setdefault(model_id, {"warnings": 0, "types": {}})
        row["warnings"] += 1
        row["types"][warning_type] = int(row["types"].get(warning_type, 0)) + 1

    parsed_models: list[dict[str, Any]] = []
    for record in records:
        model_id = str(record.model_id or "")
        warning_info = warnings_by_model.get(model_id, {"warnings": 0, "types": {}})
        parsed_models.append(
            {
                "modelId": model_id,
                "name": str(record.name or ""),
                "path": str(record.source_path or ""),
                "language": str(record.language or ""),
                "nodeCount": record.node_count,
                "edgeCount": record.edge_count,
                "warnings": int(warning_info.get("warnings", 0)),
                "types": dict(warning_info.get("types", {})),
            }
        )
    return parsed_models


def finalize_upload_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary.pop("parsedModels", None)
    summary.pop("_warningFileIndex", None)
    return summary
