"""Handler for uml:Association elements."""

import xml.etree.ElementTree as ET
from typing import Any

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.ir import Edge
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import (
    is_tool_extension,
    read_multiplicity,
    xmi_id,
    xsi_type,
)


class AssociationHandler(ElementHandler):
    """Handler for uml:Association elements."""

    def __init__(self, element_type: str = "uml:Association", edge_type: str = "Association"):
        self._element_type = element_type
        self._edge_type = edge_type

    @property
    def element_type(self) -> str:
        return self._element_type

    def handle(self, ctx, elem: ET.Element) -> None:
        """Create Association edge from owned/member ends."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()
        contract = self.get_parse_contract()

        assoc_id = self.require_xmi_id(ctx, elem, role="Edge")
        if not assoc_id:
            return

        owned_ends: dict[str, dict[str, Any]] = {}
        for end in elem.findall("./ownedEnd"):
            if is_tool_extension(end):
                continue
            end_data = self._parse_association_end(ctx, end)
            if end_data:
                owned_ends[end_data["id"]] = end_data

        ends: list[dict[str, Any]] = []
        member_end_ids = self.split_ref_list(elem.attrib.get("memberEnd"))
        if member_end_ids:
            for end_id in member_end_ids:
                parsed = owned_ends.get(end_id)
                if not parsed:
                    ref_elem = ctx.elem(end_id)
                    if ref_elem is not None:
                        parsed = self._parse_association_end(ctx, ref_elem, fallback_id=end_id)
                    else:
                        ctx.warn(
                            WarningType.DEFERRED_REF_UNRESOLVED,
                            f"Association {assoc_id} references unresolved memberEnd '{end_id}'.",
                        )
                if parsed:
                    ends.append(parsed)
        else:
            ends = list(owned_ends.values())

        if len(ends) < 2:
            message = (
                f"Association {assoc_id} has fewer than 2 resolved ends "
                f"(resolved={len(ends)}, memberEnd={len(member_end_ids)}, ownedEnd={len(owned_ends)})"
            )
            ctx.skip_with_warning(WarningType.MISSING_EDGE_ENDPOINT, message)
            return

        end1, end2 = ends[0], ends[1]

        data: dict[str, Any] = {
            "end1": self._clean_end_data(end1),
            "end2": self._clean_end_data(end2),
        }
        data.update(self.collect_concept_attributes(elem))

        assoc_name = ""
        if contract.include_name:
            assoc_name = self.read_name(elem)
            if assoc_name:
                data["name"] = assoc_name

        source_id = end1["typeId"]
        target_id = end2["typeId"]
        edge_type = contract.edge_type or self._edge_type

        composition_pairs = []
        if end1.get("aggregation") == "composite":
            composition_pairs.append((end1, end2))
        if end2.get("aggregation") == "composite":
            composition_pairs.append((end2, end1))

        if composition_pairs:
            whole_end, part_end = composition_pairs[0]
            source_id = whole_end["typeId"]
            target_id = part_end["typeId"]
            edge_type = "Composition"
            data["associationId"] = assoc_id
            data["wholeEndId"] = whole_end["id"]
            data["partEndId"] = part_end["id"]
            if len(composition_pairs) > 1:
                data["compositionPairs"] = [
                    {"wholeEndId": whole["id"], "partEndId": part["id"]} for whole, part in composition_pairs
                ]

        ctx.add_edge(
            Edge(
                id=assoc_id,
                sourceId=source_id,
                targetId=target_id,
                type=edge_type,
                data=data,
            )
        )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _parse_association_end(
        self, ctx, end: ET.Element, fallback_id: str | None = None
    ) -> dict[str, Any] | None:
        """Parse an association end and return its data."""
        end_id = xmi_id(end) or fallback_id
        if not end_id:
            end_type = xsi_type(end) or "ownedEnd"
            ctx.warn(
                WarningType.MISSING_ATTRIBUTE,
                f"Association end {end_type} is missing xmi:id and fallback id.",
            )
            return None

        type_id = end.attrib.get("type")
        if not type_id:
            type_id = self.resolve_property_type(ctx, end)
        if not type_id:
            end_type = xsi_type(end) or "ownedEnd"
            ctx.warn(
                WarningType.INVALID_TYPE_REFERENCE,
                f"Association end {end_id} ({end_type}) has no resolvable type reference.",
            )
            return None

        end_data: dict[str, Any] = {
            "id": end_id,
            "typeId": type_id,
        }

        name = self.read_name(end)
        if name:
            end_data["name"] = name

        mult = read_multiplicity(end)
        end_data.update(mult)

        end_data.update(self.collect_attributes(end, scalar_attrs=("visibility",)))

        aggregation = end.attrib.get("aggregation")
        if aggregation and aggregation != "none":
            end_data["aggregation"] = aggregation

        end_data.update(
            self.collect_attributes(
                end,
                boolean_attrs=("isUnique", "isOrdered", "isReadOnly", "isDerived", "isStatic", "isID", "isLeaf"),
            )
        )

        return end_data

    def _clean_end_data(self, end_data: dict[str, Any]) -> dict[str, Any]:
        """Drop internal parsing fields from end data payload."""
        return {key: value for key, value in end_data.items() if key not in {"typeId"} and value is not None}
