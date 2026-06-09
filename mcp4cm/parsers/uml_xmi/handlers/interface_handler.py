"""Handler for uml:Interface elements."""

from typing import Any, Dict
import xml.etree.ElementTree as ET

from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler


class InterfaceHandler(ElementHandler):
    """Handler for uml:Interface elements."""

    @property
    def element_type(self) -> str:
        return "uml:Interface"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Interface node with operations."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        interface_id = self.require_xmi_id(ctx, elem, role="Node")
        if not interface_id:
            return

        name = self.read_name(elem)
        data: Dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        ops = self.parse_owned_operations(ctx, elem)
        if ops:
            data["operations"] = ops

        self.upsert_node(
            ctx,
            node_id=interface_id,
            node_type=contract.node_type or "Interface",
            name=name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
