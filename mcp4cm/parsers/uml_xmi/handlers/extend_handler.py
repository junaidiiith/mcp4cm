"""Handler for extend relationships in Use Cases."""

from typing import Any, Dict
import xml.etree.ElementTree as ET

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.ir import Edge
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import xmi_id


class ExtendHandler(ElementHandler):
    """Handler for extend elements."""

    @property
    def element_type(self) -> str:
        return "uml:Extend"

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        extend_id = xmi_id(elem)

        source_attr = contract.source_attr or "extension"
        target_attr = contract.target_attr or "extendedCase"
        source_child_tag = contract.source_child_tag or source_attr
        target_child_tag = contract.target_child_tag or target_attr

        source_id = self.resolve_reference(elem, source_attr, source_child_tag)
        target_id = self.resolve_reference(elem, target_attr, target_child_tag)
        extension_location = self.resolve_reference(elem, "extensionLocation", "extensionLocation")

        if not source_id or not target_id:
            extend_id = xmi_id(elem) or "<no-id>"
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"uml:Extend edge {extend_id} is missing extension/extendedCase "
                f"(extension={source_id}, extendedCase={target_id})",
            )
            return

        edge_data: Dict[str, Any] = {}
        if extension_location:
            edge_data["extensionLocation"] = extension_location
            ext_point_elem = ctx.elem(extension_location)
            if ext_point_elem is not None:
                ext_point_name = ext_point_elem.attrib.get("name")
                if ext_point_name:
                    edge_data["extensionPoint"] = ext_point_name
            else:
                ctx.warn(
                    WarningType.DEFERRED_REF_UNRESOLVED,
                    f"uml:Extend references unresolved extensionLocation '{extension_location}'.",
                )

        edge_id = extend_id or f"{source_id}__extends__{target_id}"
        ctx.add_edge(
            Edge(
                id=edge_id,
                sourceId=source_id,
                targetId=target_id,
                type=contract.edge_type or "extends",
                data=edge_data,
            )
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
