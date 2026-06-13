"""Utility functions for ArchiMate parsing."""

import xml.etree.ElementTree as ET

from mcp4cm.parsers.archimate_archi.types import TYPE_RENAMES

XSI_TYPE_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}type"


def normalize_element_type(type_str: str, normalize_deprecated: bool = True) -> str:
    """
    Normalize element type string by removing namespace prefix.

    Args:
        type_str: Type string (e.g., "archimate:ApplicationComponent")
        normalize_deprecated: Whether to normalize deprecated types

    Returns:
        Normalized type string (e.g., "ApplicationComponent")
    """
    if not type_str:
        return ""

    # Step 1: Remove "archimate:" prefix if present
    if type_str.startswith("archimate:"):
        type_str = type_str[len("archimate:") :]

    # Step 2: Rename deprecated types if enabled
    if normalize_deprecated:
        type_str = TYPE_RENAMES.get(type_str, type_str)

    return type_str


def normalize_relationship_type(type_str: str, normalize_deprecated: bool = True) -> str:
    """
    Normalize relationship type string by removing namespace prefix and Relationship suffix.

    Args:
        type_str: Type string (e.g., "archimate:UsedByRelationship")
        normalize_deprecated: Whether to normalize deprecated types

    Returns:
        Normalized type string (e.g., "Serving")
    """
    if not type_str:
        return ""

    # Step 1: Remove "archimate:" prefix if present
    if type_str.startswith("archimate:"):
        type_str = type_str[len("archimate:") :]

    # Step 2: Remove "Relationship" suffix if present
    if type_str.endswith("Relationship"):
        base_name = type_str[: -len("Relationship")]
        # Capitalize first letter if needed
        if base_name:
            type_str = base_name[0].upper() + base_name[1:] if len(base_name) > 1 else base_name.upper()

    # Step 3: Rename deprecated types if enabled
    if normalize_deprecated:
        type_str = TYPE_RENAMES.get(type_str, type_str)

    return type_str


def extract_documentation(element: ET.Element) -> str | None:
    """
    Extract documentation from an element's nested <documentation> element.

    Args:
        element: XML element to extract documentation from

    Returns:
        Documentation text if present, None otherwise
    """
    doc_elem = element.find("documentation")
    if doc_elem is not None and doc_elem.text:
        return doc_elem.text.strip()
    return None


def extract_element_data(element: ET.Element, exclude_attrs: set = None) -> dict[str, str]:
    """
    Extract element data from attributes, excluding specified attributes.

    Args:
        element: XML element to extract data from
        exclude_attrs: Set of attribute names to exclude (default: id, type-related)

    Returns:
        Dictionary of element data
    """
    if exclude_attrs is None:
        exclude_attrs = {"id"}

    elem_data = {}
    for k, v in element.attrib.items():
        if k not in exclude_attrs and not k.endswith("type"):
            elem_data[k] = v

    return elem_data
