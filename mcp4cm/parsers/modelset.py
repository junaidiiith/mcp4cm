from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from mcp4cm._deps import require_networkx
from mcp4cm.core import ModelRecord, ModelingLanguage
from mcp4cm.parsers.base import BaseModelParser


class ModelSetParser(BaseModelParser):
    language: str

    def parse(self, raw: Mapping[str, Any], *, model_id: str | None = None) -> ModelRecord:
        graph_payload = raw.get("graph") or "{}"
        if isinstance(graph_payload, str):
            graph_payload = json.loads(graph_payload)

        graph = self._parse_graph(graph_payload)
        labels = raw.get("labels", ())
        if isinstance(labels, str):
            labels = (labels,)
        else:
            labels = tuple(str(label) for label in labels)

        return ModelRecord(
            model_id=model_id or str(raw.get("ids") or raw.get("id") or ""),
            language=str(raw.get("model_type") or self.language),
            graph=graph,
            labels=labels,
            raw_text=str(raw.get("txt") or ""),
            raw_xmi=str(raw.get("xmi") or ""),
            metadata={
                "is_duplicated": raw.get("is_duplicated"),
                "source": "modelset",
            },
        )

    def _parse_graph(self, payload: Mapping[str, Any]):
        nx = require_networkx()
        graph_cls = nx.MultiDiGraph if payload.get("multigraph") else nx.DiGraph
        graph = graph_cls()
        graph.graph["directed"] = bool(payload.get("directed", True))
        graph.graph["language"] = self.language

        for index, node in enumerate(payload.get("nodes", [])):
            attrs = dict(node)
            node_id = attrs.pop("id", index)
            graph.add_node(node_id, **attrs)

        for edge in payload.get("links", payload.get("edges", [])):
            attrs = dict(edge)
            source = attrs.pop("source")
            target = attrs.pop("target")
            graph.add_edge(source, target, **attrs)
        return graph


class UMLParser(ModelSetParser):
    language = ModelingLanguage.UML.value


class EcoreParser(ModelSetParser):
    language = ModelingLanguage.ECORE.value

