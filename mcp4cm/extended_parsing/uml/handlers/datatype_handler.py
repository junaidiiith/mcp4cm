"""Handler for uml:DataType elements."""

from typing import Any, Dict
import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler


class DataTypeHandler(ElementHandler):
    """Handler for uml:DataType elements."""

    @property
    def element_type(self) -> str:
        return "uml:DataType"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create DataType node."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        data_type_id = self.require_xmi_id(ctx, elem, role="Node")
        if not data_type_id:
            return

        name = self.read_name(elem)
        data: Dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        self.upsert_node(
            ctx,
            node_id=data_type_id,
            node_type=contract.node_type or "DataType",
            name=name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
