from mcp4cm.parsers.archimate import ArchimateParser
from mcp4cm.parsers.base import BaseModelParser
from mcp4cm.parsers.extended import (
    ArchimateArchiModelParser,
    BPMNSignavioModelParser,
    EcoreXMIModelParser,
    UMLXMIModelParser,
)
from mcp4cm.parsers.modelset import EcoreParser, UMLParser
from mcp4cm.parsers.registry import registry

registry.register("uml", UMLParser)
registry.register("ecore", EcoreParser)
registry.register("archimate", ArchimateParser)

__all__ = [
    "ArchimateParser",
    "ArchimateArchiModelParser",
    "BaseModelParser",
    "BPMNSignavioModelParser",
    "EcoreParser",
    "EcoreXMIModelParser",
    "UMLParser",
    "UMLXMIModelParser",
    "registry",
]
