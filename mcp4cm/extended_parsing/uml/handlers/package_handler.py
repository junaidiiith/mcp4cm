"""Handler for uml:Package elements."""

import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler


class PackageHandler(ElementHandler):
    """Handler for uml:Package elements."""

    @property
    def element_type(self) -> str:
        return "uml:Package"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Package node."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        pkg_id = self.require_xmi_id(ctx, elem, role="Node")
        if not pkg_id:
            return

        pkg_name = self.read_name(elem)
        data = self.collect_concept_attributes(elem)
        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc
        self.upsert_node(
            ctx,
            node_id=pkg_id,
            node_type=contract.node_type or "Package",
            name=pkg_name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
