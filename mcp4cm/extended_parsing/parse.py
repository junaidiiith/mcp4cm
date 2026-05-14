"""High-level parsing API for converting models into graph IR."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

try:
    from mcp4cm.base import Dataset
except ImportError:  # pragma: no cover - compatibility fallback for vendored use
    Dataset = Any  # type: ignore[misc,assignment]
from mcp4cm.extended_ir.types import IR
from mcp4cm.extended_parsing.base import get_all_parsers, get_parser
from mcp4cm.extended_parsing.types import (
    ModelParseDiagnostics,
    ParseBatchResult,
    ParseFailure,
    ParseStatus,
    ParserRunStats,
)

# Import parser modules for registration side-effects.
from mcp4cm.extended_parsing.uml.uml_parser import UMLXMIParser  # noqa: F401
from mcp4cm.extended_parsing.archimate.archimate_archi_parser import ArchiMateArchiParser  # noqa: F401
from mcp4cm.extended_parsing.bpmn.bpmn_signavio_json_parser import BPMNSignavioJSONParser  # noqa: F401
try:  # pragma: no cover - optional dependency import guard
    from mcp4cm.extended_parsing.ecore.ecore_parser import EcoreParser  # noqa: F401
    _ECORE_IMPORT_ERROR = None
except ImportError as exc:
    _ECORE_IMPORT_ERROR = exc


_LANGUAGE_ALIASES = {
    "uml": "UML",
    "archimate": "ArchiMate-Archi",
    "archimate-archi": "ArchiMate-Archi",
    "bpmn": "BPMN-Signavio-JSON",
    "bpmn-signavio-json": "BPMN-Signavio-JSON",
    "sap-signavio-bpmn": "BPMN-Signavio-JSON",
    "sap_signavio_bpmn": "BPMN-Signavio-JSON",
    "ecore": "Ecore",
}


def get_available_parsers() -> List[str]:
    """Return available parser language names."""
    languages = {parser_cls.language for parser_cls in get_all_parsers()}
    return sorted(languages)


def parse_file_to_ir(filepath: str, language: str) -> Tuple[IR, ParserRunStats]:
    """Parse a single file into IR using the requested parser language."""
    parser_class, canonical_language = _get_parser_class(language)
    parser = parser_class()
    ir, run_stats = parser.parse(filepath)

    ir.data.setdefault("source_path", str(filepath))
    ir.data.setdefault("source_language", canonical_language)
    return ir, run_stats


def parse_files_to_ir(filepaths: List[str], language: str) -> ParseBatchResult:
    """Parse multiple files into IR and collect per-file diagnostics."""
    parser_class, canonical_language = _get_parser_class(language)
    parser = parser_class()
    _configure_parser_for_paths(parser, [Path(p) for p in filepaths])

    result = ParseBatchResult(
        parser_language=canonical_language,
        totals={
            "candidates_in": len(filepaths),
            "parsed_success": 0,
            "parsed_warning": 0,
            "parsed_failure": 0,
        },
    )

    for filepath in filepaths:
        path = Path(filepath)
        relpath = str(filepath)
        file_id = _compute_file_id(path)

        diagnostics = ModelParseDiagnostics(
            file_id=file_id,
            relpath=relpath,
            parse_status="failure",
        )

        if path.exists():
            try:
                diagnostics.file_size_bytes_source = path.stat().st_size
            except OSError:
                pass

        parse_start = time.perf_counter()
        ir = None
        try:
            ir, run_stats = parser.parse(str(path))
            diagnostics.parse_time_ms = int((time.perf_counter() - parse_start) * 1000)
            _apply_run_stats(diagnostics, ir, run_stats)
            _set_parse_status(diagnostics)

            ir.data.setdefault("source_path", str(path))
            ir.data.setdefault("source_language", canonical_language)
            result.irs.append(ir)

            diagnostics_key = ir.id or file_id
            result.diagnostics[diagnostics_key] = diagnostics
        except Exception as exc:  # noqa: BLE001
            diagnostics.parse_time_ms = int((time.perf_counter() - parse_start) * 1000)
            diagnostics.parse_status = "failure"
            diagnostics.parse_error_msg = f"{type(exc).__name__}: {exc}"
            result.diagnostics[file_id] = diagnostics
            result.failures.append(
                ParseFailure(
                    relpath=relpath,
                    ir_id=(ir.id if ir is not None else None),
                    error_class=type(exc).__name__,
                    message=str(exc),
                    parser=parser.parser_id,
                )
            )

        _increment_totals(result.totals, diagnostics.parse_status)

    return result


def parse_dataset_to_ir(
    dataset: Dataset,
    language: str,
    source_key: str = "model_xmi",
    progress_callback: Callable[[int, int, ModelParseDiagnostics], None] | None = None,
    configure_parser: Callable[[Any], None] | None = None,
    compute_ir_size_bytes: bool = True,
) -> ParseBatchResult:
    """Parse model content from an in-memory dataset into IR.

    If provided, ``progress_callback`` is called after each processed model with:
    ``(processed_count, total_count, diagnostics)``.
    If provided, ``configure_parser`` is called once with the parser instance before parsing.
    ``compute_ir_size_bytes=False`` skips per-model IR JSON serialization in diagnostics.
    """
    parser_class, canonical_language = _get_parser_class(language)
    parser = parser_class()
    if configure_parser is not None:
        configure_parser(parser)

    if source_key == "file_path":
        dataset_paths = [Path(str(getattr(model, "file_path"))) for model in dataset.models if getattr(model, "file_path", None)]
        _configure_parser_for_paths(parser, dataset_paths)

    result = ParseBatchResult(
        parser_language=canonical_language,
        totals={
            "candidates_in": len(dataset.models),
            "parsed_success": 0,
            "parsed_warning": 0,
            "parsed_failure": 0,
        },
    )
    total_models = len(dataset.models)

    for index, model in enumerate(dataset.models):
        model_id = str(getattr(model, "id", f"model-{index}"))
        relpath = str(getattr(model, "file_path", model_id))

        diagnostics = ModelParseDiagnostics(
            file_id=model_id,
            relpath=relpath,
            parse_status="failure",
        )

        parse_start = time.perf_counter()
        ir = None
        try:
            source = getattr(model, source_key, None)
            if source is None:
                raise ValueError(f"Model '{model_id}' has no value for source key '{source_key}'.")

            if source_key == "file_path":
                source_path = Path(str(source))
                if not source_path.exists():
                    raise FileNotFoundError(f"Source file not found: {source_path}")
                try:
                    diagnostics.file_size_bytes_source = source_path.stat().st_size
                except OSError:
                    pass
                ir, run_stats = parser.parse(str(source_path))
            else:
                text = _coerce_source_to_text(source, model_id=model_id, source_key=source_key)
                diagnostics.file_size_bytes_source = len(text.encode("utf-8"))
                ir, run_stats = _parse_text_with_tempfile(parser, text, canonical_language)

            diagnostics.parse_time_ms = int((time.perf_counter() - parse_start) * 1000)
            _apply_run_stats(
                diagnostics,
                ir,
                run_stats,
                compute_ir_size_bytes=compute_ir_size_bytes,
            )
            _set_parse_status(diagnostics)

            # For dataset parsing, model IDs should remain aligned with source dataset IDs.
            ir.id = model_id
            ir.data.setdefault("source_model_id", model_id)
            ir.data.setdefault("source_file_path", relpath)
            ir.data.setdefault("source_language", canonical_language)

            result.irs.append(ir)
            result.diagnostics[model_id] = diagnostics
        except Exception as exc:  # noqa: BLE001
            diagnostics.parse_time_ms = int((time.perf_counter() - parse_start) * 1000)
            diagnostics.parse_status = "failure"
            diagnostics.parse_error_msg = f"{type(exc).__name__}: {exc}"
            result.diagnostics[model_id] = diagnostics
            result.failures.append(
                ParseFailure(
                    relpath=relpath,
                    ir_id=(ir.id if ir is not None else model_id),
                    error_class=type(exc).__name__,
                    message=str(exc),
                    parser=parser.parser_id,
                )
            )

        _increment_totals(result.totals, diagnostics.parse_status)
        if progress_callback is not None:
            progress_callback(index + 1, total_models, diagnostics)

    return result


def _get_parser_class(language: str):
    if not language or not language.strip():
        raise ValueError("'language' must be a non-empty string.")

    requested = language.strip()
    normalized = _LANGUAGE_ALIASES.get(requested.lower(), requested)
    normalized_lower = normalized.lower()

    if normalized_lower == "ecore" and _ECORE_IMPORT_ERROR is not None:
        raise ImportError(
            "Ecore parser is unavailable because optional dependency 'pyecore' is not installed. "
            "Install it with: pip install pyecore>=0.15.2"
        ) from _ECORE_IMPORT_ERROR

    parser_class = get_parser(normalized)
    if parser_class:
        return parser_class, parser_class.language

    for parser_cls in get_all_parsers():
        if parser_cls.language.lower() == normalized_lower:
            return parser_cls, parser_cls.language

    available = ", ".join(get_available_parsers())
    raise ValueError(f"Parser not found for language '{language}'. Available: {available}")


def _compute_file_id(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
    except Exception:
        return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


def _configure_parser_for_paths(parser, paths: List[Path]) -> None:
    """Provide optional dataset-root hints to parsers that support it."""
    if not hasattr(parser, "set_dataset_root"):
        return

    existing_paths = [p.resolve() for p in paths if p.exists()]
    if not existing_paths:
        return

    common_path = existing_paths[0] if len(existing_paths) == 1 else Path(
        os.path.commonpath([str(p) for p in existing_paths])
    )
    dataset_root = common_path if common_path.is_dir() else common_path.parent
    try:
        parser.set_dataset_root(dataset_root)
    except Exception:
        # Optional parser-specific optimization; ignore if parser rejects the hint.
        pass


def _coerce_source_to_text(source: Any, model_id: str, source_key: str) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8", errors="replace")
    if isinstance(source, str):
        return source

    raise TypeError(
        f"Model '{model_id}' source '{source_key}' must be str or bytes for in-memory parsing, "
        f"got {type(source).__name__}."
    )


def _parse_text_with_tempfile(parser, text: str, language: str) -> Tuple[IR, ParserRunStats]:
    suffix = ".xml"
    if language == "UML":
        suffix = ".xmi"
    elif language == "ArchiMate-Archi":
        suffix = ".archimate"
    elif language == "BPMN-Signavio-JSON":
        suffix = ".json"
    elif language == "Ecore":
        suffix = ".ecore"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=suffix, encoding="utf-8", delete=False) as tmp_file:
            tmp_file.write(text)
            tmp_path = Path(tmp_file.name)

        return parser.parse(str(tmp_path))
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _apply_run_stats(
    diagnostics: ModelParseDiagnostics,
    ir: IR,
    run_stats: ParserRunStats,
    compute_ir_size_bytes: bool = True,
) -> None:
    diagnostics.elements_loaded = len(ir.nodes) + len(ir.edges)
    diagnostics.elements_skipped = run_stats.elements_skipped
    diagnostics.warning_count = run_stats.warning_count
    diagnostics.warnings_by_type = {warning.value: count for warning, count in run_stats.warnings_by_type.items()}
    diagnostics.warning_msgs = {warning.value: msgs for warning, msgs in run_stats.warning_msgs.items()}
    if compute_ir_size_bytes:
        diagnostics.file_size_bytes_ir = _compute_ir_size_bytes(ir)
    else:
        diagnostics.file_size_bytes_ir = 0


def _compute_ir_size_bytes(ir: IR) -> int:
    """Compute serialized IR size in bytes using compact UTF-8 JSON."""
    try:
        payload = json.dumps(ir.to_dict(), ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        # Fallback for unexpected non-JSON-serializable values in IR payloads.
        payload = json.dumps(ir.to_dict(), ensure_ascii=False, separators=(",", ":"), default=str)
    return len(payload.encode("utf-8"))


def _set_parse_status(diagnostics: ModelParseDiagnostics) -> None:
    if diagnostics.warning_count == 0 and diagnostics.elements_skipped == 0:
        diagnostics.parse_status = "success"
    elif diagnostics.elements_loaded > 0:
        diagnostics.parse_status = "warning"
    else:
        diagnostics.parse_status = "failure"
        diagnostics.parse_error_msg = "No elements loaded"


def _increment_totals(totals: Dict[str, int], parse_status: ParseStatus) -> None:
    if parse_status == "success":
        totals["parsed_success"] += 1
    elif parse_status == "warning":
        totals["parsed_warning"] += 1
    else:
        totals["parsed_failure"] += 1
