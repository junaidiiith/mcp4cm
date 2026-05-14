"""ArchiMate model parser."""

from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

from mcp4cm.extended_parsing.base import BaseParser, register_parser
from mcp4cm.extended_parsing.types import CannotParseError
from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_parsing.types import ParserRunStats
from mcp4cm.extended_ir.types import IR, Node, Edge
from mcp4cm.extended_parsing.archimate.archimate_utils import (
    normalize_element_type,
    normalize_relationship_type,
    extract_documentation,
    extract_element_data,
    XSI_TYPE_ATTR,
)

ARCHI_NAMESPACES = [
    # original namespace from the Archi tool
    "{http://www.archimatetool.com/archimate}",
    # some models use this namespace, XML is structured the same as the original Archi namespace
    "{http://www.bolton.ac.uk/archimate}"
]

PARSER_PARAMETERS = {
    "normalize_deprecated_types": False
}

# Valid folder types for elements
ELEMENT_FOLDER_TYPES = {
    "strategy",
    "business",
    "application",
    "technology",
    "motivation",
    "implementation_migration",
    "other"
}

CONNECTORS_FOLDER_TYPE = "connectors"


@register_parser
class ArchiMateArchiParser(BaseParser):
    """Parser for ArchiMate models."""

    language = "ArchiMate-Archi"
    
    def __init__(self):
        """Initialize parser with default parameters."""
        super().__init__()
        self.normalize_deprecated_types = PARSER_PARAMETERS["normalize_deprecated_types"]

    def _validate_archimate_file(self, filepath: str) -> None:
        """
        Validate that the file is a valid ArchiMate model file.
        
        Args:
            filepath: Path to the file to validate
            
        Raises:
            CannotParseError: If the file is not a valid Archi .archimate model file.
        """
        try:
            # Parse only the root element first to check format
            context = ET.iterparse(filepath, events=("start",))
            event, root = next(context)
            
            # Check tag name and namespace
            if not root.tag.endswith("model"):
                raise CannotParseError(f"Root element is not 'model': {root.tag}")
            
            # Check Archi namespace - ElementTree embeds namespace URI in tag as {namespace}localname
            # Support both archimatetool.com and bolton.ac.uk namespaces
            if not any(root.tag.startswith(ns) for ns in ARCHI_NAMESPACES):
                raise CannotParseError(f"File does not appear to be an ArchiMate model created with Archi. Root tag: {root.tag}")
        except ET.ParseError as e:
            raise CannotParseError(f"Invalid XML format: {e}")
        except StopIteration:
            raise CannotParseError("File appears to be empty or invalid XML")
        except Exception as e:
            if isinstance(e, CannotParseError):
                raise
            raise CannotParseError(f"Cannot parse file: {e}")

    def _parse_model_data(self, root: ET.Element, filepath: str) -> Dict:
        """
        Parse model (root) data.
        
        Args:
            root: Root XML element
            filepath: Path to the file
            
        Returns:
            Dictionary with model data
        """
        model_id = root.attrib.get("id", "")
        model_name = root.attrib.get("name", "")
        model_version = root.attrib.get("version", "")
        model_data = { 
            "modelId": model_id,
            "name": model_name, 
            "version": model_version,
            "source_path": str(filepath)
        }
        
        # Parse <purpose> element and add to model data
        purpose_elem = root.find("purpose")
        if purpose_elem is not None and purpose_elem.text:
            model_data["documentation"] = purpose_elem.text.strip()
        
        return model_data

    def _parse_elements(
        self, 
        root: ET.Element, 
        id_lookup: Dict[str, Node]
    ) -> List[Node]:
        """
        Parse elements from element folders (strategy, business, application, etc.).
        
        Args:
            root: Root XML element
            id_lookup: Dictionary to store nodes by ID
            
        Returns:
            List of parsed nodes
        """
        nodes = []

        # Traverse top-level folders and recurse into nested subfolders.
        for folder in root.findall("folder"):
            folder_type = folder.attrib.get("type", "")
            if folder_type not in ELEMENT_FOLDER_TYPES:
                continue
            nodes.extend(self._parse_elements_in_folder(folder, folder_type, id_lookup))

        return nodes

    def _parse_elements_in_folder(
        self,
        folder: ET.Element,
        layer_type: str,
        id_lookup: Dict[str, Node]
    ) -> List[Node]:
        """Parse element nodes in a folder and all nested subfolders."""
        nodes = []

        for element in folder.findall("element"):
            # Extract required attributes
            elem_id = element.attrib.get("id")
            if not elem_id:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Element missing 'id' attribute in folder '{layer_type}'."
                )
                continue

            # Check for duplicate ID
            if elem_id in id_lookup:
                self.skip_with_warning(
                    WarningType.DUPLICATE_ID,
                    f"Element '{elem_id}' in folder '{layer_type}' has duplicate ID (already exists)."
                )
                continue

            xsi_type = element.attrib.get(XSI_TYPE_ATTR, "")
            if not xsi_type:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Element '{elem_id}' missing 'xsi:type' attribute in folder '{layer_type}'."
                )
                continue
            normalized_type = normalize_element_type(
                xsi_type,
                normalize_deprecated=self.normalize_deprecated_types
            )

            node_name = element.attrib.get("name", "")
            elem_data = extract_element_data(element, exclude_attrs={"id", "name", "xsi:type"})
            documentation = extract_documentation(element)
            if documentation:
                elem_data["documentation"] = documentation
            elem_data["layer"] = layer_type

            node = Node(
                id=elem_id,
                type=normalized_type,
                name=node_name,
                data=elem_data
            )
            nodes.append(node)
            id_lookup[elem_id] = node

        for subfolder in folder.findall("folder"):
            nodes.extend(self._parse_elements_in_folder(subfolder, layer_type, id_lookup))

        return nodes

    def _parse_relationships(
        self, 
        root: ET.Element, 
        id_lookup: Dict[str, Node]
    ) -> List[Edge]:
        """
        Parse relationships from relations folder.
        
        Args:
            root: Root XML element
            id_lookup: Dictionary of nodes by ID for validation
            
        Returns:
            List of parsed edges
        """
        edges = []
        
        # Find relations folder
        relations_folder = None
        for folder in root.findall("folder"):
            if folder.attrib.get("type", "") == "relations":
                relations_folder = folder
                break
        
        if relations_folder is None:
            self.warn(WarningType.OTHER, "No relations folder found.")
            return edges
        
        # Parse relationships
        for element in relations_folder.findall("element"):
            # Extract required attributes
            elem_id = element.attrib.get("id")
            if not elem_id:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    "Relationship missing 'id' attribute."
                )
                continue
            
            xsi_type = element.attrib.get(XSI_TYPE_ATTR, "")
            if not xsi_type:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Relationship '{elem_id}' missing 'xsi:type' attribute."
                )
                continue
            
            source = element.attrib.get("source")
            if not source:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Relationship '{elem_id}' missing 'source' attribute."
                )
                continue
            
            target = element.attrib.get("target")
            if not target:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Relationship '{elem_id}' missing 'target' attribute, skipping"
                )
                continue
            
            # Check source and target exist
            if source not in id_lookup:
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"Relationship '{elem_id}' references non-existent source node '{source}'"
                )
            
            if target not in id_lookup:
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"Relationship '{elem_id}' references non-existent target node '{target}'"
                )
            
            # Normalize type (remove Relationship suffix)
            normalized_type = normalize_relationship_type(
                xsi_type,
                normalize_deprecated=self.normalize_deprecated_types
            )
            edge_data = extract_element_data(element, exclude_attrs={"id", "source", "target"})
            documentation = extract_documentation(element)
            if documentation:
                edge_data["documentation"] = documentation
            
            # Extract name if present and add to edge data (as it is optional and rare for relationships to have names)
            edge_name = element.attrib.get("name", "")
            if edge_name:
                edge_data["name"] = edge_name
            
            edge = Edge(
                id=elem_id,
                sourceId=source,
                targetId=target,
                type=normalized_type,
                data=edge_data
            )
            edges.append(edge)
        
        return edges

    def _parse_connectors(
        self,
        root: ET.Element,
        id_lookup: Dict[str, Node]
    ) -> List[Node]:
        """
        Parse connector elements from connectors folder.

        Args:
            root: Root XML element
            id_lookup: Dictionary to store nodes by ID

        Returns:
            List of parsed connector nodes
        """
        connector_nodes = []

        # Find connectors folder
        connectors_folder = None
        for folder in root.findall("folder"):
            if folder.attrib.get("type", "") == CONNECTORS_FOLDER_TYPE:
                connectors_folder = folder
                break

        if connectors_folder is None:
            return connector_nodes

        # Parse connector elements (e.g., Junction)
        for element in connectors_folder.findall("element"):
            elem_id = element.attrib.get("id")
            if not elem_id:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    "Connector element missing 'id' attribute."
                )
                continue

            if elem_id in id_lookup:
                self.skip_with_warning(
                    WarningType.DUPLICATE_ID,
                    f"Connector element '{elem_id}' has duplicate ID (already exists)."
                )
                continue

            xsi_type = element.attrib.get(XSI_TYPE_ATTR, "")
            if not xsi_type:
                self.skip_with_warning(
                    WarningType.MISSING_ATTRIBUTE,
                    f"Connector element '{elem_id}' missing 'xsi:type' attribute."
                )
                continue

            normalized_type = normalize_element_type(
                xsi_type,
                normalize_deprecated=self.normalize_deprecated_types
            )

            node_name = element.attrib.get("name", "")
            elem_data = extract_element_data(element, exclude_attrs={"id", "name", "xsi:type"})
            documentation = extract_documentation(element)
            if documentation:
                elem_data["documentation"] = documentation
            elem_data["layer"] = CONNECTORS_FOLDER_TYPE

            node = Node(
                id=elem_id,
                type=normalized_type,
                name=node_name,
                data=elem_data
            )
            connector_nodes.append(node)
            id_lookup[elem_id] = node

        return connector_nodes

    def parse(self, filepath: str) -> Tuple[IR, ParserRunStats]:
        """
        Parse a ArchiMate model file into IR.
        
        Raises:
            CannotParseError: If the file is not a valid Archi .archimate model file.
        """
        self._start_run()
        self._validate_archimate_file(filepath)
        
        # Parse the full file
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        # Step 1: Parse model (root) data
        model_data = self._parse_model_data(root, filepath)
        
        # Step 2: Parse elements (with ID lookup)
        id_lookup: Dict[str, Node] = {}
        nodes = self._parse_elements(root, id_lookup)
        
        # Step 3: Parse connectors
        nodes.extend(self._parse_connectors(root, id_lookup))

        # Step 4: Parse relationships
        edges = self._parse_relationships(root, id_lookup)
        
        ir = IR(
            id=model_data["modelId"],
            language=self.language,
            data=model_data,
            nodes=nodes,
            edges=edges,
        )
        
        return ir, self._stats()
