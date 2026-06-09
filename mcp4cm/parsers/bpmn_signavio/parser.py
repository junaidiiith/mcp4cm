"""BPMN Signavio JSON parser."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp4cm.parsers.ir import Edge, IR, Node
from mcp4cm.parsers.base import BaseParser, register_parser
from mcp4cm.parsers.diagnostics import CannotParseError, ParserRunStats, WarningType

# In Signavio/Oryx JSON, these stencils are modeled as connector shapes.
EDGE_STENCIL_IDS = {
    "SequenceFlow",
    "MessageFlow",
    "Association_Unidirectional",
    "Association_Undirected",
    "Association_Bidirectional",
    "ConversationLink",
}


@dataclass
class ShapeRecord:
    """Flattened shape information extracted from nested JSON."""

    id: str
    stencil_id: str
    shape: Dict[str, Any]
    parent_id: Optional[str]
    outgoing_ids: List[str]
    target_id: Optional[str]


def _extract_stencil_id(shape: Dict[str, Any]) -> str:
    stencil = shape.get("stencil")
    if not isinstance(stencil, dict):
        return ""
    stencil_id = stencil.get("id")
    return stencil_id if isinstance(stencil_id, str) else ""


def _extract_outgoing_ids(shape: Dict[str, Any]) -> List[str]:
    outgoing = shape.get("outgoing")
    if not isinstance(outgoing, list):
        return []

    refs: List[str] = []
    for item in outgoing:
        if not isinstance(item, dict):
            continue
        resource_id = item.get("resourceId")
        if isinstance(resource_id, str) and resource_id:
            refs.append(resource_id)
    return refs


def _extract_target_id(shape: Dict[str, Any]) -> Optional[str]:
    target = shape.get("target")
    if isinstance(target, dict):
        target_id = target.get("resourceId")
        if isinstance(target_id, str) and target_id:
            return target_id
    return None


def _compact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep meaningful values while dropping empty placeholders."""
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if value in ("", None, [], {}):
            continue
        result[key] = value
    return result


def _extract_name(shape: Dict[str, Any]) -> str:
    props = shape.get("properties")
    if isinstance(props, dict):
        name = props.get("name")
        if isinstance(name, str):
            return name
    return ""


