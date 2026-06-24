#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from mcp4cm.api.services.upload_summary import (
    add_upload_warning,
    empty_upload_summary,
    finalize_upload_summary,
    merge_model_diagnostics,
)
from mcp4cm.core import ModelDiagnostics, ModelRecord
from mcp4cm.parsers.catalog import resolve_parser
from mcp4cm.parsers.parse import parse_staged_files
from mcp4cm.runtime_store import (
    json_safe,
    runtime_index_template,
    runtime_model_filename,
    spill_model_to_runtime,
)
from mcp4cm.statistics import CorpusStatisticsAccumulator

DEFAULT_TARGETS = (
    "modelset-uml-xmi",
    "modelset-ecore-xmi",
    "eamodelset-archimate",
    "sap-sam-bpmn",
)

TARGET_GROUPS: dict[str, tuple[str, ...]] = {
    "all": DEFAULT_TARGETS,
    "modelset": ("modelset-uml-xmi", "modelset-ecore-xmi"),
}


@dataclass(frozen=True)
class TargetSpec:
    name: str
    label: str
    input_dir: str
    language: str
    format: str
    parser_options: dict[str, Any] | None = None


TARGET_SPECS: dict[str, TargetSpec] = {
    "modelset-uml-xmi": TargetSpec(
        name="modelset-uml-xmi",
        label="ModelSet UML XMI PyEcore",
        input_dir="modelset-uml-xmi",
        language="uml",
        format="xml-pyecore",
    ),
    "modelset-ecore-xmi": TargetSpec(
        name="modelset-ecore-xmi",
        label="ModelSet Ecore PyEcore",
        input_dir="modelset-ecore-xmi",
        language="ecore",
        format="ecore",
        parser_options={"resolveExternalRefs": False},
    ),
    "eamodelset-archimate": TargetSpec(
        name="eamodelset-archimate",
        label="EA ModelSet ArchiMate",
        input_dir="eamodelset-archimate",
        language="archimate",
        format="xmi",
    ),
    "sap-sam-bpmn": TargetSpec(
        name="sap-sam-bpmn",
        label="SAP-SAM BPMN",
        input_dir="sap-sam-bpmn",
        language="bpmn",
        format="signavio",
    ),
    "modelset-uml-json": TargetSpec(
        name="modelset-uml-json",
        label="ModelSet UML JSON",
        input_dir="modelset-uml-json",
        language="uml",
        format="json",
    ),
    "modelset-ecore-json": TargetSpec(
        name="modelset-ecore-json",
        label="ModelSet Ecore JSON",
        input_dir="modelset-ecore-json",
        language="ecore",
        format="json",
    ),
    "eamodelset-json": TargetSpec(
        name="eamodelset-json",
        label="EA ModelSet JSON",
        input_dir="eamodelset-json",
        language="archimate",
        format="json",
    ),
}

TARGET_CHOICES = tuple(TARGET_GROUPS) + tuple(TARGET_SPECS)


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)


