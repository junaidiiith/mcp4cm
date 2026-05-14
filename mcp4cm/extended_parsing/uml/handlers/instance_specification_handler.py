"""Handler for uml:InstanceSpecification elements."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.xmi_utils import is_tool_extension, xmi_id, xsi_type

EMBEDDED_VALUE_SPEC_TYPES: frozenset[str] = frozenset(
    {
        "uml:LiteralBoolean",
        "uml:LiteralInteger",
        "uml:LiteralReal",
        "uml:LiteralString",
        "uml:LiteralUnlimitedNatural",
        "uml:Expression",
        "uml:InstanceValue",
    }
)


class InstanceSpecificationHandler(ElementHandler):
    """Create InstanceSpecification nodes with embedded slot/specification values."""

    @property
    def element_type(self) -> str:
        return "uml:InstanceSpecification"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        node_id = self.require_xmi_id(ctx, elem, role="Node")
        if not node_id:
            return

        data: Dict[str, Any] = self.collect_concept_attributes(elem)
        data.update(self.collect_child_refs(elem, child_tags=("slot",)))

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        specs = self._parse_value_spec_children(elem, "specification")
        if specs:
            data["specifications"] = specs
            if len(specs) == 1:
                data["specification"] = specs[0]

        slots = self._parse_slots(elem)
        if slots:
            data["slots"] = slots

        self.upsert_node(
            ctx,
            node_id=node_id,
            node_type=contract.node_type or "InstanceSpecification",
            name=self.read_name(elem),
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _parse_slots(self, owner: ET.Element) -> List[Dict[str, Any]]:
        slots: List[Dict[str, Any]] = []
        for slot in owner.findall("./slot"):
            if is_tool_extension(slot):
                continue

            payload: Dict[str, Any] = {}
            slot_id = xmi_id(slot)
            if slot_id:
                payload["id"] = slot_id

            payload.update(
                self.collect_attributes(
                    slot,
                    scalar_attrs=("definingFeature", "owningInstance"),
                )
            )

            values = self._parse_value_spec_children(slot, "value")
            if values:
                payload["values"] = values
                if len(values) == 1:
                    payload["value"] = values[0]

            if payload:
                slots.append(payload)

        return slots

    def _parse_value_spec_children(self, owner: ET.Element, child_tag: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for child in owner.findall(f"./{child_tag}"):
            if is_tool_extension(child):
                continue
            payload = self._parse_value_spec_element(child)
            if payload:
                items.append(payload)
        return items

    def _parse_value_spec_element(self, child: ET.Element) -> Optional[Dict[str, Any]]:
        child_type = xsi_type(child) or ""
        if child_type and child_type not in EMBEDDED_VALUE_SPEC_TYPES:
            return None

        payload: Dict[str, Any] = {}

        child_id = xmi_id(child)
        if child_id:
            payload["id"] = child_id

        if child_type:
            payload["type"] = child_type

        child_name = self.read_name(child)
        if child_name:
            payload["name"] = child_name

        value = child.attrib.get("value")
        if value is not None:
            payload["value"] = value

        symbol = child.attrib.get("symbol")
        if symbol is not None:
            payload["symbol"] = symbol

        href = child.attrib.get("href")
        if href is not None:
            payload["href"] = href

        text_value = (child.text or "").strip()
        if text_value and "value" not in payload:
            payload["text"] = text_value

        return payload or None
