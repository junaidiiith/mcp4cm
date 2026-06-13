from __future__ import annotations

import time
import uuid
from typing import Any

from mcp4cm.api.pipeline import remove_directory_quietly
from mcp4cm.api.services.upload_summary import (
    add_upload_warning,
    empty_upload_summary,
    finalize_upload_summary,
    merge_model_diagnostics,
)
from mcp4cm.api.state import DATASETS, LOG, UPLOAD_LOCK, UPLOAD_PARSE_JOBS, UPLOAD_SESSIONS
from mcp4cm.core import ModelDiagnostics, ModelRecord
from mcp4cm.parsers.parse import parse_staged_files
from mcp4cm.runtime_store import (
    RuntimeDataset,
    finalize_runtime_dataset,
    get_dataset_meta,
    runtime_dataset_ir_dir,
    runtime_model_filename,
    save_dataset_statistics,
    spill_model_to_runtime,
)
from mcp4cm.statistics import CorpusStatisticsAccumulator
from mcp4cm.utils import elapsed_ms, progress_percent


def upload_job_elapsed_ms(job: dict[str, Any], *, finished_at: float | None = None) -> int:
    started_at = float(job.get("startedAt") or time.time())
    return elapsed_ms(started_at, finished_at)


def run_upload_parse_job(upload_id: str, job_id: str) -> None:
    def report(**patch: Any) -> None:
        with UPLOAD_LOCK:
            job = UPLOAD_PARSE_JOBS.get(job_id)
            if not job:
                return
            patch.setdefault("elapsedMs", upload_job_elapsed_ms(job))
            job.update(patch)

    def parse_phase_progress(processed: int, total: int) -> dict[str, Any]:
        percent = progress_percent(processed, total, zero_total=0)
        return {
            "stage": "parse",
            "parseProcessedFiles": processed,
            "parseTotalFiles": total,
            "processedFiles": processed,
            "totalFiles": total,
            "progress": percent,
            "message": f"Parsing files: {processed} of {total}.",
        }

    session_stage_dir: str = ""
    try:
        with UPLOAD_LOCK:
            session = UPLOAD_SESSIONS.get(upload_id)
            if session is None:
                raise ValueError("Upload session disappeared.")
            language = str(session["language"])
            data_format = str(session["format"])
            session_stage_dir = str(session.get("stageDir") or "")
            parser_options = dict(session.get("parserOptions") or {})
            normalized_parser_options = dict(session.get("parserOptionsNormalized") or {})
            staged_files = list(session["files"])

        report(
            status="running",
            stage="parse",
            message="Parsing files.",
            totalFiles=len(staged_files),
            parseTotalFiles=len(staged_files),
        )
        dataset_id = uuid.uuid4().hex
        runtime_dataset, parse_summary, corpus_stats = parse_staged_dataset(
            dataset_id,
            language,
            data_format,
            parser_options,
            staged_files,
            progress=lambda processed, total: report(
                status="running",
                **parse_phase_progress(processed, total),
            ),
        )
        total_records = len(runtime_dataset)
        parse_summary["format"] = data_format
        parse_summary["language"] = language
        parse_summary["parserOptions"] = normalized_parser_options
        if total_records == 0:
            finished_at = time.time()
            with UPLOAD_LOCK:
                job = UPLOAD_PARSE_JOBS.get(job_id) or {}
            elapsed_ms = upload_job_elapsed_ms(job, finished_at=finished_at)
            report(
                status="error",
                progress=100,
                stage="complete",
                processedFiles=len(staged_files),
                totalFiles=len(staged_files),
                parseProcessedFiles=len(staged_files),
                parseTotalFiles=len(staged_files),
                message="Parsing produced 0 models. Check parser format and file contents.",
                error="Parsing produced 0 models. Check parser format and file contents.",
                uploadSummary=parse_summary,
                finishedAt=finished_at,
                elapsedMs=elapsed_ms,
            )
            with UPLOAD_LOCK:
                session = UPLOAD_SESSIONS.get(upload_id)
                if session:
                    session["status"] = "error"
            return

        DATASETS[dataset_id] = runtime_dataset
        report(
            status="running",
            stage="statistics",
            message="Calculating statistics.",
            parseProcessedFiles=len(staged_files),
            parseTotalFiles=len(staged_files),
        )
        statistics = corpus_stats.build_payload()
        save_dataset_statistics(dataset_id, statistics)

        finished_at = time.time()
        with UPLOAD_LOCK:
            job = UPLOAD_PARSE_JOBS.get(job_id) or {}
        elapsed_ms = upload_job_elapsed_ms(job, finished_at=finished_at)
        report(
            status="complete",
            progress=100,
            stage="complete",
            processedFiles=len(staged_files),
            totalFiles=len(staged_files),
            parseProcessedFiles=len(staged_files),
            parseTotalFiles=len(staged_files),
            message=f"Processing complete. Parsed {total_records} model(s).",
            datasetId=dataset_id,
            statistics=statistics,
            uploadSummary=parse_summary,
            finishedAt=finished_at,
            elapsedMs=elapsed_ms,
        )
        with UPLOAD_LOCK:
            session = UPLOAD_SESSIONS.get(upload_id)
            if session:
                session["status"] = "ready"
    except Exception as exc:
        LOG.exception("upload_parse_job_error upload_id=%s job_id=%s", upload_id, job_id)
        report(status="error", message=str(exc), error=str(exc), finishedAt=time.time())
        with UPLOAD_LOCK:
            session = UPLOAD_SESSIONS.get(upload_id)
            if session:
                session["status"] = "error"
    finally:
        remove_directory_quietly(session_stage_dir)
        with UPLOAD_LOCK:
            session = UPLOAD_SESSIONS.get(upload_id)
            if session:
                session["stageDir"] = ""
                session["files"] = []
                session["totalBytes"] = 0