def resolve_targets(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(DEFAULT_TARGETS)

    resolved: list[str] = []
    for item in selected:
        if item in TARGET_GROUPS:
            resolved.extend(TARGET_GROUPS[item])
            continue
        if item not in TARGET_SPECS:
            raise ValueError(f"Unknown target: {item}")
        resolved.append(item)

    return list(dict.fromkeys(resolved))


def iter_source_files(source_dir: Path) -> Iterable[Path]:
    for path in sorted(source_dir.rglob("*")):
        if path.is_file():
            yield path


def stage_files(source_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "relativePath": path.relative_to(source_dir).as_posix(),
            "storedPath": str(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in iter_source_files(source_dir)
    ]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def parse_dataset(
    *,
    spec: TargetSpec,
    input_dir: Path,
    output_dir: Path,
    force: bool,
) -> dict[str, Any]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Could not find input directory for {spec.name}: {input_dir}")

    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {output_dir}. Use --force to replace it.")
        shutil.rmtree(output_dir)

    output_ir_dir = output_dir / "ir"
    output_ir_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    staged_files = stage_files(input_dir)
    summary = empty_upload_summary()
    seen_files: set[str] = set()
    model_entries: list[dict[str, Any]] = []
    corpus_stats = CorpusStatisticsAccumulator()
    parser_options = resolve_parser(spec.language, spec.format).normalize_options(spec.parser_options or {})

    progress_bar = tqdm(total=len(staged_files), desc=spec.name, unit="file")
    last_processed = 0

    def progress(processed: int, _total: int) -> None:
        nonlocal last_processed
        if processed > last_processed:
            progress_bar.update(processed - last_processed)
            last_processed = processed

    def on_model(record: ModelRecord, diagnostics: ModelDiagnostics) -> None:
        merge_model_diagnostics(summary, str(record.model_id), diagnostics)
        corpus_stats.add(record)
        filename = runtime_model_filename(record.model_id, len(model_entries), seen_files)
        model_entries.append(
            spill_model_to_runtime(
                dataset_id=spec.name,
                dataset_dir=output_ir_dir,
                record=record,
                diagnostics=diagnostics,
                filename=filename,
            )
        )

    try:
        parsed = parse_staged_files(
            language=spec.language,
            format=spec.format,
            staged_files=staged_files,
            options=spec.parser_options,
            progress=progress,
            on_model=on_model,
            accumulate_records=False,
        )
    finally:
        progress_bar.close()

    summary["files"] = parsed.total_files
    summary["payloads"] = parsed.record_count
    summary["records"] = parsed.record_count
    summary["errors"] = len(parsed.invalid_files) + len(parsed.empty_files)
    summary["emptyFiles"] = list(parsed.empty_files)
    summary["invalidFiles"] = list(parsed.invalid_files)
    summary["ignoredFiles"] = [*parsed.ignored_files, *parsed.skipped_files]
    for issue in parsed.issues:
        add_upload_warning(summary, issue.type, issue.message, path=issue.path, model_id=issue.model_id)

    index_payload = runtime_index_template(
        dataset_id=spec.name,
        dataset_type=spec.language,
        model_entries=model_entries,
    )
    index_payload["source"] = {
        "inputDir": str(input_dir),
        "language": spec.language,
        "format": spec.format,
        "parserOptions": dict(parser_options.values),
    }
    write_json(output_dir / "index.json", index_payload)

    statistics = corpus_stats.build_payload()
    write_json(output_dir / "statistics.json", statistics)

    upload_summary = finalize_upload_summary(summary)
    upload_summary["format"] = spec.format
    upload_summary["language"] = spec.language
    upload_summary["parserOptions"] = dict(parser_options.values)
    write_json(output_dir / "upload_summary.json", upload_summary)

    finished_at = time.time()
    run_summary = {
        "dataset": spec.name,
        "label": spec.label,
        "inputDir": str(input_dir),
        "outputDir": str(output_dir),
        "language": spec.language,
        "format": spec.format,
        "files": parsed.total_files,
        "records": parsed.record_count,
        "invalidFiles": len(parsed.invalid_files),
        "emptyFiles": len(parsed.empty_files),
        "ignoredFiles": len(parsed.ignored_files) + len(parsed.skipped_files),
        "elapsedMs": int((finished_at - started_at) * 1000),
        "startedAt": started_at,
        "finishedAt": finished_at,
    }
    write_json(output_dir / "parse_result.json", run_summary)
    return run_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse prepared evaluation datasets into <dataset>-runtime/ir/ runtime JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/parse_datasets.py\n"
            "  python scripts/parse_datasets.py --only modelset-uml-xmi --force\n"
            "  python scripts/parse_datasets.py --data-dir data --output-dir evaluation-runs\n"
            "  python scripts/parse_datasets.py --only modelset-uml-json --only eamodelset-json\n"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=TARGET_CHOICES,
        metavar="TARGET",
        help=(
            "Parse only the selected dataset or group. "
            f"Groups: {', '.join(TARGET_GROUPS)}. Targets: {', '.join(TARGET_SPECS)}. "
            "Repeatable. Default: evaluation targets from docs/EVALUATION_CLEANSING.md."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing prepared datasets (default: data).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation"),
        help="Directory where <dataset>-runtime folders are created (default: evaluation).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing <dataset>-runtime output directories.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output.",
    )
    return parser.parse_args()


def print_summary(style: Style, results: list[dict[str, Any]]) -> None:
    if not results:
        return

    name_width = max(len(str(result["dataset"])) for result in results)
    print()
    print(style.bold(style.green("Done")))
    for result in results:
        print(
            f"  {str(result['dataset']):<{name_width}}  "
            f"{style.bold(str(result['records']))} models  "
            f"{style.dim(str(result['outputDir']) + '/ir')}"
        )


def main() -> int:
    args = parse_args()
    style = Style(enabled=sys.stdout.isatty() and not args.no_color)

    targets = resolve_targets(args.only)
    print(style.bold(style.blue("Dataset parsing")))
    print(style.dim(f"  Targets: {', '.join(targets)}"))
    print(style.dim(f"  Data directory: {args.data_dir.resolve()}"))
    print(style.dim(f"  Output directory: {args.output_dir.resolve()}"))
    print()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for target in targets:
        spec = TARGET_SPECS[target]
        input_dir = args.data_dir / spec.input_dir
        output_dir = args.output_dir / f"{spec.name}-runtime"
        print(style.bold(style.blue(spec.label)))
        print(style.dim(f"  {input_dir} -> {output_dir / 'ir'}"))
        results.append(parse_dataset(spec=spec, input_dir=input_dir, output_dir=output_dir, force=args.force))
        print()

    print_summary(style, results)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        style = Style(enabled=sys.stderr.isatty())
        print(style.red(f"error: {error}"), file=sys.stderr)
        raise SystemExit(1) from None
