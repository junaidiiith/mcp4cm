"""Handler for uml:Enumeration elements."""

import xml.etree.ElementTree as ET
from typing import Any

from mcp4cm.parsers.ir import Node
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import is_tool_extension


class EnumerationHandler(ElementHandler):
    """Handler for uml:Enumeration elements."""

    @property
    def element_type(self) -> str:
        return "uml:Enumeration"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Enumeration node with literals."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        enum_id = self.require_xmi_id(ctx, elem, role="Node")
        if not enum_id:
            return

        name = self.read_name(elem)
        data: dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        literals = self._parse_literals(ctx, elem)
        if literals:
            data["literals"] = literals

        ctx.add_node(Node(id=enum_id, type=contract.node_type or "Enumeration", name=name, data=data))

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _parse_literals(self, ctx, elem: ET.Element) -> list[dict[str, Any]]:
        """Parse ownedLiteral elements."""
        literals = []
        for lit in elem.findall("./ownedLiteral"):
            if is_tool_extension(lit):
                continue

            lit_id = self.require_xmi_id(ctx, lit, role="Enumeration literal")
            if not lit_id:
                continue

            lit_data: dict[str, Any] = {"id": lit_id}

            lit_name = self.read_name(lit)
            if lit_name:
                lit_data["name"] = lit_name

            literals.append(lit_data)

        return literals
