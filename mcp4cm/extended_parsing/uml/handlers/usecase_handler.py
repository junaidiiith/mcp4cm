"""Handler for uml:UseCase elements."""

from typing import Any, Dict, List
import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.xmi_utils import (
    is_tool_extension,
)


class UseCaseHandler(ElementHandler):
    """Handler for uml:UseCase elements."""

    @property
    def element_type(self) -> str:
        return "uml:UseCase"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create UseCase node; include/extend are handled by dedicated handlers."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        usecase_id = self.require_xmi_id(ctx, elem, role="Node")
        if not usecase_id:
            return

        name = self.read_name(elem)
        data: Dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        extension_points = self._parse_extension_points(ctx, elem)
        if extension_points:
            data["extensionPoints"] = extension_points

        self.upsert_node(
            ctx,
            node_id=usecase_id,
            node_type=contract.node_type or "UseCase",
            name=name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _parse_extension_points(self, ctx, usecase_elem: ET.Element) -> List[Dict[str, Any]]:
        """Parse extensionPoint elements."""
        out: List[Dict[str, Any]] = []
        for ext_point in usecase_elem.findall("./extensionPoint"):
            if is_tool_extension(ext_point):
                continue

            ext_point_id = self.require_xmi_id(ctx, ext_point, role="UseCase extensionPoint")
            if not ext_point_id:
                continue

            item: Dict[str, Any] = {"id": ext_point_id}

            ext_point_name = self.read_name(ext_point)
            if ext_point_name:
                item["name"] = ext_point_name

            use_case_ref = ext_point.attrib.get("useCase")
            if use_case_ref:
                item["useCaseRef"] = use_case_ref

            item.update(
                self.collect_attributes(
                    ext_point,
                    scalar_attrs=("visibility",),
                    boolean_attrs=("isLeaf",),
                )
            )

            out.append(item)

        return out
