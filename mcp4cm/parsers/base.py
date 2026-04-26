from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from mcp4cm.core import ModelRecord

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class BaseModelParser(ABC):
    """Base class for language-specific parsers.

    Subclasses are responsible for converting source records into a
    ``ModelRecord``. Generic cleansing features consume only that normalized
    output, so adding a new language such as BPMN should not require changes in
    duplicate detection, statistics, or dummy filters.
    """

    language: str

    @abstractmethod
    def parse(self, raw: Mapping[str, Any], *, model_id: str | None = None) -> ModelRecord:
        """Parse one raw dataset item into a normalized model record."""

    def names(self, record: ModelRecord) -> list[str]:
        return record.names

    def tokens(self, record: ModelRecord) -> list[str]:
        return [match.group(0).lower() for match in TOKEN_RE.finditer(record.text_for_similarity())]

    def canonical_payload(self, record: ModelRecord) -> dict[str, Any]:
        nodes = []
        for _, attrs in record.graph.nodes(data=True):
            nodes.append(
                {
                    "name": self._clean(attrs.get("name")),
                    "type": self._clean(attrs.get("type") or attrs.get("eClass")),
                    "layer": self._clean(attrs.get("layer")),
                }
            )
        edges = []
        for source, target, attrs in record.graph.edges(data=True):
            edges.append(
                {
                    "source": str(source),
                    "target": str(target),
                    "type": self._clean(attrs.get("type") or attrs.get("relationship")),
                }
            )
        return {
            "language": record.language,
            "nodes": sorted(nodes, key=lambda item: json.dumps(item, sort_keys=True)),
            "edges": sorted(edges, key=lambda item: json.dumps(item, sort_keys=True)),
        }

    def canonical_hash(self, record: ModelRecord, algorithm: str = "sha256") -> str:
        payload = json.dumps(self.canonical_payload(record), sort_keys=True, separators=(",", ":"))
        hasher = hashlib.new(algorithm)
        hasher.update(payload.encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _clean(value: Any) -> str:
        return "" if value is None else str(value).strip().lower()

