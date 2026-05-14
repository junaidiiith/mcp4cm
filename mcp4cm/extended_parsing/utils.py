"""Utility helpers for parser IR outputs."""

from __future__ import annotations

from typing import Literal, TYPE_CHECKING

from mcp4cm.extended_ir.types import IR

if TYPE_CHECKING:
    import networkx as nx


MissingNodePolicy = Literal["create", "error", "skip"]


def convert_to_networkx(graph: IR, missing_node_policy: MissingNodePolicy = "error") -> "nx.MultiDiGraph":
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
            "convert_to_networkx requires the optional dependency 'networkx'. "
            "Install it with: pip install networkx"
        ) from exc

    if missing_node_policy not in {"create", "error", "skip"}:
        raise ValueError(
            "missing_node_policy must be one of: 'create', 'error', 'skip'. "
            f"Got: {missing_node_policy!r}"
        )

    nx_graph = nx.MultiDiGraph(
        id=graph.id,
        language=graph.language,
        data=dict(graph.data),
    )

    node_ids: set[str] = set()
    for node in graph.nodes:
        nx_graph.add_node(
            node.id,
            id=node.id,
            type=node.type,
            name=node.name,
            data=dict(node.data),
        )
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
