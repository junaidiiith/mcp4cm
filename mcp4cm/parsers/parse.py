from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mcp4cm.core import ModelDiagnostics, ModelRecord
from mcp4cm.parsers.catalog import ParsedModelResult, resolve_parser


@dataclass(frozen=True)
class FileParseIssue:
    path: str
    type: str
    message: str
    model_id: str = ""


@dataclass
class ParsedFilesResult:
    records: list[ModelRecord] = field(default_factory=list)
    diagnostics: dict[str, ModelDiagnostics] = field(default_factory=dict)
    issues: list[FileParseIssue] = field(default_factory=list)
    ignored_files: list[str] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
    empty_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    total_files: int = 0
    record_count: int = 0


ProgressCallback = Callable[[int, int], None]


class ParsedModelCallback(Protocol):
    def __call__(self, record: ModelRecord, diagnostics: ModelDiagnostics) -> None: ...


def parse_file(
    path: str | Path,
    *,
    language: str,
    format: str,
    model_id: str | None = None,
    options: Mapping[str, Any] | None = None,
    relpath: str | None = None,
) -> ParsedModelResult:
    source_path = Path(path)
    descriptor = resolve_parser(language, format)
    parser_options = descriptor.normalize_options(options)
    adapter = descriptor.create_adapter()
    return adapter.parse_file(
        source_path,
        model_id=model_id or source_path.stem,
        options=parser_options,
        relpath=relpath or str(source_path),
    )


def parse_files(
    filepaths: list[str | Path],
    *,
    language: str,
    format: str,
    options: Mapping[str, Any] | None = None,
    progress: ProgressCallback | None = None,
) -> ParsedFilesResult:
    staged_files = [
        {
            "relativePath": str(Path(filepath)),
            "storedPath": str(Path(filepath)),
        }
        for filepath in filepaths
    ]
    return parse_staged_files(
        language=language,
        format=format,
        staged_files=staged_files,
        options=options,
        progress=progress,
    )


def parse_staged_files(
    *,
    language: str,
    format: str,
    staged_files: list[dict[str, Any]],
    options: Mapping[str, Any] | None = None,
    progress: ProgressCallback | None = None,
    on_model: ParsedModelCallback | None = None,
    accumulate_records: bool = True,
) -> ParsedFilesResult:
    descriptor = resolve_parser(language, format)
    parser_options = descriptor.normalize_options(options)
    adapter = descriptor.create_adapter()
    result = ParsedFilesResult(total_files=len(staged_files))

    total_files = len(staged_files)
    for file_index, staged in enumerate(staged_files, start=1):
        relpath = str(staged.get("relativePath") or "")
        source_path = Path(str(staged.get("storedPath") or ""))
        if progress:
            progress(file_index - 1, total_files)

        if is_ignored_upload_path(relpath):
            result.ignored_files.append(relpath)
            if progress:
                progress(file_index, total_files)
            continue

        if not descriptor.matches_extension(relpath):
            result.skipped_files.append(relpath)
            result.issues.append(
                FileParseIssue(
                    path=relpath,
                    type="SKIPPED_UNSUPPORTED_EXTENSION",
                    message=(
                        f"{relpath} skipped: extension '{Path(relpath).suffix.lower() or '(none)'}' "
                        f"is not supported for {language}/{format}."
                    ),
                )
            )
            if progress:
                progress(file_index, total_files)
            continue

        if not source_path.exists():
            result.invalid_files.append(relpath)
            result.issues.append(
                FileParseIssue(
                    path=relpath, type="MISSING_FILE", message=f"{relpath} does not exist in upload staging."
                )
            )
            if progress:
                progress(file_index, total_files)
            continue

        try:
            if source_path.stat().st_size == 0:
                result.empty_files.append(relpath)
                result.issues.append(FileParseIssue(path=relpath, type="EMPTY_FILE", message=f"{relpath} is empty."))
                if progress:
                    progress(file_index, total_files)
                continue
        except OSError as exc:
            result.invalid_files.append(relpath)
            result.issues.append(
                FileParseIssue(path=relpath, type="FILE_ERROR", message=f"{relpath} failed to stat: {exc}")
            )
            if progress:
                progress(file_index, total_files)
            continue

        try:
            parsed = adapter.parse_file(
                source_path,
                model_id=Path(relpath).stem,
                options=parser_options,
                relpath=relpath,
            )
        except Exception as exc:  # noqa: BLE001
            result.invalid_files.append(relpath)
            result.issues.append(
                FileParseIssue(
                    path=relpath,
                    type="PARSE_ERROR",
                    message=f"{relpath} failed to parse: {exc}",
                )
            )
            if progress:
                progress(file_index, total_files)
            continue

        if accumulate_records:
            result.records.append(parsed.record)
        else:
            result.record_count += 1
        result.diagnostics[str(parsed.record.model_id)] = parsed.diagnostics
        if on_model is not None:
            on_model(parsed.record, parsed.diagnostics)
        if progress:
            progress(file_index, total_files)

    return result


def is_ignored_upload_path(relpath: str) -> bool:
    parts = Path(relpath).parts
    return "__MACOSX" in parts or any(part.startswith("._") for part in parts) or Path(relpath).name == ".DS_Store"
