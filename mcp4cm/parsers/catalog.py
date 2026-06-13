from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp4cm.core import ModelDiagnostics, ModelingLanguage, ModelRecord
from mcp4cm.parsers.archimate_archi.parser import ArchiMateArchiParser
from mcp4cm.parsers.archimate_json.parser import ArchimateJsonParser
from mcp4cm.parsers.bpmn_signavio.parser import BPMNSignavioJSONParser
from mcp4cm.parsers.diagnostics import ParserRunStats
from mcp4cm.parsers.graph import (
    UMLFeatureProjection,
    convert_to_networkx,
    drop_ir_edges_with_missing_nodes,
    expand_uml_feature_nodes,
    normalize_graph_attributes,
)
from mcp4cm.parsers.ir import IR
from mcp4cm.parsers.modelset_json.parser import ModelSetJsonParser
from mcp4cm.parsers.uml_xmi.parser import ParseOptions as UMLParseOptions
from mcp4cm.parsers.uml_xmi.parser import UMLXMIParser
from mcp4cm.utils import parse_bool


@dataclass(frozen=True)
class OptionSpec:
    external_name: str
    internal_name: str
    default: Any
    coerce: Callable[[Any], Any] = bool


@dataclass(frozen=True)
class ParserOptions:
    values: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


@dataclass(frozen=True)
class ParsedModelResult:
    record: ModelRecord
    diagnostics: ModelDiagnostics
    ir: IR | None = None


@dataclass(frozen=True)
class ParserDescriptor:
    language: str
    format: str
    parser_id: str
    extensions: tuple[str, ...]
    adapter_factory: Callable[[], ParserAdapterBase]
    option_specs: tuple[OptionSpec, ...] = ()

    def normalize_options(self, payload: Mapping[str, Any] | None = None) -> ParserOptions:
        payload = payload or {}
        allowed = {spec.external_name: spec for spec in self.option_specs}
        unsupported = sorted(str(key) for key in payload if key not in allowed)
        if unsupported:
            raise ValueError(f"Unsupported option(s) for {self.language}/{self.format}: {', '.join(unsupported)}")
        values = {
            spec.internal_name: spec.coerce(payload.get(spec.external_name, spec.default)) for spec in self.option_specs
        }
        return ParserOptions(values)

    def matches_extension(self, relpath: str | Path) -> bool:
        return Path(str(relpath)).suffix.lower() in self.extensions

    def create_adapter(self) -> ParserAdapterBase:
        return self.adapter_factory()


class ParserAdapterBase:
    descriptor: ParserDescriptor

    def parse_file(
        self, path: Path, *, model_id: str, options: ParserOptions, relpath: str | None = None
    ) -> ParsedModelResult:
        raise NotImplementedError

    def _success_diagnostics(
        self,
        *,
        relpath: str,
        status: str,
        elements_loaded: int,
        elements_skipped: int = 0,
        parse_time_ms: int = 0,
        warning_count: int = 0,
        warnings_by_type: dict[str, int] | None = None,
        warning_messages_by_type: dict[str, list[str]] | None = None,
    ) -> ModelDiagnostics:
        return ModelDiagnostics(
            parse_status=status,
            warning_count=warning_count,
            warnings_by_type=dict(warnings_by_type or {}),
            warning_messages_by_type={
                key: list(messages) for key, messages in (warning_messages_by_type or {}).items()
            },
            elements_loaded=elements_loaded,
            elements_skipped=elements_skipped,
            parse_time_ms=parse_time_ms,
            source_path=relpath,
        )


class JsonGraphParserAdapter(ParserAdapterBase):
    parser_id = ""

    def parse_file(
        self, path: Path, *, model_id: str, options: ParserOptions, relpath: str | None = None
    ) -> ParsedModelResult:
        _ = options
        relpath = relpath or str(path)
        started = time.perf_counter()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected one JSON object per .json model file, got {type(payload).__name__}.")
        record = self.parse_payload(payload, model_id=model_id)
        record.source_path = Path(relpath)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        diagnostics = self._success_diagnostics(
            relpath=relpath,
            status="success",
            elements_loaded=record.node_count + record.edge_count,
            parse_time_ms=elapsed_ms,
        )
        return ParsedModelResult(record=record, diagnostics=diagnostics, ir=None)

    def parse_payload(self, payload: dict[str, Any], *, model_id: str) -> ModelRecord:
        raise NotImplementedError


