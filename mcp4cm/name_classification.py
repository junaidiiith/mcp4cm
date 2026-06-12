from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from mcp4cm.xmi_names import EMPTY_NAME_SENTINEL, normalize_identifier

NameClassification = Literal["missing", "type_like", "placeholder", "semantic"]

PLACEHOLDER_KEYWORDS = {
    "dummy",
    "test",
    "todo",
    "sample",
    "example",
    "foo",
    "bar",
    "temp",
    "tmp",
    "asdf",
    "placeholder",
    "untitled",
    "no name",
    "new model",
    "model",
    "class",
    "my class",
    "entity",
    "node",
    "package",
    "component",
    "attribute",
    "control flow",
    "empty name",
    "att",
}

PLACEHOLDER_PATTERNS = (
    re.compile(r"^my\s+class\s*\d*$", re.IGNORECASE),
    re.compile(r"^att(\s+[A-Za-z]|\s+\d+|[a-z0-9])?$", re.IGNORECASE),
    re.compile(r"^(class|entity|node|model|package|component|attribute|type)[\s_-]*\d*$", re.IGNORECASE),
    re.compile(r"^[A-Za-z]\d$", re.IGNORECASE),
    re.compile(r"^[A-Za-z]\s[A-Za-z]$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class NameSlotClassification:
    raw_name: str
    raw_type: str
    normalized_name: str
    normalized_type: str
    classification: NameClassification
    tokens: tuple[str, ...]


def classify_name_slot(raw_name: object, raw_type: object = "") -> NameSlotClassification:
    normalized_name = normalize_name(raw_name)
    normalized_type = normalize_type(raw_type)
    if not normalized_name or normalized_name == EMPTY_NAME_SENTINEL:
        classification: NameClassification = "missing"
    elif is_type_like_name(normalized_name, normalized_type):
        classification = "type_like"
    elif is_placeholder_name(normalized_name):
        classification = "placeholder"
    else:
        classification = "semantic"
    return NameSlotClassification(
        raw_name=str(raw_name or ""),
        raw_type=str(raw_type or ""),
        normalized_name=normalized_name,
        normalized_type=normalized_type,
        classification=classification,
        tokens=tuple(sorted(tokenize_name(normalized_name))),
    )


def normalize_name(value: object) -> str:
    return normalize_identifier(value)


def normalize_type(value: object) -> str:
    return normalize_identifier(value)


def is_type_like_name(normalized_name: str, normalized_type: str) -> bool:
    compact_name = compact_identifier(normalized_name)
    compact_type = compact_identifier(normalized_type)
    if not compact_name or not compact_type:
        return False
    if compact_name == compact_type:
        return True
    if compact_name.startswith(compact_type):
        suffix = compact_name[len(compact_type) :]
        return bool(suffix) and suffix.isdigit()
    return False


def is_placeholder_name(normalized_name: str) -> bool:
    if normalized_name in PLACEHOLDER_KEYWORDS:
        return True
    return any(pattern.match(normalized_name) for pattern in PLACEHOLDER_PATTERNS)


def tokenize_name(value: str) -> set[str]:
    return {match.group(0).lower() for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", value)}


def compact_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).lower()
