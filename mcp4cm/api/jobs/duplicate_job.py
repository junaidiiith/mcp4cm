from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from mcp4cm.api.http import paginate_items, parse_positive_int
from mcp4cm.api.services.datasets import get_duplicate_detection_dataset
from mcp4cm.api.services.duplicate_pipeline import (
    handle_duplicates,
    normalize_duplicate_group_confidence,
    raise_no_duplicate_technique_error,
    selected_duplicate_techniques,
)
from mcp4cm.api.state import DUPLICATE_JOBS, DUPLICATE_JOBS_LOCK, LOG
from mcp4cm.runtime_store import RUNTIME_DIR, load_dataset_duplicate_detection, save_dataset_duplicate_detection
from mcp4cm.utils import elapsed_ms, pair_lookup_key


def start_duplicate_job(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_duplicate_detection_dataset(body)
    selected = selected_duplicate_techniques(body)
    if not selected:
        raise_no_duplicate_technique_error(body)

    job_id = uuid.uuid4().hex
    now = time.time()
    job = {
        "jobId": job_id,
        "datasetId": str(body.get("datasetId") or ""),
        "status": "queued",
        "progress": 0,
        "currentTechnique": "",
        "completedTechniques": [],
        "selectedTechniques": selected,
        "totalTechniques": len(selected),
        "totalModels": len(dataset),
        "techniqueProgress": 0,
        "processedItems": 0,
        "totalItems": 0,
        "startedAt": now,
        "finishedAt": None,
        "elapsedMs": 0,
        "message": "Queued duplicate detection.",
        "result": None,
        "error": "",
    }
    with DUPLICATE_JOBS_LOCK:
        DUPLICATE_JOBS[job_id] = job

    thread = threading.Thread(target=run_duplicate_job, args=(job_id, body), daemon=True)
    thread.start()
    LOG.info("duplicate_job_started job_id=%s techniques=%s models=%s", job_id, selected, len(dataset))
    return job


def get_duplicate_job(job_id: str) -> dict[str, Any]:
    with DUPLICATE_JOBS_LOCK:
        job = DUPLICATE_JOBS.get(job_id)
        if not job:
            raise ValueError("Unknown duplicate detection job. Pipeline state may have been reset by a new run.")
        return dict(job)


def run_duplicate_job(job_id: str, body: dict[str, Any]) -> None:
    def report(**patch: Any) -> None:
        patch.setdefault("elapsedMs", duplicate_job_elapsed_ms(job_id))
        update_duplicate_job(job_id, **patch)

    try:
        report(status="running", message="Preparing duplicate detection.")
        result = handle_duplicates(body, progress=report)
        finished_at = time.time()
        elapsed_ms = duplicate_job_elapsed_ms(job_id, finished_at=finished_at)
        result["elapsedMs"] = elapsed_ms
        dataset_id = str(body.get("datasetId") or result.get("datasetId") or "")
        if dataset_id:
            result["datasetId"] = dataset_id
            result["jobId"] = job_id
            save_dataset_duplicate_detection(dataset_id, result)
        response_result = duplicate_result_response_preview(result)
        report(
            status="complete",
            progress=100,
            currentTechnique="",
            message="Duplicate detection complete.",
            result=response_result,
            finishedAt=finished_at,
            elapsedMs=elapsed_ms,
        )
        LOG.info(
            "duplicate_job_complete job_id=%s duplicate_pairs=%s elapsed_ms=%s",
            job_id,
            result["duplicatePairs"],
            elapsed_ms,
        )
    except Exception as exc:
        LOG.exception("duplicate_job_error job_id=%s", job_id)
        report(status="error", message=str(exc), error=str(exc), currentTechnique="", finishedAt=time.time())


def update_duplicate_job(job_id: str, **patch: Any) -> None:
    with DUPLICATE_JOBS_LOCK:
        if job_id in DUPLICATE_JOBS:
            DUPLICATE_JOBS[job_id].update(patch)


def duplicate_job_elapsed_ms(job_id: str, finished_at: float | None = None) -> int:
    with DUPLICATE_JOBS_LOCK:
        job = DUPLICATE_JOBS.get(job_id) or {}
        started_at = float(job.get("startedAt") or time.time())
    return elapsed_ms(started_at, finished_at)


def duplicate_result_response_preview(result: dict[str, Any]) -> dict[str, Any]:
    preview = dict(result)
    pairs_page = build_duplicate_pairs_page(result, page=1, page_size=50, decision="all", query="", group_id="")
    groups_page = build_duplicate_groups_page(result, page=1, page_size=25, query="", quality="")
    preview["decisions"] = pairs_page["pairs"]
    preview["pairsPage"] = pairs_page
    preview["groupsPage"] = groups_page
    preview["groups"] = groups_page["groups"]
    return preview


def get_duplicate_result_for_job(job_id: str) -> dict[str, Any]:
    dataset_id = ""
    with DUPLICATE_JOBS_LOCK:
        job = DUPLICATE_JOBS.get(job_id) or {}
        dataset_id = str(job.get("datasetId") or job.get("result", {}).get("datasetId") or "")
    if dataset_id:
        result = load_dataset_duplicate_detection(dataset_id)
        if result:
            return result

    dataset_dirs = RUNTIME_DIR.iterdir() if RUNTIME_DIR.exists() else []
    for dataset_dir in dataset_dirs:
        if not dataset_dir.is_dir():
            continue
        result = load_dataset_duplicate_detection(dataset_dir.name)
        if result and str(result.get("jobId") or "") == str(job_id):
            return result

    with DUPLICATE_JOBS_LOCK:
        job = DUPLICATE_JOBS.get(job_id)
        result = (job or {}).get("result")
    if isinstance(result, dict):
        return result
    raise ValueError(
        "Unknown duplicate detection result. The job has not completed or the persisted result is unavailable."
    )


def build_duplicate_groups_page(
    result: dict[str, Any], *, page: int, page_size: int, query: str, quality: str
) -> dict[str, Any]:
    groups = list(result.get("groups") or [])
    normalized_quality = normalize_duplicate_group_confidence(quality)
    if normalized_quality in {"strong", "high", "moderate", "low"}:
        groups = [
            group
            for group in groups
            if normalize_duplicate_group_confidence(group.get("confidence")) == normalized_quality
        ]
    if query:
        query_lower = query.lower()
        groups = [
            group
            for group in groups
            if query_lower in str(group.get("groupId", "")).lower()
            or any(query_lower in str(model_id).lower() for model_id in group.get("modelIds", []))
        ]
    groups.sort(
        key=lambda group: (int(group.get("size") or 0), int(group.get("approvedInternalPairs") or 0)), reverse=True
    )
    return paginate_items(groups, page=page, page_size=page_size, item_key="groups")


def build_duplicate_pairs_page(
    result: dict[str, Any],
    *,
    page: int,
    page_size: int,
    decision: str,
    query: str,
    group_id: str,
) -> dict[str, Any]:
    pairs = list(result.get("decisions") or [])
    if decision == "approved":
        pairs = [pair for pair in pairs if pair.get("isDuplicate") is True]
    elif decision in {"rejected", "candidate", "not_approved"}:
        pairs = [pair for pair in pairs if pair.get("isDuplicate") is not True]
    if group_id:
        group_lookup = result.get("pairGroupLookup") or {}
        pairs = [
            pair
            for pair in pairs
            if group_lookup.get(pair_lookup_key(str(pair.get("leftId")), str(pair.get("rightId")))) == group_id
        ]
    if query:
        query_lower = query.lower()
        pairs = [
            pair
            for pair in pairs
            if query_lower in str(pair.get("leftId", "")).lower()
            or query_lower in str(pair.get("rightId", "")).lower()
            or any(query_lower in str(technique).lower() for technique in pair.get("techniques", []))
        ]
    pairs.sort(key=lambda item: (item.get("isDuplicate") is True, int(item.get("voteCount") or 0)), reverse=True)
    return paginate_items(pairs, page=page, page_size=page_size, item_key="pairs")


def get_duplicate_groups_page(job_id: str, args: Any) -> dict[str, Any]:
    result = get_duplicate_result_for_job(job_id)
    return build_duplicate_groups_page(
        result,
        page=parse_positive_int(args.get("page"), 1),
        page_size=parse_positive_int(args.get("pageSize"), 25),
        query=str(args.get("query") or "").strip(),
        quality=str(args.get("quality") or "").strip().lower(),
    )


def get_duplicate_group_detail(job_id: str, group_id: str) -> dict[str, Any]:
    result = get_duplicate_result_for_job(job_id)
    group = next((item for item in result.get("groups", []) if str(item.get("groupId")) == str(group_id)), None)
    if not group:
        raise ValueError("Unknown duplicate group.")
    decisions = result.get("decisions") or []
    model_ids = set(group.get("modelIds") or [])
    internal_pairs = [
        decision
        for decision in decisions
        if decision.get("leftId") in model_ids and decision.get("rightId") in model_ids
    ]
    internal_pairs.sort(
        key=lambda item: (item.get("isDuplicate") is True, int(item.get("voteCount") or 0)), reverse=True
    )
    return {
        "group": group,
        "pairs": internal_pairs,
        "modelSummaries": [
            result.get("modelSummaries", {}).get(model_id, {"modelId": model_id})
            for model_id in group.get("modelIds", [])
        ],
    }


def get_duplicate_pairs_page(job_id: str, args: Any) -> dict[str, Any]:
    result = get_duplicate_result_for_job(job_id)
    return build_duplicate_pairs_page(
        result,
        page=parse_positive_int(args.get("page"), 1),
        page_size=parse_positive_int(args.get("pageSize"), 50),
        decision=str(args.get("decision") or "all"),
        query=str(args.get("query") or "").strip(),
        group_id=str(args.get("groupId") or "").strip(),
    )
