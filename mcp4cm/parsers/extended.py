from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp4cm.core import ModelRecord
from mcp4cm.extended_parsing.archimate.archimate_archi_parser import ArchiMateArchiParser
from mcp4cm.extended_parsing.bpmn.bpmn_signavio_json_parser import BPMNSignavioJSONParser
from mcp4cm.extended_parsing.types import ParserRunStats
from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_parsing.uml.uml_parser import ParseOptions, UMLXMIParser
from mcp4cm.extended_parsing.utils import convert_to_networkx
from mcp4cm.parsers.base import BaseModelParser
from mcp4cm.xmi_names import extract_xmi_names

FEATURE_ATTRIBUTE_KEYS = ("attributes", "ownedAttributes", "eAttributes")
FEATURE_OPERATION_KEYS = ("operations", "ownedOperations", "eOperations")
FEATURE_PARAMETER_KEYS = ("parameters", "ownedParameters", "eParameters")


@dataclass(slots=True, frozen=True)
class RepresentationProfile:
    include_attributes: bool = True
    include_operations: bool = True
    include_parameters: bool = True
    include_model_root_node: bool = False

    def as_metadata(self) -> dict[str, Any]:
        return {
            "includeAttributes": self.include_attributes,
            "includeOperations": self.include_operations,
            "includeParameters": self.include_parameters,
            "includeModelRootNode": self.include_model_root_node,
        }


class ExtendedModelParser(BaseModelParser):
    parser_language: str
    metadata_language: str
    format_name: str

    def __init__(self, representation: RepresentationProfile | None = None):
        self.representation = representation or RepresentationProfile()

    def parse_file(self, source_path: Path, *, model_id: str | None = None) -> ModelRecord:
        parser = self._create_parser()
        ir, stats = parser.parse(str(source_path))
        drop_ir_edges_with_missing_nodes(ir, stats)
        graph = convert_to_networkx(ir, missing_node_policy="error")
        graph = normalize_graph_attributes(graph, language=self.metadata_language)
        expand_feature_nodes(graph, self.representation)

        model_key = model_id or ir.id or source_path.stem
        metadata = {
            "source": "extended_parser",
            "format": self.format_name,
            "extendedLanguage": ir.language,
            "representation_profile": self.representation.as_metadata(),
            **stats_to_metadata(stats),
            **dict(ir.data or {}),
        }
        if self.metadata_language == "uml" and self.format_name == "xmi":
            extracted_names = extract_xmi_names(source_path)
            metadata["extracted_names"] = list(extracted_names.names)
            metadata["extracted_typed_names"] = list(extracted_names.typed_names)
        record_name = None
        if isinstance(ir.data, dict):
            extracted_name = str(ir.data.get("name") or "").strip()
            if extracted_name:
                record_name = extracted_name
        return ModelRecord(
            model_id=model_key,
            language=self.metadata_language,
            graph=graph,
            name=record_name,
            source_path=source_path,
            metadata=metadata,
        )

    def parse(self, raw, *, model_id: str | None = None) -> ModelRecord:  # pragma: no cover
        raise TypeError("Extended parsers require parse_file(path).")

    def _create_parser(self):
        raise NotImplementedError


class UMLXMIModelParser(ExtendedModelParser):
    language = "uml"
    parser_language = "UML"
    metadata_language = "uml"
    format_name = "xmi"

    def _create_parser(self):
        return UMLXMIParser(options=ParseOptions(include_model_root_node=self.representation.include_model_root_node))


class ArchimateArchiModelParser(ExtendedModelParser):
    language = "archimate"
    parser_language = "ArchiMate-Archi"
    metadata_language = "archimate"
    format_name = "xmi"

    def _create_parser(self):
        return ArchiMateArchiParser()


class EcoreXMIModelParser(ExtendedModelParser):
    language = "ecore"
    parser_language = "Ecore"
    metadata_language = "ecore"
    format_name = "ecore"

    def _create_parser(self):
        from mcp4cm.extended_parsing.ecore.ecore_parser import EcoreParser as ExtendedEcoreParser

        return ExtendedEcoreParser()


class BPMNSignavioModelParser(ExtendedModelParser):
    language = "bpmn"
    parser_language = "BPMN-Signavio-JSON"
    metadata_language = "bpmn"
    format_name = "signavio"

    def _create_parser(self):
        return BPMNSignavioJSONParser()


def stats_to_metadata(stats: ParserRunStats) -> dict[str, Any]:
    warning_by_type = {str(key.value if hasattr(key, "value") else key): int(value) for key, value in stats.warnings_by_type.items()}
    warning_messages_by_type: dict[str, list[str]] = {}
    warning_messages: list[str] = []
    for warning_type, messages in stats.warning_msgs.items():
        key = str(warning_type.value if hasattr(warning_type, "value") else warning_type)
        normalized_messages = [normalize_warning_message(message) for message in messages]
        warning_messages_by_type[key] = normalized_messages
        warning_messages.extend(normalized_messages)
    return {
        "parse_warnings_total": int(stats.warning_count),
        "parse_elements_skipped": int(stats.elements_skipped),
        "parse_warnings_by_type": warning_by_type,
        "parse_warning_messages": warning_messages,
        "parse_warning_messages_by_type": warning_messages_by_type,
        "parse_warning_messages_sample": warning_messages[:10],
    }


def normalize_warning_message(message: Any) -> str:
    value = str(message or "").strip()
    return value or "Warning emitted without a detailed parser message."


def drop_ir_edges_with_missing_nodes(ir, stats: ParserRunStats | None = None) -> int:
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


def expand_feature_nodes(graph, profile: RepresentationProfile) -> None:
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
    digest = hashlib.sha1(f"{parent_id}|{feature_kind}|{index}|{name}|{payload}".encode("utf-8")).hexdigest()[:12]
    return f"{parent_id}::{feature_kind}::{digest}"


def build_feature_nodes(parent_id: Any, feature_kind: str, feature_items: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
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


def build_feature_edges(parent_id: Any, edge_type: str, feature_items: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
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
