"""UML XMI parser for converting UML models to graph-based IR."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field

from mcp4cm.parsers.base import BaseParser, register_parser
from mcp4cm.parsers.diagnostics import ParserRunStats, WarningType
from mcp4cm.parsers.ir import IR, Edge, Node
from mcp4cm.parsers.uml_xmi.handlers import (
    ActorHandler,
    AssociationClassHandler,
    AssociationHandler,
    ClassHandler,
    ComponentHandler,
    DataTypeHandler,
    DependencyHandler,
    DirectedEdgeHandler,
    ElementHandler,
    EnumerationHandler,
    ExtendHandler,
    GeneralizationHandler,
    IncludeHandler,
    InformationFlowHandler,
    InstanceSpecificationHandler,
    InterfaceHandler,
    InterfaceRealizationHandler,
    ModelHandler,
    PackageHandler,
    SimpleNodeHandler,
    UseCaseHandler,
)
from mcp4cm.parsers.uml_xmi.metamodel import (
    CONTAINMENT_CHILD_TAGS,
    SUPPORTED_UML_CONCEPTS,
    TAG_TO_CONCEPT,
    UMLHandlerSpec,
)
from mcp4cm.parsers.uml_xmi.xmi_utils import (
    find_model,
    is_tool_extension,
    localname,
    xmi_id,
    xsi_type,
)

IGNORED_UNHANDLED_ELEMENTS: set[str] = set()
MULTIPLICITY_VALUE_TAGS: set[str] = {"lowerValue", "upperValue"}
EDGE_VALUE_SPEC_TAGS: set[str] = {"guard", "weight"}
CONTEXTUAL_VALUE_SPEC_TAGS: set[str] = {"specification", "value", "argument"}
EMBEDDED_VALUE_SPEC_TYPES: set[str] = {
    "uml:LiteralBoolean",
    "uml:LiteralInteger",
    "uml:LiteralReal",
    "uml:LiteralString",
    "uml:LiteralUnlimitedNatural",
    "uml:Expression",
    "uml:InstanceValue",
}

# Post-processing reference materialization for concepts that currently store
# key relationships only in node.data payload.
NODE_SCALAR_REF_KEYS: dict[str, tuple[str, ...]] = {
    "ActivityParameterNode": ("parameter",),
    "BehaviorExecutionSpecification": ("enclosingInteraction", "start", "finish"),
    "ExecutionOccurrenceSpecification": ("enclosingInteraction",),
    "Lifeline": ("interaction", "represents", "decomposedAs"),
    "Region": ("stateMachine", "state"),
    "InstanceValue": ("instance",),
    "InteractionOperand": ("enclosingInteraction", "guard"),
    "CombinedFragment": ("enclosingInteraction",),
    "ClassifierTemplateParameter": ("parameteredElement", "signature"),
    "CentralBufferNode": ("type",),
    "DataStoreNode": ("type",),
}

NODE_LIST_REF_KEYS: dict[str, tuple[str, ...]] = {
    "BehaviorExecutionSpecification": ("coveredRefs", "generalOrderingRefs"),
    "ExecutionOccurrenceSpecification": ("coveredRefs",),
    "Lifeline": ("coveredByRefs",),
    "Collaboration": ("ownedAttributeRefs",),
    "ActivityPartition": ("nodeRefs", "subpartitionRefs"),
    "InteractionOperand": ("coveredRefs", "guardRefs"),
    "CombinedFragment": ("coveredRefs",),
    "ClassifierTemplateParameter": ("constrainingClassifierRefs",),
    "RedefinableTemplateSignature": ("parameterRefs",),
}

CUSTOM_HANDLER_REGISTRY = {
    "ModelHandler": ModelHandler,
    "PackageHandler": PackageHandler,
    "ClassHandler": ClassHandler,
    "InterfaceHandler": InterfaceHandler,
    "EnumerationHandler": EnumerationHandler,
    "DataTypeHandler": DataTypeHandler,
    "ComponentHandler": ComponentHandler,
    "UseCaseHandler": UseCaseHandler,
    "ActorHandler": ActorHandler,
    "AssociationClassHandler": AssociationClassHandler,
    "InstanceSpecificationHandler": InstanceSpecificationHandler,
    "AssociationHandler": AssociationHandler,
    "GeneralizationHandler": GeneralizationHandler,
    "InterfaceRealizationHandler": InterfaceRealizationHandler,
    "DependencyHandler": DependencyHandler,
    "IncludeHandler": IncludeHandler,
    "ExtendHandler": ExtendHandler,
    "InformationFlowHandler": InformationFlowHandler,
}


@dataclass(frozen=True)
class ParseOptions:
    """Options for UML parsing."""

    # Create a Node for each uml:Package with "contains" edges to contained elements.
    include_packages: bool = True
    # Create an explicit root node for uml:Model so derived model anchoring edges
    # have a valid source endpoint in IR/networkx.
    include_model_root_node: bool = True


@dataclass
class ParseContext:
    """Context for UML parsing operations."""

    root: ET.Element
    ir: IR
    options: ParseOptions
    run_stats: ParserRunStats | None = None

    id_index: dict[str, ET.Element] = field(default_factory=dict)
    parent_map: dict[ET.Element, ET.Element] = field(default_factory=dict)

    nodes_by_id: dict[str, Node] = field(default_factory=dict)
    handler_map: dict[str, ElementHandler] = field(default_factory=dict)
    tag_handler_map: dict[str, str] = field(default_factory=dict)

    edge_ids: set[str] = field(default_factory=set)

    def elem(self, _id: str) -> ET.Element | None:
        """Get element by xmi:id."""
        return self.id_index.get(_id)

    def add_node(self, node: Node) -> None:
        """Add node to IR and index."""
        if node.id in self.nodes_by_id:
            self.skip_with_warning(
                WarningType.DUPLICATE_ID,
                f"Duplicate node id '{node.id}' encountered; keeping first node and skipping duplicate.",
            )
            return
        self.ir.nodes.append(node)
        self.nodes_by_id[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add edge to IR, avoiding duplicates."""
        if edge.id in self.edge_ids:
            self.skip_with_warning(
                WarningType.DUPLICATE_ID,
                f"Duplicate edge id '{edge.id}' encountered; keeping first edge and skipping duplicate.",
            )
            return
        self.edge_ids.add(edge.id)
        self.ir.edges.append(edge)

    def warn(self, warning_type: WarningType, message: str) -> None:
        """Record warning in parser run stats when available."""
        if self.run_stats is None:
            return
        self.run_stats.add_warning(warning_type, message)

    def skip_with_warning(self, warning_type: WarningType, message: str) -> None:
        """Record skipped element + warning in parser run stats when available."""
        if self.run_stats is None:
            return
        self.run_stats.add_skip(warning_type, message)


