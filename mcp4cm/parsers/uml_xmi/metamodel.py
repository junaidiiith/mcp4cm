"""Supported UML concepts and parsing contracts.

This module documents the parser-supported subset of the UML metamodel.
Each concept declares the attributes and children that are intentionally handled.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

HandlerKind = Literal["custom", "simple_node", "directed_edge"]


@dataclass(frozen=True)
class UMLHandlerSpec:
    """Runtime parsing specification for a UML concept."""

    kind: HandlerKind
    handler_name: str | None = None
    node_type: str | None = None
    edge_type: str | None = None
    scalar_attrs: tuple[str, ...] = ()
    boolean_attrs: tuple[str, ...] = ()
    list_attrs: tuple[str, ...] = ()
    rename_map: Mapping[str, str] = field(default_factory=dict)
    child_ref_tags: tuple[str, ...] = ()
    child_ref_rename_map: Mapping[str, str] = field(default_factory=dict)
    handled_children: tuple[str, ...] = ()
    source_attr: str | None = None
    target_attr: str | None = None
    source_child_tag: str | None = None
    target_child_tag: str | None = None
    include_name: bool = True
    skip_href_without_id: bool = False
    custom_kwargs: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class UMLParseContract:
    """Concept-level parse contract consumed by handlers."""

    node_type: str | None = None
    edge_type: str | None = None
    scalar_attrs: tuple[str, ...] = ()
    boolean_attrs: tuple[str, ...] = ()
    list_attrs: tuple[str, ...] = ()
    rename_map: Mapping[str, str] = field(default_factory=dict)
    child_ref_tags: tuple[str, ...] = ()
    child_ref_rename_map: Mapping[str, str] = field(default_factory=dict)
    handled_children: tuple[str, ...] = ()
    source_attr: str | None = None
    target_attr: str | None = None
    source_child_tag: str | None = None
    target_child_tag: str | None = None
    include_documentation: bool = True
    include_name: bool = True


@dataclass(frozen=True)
class UMLConceptSpec:
    """Specification of a supported UML concept."""

    concept_id: str
    allowed_attributes: frozenset[str]
    allowed_children: frozenset[str]
    produces: str
    handler: UMLHandlerSpec | None = None
    parse_contract: UMLParseContract | None = None


SUPPORTED_UML_CONCEPTS: Mapping[str, UMLConceptSpec] = {
    "uml:Model": UMLConceptSpec(
        concept_id="uml:Model",
        allowed_attributes=frozenset({"name", "visibility"}),
        allowed_children=frozenset({"packagedElement", "packageImport", "elementImport", "ownedComment"}),
        produces="IR metadata",
    ),
    "uml:Package": UMLConceptSpec(
        concept_id="uml:Package",
        allowed_attributes=frozenset({"name", "visibility"}),
        allowed_children=frozenset({"packagedElement", "ownedComment", "packageImport", "elementImport"}),
        produces="Node(type=Package)",
    ),
    "uml:Class": UMLConceptSpec(
        concept_id="uml:Class",
        allowed_attributes=frozenset(
            {"name", "visibility", "isAbstract", "isLeaf", "href", "templateParameter", "owningTemplateParameter"}
        ),
        allowed_children=frozenset(
            {
                "ownedAttribute",
                "ownedOperation",
                "generalization",
                "interfaceRealization",
                "ownedComment",
                "nestedClassifier",
                "ownedTemplateSignature",
                "templateBinding",
                "elementImport",
            }
        ),
        produces="Node(type=Class)",
    ),
    "uml:ClassifierTemplateParameter": UMLConceptSpec(
        concept_id="uml:ClassifierTemplateParameter",
        allowed_attributes=frozenset({"name", "parameteredElement", "signature", "constrainingClassifier"}),
        allowed_children=frozenset({"ownedParameteredElement", "constrainingClassifier", "ownedComment"}),
        produces="Node(type=ClassifierTemplateParameter)",
    ),
    "uml:RedefinableTemplateSignature": UMLConceptSpec(
        concept_id="uml:RedefinableTemplateSignature",
        allowed_attributes=frozenset({"name", "parameter"}),
        allowed_children=frozenset({"ownedParameter", "ownedComment"}),
        produces="Node(type=RedefinableTemplateSignature)",
    ),
    "uml:Interface": UMLConceptSpec(
        concept_id="uml:Interface",
        allowed_attributes=frozenset({"name", "visibility", "isAbstract", "href"}),
        allowed_children=frozenset(
            {
                "ownedOperation",
                "ownedAttribute",
                "generalization",
                "ownedComment",
                "nestedClassifier",
                "ownedTemplateSignature",
                "templateBinding",
                "elementImport",
            }
        ),
        produces="Node(type=Interface)",
    ),
    "uml:Enumeration": UMLConceptSpec(
        concept_id="uml:Enumeration",
        allowed_attributes=frozenset({"name", "visibility", "href"}),
        allowed_children=frozenset({"ownedLiteral", "ownedComment", "ownedOperation", "ownedAttribute"}),
        produces="Node(type=Enumeration)",
    ),
    "uml:DataType": UMLConceptSpec(
        concept_id="uml:DataType",
        allowed_attributes=frozenset({"name", "visibility", "isAbstract", "href"}),
        allowed_children=frozenset({"ownedComment", "templateBinding"}),
        produces="Node(type=DataType)",
    ),
    "uml:Component": UMLConceptSpec(
        concept_id="uml:Component",
        allowed_attributes=frozenset({"name", "visibility", "isAbstract", "isLeaf"}),
        allowed_children=frozenset(
            {
                "ownedUseCase",
                "packagedElement",
                "nestedClassifier",
                "generalization",
                "ownedComment",
                "ownedTemplateSignature",
                "ownedAttribute",
            }
        ),
        produces="Node(type=Component)",
    ),
    "uml:Port": UMLConceptSpec(
        concept_id="uml:Port",
        allowed_attributes=frozenset(
            {
                "name",
                "visibility",
                "type",
                "isDerived",
                "isReadOnly",
                "isUnique",
                "isOrdered",
                "isStatic",
            }
        ),
        allowed_children=frozenset({"ownedComment", "lowerValue", "upperValue", "defaultValue"}),
        produces="Node(type=Port)",
    ),
    "uml:UseCase": UMLConceptSpec(
        concept_id="uml:UseCase",
        allowed_attributes=frozenset({"name", "visibility", "isAbstract", "isLeaf", "href"}),
        allowed_children=frozenset(
            {"include", "extend", "extensionPoint", "generalization", "ownedComment", "ownedUseCase"}
        ),
        produces="Node(type=UseCase)",
    ),
    "uml:Actor": UMLConceptSpec(
        concept_id="uml:Actor",
        allowed_attributes=frozenset({"name", "visibility", "isAbstract", "isLeaf", "href"}),
        allowed_children=frozenset({"generalization", "ownedComment"}),
        produces="Node(type=Actor)",
    ),
    "uml:Activity": UMLConceptSpec(
        concept_id="uml:Activity",
        allowed_attributes=frozenset({"name", "visibility", "isReadOnly", "isSingleExecution"}),
        allowed_children=frozenset(
            {
                "ownedComment",
                "ownedBehavior",
                "ownedNode",
                "edge",
                "ownedGroup",
                "variable",
                "structuredNode",
            }
        ),
        produces="Node(type=Activity)",
    ),
    "uml:StateMachine": UMLConceptSpec(
        concept_id="uml:StateMachine",
        allowed_attributes=frozenset({"name", "visibility", "isReentrant"}),
        allowed_children=frozenset({"ownedComment", "region", "connectionPoint", "doActivity"}),
        produces="Node(type=StateMachine)",
    ),
    "uml:Interaction": UMLConceptSpec(
        concept_id="uml:Interaction",
        allowed_attributes=frozenset({"name", "visibility", "isLeaf"}),
        allowed_children=frozenset({"ownedComment", "lifeline", "message", "fragment", "nestedClassifier"}),
        produces="Node(type=Interaction)",
    ),
    "uml:InstanceSpecification": UMLConceptSpec(
        concept_id="uml:InstanceSpecification",
        allowed_attributes=frozenset({"name", "visibility", "classifier"}),
        allowed_children=frozenset({"ownedComment", "slot", "specification"}),
        produces="Node(type=InstanceSpecification)",
    ),
    "uml:AssociationClass": UMLConceptSpec(
        concept_id="uml:AssociationClass",
        allowed_attributes=frozenset(
            {
                "name",
                "visibility",
                "isAbstract",
                "isLeaf",
                "memberEnd",
                "navigableOwnedEnd",
            }
        ),
        allowed_children=frozenset(
            {
                "ownedAttribute",
                "ownedOperation",
                "generalization",
                "interfaceRealization",
                "ownedComment",
                "nestedClassifier",
                "ownedTemplateSignature",
                "templateBinding",
                "elementImport",
                "ownedEnd",
            }
        ),
        produces="Node(type=AssociationClass)",
    ),
    "uml:CommunicationPath": UMLConceptSpec(
        concept_id="uml:CommunicationPath",
        allowed_attributes=frozenset({"name", "memberEnd", "navigableOwnedEnd"}),
        allowed_children=frozenset({"ownedEnd", "name"}),
        produces="Edge(type=CommunicationPath)",
    ),
    "uml:Device": UMLConceptSpec(
        concept_id="uml:Device",
        allowed_attributes=frozenset({"name", "visibility", "isLeaf"}),
        allowed_children=frozenset({"ownedComment", "nestedNode", "deployedArtifact"}),
        produces="Node(type=Device)",
    ),
    "uml:Node": UMLConceptSpec(
        concept_id="uml:Node",
        allowed_attributes=frozenset({"name", "visibility", "isLeaf"}),
        allowed_children=frozenset({"ownedComment", "nestedNode", "deployedArtifact"}),
        produces="Node(type=Node)",
    ),
    "uml:Artifact": UMLConceptSpec(
        concept_id="uml:Artifact",
        allowed_attributes=frozenset({"name", "visibility", "fileName"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=Artifact)",
    ),
    "uml:InformationFlow": UMLConceptSpec(
        concept_id="uml:InformationFlow",
        allowed_attributes=frozenset({"name", "informationSource", "informationTarget"}),
        allowed_children=frozenset({"ownedComment", "realization", "conveyed"}),
        produces="Edge(type=InformationFlow)",
    ),
    "uml:ExecutionEnvironment": UMLConceptSpec(
        concept_id="uml:ExecutionEnvironment",
        allowed_attributes=frozenset({"name", "visibility", "isLeaf"}),
        allowed_children=frozenset({"ownedComment", "nestedNode", "deployedArtifact"}),
        produces="Node(type=ExecutionEnvironment)",
    ),
    "uml:OpaqueAction": UMLConceptSpec(
        concept_id="uml:OpaqueAction",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition", "href"}),
        allowed_children=frozenset({"ownedComment", "inputValue", "outputValue"}),
        produces="Node(type=OpaqueAction)",
    ),
    "uml:CallBehaviorAction": UMLConceptSpec(
        concept_id="uml:CallBehaviorAction",
        allowed_attributes=frozenset({"name", "visibility", "behavior", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment", "argument", "result"}),
        produces="Node(type=CallBehaviorAction)",
    ),
    "uml:SendSignalAction": UMLConceptSpec(
        concept_id="uml:SendSignalAction",
        allowed_attributes=frozenset({"name", "visibility", "signal", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment", "argument", "target"}),
        produces="Node(type=SendSignalAction)",
    ),
    "uml:ActivityParameterNode": UMLConceptSpec(
        concept_id="uml:ActivityParameterNode",
        allowed_attributes=frozenset({"name", "visibility", "parameter", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=ActivityParameterNode)",
    ),
    "uml:CentralBufferNode": UMLConceptSpec(
        concept_id="uml:CentralBufferNode",
        allowed_attributes=frozenset({"name", "visibility", "type", "incoming", "outgoing", "inState", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=CentralBufferNode)",
    ),
    "uml:DataStoreNode": UMLConceptSpec(
        concept_id="uml:DataStoreNode",
        allowed_attributes=frozenset({"name", "visibility", "type", "incoming", "outgoing", "inState", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=DataStoreNode)",
    ),
    "uml:InitialNode": UMLConceptSpec(
        concept_id="uml:InitialNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=InitialNode)",
    ),
    "uml:ActivityFinalNode": UMLConceptSpec(
        concept_id="uml:ActivityFinalNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=ActivityFinalNode)",
    ),
    "uml:FlowFinalNode": UMLConceptSpec(
        concept_id="uml:FlowFinalNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=FlowFinalNode)",
    ),
    "uml:DecisionNode": UMLConceptSpec(
        concept_id="uml:DecisionNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=DecisionNode)",
    ),
    "uml:MergeNode": UMLConceptSpec(
        concept_id="uml:MergeNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=MergeNode)",
    ),
    "uml:JoinNode": UMLConceptSpec(
        concept_id="uml:JoinNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=JoinNode)",
    ),
    "uml:ForkNode": UMLConceptSpec(
        concept_id="uml:ForkNode",
        allowed_attributes=frozenset({"name", "visibility", "incoming", "outgoing", "inPartition"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=ForkNode)",
    ),
    "uml:ActivityPartition": UMLConceptSpec(
        concept_id="uml:ActivityPartition",
        allowed_attributes=frozenset({"name", "visibility", "node"}),
        allowed_children=frozenset({"ownedComment", "subpartition"}),
        produces="Node(type=ActivityPartition)",
    ),
    "uml:MessageOccurrenceSpecification": UMLConceptSpec(
        concept_id="uml:MessageOccurrenceSpecification",
        allowed_attributes=frozenset({"name", "covered", "enclosingInteraction", "message", "toAfter"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=MessageOccurrenceSpecification)",
    ),
    "uml:ExecutionOccurrenceSpecification": UMLConceptSpec(
        concept_id="uml:ExecutionOccurrenceSpecification",
        allowed_attributes=frozenset({"name", "covered", "enclosingInteraction"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=ExecutionOccurrenceSpecification)",
    ),
    "uml:BehaviorExecutionSpecification": UMLConceptSpec(
        concept_id="uml:BehaviorExecutionSpecification",
        allowed_attributes=frozenset({"name", "covered", "enclosingInteraction", "start", "finish"}),
        allowed_children=frozenset({"ownedComment", "generalOrdering"}),
        produces="Node(type=BehaviorExecutionSpecification)",
    ),
    "uml:Collaboration": UMLConceptSpec(
        concept_id="uml:Collaboration",
        allowed_attributes=frozenset({"name", "visibility"}),
        allowed_children=frozenset({"ownedAttribute", "ownedComment"}),
        produces="Node(type=Collaboration)",
    ),
    "uml:State": UMLConceptSpec(
        concept_id="uml:State",
        allowed_attributes=frozenset({"name", "visibility", "container", "incoming", "outgoing"}),
        allowed_children=frozenset({"ownedComment", "region", "entry", "exit", "doActivity", "connectionPoint"}),
        produces="Node(type=State)",
    ),
    "uml:FinalState": UMLConceptSpec(
        concept_id="uml:FinalState",
        allowed_attributes=frozenset({"name", "visibility", "container", "incoming", "outgoing"}),
        allowed_children=frozenset({"ownedComment", "entry", "exit", "doActivity"}),
        produces="Node(type=FinalState)",
    ),
    "uml:Pseudostate": UMLConceptSpec(
        concept_id="uml:Pseudostate",
        allowed_attributes=frozenset({"name", "visibility", "container", "incoming", "outgoing", "kind"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=Pseudostate)",
    ),
    "uml:Region": UMLConceptSpec(
        concept_id="uml:Region",
        allowed_attributes=frozenset({"name", "visibility", "stateMachine", "state"}),
        allowed_children=frozenset({"ownedComment", "subvertex", "transition"}),
        produces="Node(type=Region)",
    ),
    "uml:Lifeline": UMLConceptSpec(
        concept_id="uml:Lifeline",
        allowed_attributes=frozenset({"name", "visibility", "interaction", "represents", "decomposedAs", "coveredBy"}),
        allowed_children=frozenset({"ownedComment", "selector"}),
        produces="Node(type=Lifeline)",
    ),
    "uml:CombinedFragment": UMLConceptSpec(
        concept_id="uml:CombinedFragment",
        allowed_attributes=frozenset({"name", "visibility", "interactionOperator", "covered", "enclosingInteraction"}),
        allowed_children=frozenset({"ownedComment", "operand"}),
        produces="Node(type=CombinedFragment)",
    ),
    "uml:InteractionOperand": UMLConceptSpec(
        concept_id="uml:InteractionOperand",
        allowed_attributes=frozenset({"name", "visibility", "covered", "enclosingInteraction", "guard"}),
        allowed_children=frozenset({"ownedComment", "fragment", "guard"}),
        produces="Node(type=InteractionOperand)",
    ),
    "uml:InstanceValue": UMLConceptSpec(
        concept_id="uml:InstanceValue",
        allowed_attributes=frozenset({"name", "visibility", "instance"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=InstanceValue)",
    ),
    "uml:Expression": UMLConceptSpec(
        concept_id="uml:Expression",
        allowed_attributes=frozenset({"name", "visibility", "symbol"}),
        allowed_children=frozenset({"ownedComment", "operand"}),
        produces="Node(type=Expression)",
    ),
    "uml:LiteralBoolean": UMLConceptSpec(
        concept_id="uml:LiteralBoolean",
        allowed_attributes=frozenset({"name", "visibility", "value"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=LiteralBoolean)",
    ),
    "uml:LiteralInteger": UMLConceptSpec(
        concept_id="uml:LiteralInteger",
        allowed_attributes=frozenset({"name", "visibility", "value"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=LiteralInteger)",
    ),
    "uml:LiteralReal": UMLConceptSpec(
        concept_id="uml:LiteralReal",
        allowed_attributes=frozenset({"name", "visibility", "value"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=LiteralReal)",
    ),
    "uml:LiteralString": UMLConceptSpec(
        concept_id="uml:LiteralString",
        allowed_attributes=frozenset({"name", "visibility", "value"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=LiteralString)",
    ),
    "uml:LiteralUnlimitedNatural": UMLConceptSpec(
        concept_id="uml:LiteralUnlimitedNatural",
        allowed_attributes=frozenset({"name", "visibility", "value"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=LiteralUnlimitedNatural)",
    ),
    "uml:PrimitiveType": UMLConceptSpec(
        concept_id="uml:PrimitiveType",
        allowed_attributes=frozenset({"name", "visibility", "href"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=PrimitiveType)",
    ),
    "uml:EnumerationLiteral": UMLConceptSpec(
        concept_id="uml:EnumerationLiteral",
        allowed_attributes=frozenset({"name", "visibility"}),
        allowed_children=frozenset({"ownedComment"}),
        produces="Node(type=EnumerationLiteral)",
    ),
    "uml:Association": UMLConceptSpec(
        concept_id="uml:Association",
        allowed_attributes=frozenset({"name", "memberEnd", "navigableOwnedEnd"}),
        allowed_children=frozenset({"ownedEnd", "name"}),
        produces="Edge(type=Association)",
    ),
    "uml:ControlFlow": UMLConceptSpec(
        concept_id="uml:ControlFlow",
        allowed_attributes=frozenset({"name", "source", "target", "activity", "visibility"}),
        allowed_children=frozenset({"guard"}),
        produces="Edge(type=ControlFlow)",
    ),
    "uml:ObjectFlow": UMLConceptSpec(
        concept_id="uml:ObjectFlow",
        allowed_attributes=frozenset({"name", "source", "target", "activity"}),
        allowed_children=frozenset({"guard"}),
        produces="Edge(type=ObjectFlow)",
    ),
    "uml:Transition": UMLConceptSpec(
        concept_id="uml:Transition",
        allowed_attributes=frozenset({"name", "source", "target", "container", "kind", "guard"}),
        allowed_children=frozenset({"guard", "trigger", "effect", "ownedRule"}),
        produces="Edge(type=Transition)",
    ),
    "uml:Message": UMLConceptSpec(
        concept_id="uml:Message",
        allowed_attributes=frozenset(
            {
                "name",
                "sendEvent",
                "receiveEvent",
                "interaction",
                "messageSort",
                "messageKind",
                "connector",
                "visibility",
                "signature",
            }
        ),
        allowed_children=frozenset({"ownedComment", "argument"}),
        produces="Edge(type=Message)",
    ),
    "uml:Generalization": UMLConceptSpec(
        concept_id="uml:Generalization",
        allowed_attributes=frozenset({"name", "general", "specific"}),
        allowed_children=frozenset({"general"}),
        produces="Edge(type=Generalization)",
    ),
    "uml:InterfaceRealization": UMLConceptSpec(
        concept_id="uml:InterfaceRealization",
        allowed_attributes=frozenset({"name", "client", "supplier", "implementingClassifier", "contract"}),
        allowed_children=frozenset({"supplier", "contract"}),
        produces="Edge(type=InterfaceRealization)",
    ),
    "uml:Dependency": UMLConceptSpec(
        concept_id="uml:Dependency",
        allowed_attributes=frozenset({"name", "client", "supplier"}),
        allowed_children=frozenset(),
        produces="Edge(type=Dependency)",
    ),
    "uml:Usage": UMLConceptSpec(
        concept_id="uml:Usage",
        allowed_attributes=frozenset({"name", "client", "supplier"}),
        allowed_children=frozenset(),
        produces="Edge(type=Usage)",
    ),
    "uml:Include": UMLConceptSpec(
        concept_id="uml:Include",
        allowed_attributes=frozenset({"includingCase", "addition"}),
        allowed_children=frozenset({"addition"}),
        produces="Edge(type=includes)",
    ),
    "uml:Extend": UMLConceptSpec(
        concept_id="uml:Extend",
        allowed_attributes=frozenset({"extension", "extendedCase", "extensionLocation"}),
        allowed_children=frozenset({"extendedCase", "extensionLocation"}),
        produces="Edge(type=extends)",
    ),
}


def _custom_handler_spec(handler_name: str, **kwargs: str) -> UMLHandlerSpec:
    return UMLHandlerSpec(kind="custom", handler_name=handler_name, custom_kwargs=kwargs)


def _simple_node_handler_spec(
    *,
    node_type: str,
    scalar_attrs: tuple[str, ...] = (),
    boolean_attrs: tuple[str, ...] = (),
    list_attrs: tuple[str, ...] = (),
    rename_map: Mapping[str, str] | None = None,
    child_ref_tags: tuple[str, ...] = (),
    child_ref_rename_map: Mapping[str, str] | None = None,
    handled_children: tuple[str, ...] = (),
    skip_href_without_id: bool = False,
) -> UMLHandlerSpec:
    return UMLHandlerSpec(
        kind="simple_node",
        node_type=node_type,
        scalar_attrs=scalar_attrs,
        boolean_attrs=boolean_attrs,
        list_attrs=list_attrs,
        rename_map=rename_map or {},
        child_ref_tags=child_ref_tags,
        child_ref_rename_map=child_ref_rename_map or {},
        handled_children=handled_children,
        skip_href_without_id=skip_href_without_id,
    )


def _directed_edge_handler_spec(
    *,
    edge_type: str,
    source_attr: str,
    target_attr: str,
    source_child_tag: str | None = None,
    target_child_tag: str | None = None,
    scalar_attrs: tuple[str, ...] = (),
    list_attrs: tuple[str, ...] = (),
    rename_map: Mapping[str, str] | None = None,
    child_ref_tags: tuple[str, ...] = (),
    child_ref_rename_map: Mapping[str, str] | None = None,
    handled_children: tuple[str, ...] = (),
    include_name: bool = True,
) -> UMLHandlerSpec:
    return UMLHandlerSpec(
        kind="directed_edge",
        edge_type=edge_type,
        source_attr=source_attr,
        target_attr=target_attr,
        source_child_tag=source_child_tag,
        target_child_tag=target_child_tag,
        scalar_attrs=scalar_attrs,
        list_attrs=list_attrs,
        rename_map=rename_map or {},
        child_ref_tags=child_ref_tags,
        child_ref_rename_map=child_ref_rename_map or {},
        handled_children=handled_children,
        include_name=include_name,
    )


def _node_parse_contract(
    *,
    node_type: str,
    scalar_attrs: tuple[str, ...] = (),
    boolean_attrs: tuple[str, ...] = (),
    list_attrs: tuple[str, ...] = (),
    rename_map: Mapping[str, str] | None = None,
    child_ref_tags: tuple[str, ...] = (),
    child_ref_rename_map: Mapping[str, str] | None = None,
    handled_children: tuple[str, ...] = (),
    include_documentation: bool = True,
) -> UMLParseContract:
    return UMLParseContract(
        node_type=node_type,
        scalar_attrs=scalar_attrs,
        boolean_attrs=boolean_attrs,
        list_attrs=list_attrs,
        rename_map=rename_map or {},
        child_ref_tags=child_ref_tags,
        child_ref_rename_map=child_ref_rename_map or {},
        handled_children=handled_children,
        include_documentation=include_documentation,
        include_name=True,
    )


def _edge_parse_contract(
    *,
    edge_type: str,
    source_attr: str | None = None,
    target_attr: str | None = None,
    source_child_tag: str | None = None,
    target_child_tag: str | None = None,
    scalar_attrs: tuple[str, ...] = (),
    list_attrs: tuple[str, ...] = (),
    rename_map: Mapping[str, str] | None = None,
    child_ref_tags: tuple[str, ...] = (),
    child_ref_rename_map: Mapping[str, str] | None = None,
    handled_children: tuple[str, ...] = (),
    include_name: bool = True,
) -> UMLParseContract:
    return UMLParseContract(
        edge_type=edge_type,
        source_attr=source_attr,
        target_attr=target_attr,
        source_child_tag=source_child_tag,
        target_child_tag=target_child_tag,
        scalar_attrs=scalar_attrs,
        list_attrs=list_attrs,
        rename_map=rename_map or {},
        child_ref_tags=child_ref_tags,
        child_ref_rename_map=child_ref_rename_map or {},
        handled_children=handled_children,
        include_documentation=False,
        include_name=include_name,
    )


def _parse_contract_from_handler_spec(handler_spec: UMLHandlerSpec) -> UMLParseContract | None:
    if handler_spec.kind == "simple_node":
        if not handler_spec.node_type:
            return None
        return _node_parse_contract(
            node_type=handler_spec.node_type,
            scalar_attrs=handler_spec.scalar_attrs,
            boolean_attrs=handler_spec.boolean_attrs,
            list_attrs=handler_spec.list_attrs,
            rename_map=handler_spec.rename_map,
            child_ref_tags=handler_spec.child_ref_tags,
            child_ref_rename_map=handler_spec.child_ref_rename_map,
            handled_children=handler_spec.handled_children,
        )

    if handler_spec.kind == "directed_edge":
        if not handler_spec.edge_type:
            return None
        return _edge_parse_contract(
            edge_type=handler_spec.edge_type,
            source_attr=handler_spec.source_attr,
            target_attr=handler_spec.target_attr,
            source_child_tag=handler_spec.source_child_tag,
            target_child_tag=handler_spec.target_child_tag,
            scalar_attrs=handler_spec.scalar_attrs,
            list_attrs=handler_spec.list_attrs,
            rename_map=handler_spec.rename_map,
            child_ref_tags=handler_spec.child_ref_tags,
            child_ref_rename_map=handler_spec.child_ref_rename_map,
            handled_children=handler_spec.handled_children,
            include_name=handler_spec.include_name,
        )

    return None


CONCEPT_HANDLER_SPECS: Mapping[str, UMLHandlerSpec] = {
    "uml:Model": _custom_handler_spec("ModelHandler"),
    "uml:Package": _custom_handler_spec("PackageHandler"),
    "uml:Class": _custom_handler_spec("ClassHandler"),
    "uml:ClassifierTemplateParameter": _simple_node_handler_spec(
        node_type="ClassifierTemplateParameter",
        scalar_attrs=("parameteredElement", "signature"),
        list_attrs=("constrainingClassifier",),
        rename_map={"constrainingClassifier": "constrainingClassifierRefs"},
    ),
    "uml:RedefinableTemplateSignature": _simple_node_handler_spec(
        node_type="RedefinableTemplateSignature",
        list_attrs=("parameter",),
        rename_map={"parameter": "parameterRefs"},
    ),
    "uml:Interface": _custom_handler_spec("InterfaceHandler"),
    "uml:Enumeration": _custom_handler_spec("EnumerationHandler"),
    "uml:DataType": _custom_handler_spec("DataTypeHandler"),
    "uml:Component": _custom_handler_spec("ComponentHandler"),
    "uml:Port": _simple_node_handler_spec(
        node_type="Port",
        scalar_attrs=("visibility", "type"),
        boolean_attrs=(
            "isDerived",
            "isReadOnly",
            "isUnique",
            "isOrdered",
            "isStatic",
        ),
    ),
    "uml:UseCase": _custom_handler_spec("UseCaseHandler"),
    "uml:Actor": _custom_handler_spec("ActorHandler"),
    "uml:Activity": _simple_node_handler_spec(
        node_type="Activity",
        scalar_attrs=("visibility",),
        boolean_attrs=("isReadOnly", "isSingleExecution"),
    ),
    "uml:StateMachine": _simple_node_handler_spec(
        node_type="StateMachine",
        scalar_attrs=("visibility",),
        boolean_attrs=("isReentrant",),
    ),
    "uml:Interaction": _simple_node_handler_spec(
        node_type="Interaction",
        scalar_attrs=("visibility",),
        boolean_attrs=("isLeaf",),
    ),
    "uml:InstanceSpecification": _custom_handler_spec("InstanceSpecificationHandler"),
    "uml:AssociationClass": _custom_handler_spec("AssociationClassHandler"),
    "uml:CommunicationPath": _custom_handler_spec(
        "AssociationHandler",
        element_type="uml:CommunicationPath",
        edge_type="CommunicationPath",
    ),
    "uml:Device": _simple_node_handler_spec(
        node_type="Device",
        scalar_attrs=("visibility",),
        boolean_attrs=("isLeaf",),
    ),
    "uml:Node": _simple_node_handler_spec(
        node_type="Node",
        scalar_attrs=("visibility",),
        boolean_attrs=("isLeaf",),
    ),
    "uml:Artifact": _simple_node_handler_spec(
        node_type="Artifact",
        scalar_attrs=("visibility", "fileName"),
    ),
    "uml:InformationFlow": _custom_handler_spec("InformationFlowHandler"),
    "uml:ExecutionEnvironment": _simple_node_handler_spec(
        node_type="ExecutionEnvironment",
        scalar_attrs=("visibility",),
        boolean_attrs=("isLeaf",),
    ),
    "uml:OpaqueAction": _simple_node_handler_spec(
        node_type="OpaqueAction",
        scalar_attrs=("visibility", "href"),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:CallBehaviorAction": _simple_node_handler_spec(
        node_type="CallBehaviorAction",
        scalar_attrs=("visibility", "behavior"),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:SendSignalAction": _simple_node_handler_spec(
        node_type="SendSignalAction",
        scalar_attrs=("visibility", "signal"),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:ActivityParameterNode": _simple_node_handler_spec(
        node_type="ActivityParameterNode",
        scalar_attrs=("visibility", "parameter"),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:CentralBufferNode": _simple_node_handler_spec(
        node_type="CentralBufferNode",
        scalar_attrs=("visibility", "type"),
        list_attrs=("incoming", "outgoing", "inState", "inPartition"),
        rename_map={
            "incoming": "incomingRefs",
            "outgoing": "outgoingRefs",
            "inState": "inStateRefs",
            "inPartition": "inPartitionRefs",
        },
    ),
    "uml:DataStoreNode": _simple_node_handler_spec(
        node_type="DataStoreNode",
        scalar_attrs=("visibility", "type"),
        list_attrs=("incoming", "outgoing", "inState", "inPartition"),
        rename_map={
            "incoming": "incomingRefs",
            "outgoing": "outgoingRefs",
            "inState": "inStateRefs",
            "inPartition": "inPartitionRefs",
        },
    ),
    "uml:InitialNode": _simple_node_handler_spec(
        node_type="InitialNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:ActivityFinalNode": _simple_node_handler_spec(
        node_type="ActivityFinalNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:FlowFinalNode": _simple_node_handler_spec(
        node_type="FlowFinalNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs"},
    ),
    "uml:DecisionNode": _simple_node_handler_spec(
        node_type="DecisionNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:MergeNode": _simple_node_handler_spec(
        node_type="MergeNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:JoinNode": _simple_node_handler_spec(
        node_type="JoinNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:ForkNode": _simple_node_handler_spec(
        node_type="ForkNode",
        scalar_attrs=("visibility",),
        list_attrs=("incoming", "outgoing", "inPartition"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs", "inPartition": "inPartitionRefs"},
    ),
    "uml:ActivityPartition": _simple_node_handler_spec(
        node_type="ActivityPartition",
        scalar_attrs=("visibility",),
        list_attrs=("node",),
        rename_map={"node": "nodeRefs"},
        child_ref_tags=("subpartition",),
    ),
    "uml:MessageOccurrenceSpecification": _simple_node_handler_spec(
        node_type="MessageOccurrenceSpecification",
        scalar_attrs=("enclosingInteraction", "message", "toAfter"),
        list_attrs=("covered",),
        rename_map={"covered": "coveredRefs"},
    ),
    "uml:ExecutionOccurrenceSpecification": _simple_node_handler_spec(
        node_type="ExecutionOccurrenceSpecification",
        scalar_attrs=("enclosingInteraction",),
        list_attrs=("covered",),
        rename_map={"covered": "coveredRefs"},
    ),
    "uml:BehaviorExecutionSpecification": _simple_node_handler_spec(
        node_type="BehaviorExecutionSpecification",
        scalar_attrs=("enclosingInteraction", "start", "finish"),
        list_attrs=("covered",),
        rename_map={"covered": "coveredRefs"},
        child_ref_tags=("generalOrdering",),
    ),
    "uml:Collaboration": _simple_node_handler_spec(
        node_type="Collaboration",
        scalar_attrs=("visibility",),
        child_ref_tags=("ownedAttribute",),
    ),
    "uml:State": _simple_node_handler_spec(
        node_type="State",
        scalar_attrs=("visibility", "container"),
        list_attrs=("incoming", "outgoing"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs"},
        child_ref_tags=("connectionPoint",),
    ),
    "uml:FinalState": _simple_node_handler_spec(
        node_type="FinalState",
        scalar_attrs=("visibility", "container"),
        list_attrs=("incoming", "outgoing"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs"},
    ),
    "uml:Pseudostate": _simple_node_handler_spec(
        node_type="Pseudostate",
        scalar_attrs=("visibility", "container", "kind"),
        list_attrs=("incoming", "outgoing"),
        rename_map={"incoming": "incomingRefs", "outgoing": "outgoingRefs"},
    ),
    "uml:Region": _simple_node_handler_spec(
        node_type="Region",
        scalar_attrs=("visibility", "stateMachine", "state"),
    ),
    "uml:Lifeline": _simple_node_handler_spec(
        node_type="Lifeline",
        scalar_attrs=("visibility", "interaction", "represents", "decomposedAs"),
        list_attrs=("coveredBy",),
        rename_map={"coveredBy": "coveredByRefs"},
    ),
    "uml:CombinedFragment": _simple_node_handler_spec(
        node_type="CombinedFragment",
        scalar_attrs=("visibility", "interactionOperator", "enclosingInteraction"),
        list_attrs=("covered",),
        rename_map={"covered": "coveredRefs"},
    ),
    "uml:InteractionOperand": _simple_node_handler_spec(
        node_type="InteractionOperand",
        scalar_attrs=("visibility", "enclosingInteraction", "guard"),
        list_attrs=("covered",),
        rename_map={"covered": "coveredRefs"},
        child_ref_tags=("guard",),
    ),
    "uml:InstanceValue": _simple_node_handler_spec(
        node_type="InstanceValue",
        scalar_attrs=("visibility", "instance"),
    ),
    "uml:Expression": _simple_node_handler_spec(
        node_type="Expression",
        scalar_attrs=("visibility", "symbol"),
    ),
    "uml:LiteralBoolean": _simple_node_handler_spec(
        node_type="LiteralBoolean",
        scalar_attrs=("visibility", "value"),
    ),
    "uml:LiteralInteger": _simple_node_handler_spec(
        node_type="LiteralInteger",
        scalar_attrs=("visibility", "value"),
    ),
    "uml:LiteralReal": _simple_node_handler_spec(
        node_type="LiteralReal",
        scalar_attrs=("visibility", "value"),
    ),
    "uml:LiteralString": _simple_node_handler_spec(
        node_type="LiteralString",
        scalar_attrs=("visibility", "value"),
    ),
    "uml:LiteralUnlimitedNatural": _simple_node_handler_spec(
        node_type="LiteralUnlimitedNatural",
        scalar_attrs=("visibility", "value"),
    ),
    "uml:PrimitiveType": _simple_node_handler_spec(
        node_type="PrimitiveType",
        scalar_attrs=("visibility", "href"),
        skip_href_without_id=True,
    ),
    "uml:EnumerationLiteral": _simple_node_handler_spec(
        node_type="EnumerationLiteral",
        scalar_attrs=("visibility",),
    ),
    "uml:Association": _custom_handler_spec("AssociationHandler"),
    "uml:ControlFlow": _directed_edge_handler_spec(
        edge_type="ControlFlow",
        source_attr="source",
        target_attr="target",
        scalar_attrs=("activity", "visibility"),
    ),
    "uml:ObjectFlow": _directed_edge_handler_spec(
        edge_type="ObjectFlow",
        source_attr="source",
        target_attr="target",
        scalar_attrs=("activity",),
    ),
    "uml:Transition": _directed_edge_handler_spec(
        edge_type="Transition",
        source_attr="source",
        target_attr="target",
        scalar_attrs=("container", "kind", "guard"),
        child_ref_tags=("ownedRule",),
    ),
    "uml:Message": _directed_edge_handler_spec(
        edge_type="Message",
        source_attr="sendEvent",
        target_attr="receiveEvent",
        scalar_attrs=("interaction", "messageSort", "messageKind", "connector", "visibility", "signature"),
    ),
    "uml:Generalization": _custom_handler_spec("GeneralizationHandler"),
    "uml:InterfaceRealization": _custom_handler_spec("InterfaceRealizationHandler"),
    "uml:Dependency": _custom_handler_spec(
        "DependencyHandler",
        element_type="uml:Dependency",
        edge_type="Dependency",
    ),
    "uml:Usage": _custom_handler_spec(
        "DependencyHandler",
        element_type="uml:Usage",
        edge_type="Usage",
    ),
    "uml:Include": _custom_handler_spec("IncludeHandler"),
    "uml:Extend": _custom_handler_spec("ExtendHandler"),
}


CUSTOM_CONCEPT_PARSE_CONTRACTS: Mapping[str, UMLParseContract] = {
    "uml:Model": _node_parse_contract(
        node_type="ModelMetadata",
        scalar_attrs=("visibility",),
        include_documentation=False,
    ),
    "uml:Package": _node_parse_contract(
        node_type="Package",
        scalar_attrs=("visibility",),
    ),
    "uml:Class": _node_parse_contract(
        node_type="Class",
        scalar_attrs=("visibility", "href", "owningTemplateParameter"),
        boolean_attrs=("isAbstract", "isLeaf"),
        list_attrs=("templateParameter",),
    ),
    "uml:Interface": _node_parse_contract(
        node_type="Interface",
        scalar_attrs=("visibility", "href"),
        boolean_attrs=("isAbstract",),
    ),
    "uml:Enumeration": _node_parse_contract(
        node_type="Enumeration",
        scalar_attrs=("visibility", "href"),
    ),
    "uml:DataType": _node_parse_contract(
        node_type="DataType",
        scalar_attrs=("visibility", "href"),
        boolean_attrs=("isAbstract",),
    ),
    "uml:Component": _node_parse_contract(
        node_type="Component",
        scalar_attrs=("visibility",),
        boolean_attrs=("isAbstract", "isLeaf"),
    ),
    "uml:UseCase": _node_parse_contract(
        node_type="UseCase",
        scalar_attrs=("visibility", "href"),
        boolean_attrs=("isAbstract", "isLeaf"),
    ),
    "uml:Actor": _node_parse_contract(
        node_type="Actor",
        scalar_attrs=("visibility", "href"),
        boolean_attrs=("isAbstract", "isLeaf"),
    ),
    "uml:InstanceSpecification": _node_parse_contract(
        node_type="InstanceSpecification",
        scalar_attrs=("visibility",),
        list_attrs=("classifier",),
        rename_map={"classifier": "classifierRefs"},
        child_ref_tags=("slot",),
    ),
    "uml:AssociationClass": _node_parse_contract(
        node_type="AssociationClass",
        scalar_attrs=("visibility",),
        boolean_attrs=("isAbstract", "isLeaf"),
        list_attrs=("memberEnd", "navigableOwnedEnd"),
    ),
    "uml:CommunicationPath": _edge_parse_contract(
        edge_type="CommunicationPath",
        list_attrs=("navigableOwnedEnd",),
        include_name=True,
    ),
    "uml:InformationFlow": _edge_parse_contract(
        edge_type="InformationFlow",
        source_attr="informationSource",
        target_attr="informationTarget",
        include_name=True,
    ),
    "uml:Association": _edge_parse_contract(
        edge_type="Association",
        list_attrs=("navigableOwnedEnd",),
        include_name=True,
    ),
    "uml:Generalization": _edge_parse_contract(
        edge_type="Generalization",
        source_attr="specific",
        target_attr="general",
        target_child_tag="general",
        include_name=True,
    ),
    "uml:InterfaceRealization": _edge_parse_contract(
        edge_type="InterfaceRealization",
        source_attr="implementingClassifier",
        target_attr="contract",
        target_child_tag="contract",
        scalar_attrs=("client", "supplier"),
        include_name=True,
    ),
    "uml:Dependency": _edge_parse_contract(
        edge_type="Dependency",
        source_attr="client",
        target_attr="supplier",
        include_name=True,
    ),
    "uml:Usage": _edge_parse_contract(
        edge_type="Usage",
        source_attr="client",
        target_attr="supplier",
        include_name=True,
    ),
    "uml:Include": _edge_parse_contract(
        edge_type="includes",
        source_attr="includingCase",
        target_attr="addition",
        target_child_tag="addition",
        include_name=False,
    ),
    "uml:Extend": _edge_parse_contract(
        edge_type="extends",
        source_attr="extension",
        target_attr="extendedCase",
        target_child_tag="extendedCase",
        scalar_attrs=("extensionLocation",),
        include_name=False,
    ),
}

_missing_handler_specs = sorted(set(SUPPORTED_UML_CONCEPTS) - set(CONCEPT_HANDLER_SPECS))
_extra_handler_specs = sorted(set(CONCEPT_HANDLER_SPECS) - set(SUPPORTED_UML_CONCEPTS))
if _missing_handler_specs or _extra_handler_specs:
    raise ValueError(f"UML handler spec mismatch (missing={_missing_handler_specs}, extra={_extra_handler_specs})")

CONCEPT_PARSE_CONTRACTS: Mapping[str, UMLParseContract | None] = {
    concept_id: CUSTOM_CONCEPT_PARSE_CONTRACTS.get(
        concept_id, _parse_contract_from_handler_spec(CONCEPT_HANDLER_SPECS[concept_id])
    )
    for concept_id in SUPPORTED_UML_CONCEPTS
}
_missing_parse_contracts = sorted(
    concept_id for concept_id, parse_contract in CONCEPT_PARSE_CONTRACTS.items() if parse_contract is None
)
_extra_parse_contracts = sorted(set(CUSTOM_CONCEPT_PARSE_CONTRACTS) - set(SUPPORTED_UML_CONCEPTS))
if _missing_parse_contracts or _extra_parse_contracts:
    raise ValueError(
        f"UML parse contract mismatch (missing={_missing_parse_contracts}, extra={_extra_parse_contracts})"
    )

SUPPORTED_UML_CONCEPTS = {
    concept_id: replace(
        spec,
        handler=CONCEPT_HANDLER_SPECS[concept_id],
        parse_contract=CONCEPT_PARSE_CONTRACTS[concept_id],
    )
    for concept_id, spec in SUPPORTED_UML_CONCEPTS.items()
}


TAG_TO_CONCEPT: dict[str, str] = {
    "Model": "uml:Model",
    "generalization": "uml:Generalization",
    "interfaceRealization": "uml:InterfaceRealization",
    "include": "uml:Include",
    "extend": "uml:Extend",
    "ownedUseCase": "uml:UseCase",
    "ownedBehavior": "uml:Activity",
    "doActivity": "uml:StateMachine",
    "nestedNode": "uml:ExecutionEnvironment",
    "region": "uml:Region",
    "transition": "uml:Transition",
    "message": "uml:Message",
    "lifeline": "uml:Lifeline",
    "operand": "uml:InteractionOperand",
}


CONTAINMENT_CHILD_TAGS: frozenset[str] = frozenset(
    {
        "packagedElement",
        "ownedUseCase",
        "ownedBehavior",
        "doActivity",
        "nestedNode",
        "nestedClassifier",
        "ownedNode",
        "ownedGroup",
        "edge",
        "subvertex",
        "region",
        "transition",
        "fragment",
        "lifeline",
        "message",
        "operand",
    }
)


def concept_spec(concept_id: str) -> UMLConceptSpec:
    """Return metamodel spec for a concept id."""
    return SUPPORTED_UML_CONCEPTS[concept_id]
