"""UML parser handlers for different element types."""

from mcp4cm.parsers.uml_xmi.handlers.base_handler import ElementHandler
from mcp4cm.parsers.uml_xmi.handlers.model_handler import ModelHandler
from mcp4cm.parsers.uml_xmi.handlers.package_handler import PackageHandler
from mcp4cm.parsers.uml_xmi.handlers.class_handler import ClassHandler
from mcp4cm.parsers.uml_xmi.handlers.interface_handler import InterfaceHandler
from mcp4cm.parsers.uml_xmi.handlers.association_handler import AssociationHandler
from mcp4cm.parsers.uml_xmi.handlers.generalization_handler import GeneralizationHandler
from mcp4cm.parsers.uml_xmi.handlers.interface_realization_handler import InterfaceRealizationHandler
from mcp4cm.parsers.uml_xmi.handlers.dependency_handler import DependencyHandler
from mcp4cm.parsers.uml_xmi.handlers.enumeration_handler import EnumerationHandler
from mcp4cm.parsers.uml_xmi.handlers.datatype_handler import DataTypeHandler
from mcp4cm.parsers.uml_xmi.handlers.component_handler import ComponentHandler
from mcp4cm.parsers.uml_xmi.handlers.usecase_handler import UseCaseHandler
from mcp4cm.parsers.uml_xmi.handlers.include_handler import IncludeHandler
from mcp4cm.parsers.uml_xmi.handlers.extend_handler import ExtendHandler
from mcp4cm.parsers.uml_xmi.handlers.actor_handler import ActorHandler
from mcp4cm.parsers.uml_xmi.handlers.simple_node_handler import SimpleNodeHandler
from mcp4cm.parsers.uml_xmi.handlers.association_class_handler import AssociationClassHandler
from mcp4cm.parsers.uml_xmi.handlers.information_flow_handler import InformationFlowHandler
from mcp4cm.parsers.uml_xmi.handlers.directed_edge_handler import DirectedEdgeHandler
from mcp4cm.parsers.uml_xmi.handlers.instance_specification_handler import InstanceSpecificationHandler

__all__ = [
    "ElementHandler",
    "ModelHandler",
    "PackageHandler",
    "ClassHandler",
    "InterfaceHandler",
    "AssociationHandler",
    "GeneralizationHandler",
    "InterfaceRealizationHandler",
    "DependencyHandler",
    "EnumerationHandler",
    "DataTypeHandler",
    "ComponentHandler",
    "UseCaseHandler",
    "IncludeHandler",
    "ExtendHandler",
    "ActorHandler",
    "SimpleNodeHandler",
    "AssociationClassHandler",
    "InformationFlowHandler",
    "DirectedEdgeHandler",
    "InstanceSpecificationHandler",
]