@register_parser
class BPMNSignavioJSONParser(BaseParser):
    """Parser for BPMN models exported in Signavio/Oryx JSON format."""

    language = "BPMN-Signavio-JSON"

    def parse(self, filepath: str) -> Tuple[IR, ParserRunStats]:
        self._start_run()

        path = Path(filepath)
        if not path.exists():
            raise CannotParseError(f"File does not exist: {filepath}")

        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise CannotParseError(f"Invalid JSON: {exc}") from exc
        except Exception as exc:
            raise CannotParseError(f"Cannot read file as JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise CannotParseError("Expected JSON object as top-level model document.")

        root_stencil = _extract_stencil_id(data)
        if root_stencil != "BPMNDiagram":
            raise CannotParseError(
                "JSON does not look like a Signavio BPMN diagram (missing top-level stencil.id=BPMNDiagram)."
            )

        model_id = data.get("resourceId")
        if not isinstance(model_id, str) or not model_id:
            model_id = path.stem

        root_props = data.get("properties")
        root_props = root_props if isinstance(root_props, dict) else {}
        model_name = root_props.get("name", "")
        model_name = model_name if isinstance(model_name, str) else ""

        ir = IR(
            id=model_id,
            language=self.language,
            data={
                "modelId": model_id,
                "name": model_name,
                "stencilId": root_stencil,
                "stencilset": data.get("stencilset", {}),
                "ssextensions": data.get("ssextensions", []),
                "language": data.get("language", ""),
            },
        )

        records: Dict[str, ShapeRecord] = {}
        order: List[str] = []
        parent_of: Dict[str, Optional[str]] = {}
        incoming_refs: Dict[str, List[str]] = {}

        self._collect_shapes(data, None, records, order, parent_of)
        self._build_incoming_index(records, incoming_refs)
        edge_ids = self._identify_edge_shapes(records)
        node_ids = {shape_id for shape_id in records if shape_id not in edge_ids}

        for shape_id in order:
            if shape_id not in node_ids:
                continue
            rec = records[shape_id]
            node_data = self._build_node_data(rec)
            ir.nodes.append(
                Node(
                    id=rec.id,
                    type=rec.stencil_id,
                    name=_extract_name(rec.shape),
                    data=node_data,
                )
            )

        for shape_id in order:
            if shape_id not in edge_ids:
                continue
            rec = records[shape_id]
            source_id = self._resolve_edge_source(rec, incoming_refs, node_ids)
            target_id = self._resolve_edge_target(rec, node_ids)

            if not source_id or not target_id:
                self.skip_with_warning(
                    WarningType.MISSING_EDGE_ENDPOINT,
                    (
                        f"Skipping edge '{rec.id}' ({rec.stencil_id}) due missing endpoint(s): "
                        f"source='{source_id or ''}', target='{target_id or ''}'."
                    ),
                )
                continue

            if source_id not in node_ids:
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"Edge '{rec.id}' source '{source_id}' does not resolve to a parsed node.",
                )
            if target_id not in node_ids:
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"Edge '{rec.id}' target '{target_id}' does not resolve to a parsed node.",
                )

            ir.edges.append(
                Edge(
                    id=rec.id,
                    sourceId=source_id,
                    targetId=target_id,
                    type=rec.stencil_id,
                    data=self._build_edge_data(rec),
                )
            )

        contains_ids: set[str] = set()
        for child_id, parent_id in parent_of.items():
            if not parent_id:
                continue
            if parent_id not in node_ids or child_id not in node_ids:
                continue

            edge_id = f"contains:{parent_id}->{child_id}"
            if edge_id in contains_ids:
                continue
            contains_ids.add(edge_id)

            ir.edges.append(
                Edge(
                    id=edge_id,
                    sourceId=parent_id,
                    targetId=child_id,
                    type="contains",
                    data={"feature": "childShapes"},
                )
            )

        return ir, self._stats()

    def _collect_shapes(
        self,
        shape: Dict[str, Any],
        parent_id: Optional[str],
        records: Dict[str, ShapeRecord],
        order: List[str],
        parent_of: Dict[str, Optional[str]],
    ) -> None:
        shape_id = shape.get("resourceId")
        if not isinstance(shape_id, str) or not shape_id:
            self.skip_with_warning(
                WarningType.MISSING_ATTRIBUTE,
                f"Encountered shape without resourceId under parent '{parent_id or ''}', skipping shape.",
            )
            return

        stencil_id = _extract_stencil_id(shape)
        if not stencil_id:
            self.skip_with_warning(
                WarningType.UNKNOWN_NODE_TYPE,
                f"Shape '{shape_id}' has no stencil.id; skipping shape.",
            )
            return

        if shape_id in records:
            self.skip_with_warning(
                WarningType.DUPLICATE_ID,
                f"Duplicate shape resourceId '{shape_id}', keeping first occurrence.",
            )
            return

        rec = ShapeRecord(
            id=shape_id,
            stencil_id=stencil_id,
            shape=shape,
            parent_id=parent_id,
            outgoing_ids=_extract_outgoing_ids(shape),
            target_id=_extract_target_id(shape),
        )
        records[shape_id] = rec
        order.append(shape_id)
        parent_of[shape_id] = parent_id

        children = shape.get("childShapes")
        if not isinstance(children, list):
            return

        for child in children:
            if not isinstance(child, dict):
                self.skip_with_warning(
                    WarningType.OTHER,
                    f"Shape '{shape_id}' has non-object child entry in childShapes; skipping child.",
                )
                continue
            self._collect_shapes(child, shape_id, records, order, parent_of)

    def _build_incoming_index(
        self,
        records: Dict[str, ShapeRecord],
        incoming_refs: Dict[str, List[str]],
    ) -> None:
        for rec in records.values():
            for target_ref in rec.outgoing_ids:
                if target_ref not in records:
                    self.warn(
                        WarningType.UNRESOLVED_REFERENCE,
                        f"Shape '{rec.id}' outgoing reference points to unknown shape '{target_ref}'.",
                    )
                    continue
                incoming_refs.setdefault(target_ref, []).append(rec.id)

    def _identify_edge_shapes(self, records: Dict[str, ShapeRecord]) -> set[str]:
        edge_ids: set[str] = set()
        for rec in records.values():
            if rec.stencil_id in EDGE_STENCIL_IDS or rec.target_id:
                edge_ids.add(rec.id)
        return edge_ids

    def _resolve_edge_source(
        self,
        rec: ShapeRecord,
        incoming_refs: Dict[str, List[str]],
        node_ids: set[str],
    ) -> Optional[str]:
        source_candidates = [source for source in incoming_refs.get(rec.id, []) if source in node_ids]
        if source_candidates:
            if len(source_candidates) > 1:
                self.warn(
                    WarningType.OTHER,
                    f"Edge '{rec.id}' has multiple source candidates {source_candidates}; using first.",
                )
            return source_candidates[0]

        source_attr = rec.shape.get("source")
        if isinstance(source_attr, dict):
            source_id = source_attr.get("resourceId")
            if isinstance(source_id, str) and source_id:
                return source_id
        if isinstance(source_attr, str) and source_attr:
            return source_attr

        return None

    def _resolve_edge_target(self, rec: ShapeRecord, node_ids: set[str]) -> Optional[str]:
        if rec.target_id:
            return rec.target_id

        for ref in rec.outgoing_ids:
            if ref in node_ids and ref != rec.id:
                return ref

        target_attr = rec.shape.get("target")
        if isinstance(target_attr, str) and target_attr:
            return target_attr

        return None

    def _build_node_data(self, rec: ShapeRecord) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        props = rec.shape.get("properties")
        if isinstance(props, dict):
            data.update(_compact_dict(props))

        if rec.parent_id:
            data["parentId"] = rec.parent_id

        for key in ("bounds", "labels", "formats", "layers", "glossaryLinks", "offset"):
            value = rec.shape.get(key)
            if value not in (None, [], {}):
                data[key] = value

        return data

    def _build_edge_data(self, rec: ShapeRecord) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        props = rec.shape.get("properties")
        if isinstance(props, dict):
            data.update(_compact_dict(props))

        for key in ("bounds", "dockers", "labels", "formats", "glossaryLinks"):
            value = rec.shape.get(key)
            if value not in (None, [], {}):
                data[key] = value

        return data
