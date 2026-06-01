from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

EMPTY_NAME_SENTINEL = "empty name"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"


@dataclass(frozen=True, slots=True)
class XMINameExtraction:
    names: tuple[str, ...]
    typed_names: tuple[str, ...]


def normalize_identifier(text: object) -> str:
    """Normalize camelCase, PascalCase, snake_case, and kebab-case identifiers."""
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return " ".join(value.split()).lower()


def extract_xmi_names(source_path: Path | str) -> XMINameExtraction:
    """Extract the models's normalized in-memory name representations."""
    root = ET.parse(source_path).getroot()
    names: list[str] = []
    typed_names: list[str] = []

    for elem in root.iter():
        xsi_type = elem.get(f"{{{XSI_NAMESPACE}}}type")
        raw_type = xsi_type.split(":")[-1] if xsi_type else elem.tag.split("}")[-1]
        artifact_type = normalize_identifier(raw_type)

        if "name" in elem.attrib:
            raw_name = elem.attrib["name"].strip()
            name = normalize_identifier(raw_name) if raw_name else EMPTY_NAME_SENTINEL
            names.append(name)
            typed_names.append(f"{artifact_type}: {name}")

        if elem.tag.endswith("ownedComment") and "body" in elem.attrib:
            comment = elem.attrib["body"].strip()
            if comment:
                normalized_comment = normalize_identifier(comment)
                names.append(normalized_comment)
                typed_names.append(f"comment: {normalized_comment}")

    return XMINameExtraction(names=tuple(names), typed_names=tuple(typed_names))
