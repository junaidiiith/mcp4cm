from __future__ import annotations

import shutil
from pathlib import Path

from mcp4cm.api.state import (
    AFTER_DUMMY_STATISTICS_JOBS,
    AFTER_DUMMY_STATISTICS_LOCK,
    DATASETS,
    DUMMY_JOBS,
    DUMMY_JOBS_LOCK,
    DUPLICATE_JOBS,
    DUPLICATE_JOBS_LOCK,
    LABEL_PIPELINE_CACHE,
    LABEL_PIPELINE_CACHE_LOCK,
    LOG,
    UPLOAD_LOCK,
    UPLOAD_PARSE_JOBS,
    UPLOAD_SESSIONS,
)
from mcp4cm.runtime_store import RUNTIME_DIR


def has_active_pipeline_run() -> bool:
    with UPLOAD_LOCK:
        for session in UPLOAD_SESSIONS.values():
            if str(session.get("status") or "") in {"collecting", "processing"}:
                return True
        for job in UPLOAD_PARSE_JOBS.values():
            if str(job.get("status") or "") in {"queued", "running"}:
                return True
    with DUPLICATE_JOBS_LOCK:
        for job in DUPLICATE_JOBS.values():
            if str(job.get("status") or "") in {"queued", "running"}:
                return True
    with DUMMY_JOBS_LOCK:
        for job in DUMMY_JOBS.values():
            if str(job.get("status") or "") in {"queued", "running"}:
                return True
    return False


def remove_directory_quietly(path: Path | str | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(Path(path), ignore_errors=True)
    except Exception:
        LOG.exception("runtime_cleanup_failed path=%s", path)


def reset_pipeline_state() -> None:
    stage_dirs: list[Path] = []
    with UPLOAD_LOCK:
        for session in UPLOAD_SESSIONS.values():
            stage_dir = str(session.get("stageDir") or "")
            if stage_dir:
                stage_dirs.append(Path(stage_dir))
        UPLOAD_SESSIONS.clear()
        UPLOAD_PARSE_JOBS.clear()
    with DUPLICATE_JOBS_LOCK:
        DUPLICATE_JOBS.clear()
    with DUMMY_JOBS_LOCK:
        DUMMY_JOBS.clear()
    with AFTER_DUMMY_STATISTICS_LOCK:
        AFTER_DUMMY_STATISTICS_JOBS.clear()
    with LABEL_PIPELINE_CACHE_LOCK:
        LABEL_PIPELINE_CACHE.clear()
    DATASETS.clear()
    for stage_dir in stage_dirs:
        remove_directory_quietly(stage_dir)
    remove_directory_quietly(RUNTIME_DIR)
