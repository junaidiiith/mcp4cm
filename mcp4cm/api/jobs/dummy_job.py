from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from mcp4cm.api.services.datasets import build_statistics_payload, get_dataset
from mcp4cm.api.state import AFTER_DUMMY_STATISTICS_JOBS, AFTER_DUMMY_STATISTICS_LOCK, DUMMY_JOBS, DUMMY_JOBS_LOCK, LOG
from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.runtime_store import RuntimeDataset
from mcp4cm.dummy import evaluate_dummy_filters
from mcp4cm.runtime_store import (
    delete_dataset_after_dummy_retained_model_ids,
    delete_dataset_after_dummy_statistics,
    save_dataset_after_dummy_retained_model_ids,
    save_dataset_after_dummy_statistics,
)
from mcp4cm.utils import elapsed_ms


def start_dummy_job(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(body)
    dataset_id = str(body.get("datasetId") or "")
    job_id = uuid.uuid4().hex
    total_models = len(dataset)
    now = time.time()
    job = {
        "jobId": job_id,
        "datasetId": dataset_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "processedModels": 0,
        "totalModels": total_models,
        "message": "Queued dummy cleansing.",
        "startedAt": now,
        "finishedAt": None,
        "elapsedMs": 0,
        "result": None,
        "error": "",
    }
    with DUMMY_JOBS_LOCK:
        DUMMY_JOBS[job_id] = job

    thread = threading.Thread(target=run_dummy_job, args=(job_id, body), daemon=True)
    thread.start()
    return job


def get_dummy_job(job_id: str) -> dict[str, Any]:
    with DUMMY_JOBS_LOCK:
        job = DUMMY_JOBS.get(job_id)
        if not job:
            raise ValueError("Unknown dummy cleansing job. Pipeline state may have been reset by a new run.")
        return dict(job)


def run_dummy_job(job_id: str, body: dict[str, Any]) -> None:
    def report(**patch: Any) -> None:
        patch.setdefault("elapsedMs", dummy_job_elapsed_ms(job_id))
        update_dummy_job(job_id, **patch)

    dataset_id = str(body.get("datasetId") or "")
    configs = body.get("filterConfigs")
    try:
        dataset = get_dataset(body)
        total_models = len(dataset)
        report(
            status="running",
            stage="loading",
            progress=0,
            processedModels=0,
            totalModels=total_models,
            message="Loading models from runtime storage.",
        )
        records = load_dummy_job_records(job_id, dataset, total_models, report)
        report(
            stage="filtering",
            progress=75,
            processedModels=0,
            totalModels=len(records),
            message="Evaluating dummy filters.",
        )
        evaluation_dataset = Dataset(records, getattr(dataset, "dataset_type", "runtime"), getattr(dataset, "root", None))
        evaluation = evaluate_dummy_filters(evaluation_dataset, filter_configs=configs if isinstance(configs, list) else None)
        report(
            stage="summarizing",
            progress=95,
            processedModels=len(records),
            totalModels=len(records),
            message="Building dummy cleansing results.",
        )
        retained_model_ids = {outcome.model_id for outcome in evaluation.model_outcomes if not outcome.removed}
        statistics_job_id = uuid.uuid4().hex
        if dataset_id:
            start_after_dummy_statistics_job(
                dataset_id=dataset_id,
                job_id=statistics_job_id,
                records=records,
                retained_model_ids=retained_model_ids,
            )
        result = dummy_response_payload(evaluation, statistics_job_id if dataset_id else "")
        finished_at = time.time()
        report(
            status="complete",
            stage="complete",
            progress=100,
            processedModels=len(records),
            totalModels=len(records),
            message="Dummy cleansing complete.",
            result=result,
            finishedAt=finished_at,
            elapsedMs=dummy_job_elapsed_ms(job_id, finished_at=finished_at),
        )
    except Exception as exc:
        LOG.exception("dummy_job_error job_id=%s dataset_id=%s", job_id, dataset_id)
        report(status="error", stage="error", message=str(exc), error=str(exc), finishedAt=time.time())


def load_dummy_job_records(job_id: str, dataset: Dataset | RuntimeDataset, total_models: int, report) -> list[ModelRecord]:
    records: list[ModelRecord] = []
    last_report = 0
    for index, record in enumerate(dataset, start=1):
        records.append(record)
        if index == total_models or index - last_report >= 25:
            last_report = index
            progress = round((index / max(1, total_models)) * 75)
            report(
                stage="loading",
                progress=min(progress, 75),
                processedModels=index,
                totalModels=total_models,
                message=f"Loading models from runtime storage ({index}/{total_models}).",
            )
    return records


def update_dummy_job(job_id: str, **patch: Any) -> None:
    with DUMMY_JOBS_LOCK:
        if job_id in DUMMY_JOBS:
            DUMMY_JOBS[job_id].update(patch)


def dummy_job_elapsed_ms(job_id: str, finished_at: float | None = None) -> int:
    with DUMMY_JOBS_LOCK:
        job = DUMMY_JOBS.get(job_id) or {}
        started_at = float(job.get("startedAt") or time.time())
    return elapsed_ms(started_at, finished_at)


def dummy_response_payload(evaluation, statistics_job_id: str = "") -> dict[str, Any]:
    return {
        "runSummary": {
            "totalModels": evaluation.run_summary.total_models,
            "removedModels": evaluation.run_summary.removed_models,
            "remainingModels": evaluation.run_summary.remaining_models,
            "removalRate": evaluation.run_summary.removal_rate,
        },
        "filterSummaries": [
            {
                "filterId": summary.filter_id,
                "filteredCount": summary.filtered_count,
                "remainingCount": summary.remaining_count,
                "triggeredModelIds": list(summary.triggered_model_ids),
            }
            for summary in evaluation.filter_summaries
        ],
        "modelOutcomes": [
            {
                "modelId": outcome.model_id,
                "removed": outcome.removed,
                "primaryRemovalReason": outcome.primary_removal_reason,
                "allTriggeredFilters": list(outcome.all_triggered_filters),
            }
            for outcome in evaluation.model_outcomes
        ],
        "findings": [
            {
                "modelId": finding.model_id,
                "filterId": finding.filter_id,
                "reason": finding.reason,
                "score": finding.score,
                "threshold": finding.threshold,
                "decision": finding.decision,
                "evidence": list(finding.evidence),
                "evidenceNodes": list(finding.evidence_nodes),
                "metrics": finding.metrics or {},
            }
            for finding in evaluation.findings
        ],
        "statisticsJobId": statistics_job_id,
    }


def start_after_dummy_statistics_job(
    *,
    dataset_id: str,
    job_id: str,
    records: list[ModelRecord],
    retained_model_ids: set[str],
) -> None:
    delete_dataset_after_dummy_statistics(dataset_id)
    delete_dataset_after_dummy_retained_model_ids(dataset_id)
    save_dataset_after_dummy_retained_model_ids(dataset_id, retained_model_ids)
    with AFTER_DUMMY_STATISTICS_LOCK:
        AFTER_DUMMY_STATISTICS_JOBS[dataset_id] = {
            "jobId": job_id,
            "status": "running",
            "error": "",
            "startedAt": time.time(),
            "finishedAt": None,
        }

    thread = threading.Thread(
        target=run_after_dummy_statistics_job,
        kwargs={
            "dataset_id": dataset_id,
            "job_id": job_id,
            "records": records,
            "retained_model_ids": retained_model_ids,
        },
        daemon=True,
    )
    thread.start()


def run_after_dummy_statistics_job(
    *,
    dataset_id: str,
    job_id: str,
    records: list[ModelRecord],
    retained_model_ids: set[str],
) -> None:
    try:
        after_statistics = build_statistics_payload(
            (record for record in records if record.model_id in retained_model_ids),
            skip_topic_model=True,
            topic_model_skip_reason="Topic modeling skipped for after-cleansing visualizations.",
        )
        with AFTER_DUMMY_STATISTICS_LOCK:
            current = AFTER_DUMMY_STATISTICS_JOBS.get(dataset_id)
            if current and current.get("jobId") != job_id:
                return
        save_dataset_after_dummy_statistics(dataset_id, after_statistics)
        with AFTER_DUMMY_STATISTICS_LOCK:
            current = AFTER_DUMMY_STATISTICS_JOBS.get(dataset_id)
            if current and current.get("jobId") == job_id:
                current.update({"status": "complete", "finishedAt": time.time(), "error": ""})
    except Exception as exc:  # pragma: no cover - defensive background worker
        LOG.exception("after_dummy_statistics_failed dataset_id=%s job_id=%s", dataset_id, job_id)
        with AFTER_DUMMY_STATISTICS_LOCK:
            current = AFTER_DUMMY_STATISTICS_JOBS.get(dataset_id)
            if current and current.get("jobId") == job_id:
                current.update({"status": "error", "finishedAt": time.time(), "error": str(exc)})
