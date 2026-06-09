"""Handler for include relationships in Use Cases."""

import xml.etree.ElementTree as ET

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.ir import Edge
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import xmi_id


class IncludeHandler(ElementHandler):
    """Handler for include elements."""

    @property
    def element_type(self) -> str:
        return "uml:Include"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        include_id = xmi_id(elem)
        source_attr = contract.source_attr or "includingCase"
        target_attr = contract.target_attr or "addition"
        source_child_tag = contract.source_child_tag or source_attr
        target_child_tag = contract.target_child_tag or target_attr

        source_id = self.resolve_reference(elem, source_attr, source_child_tag)
        target_id = self.resolve_reference(elem, target_attr, target_child_tag)

        if not source_id or not target_id:
            include_id = xmi_id(elem) or "<no-id>"
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"uml:Include edge {include_id} is missing includingCase/addition "
                f"(includingCase={source_id}, addition={target_id})",
            )
            return

        edge_id = include_id or f"{source_id}__includes__{target_id}"
        ctx.add_edge(
            Edge(
                id=edge_id,
                sourceId=source_id,
                targetId=target_id,
                type=contract.edge_type or "includes",
                data={},
            )
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
