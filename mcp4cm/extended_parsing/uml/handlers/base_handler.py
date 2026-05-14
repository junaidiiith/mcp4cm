"""Base handler class for UML element handlers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set
import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_ir.types import Node
from mcp4cm.extended_parsing.uml.metamodel import SUPPORTED_UML_CONCEPTS, UMLConceptSpec, UMLParseContract
from mcp4cm.extended_parsing.uml.xmi_utils import (
    xmi_id,
    xsi_type,
    localname,
    is_tool_extension,
    href_to_type_ref,
    parse_boolean,
    read_multiplicity,
    XSI_NS,
)


class ElementHandler(ABC):
    """Base class for element-specific handlers."""

    @property
    @abstractmethod
    def element_type(self) -> str:
        """Return the UML concept identifier handled by this class."""

    @abstractmethod
    def handle(self, ctx, elem: ET.Element) -> None:
        """Handle a single element."""

    def concept_spec(self) -> Optional[UMLConceptSpec]:
        """Return metamodel concept spec for the current handler."""
        return SUPPORTED_UML_CONCEPTS.get(self.element_type)

    def get_parse_contract(self) -> UMLParseContract:
        """Return parse contract for the current handler, if defined."""
        concept = self.concept_spec()
        if concept is None or concept.parse_contract is None:
            return UMLParseContract()
        return concept.parse_contract

    def get_handled_attributes(self) -> Set[str]:
        """Return set of attribute names this handler processes."""
        concept = self.concept_spec()
        if concept is None:
            return set()
        return set(concept.allowed_attributes)

    def get_handled_children(self) -> Set[str]:
        """Return set of child element tags this handler processes."""
        concept = self.concept_spec()
        if concept is None:
            return set()
        return set(concept.allowed_children)

    def log_unhandled_attributes(self, ctx, elem: ET.Element, handled: Set[str]) -> None:
        """Log unhandled attributes for an element."""
        elem_id = xmi_id(elem)
        elem_type = xsi_type(elem) or localname(elem.tag)

        for attr_name, attr_value in elem.attrib.items():
            if attr_name.startswith("{"):
                continue

            attr_local = localname(attr_name) if "}" in attr_name else attr_name
            if attr_local in {"id", "type"}:
                continue

            if attr_local not in handled:
                ctx.warn(
                    WarningType.UNHANDLED_ATTRIBUTE,
                    f"[UNHANDLED ATTRIBUTE] Element: {elem_type} "
                    f"(ID: {elem_id}), Attribute: {attr_local}, Value: {attr_value}",
                )

    def log_unhandled_children(self, ctx, elem: ET.Element, handled: Set[str]) -> None:
        """Log unhandled child elements."""
        elem_id = xmi_id(elem)
        elem_type = xsi_type(elem) or localname(elem.tag)

        handler_map = ctx.handler_map

        for child in elem:
            child_tag = localname(child.tag)
            if child_tag in {"Extension", "eAnnotations", "details", "name"}:
                continue

            # If child has a dedicated handler (xsi:type or tag based), don't flag it.
            child_type = xsi_type(child)
            if child_type and child_type in handler_map:
                continue
            if child_tag in ctx.tag_handler_map and ctx.tag_handler_map[child_tag] in handler_map:
                continue

            if child_tag not in handled:
                child_id = xmi_id(child)
                if child_type:
                    ctx.warn(
                        WarningType.UNHANDLED_CHILD,
                        f"[UNHANDLED CHILD] Element: {elem_type} (ID: {elem_id}), "
                        f"Child: {child_tag} (xsi:type={child_type}, ID: {child_id})",
                    )
                else:
                    ctx.warn(
                        WarningType.UNHANDLED_CHILD,
                        f"[UNHANDLED CHILD] Element: {elem_type} (ID: {elem_id}), "
                        f"Child: {child_tag} (ID: {child_id})",
                    )

    def require_xmi_id(self, ctx, elem: ET.Element, *, role: str = "Element") -> Optional[str]:
        """Return xmi:id or record a skip with warning when missing."""
        elem_id = xmi_id(elem)
        if elem_id:
            return elem_id

        elem_type = xsi_type(elem) or localname(elem.tag)
        ctx.skip_with_warning(
            WarningType.MISSING_ATTRIBUTE,
            f"{role} {elem_type} is missing required xmi:id",
        )
        return None

    def read_name(self, elem: ET.Element) -> str:
        """Read an element name from attribute first, then optional child tag."""
        name_attr = elem.attrib.get("name")
        if name_attr is not None:
            return name_attr

        name_elem = elem.find("./name")
        if name_elem is None:
            return ""

        xsi_nil_attr = name_elem.attrib.get(f"{{{XSI_NS}}}nil")
        if parse_boolean(xsi_nil_attr) is True:
            return ""

        value_attr = name_elem.attrib.get("value")
        if value_attr is not None:
            return value_attr

        text = (name_elem.text or "").strip()
        if text:
            return text

        return ""

    def extract_documentation(self, elem: ET.Element) -> str:
        """Extract documentation from ownedComment elements."""
        bodies = []
        for comment in elem.findall("./ownedComment"):
            if is_tool_extension(comment):
                continue
            body = comment.attrib.get("body")
            if body:
                bodies.append(body)
        return "\n".join(bodies) if bodies else ""

    def collect_attributes(
        self,
        elem: ET.Element,
        *,
        scalar_attrs: Iterable[str] = (),
        boolean_attrs: Iterable[str] = (),
        list_attrs: Iterable[str] = (),
        rename_map: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        """Collect attributes with centralized conversion semantics."""
        out: Dict[str, Any] = {}
        rename_map = rename_map or {}

        for attr_name in scalar_attrs:
            value = elem.attrib.get(attr_name)
            if value is not None:
                out[rename_map.get(attr_name, attr_name)] = value

        for attr_name in boolean_attrs:
            bool_value = parse_boolean(elem.attrib.get(attr_name))
            if bool_value is not None:
                out[rename_map.get(attr_name, attr_name)] = bool_value

        for attr_name in list_attrs:
            values = self.split_ref_list(elem.attrib.get(attr_name))
            if values:
                out[rename_map.get(attr_name, attr_name)] = values

        return out

    def collect_concept_attributes(self, elem: ET.Element) -> Dict[str, Any]:
        """Collect attributes declared in the concept parse contract."""
        contract = self.get_parse_contract()
        return self.collect_attributes(
            elem,
            scalar_attrs=contract.scalar_attrs,
            boolean_attrs=contract.boolean_attrs,
            list_attrs=contract.list_attrs,
            rename_map=contract.rename_map,
        )

    def collect_child_refs(
        self,
        elem: ET.Element,
        *,
        child_tags: Iterable[str] = (),
        rename_map: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, List[str]]:
        """Collect xmi:id references from selected direct child tags."""
        tags = tuple(dict.fromkeys(child_tags))
        if not tags:
            return {}

        tag_set = set(tags)
        rename_map = rename_map or {}
        refs_by_tag: Dict[str, List[str]] = {tag: [] for tag in tags}

        for child in elem:
            if is_tool_extension(child):
                continue
            child_tag = localname(child.tag)
            if child_tag not in tag_set:
                continue
            child_id = xmi_id(child)
            if child_id:
                refs_by_tag[child_tag].append(child_id)

        out: Dict[str, List[str]] = {}
        for tag in tags:
            refs = refs_by_tag.get(tag) or []
            if not refs:
                continue
            key = rename_map.get(tag, f"{tag}Refs")
            out[key] = refs
        return out

    def upsert_node(
        self,
        ctx,
        *,
        node_id: str,
        node_type: str,
        name: str,
        data: Dict[str, Any],
    ) -> None:
        """Insert a node once and merge data on repeated encounters."""
        if node_id not in ctx.nodes_by_id:
            ctx.add_node(Node(id=node_id, type=node_type, name=name, data=data))
            return

        existing = ctx.nodes_by_id[node_id]
        if existing.type != node_type or (name and existing.name and existing.name != name):
            ctx.skip_with_warning(
                WarningType.DUPLICATE_ID,
                f"Duplicate node id '{node_id}' encountered with conflicting payload; "
                f"keeping first node definition.",
            )
        if name and not existing.name:
            existing.name = name
        existing.data.update({k: v for k, v in data.items() if k not in existing.data})

    def split_ref_list(self, refs: Optional[str]) -> List[str]:
        """Split a whitespace-separated IDREF list into values."""
        if not refs:
            return []
        return [part for part in refs.split() if part]

    def resolve_reference(self, elem: ET.Element, attr_name: str, child_tag: str) -> Optional[str]:
        """Resolve reference from attribute first, then from nested child element."""
        attr_value = elem.attrib.get(attr_name)
        if attr_value:
            return attr_value

        child = elem.find(f"./{child_tag}")
        if child is None:
            return None

        href = child.attrib.get("href")
        if href:
            # Keep local ID references and external hrefs as they appear.
            if "#" in href and not href.startswith("http"):
                return href.split("#", 1)[-1].lstrip("/")
            return href

        ref = child.attrib.get("idref")
        if ref:
            return ref

        return None

    def parse_owned_operations(self, ctx, owner_elem: ET.Element) -> List[Dict[str, Any]]:
        """Parse ownedOperation elements."""
        out: List[Dict[str, Any]] = []
        for op in owner_elem.findall("./ownedOperation"):
            if is_tool_extension(op):
                continue

            op_id = xmi_id(op)
            if not op_id:
                owner_id = xmi_id(owner_elem)
                owner_type = xsi_type(owner_elem) or localname(owner_elem.tag)
                ctx.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"{owner_type} (ID: {owner_id}) has ownedOperation without xmi:id",
                )
                continue

            item: Dict[str, Any] = {"id": op_id}

            op_name = self.read_name(op)
            if op_name:
                item["name"] = op_name

            item.update(
                self.collect_attributes(
                    op,
                    scalar_attrs=("visibility",),
                    boolean_attrs=("isAbstract", "isStatic", "isQuery"),
                )
            )

            params = self.parse_owned_parameters(ctx, op)
            if params:
                item["parameters"] = params

            out.append(item)

        return out

    def parse_owned_parameters(self, ctx, owner_elem: ET.Element) -> List[Dict[str, Any]]:
        """Parse ownedParameter elements (typically from operations)."""
        params = []
        for param in owner_elem.findall("./ownedParameter"):
            if is_tool_extension(param):
                continue

            param_id = xmi_id(param)
            if not param_id:
                owner_id = xmi_id(owner_elem)
                owner_type = xsi_type(owner_elem) or localname(owner_elem.tag)
                ctx.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"{owner_type} (ID: {owner_id}) has ownedParameter without xmi:id",
                )
                continue

            param_data: Dict[str, Any] = {"id": param_id}

            param_name = self.read_name(param)
            if param_name:
                param_data["name"] = param_name

            direction = param.attrib.get("direction")
            if direction:
                param_data["direction"] = direction

            param_data.update(
                self.collect_attributes(
                    param,
                    boolean_attrs=("isUnique", "isOrdered"),
                )
            )

            mult = read_multiplicity(param)
            param_data.update(mult)

            type_ref = self.resolve_property_type(ctx, param)
            if type_ref:
                param_data["type"] = type_ref

            params.append(param_data)

        return params

    def resolve_property_type(self, ctx, prop: ET.Element) -> Optional[str]:
        """Resolve type reference for a property-like element."""
        type_id = prop.attrib.get("type")
        if type_id:
            return type_id

        type_elem = prop.find("./type")
        if type_elem is not None and "href" in type_elem.attrib:
            return href_to_type_ref(type_elem.attrib["href"])

        return None

    def set_resolved_type_fields(
        self,
        data: Dict[str, Any],
        resolved_type: str,
        *,
        type_key: str = "type",
        qualified_type_key: str = "qualifiedType",
    ) -> None:
        """Store a resolved type in normalized short + qualified form when possible."""
        if "::" in resolved_type:
            _, short_name = resolved_type.rsplit("::", 1)
            data[type_key] = short_name
            data[qualified_type_key] = resolved_type
            return
        data[type_key] = resolved_type