class ModelSetJsonAdapter(JsonGraphParserAdapter):
    def __init__(self, language: str):
        self.language = language
        self.parser = ModelSetJsonParser(language)

    def parse_payload(self, payload: dict[str, Any], *, model_id: str) -> ModelRecord:
        payload_id = payload.get("ids") or payload.get("id") or model_id
        return self.parser.parse(payload, model_id=str(payload_id))


class ArchimateJsonAdapter(JsonGraphParserAdapter):
    language = ModelingLanguage.ARCHIMATE.value

    def __init__(self):
        self.parser = ArchimateJsonParser()

    def parse_payload(self, payload: dict[str, Any], *, model_id: str) -> ModelRecord:
        payload_id = payload.get("archimateId") or payload.get("identifier") or payload.get("id") or model_id
        return self.parser.parse(payload, model_id=str(payload_id))


class IRParserAdapter(ParserAdapterBase):
    metadata_language: str
    format_name: str

    def parse_file(
        self, path: Path, *, model_id: str, options: ParserOptions, relpath: str | None = None
    ) -> ParsedModelResult:
        relpath = relpath or str(path)
        started = time.perf_counter()
        parser = self.create_parser(options)
        ir, stats = parser.parse(str(path))
        drop_ir_edges_with_missing_nodes(ir, stats)
        graph = convert_to_networkx(ir, missing_node_policy="error")
        graph = normalize_graph_attributes(graph, language=self.metadata_language)
        self.apply_projection(graph, options)

        model_key = model_id or ir.id or path.stem
        metadata = {
            "source": "parser",
            "format": self.format_name,
            "parserLanguage": ir.language,
            **dict(ir.data or {}),
        }
        record_name = None
        if isinstance(ir.data, dict):
            extracted_name = str(ir.data.get("name") or "").strip()
            if extracted_name:
                record_name = extracted_name
        record = ModelRecord(
            model_id=model_key,
            language=self.metadata_language,
            graph=graph,
            name=record_name,
            source_path=Path(relpath),
            metadata=metadata,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        diagnostics = diagnostics_from_stats(
            relpath=relpath,
            status=parse_status_for(record, stats),
            elements_loaded=record.node_count + record.edge_count,
            parse_time_ms=elapsed_ms,
            stats=stats,
        )
        return ParsedModelResult(record=record, diagnostics=diagnostics, ir=ir)

    def create_parser(self, options: ParserOptions):
        raise NotImplementedError

    def apply_projection(self, graph, options: ParserOptions) -> None:
        _ = graph, options


class UMLXMIAdapter(IRParserAdapter):
    metadata_language = "uml"
    format_name = "xmi"

    def create_parser(self, options: ParserOptions):
        return UMLXMIParser(
            options=UMLParseOptions(include_model_root_node=bool(options.get("include_model_root_node", True)))
        )

    def apply_projection(self, graph, options: ParserOptions) -> None:
        expand_uml_feature_nodes(
            graph,
            UMLFeatureProjection(
                include_attributes=bool(options.get("include_attributes", True)),
                include_operations=bool(options.get("include_operations", True)),
                include_parameters=bool(options.get("include_parameters", True)),
            ),
        )


class UMLXMLPyEcoreAdapter(IRParserAdapter):
    metadata_language = "uml"
    format_name = "xml-pyecore"

    def __init__(self):
        from mcp4cm.parsers.uml_xml_pyecore.parser import UMLXMLPyEcoreParser

        self.parser = UMLXMLPyEcoreParser()

    def create_parser(self, options: ParserOptions):
        _ = options
        return self.parser


class ArchimateArchiAdapter(IRParserAdapter):
    metadata_language = "archimate"
    format_name = "xmi"

    def create_parser(self, options: ParserOptions):
        _ = options
        return ArchiMateArchiParser()


class EcoreFileAdapter(IRParserAdapter):
    metadata_language = "ecore"
    format_name = "ecore"

    def __init__(self):
        from mcp4cm.parsers.ecore_ecore.parser import EcoreParser as EcoreFileParser

        self.parser = EcoreFileParser()

    def create_parser(self, options: ParserOptions):
        self.parser.set_enable_scoped_uri_mappings(bool(options.get("resolve_external_refs", True)))
        return self.parser


class BPMNSignavioAdapter(IRParserAdapter):
    metadata_language = "bpmn"
    format_name = "signavio"

    def create_parser(self, options: ParserOptions):
        _ = options
        return BPMNSignavioJSONParser()


def diagnostics_from_stats(
    *,
    relpath: str,
    status: str,
    elements_loaded: int,
    parse_time_ms: int,
    stats: ParserRunStats,
) -> ModelDiagnostics:
    warnings_by_type = {
        str(key.value if hasattr(key, "value") else key): int(value) for key, value in stats.warnings_by_type.items()
    }
    warning_messages_by_type: dict[str, list[str]] = {}
    for warning_type, messages in stats.warning_msgs.items():
        key = str(warning_type.value if hasattr(warning_type, "value") else warning_type)
        warning_messages_by_type[key] = [normalize_warning_message(message) for message in messages]
    return ModelDiagnostics(
        parse_status=status,
        warning_count=int(stats.warning_count),
        warnings_by_type=warnings_by_type,
        warning_messages_by_type=warning_messages_by_type,
        elements_loaded=elements_loaded,
        elements_skipped=int(stats.elements_skipped),
        parse_time_ms=parse_time_ms,
        source_path=relpath,
    )


def parse_status_for(record: ModelRecord, stats: ParserRunStats) -> str:
    if stats.warning_count == 0 and stats.elements_skipped == 0:
        return "success"
    if record.node_count + record.edge_count > 0:
        return "warning"
    return "failure"


def normalize_warning_message(message: Any) -> str:
    value = str(message or "").strip()
    return value or "Warning emitted without a detailed parser message."


def bool_option(value: Any) -> bool:
    return parse_bool(value, default=False)


_DESCRIPTORS: dict[tuple[str, str], ParserDescriptor] = {}


def register_descriptor(descriptor: ParserDescriptor) -> ParserDescriptor:
    _DESCRIPTORS[(descriptor.language.lower(), descriptor.format.lower())] = descriptor
    return descriptor


def resolve_parser(language: str, data_format: str) -> ParserDescriptor:
    key = (str(language).lower(), str(data_format).lower())
    try:
        return _DESCRIPTORS[key]
    except KeyError as exc:
        supported = ", ".join(f"{language}/{data_format}" for language, data_format in sorted(_DESCRIPTORS))
        raise ValueError(
            f"Unsupported language/format combination: {language}/{data_format}. Supported: {supported}"
        ) from exc


def parser_descriptors() -> tuple[ParserDescriptor, ...]:
    return tuple(_DESCRIPTORS[key] for key in sorted(_DESCRIPTORS))


register_descriptor(
    ParserDescriptor(
        language="uml",
        format="json",
        parser_id="modelset-json-uml",
        extensions=(".json",),
        adapter_factory=lambda: ModelSetJsonAdapter("uml"),
    )
)
register_descriptor(
    ParserDescriptor(
        language="ecore",
        format="json",
        parser_id="modelset-json-ecore",
        extensions=(".json",),
        adapter_factory=lambda: ModelSetJsonAdapter("ecore"),
    )
)
register_descriptor(
    ParserDescriptor(
        language="archimate",
        format="json",
        parser_id="archimate-json",
        extensions=(".json",),
        adapter_factory=ArchimateJsonAdapter,
    )
)
register_descriptor(
    ParserDescriptor(
        language="uml",
        format="xmi",
        parser_id="uml-xmi",
        extensions=(".xmi", ".xml"),
        adapter_factory=UMLXMIAdapter,
        option_specs=(
            OptionSpec("includeAttributes", "include_attributes", True, bool_option),
            OptionSpec("includeOperations", "include_operations", True, bool_option),
            OptionSpec("includeParameters", "include_parameters", True, bool_option),
            OptionSpec("includeModelRootNode", "include_model_root_node", True, bool_option),
        ),
    )
)
register_descriptor(
    ParserDescriptor(
        language="uml",
        format="xml-pyecore",
        parser_id="uml-xml-pyecore",
        extensions=(".xmi", ".uml", ".xml"),
        adapter_factory=UMLXMLPyEcoreAdapter,
    )
)
register_descriptor(
    ParserDescriptor(
        language="archimate",
        format="xmi",
        parser_id="archimate-archi",
        extensions=(".archimate", ".xml"),
        adapter_factory=ArchimateArchiAdapter,
    )
)
register_descriptor(
    ParserDescriptor(
        language="ecore",
        format="ecore",
        parser_id="ecore-ecore",
        extensions=(".ecore",),
        adapter_factory=EcoreFileAdapter,
        option_specs=(OptionSpec("resolveExternalRefs", "resolve_external_refs", True, bool_option),),
    )
)
register_descriptor(
    ParserDescriptor(
        language="bpmn",
        format="signavio",
        parser_id="bpmn-signavio",
        extensions=(".json",),
        adapter_factory=BPMNSignavioAdapter,
    )
)
