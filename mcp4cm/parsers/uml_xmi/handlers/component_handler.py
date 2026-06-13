"""Handler for uml:Component elements."""

import xml.etree.ElementTree as ET
from typing import Any

from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler


class ComponentHandler(ElementHandler):
    """Handler for uml:Component elements."""

    @property
    def element_type(self) -> str:
        return "uml:Component"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        component_id = self.require_xmi_id(ctx, elem, role="Node")
        if not component_id:
            return

        name = self.read_name(elem)
        data: dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        self.upsert_node(
            ctx,
            node_id=component_id,
            node_type=contract.node_type or "Component",
            name=name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
