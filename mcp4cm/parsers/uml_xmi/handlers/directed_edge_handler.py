"""Generic handler for directed UML relationships."""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Set
import xml.etree.ElementTree as ET

from mcp4cm.parsers.diagnostics import WarningType
from mcp4cm.parsers.ir import Edge
from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import is_tool_extension, xmi_id, xsi_type


EMBEDDED_VALUE_SPEC_TYPES: frozenset[str] = frozenset(
    {
        "uml:LiteralBoolean",
        "uml:LiteralInteger",
        "uml:LiteralReal",
        "uml:LiteralString",
        "uml:LiteralUnlimitedNatural",
        "uml:Expression",
        "uml:InstanceValue",
    }
)


class DirectedEdgeHandler(ElementHandler):
    """Map typed relationship elements to directed IR edges."""

    def __init__(
        self,
        *,
        element_type: str,
        edge_type: str,
        source_attr: str,
        target_attr: str,
        source_child_tag: Optional[str] = None,
        target_child_tag: Optional[str] = None,
        scalar_attrs: Sequence[str] = (),
        list_attrs: Sequence[str] = (),
        rename_map: Optional[Mapping[str, str]] = None,
        child_ref_tags: Sequence[str] = (),
        child_ref_rename_map: Optional[Mapping[str, str]] = None,
        handled_children: Sequence[str] = (),
        include_name: bool = True,
    ):
        self._element_type = element_type
        self._edge_type = edge_type
        self._source_attr = source_attr
        self._target_attr = target_attr
        self._source_child_tag = source_child_tag or source_attr
        self._target_child_tag = target_child_tag or target_attr
        self._scalar_attrs = tuple(scalar_attrs)
        self._list_attrs = tuple(list_attrs)
        self._rename_map = dict(rename_map or {})
        self._child_ref_tags = tuple(child_ref_tags)
        self._child_ref_rename_map = dict(child_ref_rename_map or {})
        self._handled_children = tuple(handled_children)
        self._include_name = include_name

    @property
    def element_type(self) -> str:
        return self._element_type

    def get_handled_attributes(self) -> Set[str]:
        return {
            "name" if self._include_name else "",
            self._source_attr,
            self._target_attr,
            *self._scalar_attrs,
            *self._list_attrs,
        } - {""}

    def get_handled_children(self) -> Set[str]:
        return {
            self._source_child_tag,
            self._target_child_tag,
            *self._child_ref_tags,
            *self._handled_children,
        }

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()

        rel_id = self.require_xmi_id(ctx, elem, role="Edge")
        if not rel_id:
            return

        source_refs = self.split_ref_list(
            self.resolve_reference(elem, self._source_attr, self._source_child_tag)
        )
        target_refs = self.split_ref_list(
            self.resolve_reference(elem, self._target_attr, self._target_child_tag)
        )
        if not source_refs or not target_refs:
            ctx.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"{self._element_type} edge {rel_id} is missing source/target "
                f"({self._source_attr}={source_refs}, {self._target_attr}={target_refs})",
            )
            return

        edge_data: Dict[str, object] = self.collect_attributes(
            elem,
            scalar_attrs=self._scalar_attrs,
            list_attrs=self._list_attrs,
            rename_map=self._rename_map,
        )
        if self._include_name:
            name = self.read_name(elem)
            if name:
                edge_data["name"] = name

        edge_data.update(
            self.collect_child_refs(
                elem,
                child_tags=self._child_ref_tags,
                rename_map=self._child_ref_rename_map,
            )
        )
        edge_data.update(self._collect_embedded_value_specs(elem, existing_keys=set(edge_data.keys())))

        edge_index = 0
        for source_id in source_refs:
            for target_id in target_refs:
                edge_id = rel_id if edge_index == 0 else f"{rel_id}__{edge_index}"
                edge_index += 1
                ctx.add_edge(
                    Edge(
                        id=edge_id,
                        sourceId=source_id,
                        targetId=target_id,
                        type=self._edge_type,
                        data=edge_data,
                    )
                )

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)

    def _collect_embedded_value_specs(self, elem: ET.Element, *, existing_keys: Set[str]) -> Dict[str, object]:
        """Embed guard/weight/argument/ownedRule ValueSpecifications into edge data."""
        out: Dict[str, object] = {}

        arguments = self._parse_value_spec_children(elem, "argument")
        if arguments:
            out["arguments"] = arguments

        owned_rules = self._parse_owned_rules(elem)
        if owned_rules:
            out["ownedRules"] = owned_rules

        for child_tag in ("guard", "weight"):
            spec = self._parse_value_spec_child(elem, child_tag)
            if spec is None:
                continue

            # Preserve legacy scalar guard/weight attributes when present.
            if child_tag in out or child_tag in existing_keys:
                out[f"{child_tag}Spec"] = spec
            else:
                out[child_tag] = spec

        guard_ref = self._resolve_existing_guard_ref(existing_keys, elem)
        if guard_ref and owned_rules:
            matching_rule = next((rule for rule in owned_rules if str(rule.get("id") or "") == guard_ref), None)
            if matching_rule:
                out["guardRule"] = matching_rule

        return out

    def _parse_value_spec_child(self, owner: ET.Element, child_tag: str) -> Optional[Dict[str, object]]:
        child = owner.find(f"./{child_tag}")
        if child is None or is_tool_extension(child):
            return None
        return self._parse_value_spec_element(child)

    def _parse_value_spec_children(self, owner: ET.Element, child_tag: str) -> list[Dict[str, object]]:
        payloads: list[Dict[str, object]] = []
        for child in owner.findall(f"./{child_tag}"):
            if is_tool_extension(child):
                continue
            payload = self._parse_value_spec_element(child)
            if payload:
                payloads.append(payload)
        return payloads

    def _parse_value_spec_element(self, child: ET.Element) -> Optional[Dict[str, object]]:
        child_type = xsi_type(child) or ""
        if child_type and child_type not in EMBEDDED_VALUE_SPEC_TYPES:
            return None

        payload: Dict[str, object] = {}

        child_id = xmi_id(child)
        if child_id:
            payload["id"] = child_id

        if child_type:
            payload["type"] = child_type

        child_name = self.read_name(child)
        if child_name:
            payload["name"] = child_name

        value = child.attrib.get("value")
        if value is not None:
            payload["value"] = value

        symbol = child.attrib.get("symbol")
        if symbol is not None:
            payload["symbol"] = symbol

        href = child.attrib.get("href")
        if href is not None:
            payload["href"] = href

        text_value = (child.text or "").strip()
        if text_value and "value" not in payload:
            payload["text"] = text_value

        return payload or None

    def _parse_owned_rules(self, owner: ET.Element) -> list[Dict[str, object]]:
        rules: list[Dict[str, object]] = []
        for rule in owner.findall("./ownedRule"):
            if is_tool_extension(rule):
                continue

            rule_payload: Dict[str, object] = {}
            rule_id = xmi_id(rule)
            if rule_id:
                rule_payload["id"] = rule_id

            rule_name = self.read_name(rule)
            if rule_name:
                rule_payload["name"] = rule_name

            context_ref = rule.attrib.get("context")
            if context_ref:
                rule_payload["context"] = context_ref

            spec_payload = self._parse_value_spec_child(rule, "specification")
            if spec_payload:
                rule_payload["specification"] = spec_payload

            if rule_payload:
                rules.append(rule_payload)

        return rules

    def _resolve_existing_guard_ref(self, existing_keys: Set[str], elem: ET.Element) -> str:
        if "guard" not in existing_keys:
            return ""
        guard_ref = elem.attrib.get("guard")
        return str(guard_ref or "")
