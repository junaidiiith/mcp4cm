"""Utility helpers for parser IR outputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from mcp4cm.parsers.diagnostics import ParserRunStats, WarningType
from mcp4cm.parsers.ir import IR

if TYPE_CHECKING:
    import networkx as nx


MissingNodePolicy = Literal["create", "error", "skip"]
FEATURE_ATTRIBUTE_KEYS = ("attributes", "ownedAttributes", "eAttributes")
FEATURE_OPERATION_KEYS = ("operations", "ownedOperations", "eOperations")
FEATURE_PARAMETER_KEYS = ("parameters", "ownedParameters", "eParameters")


@dataclass(slots=True, frozen=True)
class UMLFeatureProjection:
    include_attributes: bool = True
    include_operations: bool = True
    include_parameters: bool = True


def convert_to_networkx(graph: IR, missing_node_policy: MissingNodePolicy = "error") -> nx.MultiDiGraph:
    """
    Convert an IR graph into an equivalent NetworkX MultiDiGraph.

    Args:
        graph: IR graph instance.
        missing_node_policy: Behavior when edges reference nodes not present in ``graph.nodes``.
            - ``create``: Create placeholder nodes.
            - ``error``: Raise ``ValueError``.
            - ``skip``: Skip edges with missing endpoints.

    Returns:
        NetworkX MultiDiGraph with IR metadata stored as graph/node/edge attributes.
    """
    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError(
            "convert_to_networkx requires the optional dependency 'networkx'. Install it with: pip install networkx"
        ) from exc

    if missing_node_policy not in {"create", "error", "skip"}:
        raise ValueError(f"missing_node_policy must be one of: 'create', 'error', 'skip'. Got: {missing_node_policy!r}")

    nx_graph = nx.MultiDiGraph(
        id=graph.id,
        language=graph.language,
        data=dict(graph.data),
    )

    node_ids: set[str] = set()
    for node in graph.nodes:
        node_attrs: dict[str, Any] = {
            "id": node.id,
            "type": node.type,
            "name": node.name,
            "data": dict(node.data),
        }
        if node.eClass:
            node_attrs["eClass"] = node.eClass
        nx_graph.add_node(node.id, **node_attrs)
        node_ids.add(node.id)

    for edge in graph.edges:
        missing_endpoints = [n_id for n_id in (edge.sourceId, edge.targetId) if n_id not in node_ids]
        if missing_endpoints:
            if missing_node_policy == "error":
                raise ValueError(
                    f"Edge '{edge.id}' references missing node(s): {', '.join(sorted(set(missing_endpoints)))}"
                )
            if missing_node_policy == "skip":
                continue

            for missing_id in missing_endpoints:
                if missing_id in node_ids:
                    continue
                nx_graph.add_node(
                    missing_id,
                    id=missing_id,
                    type="UnresolvedReference",
                    name="",
                    data={},
                    placeholder=True,
                )
                node_ids.add(missing_id)

        edge_key = edge.id
        if nx_graph.has_edge(edge.sourceId, edge.targetId, key=edge_key):
            suffix = 1
            while nx_graph.has_edge(edge.sourceId, edge.targetId, key=f"{edge.id}__{suffix}"):
                suffix += 1
            edge_key = f"{edge.id}__{suffix}"

        nx_graph.add_edge(
            edge.sourceId,
            edge.targetId,
            key=edge_key,
            id=edge.id,
            type=edge.type,
            data=dict(edge.data),
        )

    return nx_graph


def drop_ir_edges_with_missing_nodes(ir: IR, stats: ParserRunStats | None = None) -> int:
    node_ids = {str(node.id) for node in ir.nodes}
    kept_edges = []
    dropped = 0

    for edge in ir.edges:
        source_id = str(edge.sourceId)
        target_id = str(edge.targetId)
        missing = []
        if source_id not in node_ids:
            missing.append(f"source='{source_id}'")
        if target_id not in node_ids:
            missing.append(f"target='{target_id}'")
        if missing:
            dropped += 1
            if stats is not None:
                stats.add_skip(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"Dropped edge '{edge.id}' ({edge.type}) due missing endpoint(s): {', '.join(missing)}",
                )
            continue
        kept_edges.append(edge)

    ir.edges = kept_edges
    return dropped


def normalize_graph_attributes(graph, *, language: str = ""):
    for _, attrs in graph.nodes(data=True):
        data = attrs.get("data") if isinstance(attrs.get("data"), dict) else {}
        if "name" not in attrs and isinstance(data.get("name"), str):
            attrs["name"] = data.get("name", "")
        if "type" not in attrs and isinstance(data.get("type"), str):
            attrs["type"] = data.get("type", "")
        attrs["name"] = str(attrs.get("name") or "")
        attrs["type"] = str(attrs.get("type") or attrs.get("eClass") or "")
    for _, _, attrs in graph.edges(data=True):
        data = attrs.get("data") if isinstance(attrs.get("data"), dict) else {}
        if "type" not in attrs and isinstance(data.get("type"), str):
            attrs["type"] = data.get("type", "")
        attrs["type"] = str(attrs.get("type") or attrs.get("relationship") or "")
    return graph


def expand_uml_feature_nodes(graph, profile: UMLFeatureProjection) -> None:
    synthetic_nodes: list[tuple[str, dict[str, Any]]] = []
    synthetic_edges: list[tuple[str, str, dict[str, Any]]] = []

    for node_id, attrs in list(graph.nodes(data=True)):
        data = attrs.get("data") if isinstance(attrs.get("data"), dict) else {}
        if profile.include_attributes:
            feature_items = extract_features(attrs, data, FEATURE_ATTRIBUTE_KEYS)
            synthetic_nodes.extend(build_feature_nodes(node_id, "attribute", feature_items))
            synthetic_edges.extend(build_feature_edges(node_id, "has_attribute", feature_items))
        if profile.include_operations:
            feature_items = extract_features(attrs, data, FEATURE_OPERATION_KEYS)
            synthetic_nodes.extend(build_feature_nodes(node_id, "operation", feature_items))
            synthetic_edges.extend(build_feature_edges(node_id, "has_operation", feature_items))
        if profile.include_parameters:
            feature_items = extract_features(attrs, data, FEATURE_PARAMETER_KEYS)
            synthetic_nodes.extend(build_feature_nodes(node_id, "parameter", feature_items))
            synthetic_edges.extend(build_feature_edges(node_id, "has_parameter", feature_items))

    for synthetic_id, feature_attrs in synthetic_nodes:
        if synthetic_id not in graph:
            graph.add_node(synthetic_id, **feature_attrs)
    for source_id, target_id, edge_attrs in synthetic_edges:
        graph.add_edge(source_id, target_id, **edge_attrs)


def extract_features(attrs: dict[str, Any], data: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    values: list[Any] = []
    for key in keys:
        candidate = attrs.get(key, data.get(key))
        if isinstance(candidate, list):
            values.extend(candidate)
        elif candidate is not None:
            values.append(candidate)
    result: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, dict):
            feature_name = str(value.get("name") or value.get("id") or value.get("type") or "")
            feature_data = dict(value)
        else:
            feature_name = str(value)
            feature_data = {"value": value}
        result.append({"name": feature_name, "data": feature_data})
    return result


def feature_node_id(parent_id: Any, feature_kind: str, index: int, feature: dict[str, Any]) -> str:
    name = feature.get("name") or ""
    payload = json.dumps(feature.get("data") or {}, sort_keys=True, default=str)
    digest = hashlib.sha1(f"{parent_id}|{feature_kind}|{index}|{name}|{payload}".encode()).hexdigest()[:12]
    return f"{parent_id}::{feature_kind}::{digest}"


def build_feature_nodes(
    parent_id: Any, feature_kind: str, feature_items: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    for index, feature in enumerate(feature_items):
        name = feature.get("name") or ""
        synthetic_node_id = feature_node_id(parent_id, feature_kind, index, feature)
        nodes.append(
            (
                synthetic_node_id,
                {
                    "id": synthetic_node_id,
                    "type": feature_kind,
                    "name": str(name),
                    "feature_kind": feature_kind,
                    "parent_id": str(parent_id),
                    "data": dict(feature.get("data") or {}),
                },
            )
        )
    return nodes


def build_feature_edges(
    parent_id: Any, edge_type: str, feature_items: list[dict[str, Any]]
) -> list[tuple[str, str, dict[str, Any]]]:
    edges: list[tuple[str, str, dict[str, Any]]] = []
    feature_kind = edge_type.replace("has_", "")
    for index, feature in enumerate(feature_items):
        synthetic_node_id = feature_node_id(parent_id, feature_kind, index, feature)
        edges.append(
            (
                str(parent_id),
                synthetic_node_id,
                {
                    "id": f"{parent_id}->{synthetic_node_id}:{edge_type}",
                    "type": edge_type,
                    "feature_kind": edge_type,
                },
            )
        )
    return edges
