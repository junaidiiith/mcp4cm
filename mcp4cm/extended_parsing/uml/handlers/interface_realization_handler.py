"""Handler for interfaceRealization elements."""

import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_ir.types import Edge
from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.xmi_utils import xmi_id


class InterfaceRealizationHandler(ElementHandler):
    """Handler for interface realization relationships."""

    @property
    def element_type(self) -> str:
        return "uml:InterfaceRealization"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        rel_id = xmi_id(elem)

        source_attr = contract.source_attr or "implementingClassifier"
        target_attr = contract.target_attr or "contract"
        source_child_tag = contract.source_child_tag or source_attr
        target_child_tag = contract.target_child_tag or target_attr

        source_id = self.resolve_reference(elem, source_attr, source_child_tag) or elem.attrib.get("client")
        target_id = self.resolve_reference(elem, target_attr, target_child_tag) or elem.attrib.get("supplier")

        if not source_id or not target_id:
            rel_label = rel_id or "<no-id>"
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"uml:InterfaceRealization edge {rel_label} is missing source/target "
                f"(source={source_id}, target={target_id})",
            )
            return

        edge_id = rel_id or f"{source_id}__realizes__{target_id}"
        data = self.collect_concept_attributes(elem)
        data[source_attr] = elem.attrib.get(source_attr)
        data[target_attr] = elem.attrib.get(target_attr)
        data = {k: v for k, v in data.items() if v is not None}
        if contract.include_name:
            rel_name = self.read_name(elem)
            if rel_name:
                data["name"] = rel_name

        ctx.add_edge(
            Edge(
                id=edge_id,
                sourceId=source_id,
                targetId=target_id,
                type=contract.edge_type or "InterfaceRealization",
                data=data,
            )
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
