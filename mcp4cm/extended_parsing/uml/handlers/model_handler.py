"""Handler for uml:Model elements."""

import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.xmi_utils import (
    xmi_id,
    is_tool_extension,
    XMI_NS,
)


class ModelHandler(ElementHandler):
    """Handler for uml:Model root elements."""

    @property
    def element_type(self) -> str:
        return "uml:Model"

    def handle(self, ctx, elem: ET.Element) -> None:
        """Extract model metadata and store in IR data."""
        handled_attrs = self.get_handled_attributes()
        handled_children = self.get_handled_children()

        model_id = xmi_id(elem) or "model"
        model_name = self.read_name(elem)

        root = ctx.root
        xmi_version = root.attrib.get(f"{{{XMI_NS}}}version")

        imports = []
        for pi in elem.findall("./packageImport"):
            if is_tool_extension(pi):
                continue

            imported = pi.attrib.get("importedPackage")
            if imported:
                imports.append(imported)
                continue

            imported_elem = pi.find("./importedPackage")
            if imported_elem is not None and "href" in imported_elem.attrib:
                imports.append(imported_elem.attrib["href"])

        ctx.ir.data.update(
            {
                "modelId": model_id,
                "name": model_name,
            }
        )

        ctx.ir.data.update(self.collect_concept_attributes(elem))
        if xmi_version:
            ctx.ir.data["xmi_version"] = xmi_version
        if imports:
            ctx.ir.data["imports"] = imports

        self.log_unhandled_attributes(ctx, elem, handled_attrs)
        self.log_unhandled_children(ctx, elem, handled_children)
