"""Handler for uml:Class elements."""

from typing import Any, Dict, List
import xml.etree.ElementTree as ET

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import (
    xsi_type,
    is_tool_extension,
    read_multiplicity,
)


class ClassHandler(ElementHandler):
    """Handler for uml:Class elements."""

    @property
    def element_type(self) -> str:
        return "uml:Class"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Class node with attributes and operations."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        class_id = self.require_xmi_id(ctx, elem, role="Node")
        if not class_id:
            return

        name = self.read_name(elem)
        data: Dict[str, Any] = self.collect_concept_attributes(elem)

        doc = self.extract_documentation(elem)
        if doc:
            data["documentation"] = doc

        attrs = self._parse_owned_attributes(ctx, elem)
        if attrs:
            data["attributes"] = attrs

        ops = self.parse_owned_operations(ctx, elem)
        if ops:
            data["operations"] = ops

        self.upsert_node(
            ctx,
            node_id=class_id,
            node_type=contract.node_type or "Class",
            name=name,
            data=data,
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _parse_owned_attributes(self, ctx, class_elem: ET.Element) -> List[Dict[str, Any]]:
        """Parse ownedAttribute elements (excluding association ends)."""
        out: List[Dict[str, Any]] = []
        for attr in class_elem.findall("./ownedAttribute"):
            if is_tool_extension(attr):
                continue

            # Class-owned association ends are represented by association references.
            if "association" in attr.attrib or "owningAssociation" in attr.attrib:
                continue

            attr_id = self.require_xmi_id(ctx, attr, role="Class ownedAttribute")
            if not attr_id:
                continue

            item: Dict[str, Any] = {"id": attr_id}

            attr_name = self.read_name(attr)
            if attr_name:
                item["name"] = attr_name

            type_id = attr.attrib.get("type")
            if type_id:
                item["typeRef"] = type_id
            else:
                resolved_type = self.resolve_property_type(ctx, attr)
                if resolved_type:
                    self.set_resolved_type_fields(item, resolved_type)
                else:
                    attr_type = xsi_type(attr) or "ownedAttribute"
                    ctx.warn(
                        WarningType.INVALID_TYPE_REFERENCE,
                        f"Attribute {attr_id} ({attr_type}) has no resolvable type reference.",
                    )

            item.update(read_multiplicity(attr))
            item.update(
                self.collect_attributes(
                    attr,
                    scalar_attrs=("visibility",),
                    boolean_attrs=(
                        "isStatic",
                        "isDerived",
                        "isReadOnly",
                        "isUnique",
                        "isOrdered",
                        "isID",
                        "isLeaf",
                    ),
                )
            )

            aggregation = attr.attrib.get("aggregation")
            if aggregation and aggregation != "none":
                item["aggregation"] = aggregation

            default_value = attr.find("./defaultValue")
            if default_value is not None and "value" in default_value.attrib:
                item["default"] = default_value.attrib["value"]

            out.append(item)

        return out