@register_parser
class UMLXMIParser(BaseParser):
    language = "UML"

    def __init__(
        self,
        options: ParseOptions | None = None,
        handlers: list[ElementHandler] | None = None,
    ):
        super().__init__()
        self.options = options or ParseOptions()
        self.handlers = handlers or self._get_default_handlers()

    def _get_default_handlers(self) -> list[ElementHandler]:
        """Build default handlers from executable metamodel specs."""
        handlers: list[ElementHandler] = []
        for concept_id, concept in SUPPORTED_UML_CONCEPTS.items():
            handler_spec = concept.handler
            if handler_spec is None:
                raise ValueError(f"Concept '{concept_id}' has no runtime handler specification.")
            handlers.append(self._build_handler_from_spec(concept_id, handler_spec))
        return handlers

    def _build_handler_from_spec(
        self,
        concept_id: str,
        handler_spec: UMLHandlerSpec,
    ) -> ElementHandler:
        """Instantiate a runtime handler from metamodel metadata."""
        if handler_spec.kind == "simple_node":
            if not handler_spec.node_type:
                raise ValueError(f"Simple-node concept '{concept_id}' is missing node_type.")
            return SimpleNodeHandler(
                element_type=concept_id,
                node_type=handler_spec.node_type,
                scalar_attrs=handler_spec.scalar_attrs,
                boolean_attrs=handler_spec.boolean_attrs,
                list_attrs=handler_spec.list_attrs,
                rename_map=handler_spec.rename_map,
                child_ref_tags=handler_spec.child_ref_tags,
                child_ref_rename_map=handler_spec.child_ref_rename_map,
                handled_children=handler_spec.handled_children,
                skip_href_without_id=handler_spec.skip_href_without_id,
            )

        if handler_spec.kind == "directed_edge":
            if not handler_spec.edge_type or not handler_spec.source_attr or not handler_spec.target_attr:
                raise ValueError(f"Directed-edge concept '{concept_id}' is missing edge_type/source_attr/target_attr.")
            return DirectedEdgeHandler(
                element_type=concept_id,
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

        if handler_spec.kind == "custom":
            if not handler_spec.handler_name:
                raise ValueError(f"Custom concept '{concept_id}' is missing handler_name.")
            handler_class = CUSTOM_HANDLER_REGISTRY.get(handler_spec.handler_name)
            if handler_class is None:
                raise ValueError(
                    f"Custom handler '{handler_spec.handler_name}' for concept '{concept_id}' is not registered."
                )
            handler = handler_class(**dict(handler_spec.custom_kwargs))
            if handler.element_type != concept_id:
                raise ValueError(
                    f"Custom handler '{handler_spec.handler_name}' resolved element_type "
                    f"'{handler.element_type}', expected '{concept_id}'."
                )
            return handler

        raise ValueError(f"Unsupported handler kind '{handler_spec.kind}' for concept '{concept_id}'.")

    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        """Parse a UML XMI file into IR."""
        self._start_run()

        tree = ET.parse(filepath)
        root = tree.getroot()

        model = find_model(root)
        model_id = xmi_id(model) or "model"
        model_name = model.attrib.get("name", "")

        ir = IR(id=model_id, language=self.language, data={"name": model_name})
        ctx = ParseContext(root=root, ir=ir, options=self.options, run_stats=self._stats())
        if self.options.include_model_root_node:
            ctx.add_node(
                Node(
                    id=model_id,
                    type="Model",
                    name=model_name,
                    data={"xmiType": "uml:Model"},
                )
            )

        self._build_indices(ctx)
        self._parse_elements(ctx, model)
        self._create_containment_edges(ctx, model)
        self._create_model_contains_edges(ctx, model)
        self._create_xml_ownership_edges(ctx)
        self._create_reference_edges(ctx)

        return ctx.ir, self._stats()

    def _build_indices(self, ctx: ParseContext) -> None:
        """Build xmi:id index and parent map."""
        for e in ctx.root.iter():
            _id = xmi_id(e)
            if _id:
                if _id in ctx.id_index:
                    ctx.warn(
                        WarningType.DUPLICATE_ID,
                        f"Duplicate xmi:id '{_id}' encountered in XML; keeping first element in lookup index.",
                    )
                    continue
                ctx.id_index[_id] = e

        for parent in ctx.root.iter():
            for child in list(parent):
                ctx.parent_map[child] = parent

    def _resolve_handler_key(self, ctx: ParseContext, elem: ET.Element) -> str | None:
        """Resolve a handler key from XML tag and/or xsi:type."""
        tag_name = localname(elem.tag)

        if tag_name == "packagedElement":
            return xsi_type(elem)

        typed = xsi_type(elem)
        if typed:
            return typed

        tag_mapped = ctx.tag_handler_map.get(tag_name)
        if tag_mapped:
            return tag_mapped

        return None

    def _parse_elements(self, ctx: ParseContext, model: ET.Element) -> None:
        """Parse all model descendants using registered handlers."""
        ctx.handler_map = {}
        for handler in self.handlers:
            handler_key = handler.element_type
            if handler_key in ctx.handler_map:
                raise ValueError(
                    f"Duplicate handler registration for '{handler_key}' "
                    f"({type(ctx.handler_map[handler_key]).__name__} and {type(handler).__name__})."
                )
            ctx.handler_map[handler_key] = handler
        ctx.tag_handler_map = dict(TAG_TO_CONCEPT)

        if "uml:Model" not in ctx.handler_map:
            ctx.skip_with_warning(
                WarningType.UNKNOWN_NODE_TYPE,
                "No uml:Model handler registered; parser cannot handle model root.",
            )
            return

        for elem in model.iter():
            if is_tool_extension(elem):
                continue

            # Multiplicity value objects belong to their owning property/association end
            # and are embedded through read_multiplicity(...), not standalone graph nodes.
            if localname(elem.tag) in MULTIPLICITY_VALUE_TAGS:
                continue

            # ActivityEdge guard/weight value specifications should stay embedded in
            # their owning directed edge payload.
            elem_tag = localname(elem.tag)
            elem_type = xsi_type(elem) or ""
            if elem_tag in EDGE_VALUE_SPEC_TAGS and (
                elem_type in EMBEDDED_VALUE_SPEC_TYPES or (not elem_type and "value" in elem.attrib)
            ):
                continue

            parent = ctx.parent_map.get(elem)
            parent_tag = localname(parent.tag) if parent is not None else ""
            if (
                elem_tag in CONTEXTUAL_VALUE_SPEC_TAGS
                and (
                    elem_type in EMBEDDED_VALUE_SPEC_TYPES
                    or (not elem_type and ("value" in elem.attrib or "symbol" in elem.attrib))
                )
                and (
                    (elem_tag == "specification" and parent_tag == "ownedRule")
                    or (elem_tag == "value" and parent_tag == "slot")
                    or (elem_tag == "argument" and parent_tag == "message")
                )
            ):
                continue

            handler_key = self._resolve_handler_key(ctx, elem)
            if not handler_key:
                continue

            handler = ctx.handler_map.get(handler_key)
            if handler:
                handler.handle(ctx, elem)
                continue

            # Report any typed element without a registered handler.
            elem_id = xmi_id(elem)
            elem_type = xsi_type(elem)
            if elem_type and elem_type not in IGNORED_UNHANDLED_ELEMENTS:
                ctx.skip_with_warning(
                    WarningType.UNKNOWN_NODE_TYPE,
                    f"[UNHANDLED ELEMENT] Type: {elem_type}, ID: {elem_id}, Tag: {localname(elem.tag)}",
                )

    def _create_containment_edges(self, ctx: ParseContext, model: ET.Element) -> None:
        """Create containment edges for packages and their contents."""
        if not ctx.options.include_packages:
            return

        self._walk_containment(ctx, model, current_pkg_id=None)

    def _create_model_contains_edges(self, ctx: ParseContext, model: ET.Element) -> None:
        """Connect top-level model children to the model id for graph anchoring."""
        model_id = str(ctx.ir.data.get("modelId") or ctx.ir.id)
        if model_id not in ctx.nodes_by_id:
            ctx.warn(
                WarningType.UNRESOLVED_REFERENCE,
                f"Skipping model anchoring edges because model node '{model_id}' is not present in parsed nodes.",
            )
            return

        for child in list(model):
            if is_tool_extension(child):
                continue
            child_id = xmi_id(child)
            if not child_id or child_id not in ctx.nodes_by_id:
                continue
            ctx.add_edge(
                Edge(
                    id=f"{model_id}__model_contains__{child_id}",
                    sourceId=model_id,
                    targetId=child_id,
                    type="contains",
                    data={"derivedFrom": "modelOwnership"},
                )
            )

    def _child_concept_and_id(self, child: ET.Element) -> tuple[str, str] | None:
        """Resolve concept type and xmi:id for containment-relevant child elements."""
        if is_tool_extension(child):
            return None

        child_tag = localname(child.tag)
        child_id = xmi_id(child)
        if not child_id:
            return None

        if child_tag == "packagedElement":
            child_type = xsi_type(child)
            if not child_type:
                return None
            return (child_type, child_id)

        child_type = xsi_type(child)
        if child_type:
            return (child_type, child_id)

        tag_mapped = TAG_TO_CONCEPT.get(child_tag)
        if tag_mapped:
            return (tag_mapped, child_id)

        return None

    def _walk_containment(self, ctx: ParseContext, container: ET.Element, current_pkg_id: str | None) -> None:
        """Recursively walk containment-relevant children."""
        for child in list(container):
            if is_tool_extension(child):
                continue

            child_tag = localname(child.tag)
            next_pkg_id = current_pkg_id

            if child_tag in CONTAINMENT_CHILD_TAGS:
                child_info = self._child_concept_and_id(child)
                if child_info:
                    child_type, child_id = child_info

                    if child_type == "uml:Package":
                        if child_id not in ctx.nodes_by_id:
                            ctx.warn(
                                WarningType.UNRESOLVED_REFERENCE,
                                f"Skipping containment package '{child_id}' because no corresponding node exists.",
                            )
                            next_pkg_id = None
                        elif current_pkg_id and current_pkg_id in ctx.nodes_by_id:
                            ctx.add_edge(
                                Edge(
                                    id=f"{current_pkg_id}__contains__{child_id}",
                                    sourceId=current_pkg_id,
                                    targetId=child_id,
                                    type="contains",
                                    data={},
                                )
                            )
                            next_pkg_id = child_id
                        else:
                            next_pkg_id = child_id
                    elif current_pkg_id and current_pkg_id in ctx.nodes_by_id and child_id in ctx.nodes_by_id:
                        ctx.add_edge(
                            Edge(
                                id=f"{current_pkg_id}__contains__{child_id}",
                                sourceId=current_pkg_id,
                                targetId=child_id,
                                type="contains",
                                data={"elementType": child_type},
                            )
                        )
                    elif current_pkg_id and current_pkg_id in ctx.nodes_by_id and child_id not in ctx.nodes_by_id:
                        ctx.warn(
                            WarningType.UNRESOLVED_REFERENCE,
                            f"Skipping containment edge {current_pkg_id} -> {child_id} "
                            f"({child_type}) due to missing target node.",
                        )

            self._walk_containment(ctx, child, current_pkg_id=next_pkg_id)

    def _create_xml_ownership_edges(self, ctx: ParseContext) -> None:
        """Connect each parsed node to its nearest parsed ancestor in XML."""
        for node_id in ctx.nodes_by_id:
            elem = ctx.elem(node_id)
            if elem is None:
                continue

            parent = ctx.parent_map.get(elem)
            owner_id: str | None = None
            while parent is not None:
                parent_id = xmi_id(parent)
                if parent_id and parent_id in ctx.nodes_by_id:
                    owner_id = parent_id
                    break
                parent = ctx.parent_map.get(parent)

            if not owner_id:
                continue

            ctx.add_edge(
                Edge(
                    id=f"{owner_id}__owns__{node_id}",
                    sourceId=owner_id,
                    targetId=node_id,
                    type="contains",
                    data={"derivedFrom": "xmlOwnership"},
                )
            )

    def _create_reference_edges(self, ctx: ParseContext) -> None:
        """Materialize node-to-node edges from selected reference fields in node.data."""
        for node in list(ctx.ir.nodes):
            scalar_keys = NODE_SCALAR_REF_KEYS.get(node.type, ())
            list_keys = NODE_LIST_REF_KEYS.get(node.type, ())
            if not scalar_keys and not list_keys:
                continue

            for key in scalar_keys:
                value = node.data.get(key)
                if isinstance(value, str):
                    self._add_reference_edge(ctx, source_id=node.id, key=key, target_ids=(value,))

            for key in list_keys:
                value = node.data.get(key)
                if isinstance(value, list):
                    target_ids = tuple(v for v in value if isinstance(v, str))
                    self._add_reference_edge(ctx, source_id=node.id, key=key, target_ids=target_ids)

    def _add_reference_edge(
        self,
        ctx: ParseContext,
        *,
        source_id: str,
        key: str,
        target_ids: Iterable[str],
    ) -> None:
        """Create reference edges from source to existing target nodes."""
        for target_id in target_ids:
            if target_id not in ctx.nodes_by_id:
                continue
            ctx.add_edge(
                Edge(
                    id=f"{source_id}__ref__{key}__{target_id}",
                    sourceId=source_id,
                    targetId=target_id,
                    type="references",
                    data={"referenceKey": key},
                )
            )
