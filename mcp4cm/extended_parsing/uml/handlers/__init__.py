"""UML parser handlers for different element types."""

from mcp4cm.extended_parsing.uml.handlers.base_handler import ElementHandler
from mcp4cm.extended_parsing.uml.handlers.model_handler import ModelHandler
from mcp4cm.extended_parsing.uml.handlers.package_handler import PackageHandler
from mcp4cm.extended_parsing.uml.handlers.class_handler import ClassHandler
from mcp4cm.extended_parsing.uml.handlers.interface_handler import InterfaceHandler
from mcp4cm.extended_parsing.uml.handlers.association_handler import AssociationHandler
from mcp4cm.extended_parsing.uml.handlers.generalization_handler import GeneralizationHandler
from mcp4cm.extended_parsing.uml.handlers.interface_realization_handler import InterfaceRealizationHandler
from mcp4cm.extended_parsing.uml.handlers.dependency_handler import DependencyHandler
from mcp4cm.extended_parsing.uml.handlers.enumeration_handler import EnumerationHandler
from mcp4cm.extended_parsing.uml.handlers.datatype_handler import DataTypeHandler
from mcp4cm.extended_parsing.uml.handlers.component_handler import ComponentHandler
from mcp4cm.extended_parsing.uml.handlers.usecase_handler import UseCaseHandler
from mcp4cm.extended_parsing.uml.handlers.include_handler import IncludeHandler
from mcp4cm.extended_parsing.uml.handlers.extend_handler import ExtendHandler
from mcp4cm.extended_parsing.uml.handlers.actor_handler import ActorHandler
from mcp4cm.extended_parsing.uml.handlers.simple_node_handler import SimpleNodeHandler
from mcp4cm.extended_parsing.uml.handlers.association_class_handler import AssociationClassHandler
from mcp4cm.extended_parsing.uml.handlers.information_flow_handler import InformationFlowHandler
from mcp4cm.extended_parsing.uml.handlers.directed_edge_handler import DirectedEdgeHandler
from mcp4cm.extended_parsing.uml.handlers.instance_specification_handler import InstanceSpecificationHandler

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
