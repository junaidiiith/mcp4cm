from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp4cm._deps import require_networkx
from mcp4cm.core import ModelRecord, ModelingLanguage


class ArchimateJsonParser:
    language = ModelingLanguage.ARCHIMATE.value

    def parse(self, raw: Mapping[str, Any], *, model_id: str | None = None) -> ModelRecord:
        nx = require_networkx()
        graph = nx.DiGraph(language=self.language)

        for element in raw.get("elements", []):
            attrs = dict(element)
            node_id = str(attrs.pop("id"))
            graph.add_node(node_id, **attrs)

        for relationship in raw.get("relationships", []):
            attrs = dict(relationship)
            source = attrs.pop("sourceId")
            target = attrs.pop("targetId")
            rel_id = attrs.pop("id", None)
            if rel_id:
                attrs["relationship_id"] = rel_id
            graph.add_edge(source, target, **attrs)

        tags = raw.get("tags") or ()
        return ModelRecord(
            model_id=model_id or str(raw.get("archimateId") or raw.get("identifier") or ""),
            language=self.language,
            graph=graph,
            labels=tuple(str(tag) for tag in tags),
            name=raw.get("name"),
            raw_text=" ".join(
                value
                for value in [str(raw.get("name") or ""), str(raw.get("description") or "")]
                if value
            ),
            metadata={
                "identifier": raw.get("identifier"),
                "source": raw.get("source"),
                "language": raw.get("language"),
                "source_file": raw.get("sourceFile"),
                "duplicates": raw.get("duplicates") or [],
                "views": raw.get("views") or [],
            },
        )
