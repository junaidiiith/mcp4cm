from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage

from mcp4cm.api.jobs.parse_job import run_upload_parse_job
from mcp4cm.api.pipeline import has_active_pipeline_run, reset_pipeline_state
from mcp4cm.api.state import UPLOAD_LOCK, UPLOAD_PARSE_JOBS, UPLOAD_SESSIONS
from mcp4cm.parsers.catalog import resolve_parser


def validate_language_and_format(language: str, data_format: str) -> None:
    resolve_parser(language, data_format)


def parser_option_payload_from_body(body: dict[str, Any], language: str, data_format: str) -> dict[str, Any]:
    descriptor = resolve_parser(language, data_format)
    option_names = {spec.external_name for spec in descriptor.option_specs}
    base_keys = {"language", "format"}
    unsupported = sorted(str(key) for key in body if key not in base_keys and key not in option_names)
    if unsupported:
        raise ValueError(
            f"Unsupported option(s) for {language}/{data_format}: {', '.join(unsupported)}"
        )
    return {key: body[key] for key in option_names if key in body}


def start_upload_session(body: dict[str, Any]) -> dict[str, Any]:
    import tempfile

    if has_active_pipeline_run():
        raise ValueError("A pipeline run is already active. Wait for it to complete before starting a new run.")
    reset_pipeline_state()
    language = str(body.get("language") or "").lower()
    data_format = str(body.get("format") or "json").lower()
    validate_language_and_format(language, data_format)
    parser_options_payload = parser_option_payload_from_body(body, language, data_format)
    parser_options = resolve_parser(language, data_format).normalize_options(parser_options_payload)
    upload_id = uuid.uuid4().hex
    stage_dir = Path(tempfile.mkdtemp(prefix="mcp4cm-upload-"))
    session = {
        "uploadId": upload_id,
        "language": language,
        "format": data_format,
        "parserOptions": parser_options_payload,
        "parserOptionsNormalized": dict(parser_options.values),
        "stageDir": str(stage_dir),
        "files": [],
        "totalBytes": 0,
        "createdAt": time.time(),
        "status": "collecting",
        "jobId": "",
    }
    with UPLOAD_LOCK:
        UPLOAD_SESSIONS[upload_id] = session
    return {
        "uploadId": upload_id,
        "language": language,
        "format": data_format,
        "status": session["status"],
        "fileCount": 0,
        "totalBytes": 0,
    }


def upload_chunk(upload_id: str, body: dict[str, Any]) -> dict[str, Any]:
    files = body.get("files") or []
    if not isinstance(files, list) or not files:
        raise ValueError("At least one file is required in an upload chunk.")

    with UPLOAD_LOCK:
        session = UPLOAD_SESSIONS.get(upload_id)
        if session is None:
            raise ValueError("Unknown uploadId. Start an upload session first.")
        if session.get("status") != "collecting":
            raise ValueError("Upload session is not accepting files.")
        stage_dir = Path(str(session["stageDir"]))
        staged_files = list(session["files"])
        total_bytes = int(session.get("totalBytes", 0))

    chunk_bytes = 0
    chunk_files = 0
    for file_item in files:
        if not isinstance(file_item, FileStorage):
            raise ValueError("Chunk upload requires multipart file items.")
        relpath = sanitized_relpath(file_item.filename or "")
        destination = unique_staged_path(stage_dir, relpath)
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_item.save(destination)
        file_size = destination.stat().st_size
        staged_files.append(
            {
                "relativePath": relpath,
                "storedPath": str(destination),
                "sizeBytes": file_size,
            }
        )
        chunk_bytes += file_size
        chunk_files += 1

    with UPLOAD_LOCK:
        session = UPLOAD_SESSIONS.get(upload_id)
        if session is None:
            raise ValueError("Unknown uploadId. Start an upload session first.")
        session["files"] = staged_files
        session["totalBytes"] = total_bytes + chunk_bytes

    return {
        "uploadId": upload_id,
        "status": "collecting",
        "chunkFiles": chunk_files,
        "chunkBytes": chunk_bytes,
        "totalFiles": len(staged_files),
        "totalBytes": total_bytes + chunk_bytes,
    }


def start_upload_parse(upload_id: str) -> dict[str, Any]:
    with UPLOAD_LOCK:
        session = UPLOAD_SESSIONS.get(upload_id)
        if session is None:
            raise ValueError("Unknown uploadId. Start an upload session first.")
        if not session.get("files"):
            raise ValueError("Upload session has no staged files.")
        existing_job_id = str(session.get("jobId") or "")
        if existing_job_id:
            existing_job = UPLOAD_PARSE_JOBS.get(existing_job_id)
            if existing_job and existing_job.get("status") in {"queued", "running"}:
                return dict(existing_job)
        job_id = uuid.uuid4().hex
        job = {
            "jobId": job_id,
            "uploadId": upload_id,
            "status": "queued",
            "progress": 0,
            "processedFiles": 0,
            "totalFiles": len(session["files"]),
            "stage": "queued",
            "parseProcessedFiles": 0,
            "parseTotalFiles": len(session["files"]),
            "message": "Queued parse job.",
            "error": "",
            "datasetId": "",
            "statistics": None,
            "uploadSummary": None,
            "startedAt": time.time(),
            "finishedAt": None,
            "elapsedMs": 0,
        }
        UPLOAD_PARSE_JOBS[job_id] = job
        session["jobId"] = job_id
        session["status"] = "processing"

    thread = threading.Thread(target=run_upload_parse_job, args=(upload_id, job_id), daemon=True)
    thread.start()
    return dict(job)


def get_upload_parse_job(upload_id: str, job_id: str) -> dict[str, Any]:
    with UPLOAD_LOCK:
        job = UPLOAD_PARSE_JOBS.get(job_id)
        if not job or job.get("uploadId") != upload_id:
            raise ValueError("Unknown upload parse job. Pipeline state may have been reset by a new run.")
        return dict(job)


def sanitized_relpath(name: str) -> str:
    candidate = Path(name or "").as_posix().strip()
    if not candidate:
        return f"file-{uuid.uuid4().hex}.bin"
    parts = [part for part in Path(candidate).parts if part not in {"", ".", ".."}]
    if not parts:
        return f"file-{uuid.uuid4().hex}.bin"
    return Path(*parts).as_posix()


def unique_staged_path(stage_dir: Path, relpath: str) -> Path:
    candidate = stage_dir / relpath
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    counter = 1
    while True:
        next_candidate = parent / f"{stem}-{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def register_routes(app) -> None:
    from flask import jsonify

    from mcp4cm.api.http import read_json_body, read_upload_request

    @app.route("/api/uploads/start", methods=["POST"])
    def start_upload_session_route():
        return jsonify(start_upload_session(read_json_body()))

    @app.route("/api/uploads/<upload_id>/chunks", methods=["POST"])
    def upload_chunk_route(upload_id: str):
        return jsonify(upload_chunk(upload_id, read_upload_request()))

    @app.route("/api/uploads/<upload_id>/parse", methods=["POST"])
    def start_upload_parse_route(upload_id: str):
        return jsonify(start_upload_parse(upload_id))

    @app.route("/api/uploads/<upload_id>/jobs/<job_id>", methods=["GET"])
    def get_upload_parse_job_route(upload_id: str, job_id: str):
        return jsonify(get_upload_parse_job(upload_id, job_id))
