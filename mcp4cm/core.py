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
        if self.name:
            names.append(self.name)
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
        return values

    def text_for_similarity(self, include_types: bool = True) -> str:
        parts = self.names
        if include_types:
            parts = [*parts, *self.types]
        if self.raw_text:
            parts.append(self.raw_text)
        return " ".join(parts)


@dataclass(slots=True)
class Dataset:
    """A collection of normalized model records."""

    records: list[ModelRecord]
    dataset_type: DatasetType | str
    root: Path | None = None

    def __iter__(self) -> Iterable[ModelRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> ModelRecord:
        return self.records[index]

    def ids(self) -> list[str]:
        return [record.model_id for record in self.records]
