from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ModelingLanguage(str, Enum):
    UML = "uml"
    ECORE = "ecore"
    ARCHIMATE = "archimate"
    BPMN = "bpmn"


class DatasetType(str, Enum):
    MODELSET = "modelset"
    MODELSET_UML = "modelset_uml"
    MODELSET_ECORE = "modelset_ecore"
    EAMODELSET = "eamodelset"


@dataclass(slots=True)
class ModelRecord:
    """Normalized model representation used across the library."""

    model_id: str
    language: str
    graph: Any
    labels: tuple[str, ...] = ()
    name: str | None = None
    source_path: Path | None = None
    raw_text: str = ""
    raw_xmi: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    @property
    def names(self) -> list[str]:
        names: list[str] = []
        for _, attrs in self.graph.nodes(data=True):
            value = attrs.get("name")
            if value:
                names.append(str(value))
        return names

    @property
    def types(self) -> list[str]:
        values: list[str] = []
        for _, attrs in self.graph.nodes(data=True):
            value = attrs.get("type") or attrs.get("eClass")
            if value:
                values.append(str(value))
        for _, _, attrs in self.graph.edges(data=True):
            value = attrs.get("type") or attrs.get("relationship") or attrs.get("label")
            if value:
                values.append(str(value))
        return values

    def text_for_similarity(self, include_types: bool = True) -> str:
        parts = self.names
        if include_types:
            parts = [*parts, *self.types]
        if self.raw_text:
            parts.append(self.raw_text)
        return " ".join(parts)


@dataclass(slots=True)
class ModelDiagnostics:
    """Parser-neutral diagnostics for a parsed model."""

    parse_status: str
    warning_count: int = 0
    warnings_by_type: dict[str, int] = field(default_factory=dict)
    warning_messages_by_type: dict[str, list[str]] = field(default_factory=dict)
    error_message: str = ""
    elements_loaded: int = 0
    elements_skipped: int = 0
    parse_time_ms: int = 0
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parseStatus": self.parse_status,
            "warningCount": self.warning_count,
            "warningsByType": dict(self.warnings_by_type),
            "warningMessagesByType": {key: list(messages) for key, messages in self.warning_messages_by_type.items()},
            "errorMessage": self.error_message,
            "elementsLoaded": self.elements_loaded,
            "elementsSkipped": self.elements_skipped,
            "parseTimeMs": self.parse_time_ms,
            "sourcePath": self.source_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ModelDiagnostics":
        payload = payload or {}
        return cls(
            parse_status=str(payload.get("parseStatus") or payload.get("parse_status") or "success"),
            warning_count=int(payload.get("warningCount") or payload.get("warning_count") or 0),
            warnings_by_type=dict(payload.get("warningsByType") or payload.get("warnings_by_type") or {}),
            warning_messages_by_type={
                str(key): [str(message) for message in (messages or [])]
                for key, messages in dict(payload.get("warningMessagesByType") or payload.get("warning_messages_by_type") or {}).items()
            },
            error_message=str(payload.get("errorMessage") or payload.get("error_message") or ""),
            elements_loaded=int(payload.get("elementsLoaded") or payload.get("elements_loaded") or 0),
            elements_skipped=int(payload.get("elementsSkipped") or payload.get("elements_skipped") or 0),
            parse_time_ms=int(payload.get("parseTimeMs") or payload.get("parse_time_ms") or 0),
            source_path=str(payload.get("sourcePath") or payload.get("source_path") or ""),
        )


@dataclass(slots=True)
class Dataset:
    """A collection of normalized model records."""

    records: list[ModelRecord]
    dataset_type: DatasetType | str
    root: Path | None = None
    diagnostics: dict[str, ModelDiagnostics] = field(default_factory=dict)

    def __iter__(self) -> Iterable[ModelRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> ModelRecord:
        return self.records[index]

    def ids(self) -> list[str]:
        return [record.model_id for record in self.records]