def parse_staged_dataset(
    dataset_id: str,
    language: str,
    data_format: str,
    parser_options: dict[str, Any],
    staged_files: list[dict[str, Any]],
    progress=None,
) -> tuple[RuntimeDataset, dict[str, Any], CorpusStatisticsAccumulator]:
    summary = empty_upload_summary()
    seen_files: set[str] = set()
    model_entries: list[dict[str, Any]] = []
    corpus_stats = CorpusStatisticsAccumulator()
    dataset_dir = runtime_dataset_ir_dir(dataset_id)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    def on_model(record: ModelRecord, diagnostics: ModelDiagnostics) -> None:
        merge_model_diagnostics(summary, str(record.model_id), diagnostics)
        corpus_stats.add(record)
        filename = runtime_model_filename(record.model_id, len(model_entries), seen_files)
        model_entries.append(
            spill_model_to_runtime(
                dataset_id=dataset_id,
                dataset_dir=dataset_dir,
                record=record,
                diagnostics=diagnostics,
                filename=filename,
            )
        )

    parsed = parse_staged_files(
        language=language,
        format=data_format,
        staged_files=staged_files,
        options=parser_options,
        progress=progress,
        on_model=on_model,
        accumulate_records=False,
    )
    summary["files"] = parsed.total_files
    summary["payloads"] = parsed.record_count
    summary["records"] = parsed.record_count
    summary["errors"] = len(parsed.invalid_files) + len(parsed.empty_files)
    summary["emptyFiles"] = list(parsed.empty_files)
    summary["invalidFiles"] = list(parsed.invalid_files)
    summary["ignoredFiles"] = [*parsed.ignored_files, *parsed.skipped_files]
    for issue in parsed.issues:
        add_upload_warning(summary, issue.type, issue.message, path=issue.path, model_id=issue.model_id)
    if model_entries:
        finalize_runtime_dataset(dataset_id=dataset_id, dataset_type=language, model_entries=model_entries)
    runtime_dataset = RuntimeDataset.from_meta(
        dataset_id, get_dataset_meta(dataset_id) or {"recordCount": 0, "models": []}
    )
    return runtime_dataset, finalize_upload_summary(summary), corpus_stats
