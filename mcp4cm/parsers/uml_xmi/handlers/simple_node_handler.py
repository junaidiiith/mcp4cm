"""Generic handler for UML concepts mapped to simple IR nodes."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence

from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.xmi_utils import xmi_id


class SimpleNodeHandler(ElementHandler):
    """Configurable node handler for concepts represented as simple nodes."""

    def __init__(
        self,
        *,
        element_type: str,
        node_type: str,
        scalar_attrs: Sequence[str] = (),
        boolean_attrs: Sequence[str] = (),
        list_attrs: Sequence[str] = (),
        rename_map: Mapping[str, str] | None = None,
        child_ref_tags: Sequence[str] = (),
        child_ref_rename_map: Mapping[str, str] | None = None,
        handled_children: Sequence[str] = (),
        include_documentation: bool = True,
        log_unhandled: bool = True,
        skip_href_without_id: bool = False,
    ):
        self._element_type = element_type
        self._node_type = node_type
        self._scalar_attrs = tuple(scalar_attrs)
        self._boolean_attrs = tuple(boolean_attrs)
        self._list_attrs = tuple(list_attrs)
        self._rename_map = dict(rename_map or {})
        self._child_ref_tags = tuple(child_ref_tags)
        self._child_ref_rename_map = dict(child_ref_rename_map or {})
        self._handled_children = tuple(handled_children)
        self._include_documentation = include_documentation
        self._log_unhandled = log_unhandled
        self._skip_href_without_id = skip_href_without_id

    @property
    def element_type(self) -> str:
        return self._element_type

    def get_handled_attributes(self) -> set[str]:
        return {
            "name",
            *self._scalar_attrs,
            *self._boolean_attrs,
            *self._list_attrs,
        }

    def get_handled_children(self) -> set[str]:
        handled = set(self._child_ref_tags)
        handled.update(self._handled_children)
        if self._include_documentation:
            handled.add("ownedComment")
        return handled

    def handle(self, ctx, elem: ET.Element) -> None:
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()

        # External type references (e.g., PrimitiveTypes.xmi#//String) are not
        # model elements and commonly have no xmi:id.
        if self._skip_href_without_id and not xmi_id(elem) and elem.attrib.get("href"):
            return

        node_id = self.require_xmi_id(ctx, elem, role="Node")
        if not node_id:
            return

        data: dict[str, object] = self.collect_attributes(
            elem,
            scalar_attrs=self._scalar_attrs,
            boolean_attrs=self._boolean_attrs,
            list_attrs=self._list_attrs,
            rename_map=self._rename_map,
        )

        if self._include_documentation:
            doc = self.extract_documentation(elem)
            if doc:
                data["documentation"] = doc

        data.update(
            self.collect_child_refs(
                elem,
                child_tags=self._child_ref_tags,
                rename_map=self._child_ref_rename_map,
            )
        )

        self.upsert_node(
            ctx,
            node_id=node_id,
            node_type=self._node_type,
            name=self.read_name(elem),
            data=data,
        )

        if self._log_unhandled:
            self.log_unhandled_attributes(ctx, elem, handled_attrs)
            self.log_unhandled_children(ctx, elem, handled_children)
