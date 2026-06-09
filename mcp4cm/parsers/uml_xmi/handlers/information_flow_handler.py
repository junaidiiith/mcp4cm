"""Handler for uml:InformationFlow elements."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.ir import Edge
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler


class InformationFlowHandler(ElementHandler):
    """Map InformationFlow concepts to directed IR edges."""

    @property
    def element_type(self) -> str:
        return "uml:InformationFlow"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        flow_id = self.require_xmi_id(ctx, elem, role="Edge")
        if not flow_id:
            return

        source_attr = contract.source_attr or "informationSource"
        target_attr = contract.target_attr or "informationTarget"
        source_child_tag = contract.source_child_tag or source_attr
        target_child_tag = contract.target_child_tag or target_attr

        sources = self.split_ref_list(self.resolve_reference(elem, source_attr, source_child_tag))
        targets = self.split_ref_list(self.resolve_reference(elem, target_attr, target_child_tag))
        if not sources or not targets:
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"uml:InformationFlow edge {flow_id} is missing source/target "
                f"(informationSource={sources}, informationTarget={targets})",
            )
            return

        edge_index = 0
        for source_id in sources:
            for target_id in targets:
                edge_id = flow_id if edge_index == 0 else f"{flow_id}__{edge_index}"
                edge_index += 1
                edge_data = self.collect_concept_attributes(elem)
                if contract.include_name:
                    flow_name = self.read_name(elem)
                    if flow_name:
                        edge_data["name"] = flow_name
                ctx.add_edge(
                    Edge(
                        id=edge_id,
                        sourceId=source_id,
                        targetId=target_id,
                        type=contract.edge_type or "InformationFlow",
                        data=edge_data,
                    )
                )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
