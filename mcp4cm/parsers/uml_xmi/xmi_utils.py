"""XMI utility functions for UML parsing."""

import os
from typing import Dict, Optional
import xml.etree.ElementTree as ET

# === Namespaces ===
XMI_NS = "http://schema.omg.org/spec/XMI/2.1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
UML_NS = "http://www.eclipse.org/uml2/5.0.0/UML"

XMI_ID = f"{{{XMI_NS}}}id"
XMI_TYPE = f"{{{XMI_NS}}}type"
XSI_TYPE = f"{{{XSI_NS}}}type"


def localname(tag: str) -> str:
    """Extract local name from namespaced tag."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def xmi_id(elem: ET.Element) -> Optional[str]:
    """Extract xmi:id attribute from element."""
    return elem.attrib.get(XMI_ID)


def xsi_type(elem: ET.Element) -> Optional[str]:
    """Extract type attribute from element (prefer xsi:type, fallback to xmi:type)."""
    return elem.attrib.get(XSI_TYPE) or elem.attrib.get(XMI_TYPE)


def is_tool_extension(elem: ET.Element) -> bool:
    """Check if element is a tool-specific extension (should be skipped)."""
    ln = localname(elem.tag)
    return ln in {"Extension", "eAnnotations", "details"}


def read_multiplicity(owner: ET.Element) -> Dict[str, str]:
    """
    Reads lowerValue/upperValue from a Property/ownedEnd element.
    Returns only present keys (no nulls).
    """
    out: Dict[str, str] = {}
    lower = owner.find("./lowerValue")
    upper = owner.find("./upperValue")
    if lower is not None and "value" in lower.attrib:
        out["lower"] = lower.attrib["value"]
    if upper is not None and "value" in upper.attrib:
        out["upper"] = upper.attrib["value"]
    return out


# TODO: Verify this is stable
def href_to_type_ref(href: str) -> str:
    """
    Heuristic conversion of an external href (PrimitiveTypes etc.) into a stable string.
    Examples:
      ".../PrimitiveTypes.xmi#//Integer" -> "PrimitiveTypes::Integer"
      "pathmap://.../GenMyModelPrimitiveTypes.library.uml#//Date" -> "GenMyModelPrimitiveTypes::Date"
    """
    if "#//" not in href:
        return href  # unknown form, keep raw

    base, frag = href.split("#//", 1)
    type_name = frag.strip("/")

    fname = os.path.basename(base)
    for ext in [".xmi", ".uml"]:
        if fname.endswith(ext):
            fname = fname[: -len(ext)]
    fname = fname.replace(".library", "")

    lib = "PrimitiveTypes" if "PrimitiveTypes" in fname else (fname or "ExternalTypes")
    return f"{lib}::{type_name}"


def find_model(root: ET.Element) -> ET.Element:
    """Find the uml:Model element in the XMI tree."""
    for e in root.iter():
        if e.tag == f"{{{UML_NS}}}Model":
            return e
    for e in root.iter():
        if xsi_type(e) == "uml:Model":
            return e
    raise ValueError("No uml:Model found in XMI.")


# TODO: Verify if this is needed
def parse_boolean(value: Optional[str]) -> Optional[bool]:
    """
    Convert XML boolean string to Python boolean.
    
    XML booleans are typically "true" or "false" (case-insensitive).
    Returns None if value is None or empty, True/False otherwise.
    """
    if not value:
        return None
    return value.lower() in ("true", "1", "yes")
