from __future__ import annotations

import time
from typing import Any


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))  # type: ignore[return-value]


def pair_lookup_key(left_id: str, right_id: str) -> str:
    left, right = pair_key(left_id, right_id)
    return f"{left}\u0000{right}"


def pair_count(item_count: int) -> int:
    return item_count * (item_count - 1) // 2


def elapsed_ms(started_at: float, finished_at: float | None = None) -> int:
    return round(((finished_at or time.time()) - started_at) * 1000)


def parse_bool(value: Any, *, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def progress_percent(current: int, total: int, *, zero_total: int = 100, clamp: bool = False) -> int:
    if total <= 0:
        return zero_total
    percent = round((current / total) * 100)
    if clamp:
        return min(max(percent, 0), 100)
    return percent
