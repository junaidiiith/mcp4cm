"""Handler for uml:Generalization elements."""

import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_ir.types import Edge
from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.xmi_utils import xmi_id


class GeneralizationHandler(ElementHandler):
    """Handler for uml:Generalization elements (inheritance relationships)."""

    @property
    def element_type(self) -> str:
        return "uml:Generalization"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Generalization edge."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        gen_id = xmi_id(elem)

        source_attr = contract.source_attr or "specific"
        target_attr = contract.target_attr or "general"
        source_child_tag = contract.source_child_tag or source_attr
        target_child_tag = contract.target_child_tag or target_attr

        specific_id = self.resolve_reference(elem, source_attr, source_child_tag)
        if not specific_id:
            parent = ctx.parent_map.get(elem)
            if parent is not None:
                specific_id = xmi_id(parent)

        general_id = self.resolve_reference(elem, target_attr, target_child_tag)

        if not specific_id or not general_id:
            gen_label = gen_id or "<no-id>"
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"uml:Generalization edge {gen_label} is missing specific/general "
                f"(specific={specific_id}, general={general_id})",
            )
            return

        edge_id = gen_id or f"{specific_id}__generalization__{general_id}"

        data: dict = {
            "general": general_id,
            "specific": specific_id,
        }
        if contract.include_name:
            name = self.read_name(elem)
            if name:
                data["name"] = name

        ctx.add_edge(
            Edge(
                id=edge_id,
                sourceId=specific_id,
                targetId=general_id,
                type=contract.edge_type or "Generalization",
                data=data,
            )
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
