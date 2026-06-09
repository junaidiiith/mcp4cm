"""Intermediate Representation (IR) for conceptual models."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple
import json


@dataclass
class Node:
    """Represents a node in the IR graph."""

    id: str
    type: str
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    eClass: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary."""
        return asdict(self)


@dataclass
class Edge:
    """Represents an edge in the IR graph."""

    id: str
    sourceId: str
    targetId: str
    type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge to dictionary."""
        return asdict(self)


@dataclass
class IR:
    """Intermediate Representation for a conceptual model."""

    id: str
    language: str
    data: Dict[str, Any] = field(default_factory=dict)
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert IR to dictionary."""
        return {
            "id": self.id,
            "language": self.language,
            "data": self.data,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert IR to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, filepath: str) -> None:
        """Save IR to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IR":
        """Create IR from dictionary."""
        nodes = [Node(**node) for node in data.get("nodes", [])]
        edges = [Edge(**edge) for edge in data.get("edges", [])]
        return cls(
            id=data["id"],
            language=data["language"],
            data=data.get("data", {}),
            nodes=nodes,
            edges=edges,
        )

    @classmethod
    def load(cls, filepath: str) -> "IR":
        """Load IR from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate IR structure.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check required fields
        if not self.id:
            errors.append("IR missing required field: id")
        if not self.language:
            errors.append("IR missing required field: language")

        # Check node IDs are unique
        node_ids = set()
        for node in self.nodes:
            if not node.id:
                errors.append("Node missing required field: id")
            elif node.id in node_ids:
                errors.append(f"Duplicate node ID: {node.id}")
            else:
                node_ids.add(node.id)

        # Check edge references
        for edge in self.edges:
            if not edge.id:
                errors.append("Edge missing required field: id")
            if not edge.sourceId:
                errors.append(f"Edge {edge.id} missing required field: sourceId")
            elif edge.sourceId not in node_ids:
                errors.append(f"Edge {edge.id} references non-existent source node: {edge.sourceId}")
            if not edge.targetId:
                errors.append(f"Edge {edge.id} missing required field: targetId")
            elif edge.targetId not in node_ids:
                errors.append(f"Edge {edge.id} references non-existent target node: {edge.targetId}")

        return len(errors) == 0, errors

