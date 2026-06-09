from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from mcp4cm.core import ModelRecord

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def record_names(record: ModelRecord) -> list[str]:
    return record.names


def record_tokens(record: ModelRecord) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(record.text_for_similarity())]


def canonical_graph_payload(record: ModelRecord) -> dict[str, Any]:
    nodes = []
    for _, attrs in record.graph.nodes(data=True):
        nodes.append(
            {
                "name": _clean(attrs.get("name")),
                "type": _clean(attrs.get("type") or attrs.get("eClass")),
                "layer": _clean(attrs.get("layer")),
            }
        )
    edges = []
    for source, target, attrs in record.graph.edges(data=True):
        edges.append(
            {
                "source": str(source),
                "target": str(target),
                "type": _clean(attrs.get("type") or attrs.get("relationship")),
            }
        )
    return {
        "language": record.language,
        "nodes": sorted(nodes, key=lambda item: json.dumps(item, sort_keys=True)),
        "edges": sorted(edges, key=lambda item: json.dumps(item, sort_keys=True)),
    }


def canonical_graph_hash(record: ModelRecord, algorithm: str = "sha256") -> str:
    payload = json.dumps(canonical_graph_payload(record), sort_keys=True, separators=(",", ":"))
    hasher = hashlib.new(algorithm)
    hasher.update(payload.encode("utf-8"))
    return hasher.hexdigest()


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip().lower()
