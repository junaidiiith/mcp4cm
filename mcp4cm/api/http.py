from __future__ import annotations

from typing import Any

from flask import request
from werkzeug.datastructures import FileStorage


def read_json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object request body.")
    return data


def read_upload_request() -> dict[str, Any]:
    if request.files or request.form:
        return {
            "language": request.form.get("language", ""),
            "format": request.form.get("format", "json"),
            "includeAttributes": request.form.get("includeAttributes", "true"),
            "includeOperations": request.form.get("includeOperations", "true"),
            "includeParameters": request.form.get("includeParameters", "true"),
            "includeModelRootNode": request.form.get("includeModelRootNode", "true"),
            "resolveExternalRefs": request.form.get("resolveExternalRefs", "true"),
            "files": request.files.getlist("files"),
        }
    return read_json_body()


def parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def parse_positive_int_param(raw_value: Any, field_name: str) -> int | None:
    if raw_value in (None, ""):
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return value


def paginate_items(items: list[dict[str, Any]], *, page: int, page_size: int, item_key: str) -> dict[str, Any]:
    page_size = min(max(page_size, 1), 250)
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    return {
        item_key: items[start : start + page_size],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": total_pages,
    }
