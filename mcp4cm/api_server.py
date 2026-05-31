from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge

from mcp4cm._deps import require_networkx
from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.dummy import (
    default_filter_configs,
    evaluate_dummy_filters,
)
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    detect_duplicates_by_name_hash,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.parsers.archimate import ArchimateParser
from mcp4cm.parsers.extended import (
    ArchimateArchiModelParser,
    BPMNSignavioModelParser,
    EcoreXMIModelParser,
    RepresentationProfile,
    UMLXMIModelParser,
)
from mcp4cm.parsers.modelset import EcoreParser, UMLParser
from mcp4cm.statistics import dataset_summary, name_counts, node_names, type_counts

DATASETS: dict[str, Dataset] = {}
DUPLICATE_JOBS: dict[str, dict[str, Any]] = {}
UPLOAD_SESSIONS: dict[str, dict[str, Any]] = {}
UPLOAD_PARSE_JOBS: dict[str, dict[str, Any]] = {}
DUPLICATE_JOBS_LOCK = threading.Lock()
UPLOAD_LOCK = threading.Lock()
WEBAPP_DIST = Path(__file__).resolve().parents[1] / "webapp" / "dist"
RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
RUNTIME_IR_DIR = RUNTIME_DIR / "ir"
RUNTIME_INDEX = RUNTIME_DIR / "index.json"
LOG = logging.getLogger("mcp4cm.api")
SUPPORTED_LANGUAGES = {"uml", "ecore", "archimate", "bpmn"}
SUPPORTED_FORMATS = {"json", "xmi", "ecore", "signavio"}
RUNTIME_LOCK = threading.Lock()


def default_dummy_filter_configs(language: str) -> list[dict[str, Any]]:
    _ = language
    return default_filter_configs()


def create_app(webapp_dist: Path | str = WEBAPP_DIST) -> Flask:
    configure_logging()
    app = Flask(__name__)
    dist_path = Path(webapp_dist)

    @app.before_request
    def log_request_start():
        g.request_started_at = time.perf_counter()
        LOG.info("request_start method=%s path=%s content_length=%s", request.method, request.path, request.content_length)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        elapsed_ms = (time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000
        LOG.info("request_end method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.path, response.status_code, elapsed_ms)
        return response

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True})

    @app.route("/api/datasets/<dataset_id>/models/<model_id>/inspect", methods=["GET"])
    def inspect_model_route(dataset_id: str, model_id: str):
        node_limit = request.args.get("nodeLimit")
        edge_limit = request.args.get("edgeLimit")
        include_attrs = parse_form_bool(request.args.get("includeAttrs"), True)
        return jsonify(
            inspect_dataset_model(
                dataset_id=dataset_id,
                model_id=model_id,
                node_limit=parse_positive_int_param(node_limit, "nodeLimit"),
                edge_limit=parse_positive_int_param(edge_limit, "edgeLimit"),
                include_attrs=include_attrs,
            )
        )

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

    @app.route("/api/dummy", methods=["POST"])
    def dummy_filters():
        return jsonify(handle_dummy(read_json_body()))

    @app.route("/api/duplicates/jobs", methods=["POST"])
    def start_duplicates_job():
        return jsonify(start_duplicate_job(read_json_body()))

    @app.route("/api/duplicates/jobs/<job_id>", methods=["GET"])
    def get_duplicates_job(job_id: str):
        return jsonify(get_duplicate_job(job_id))

    @app.route("/api/<path:_path>", methods=["GET", "POST", "OPTIONS"])
    def api_not_found(_path: str):
        return jsonify({"error": "Not found"}), 404

    @app.route("/", defaults={"asset_path": ""})
    @app.route("/<path:asset_path>")
    def frontend(asset_path: str):
        if asset_path and (dist_path / asset_path).is_file():
            return send_from_directory(dist_path, asset_path)
        index_path = dist_path / "index.html"
        if index_path.is_file():
            return send_from_directory(dist_path, "index.html")
        return jsonify({"ok": True, "message": "MCP4CM Flask API is running. Build webapp/ to serve the React UI."})

    @app.errorhandler(ValueError)
    def value_error(exc: ValueError):
        LOG.warning("bad_request path=%s error=%s", request.path, exc)
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(json.JSONDecodeError)
    def json_error(exc: json.JSONDecodeError):
        LOG.warning("invalid_json path=%s error=%s", request.path, exc)
        return jsonify({"error": f"Invalid JSON: {exc.msg}"}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(exc: RequestEntityTooLarge):
        LOG.warning("request_too_large path=%s error=%s", request.path, exc)
        return jsonify({"error": "Upload too large for a single request. Use chunked upload session endpoints."}), 413

    @app.errorhandler(Exception)
    def unexpected_error(exc: Exception):
        LOG.exception("unhandled_error path=%s", request.path)
        return jsonify({"error": "Internal server error. Check backend logs for details."}), 500

    return app


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return

    level_name = os.environ.get("MCP4CM_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    log_file = os.environ.get("MCP4CM_LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=handlers, force=True)


def runtime_index_template() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": time.time(),
        "datasets": {},
    }


def ensure_runtime_store() -> None:
    RUNTIME_IR_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNTIME_INDEX.exists():
        RUNTIME_INDEX.write_text(json.dumps(runtime_index_template(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_runtime_index() -> dict[str, Any]:
    ensure_runtime_store()
    try:
        payload = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
    except Exception:
        payload = runtime_index_template()
    if not isinstance(payload, dict):
        payload = runtime_index_template()
    payload.setdefault("version", 1)
    payload.setdefault("updatedAt", time.time())
    payload.setdefault("datasets", {})
    if not isinstance(payload["datasets"], dict):
        payload["datasets"] = {}
    return payload


def save_runtime_index(index_payload: dict[str, Any]) -> None:
    index_payload["updatedAt"] = time.time()
    RUNTIME_IR_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = RUNTIME_INDEX.with_suffix(".tmp")
    temp_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(RUNTIME_INDEX)


def runtime_model_filename(model_id: str, index: int, seen: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(model_id or "").strip()) or f"model_{index + 1}"
    candidate = f"{base}.json"
    counter = 1
    while candidate in seen:
        candidate = f"{base}_{counter}.json"
        counter += 1
    seen.add(candidate)
    return candidate


def _flatten_runtime_attrs(attrs: Any, *, skip_keys: set[str]) -> dict[str, Any]:
    if not isinstance(attrs, dict):
        return {}
    flattened: dict[str, Any] = {}
    for raw_key, raw_value in attrs.items():
        key = str(raw_key)
        if key == "attrs" or key in skip_keys:
            continue
        flattened[key] = json_safe(raw_value)
    return flattened


def _drop_runtime_data_duplicates(payload: dict[str, Any], *, protected_keys: set[str]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload
    for key in list(payload.keys()):
        if key == "data" or key in protected_keys:
            continue
        if key in data and payload.get(key) == data.get(key):
            payload.pop(key, None)
    return payload


def serialize_graph_for_runtime(graph) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "directed": bool(graph.is_directed()),
        "multigraph": bool(graph.is_multigraph()),
        "graphAttrs": json_safe(dict(graph.graph)),
        "nodes": [],
        "edges": [],
    }
    for node_id, attrs in graph.nodes(data=True):
        node_entry: dict[str, Any] = {"id": json_safe(node_id)}
        node_entry.update(_flatten_runtime_attrs(attrs, skip_keys={"id"}))
        payload["nodes"].append(
            _drop_runtime_data_duplicates(
                node_entry,
                protected_keys={"id", "type", "name"},
            )
        )
    if graph.is_multigraph():
        for source, target, key, attrs in graph.edges(keys=True, data=True):
            edge_entry: dict[str, Any] = {
                "source": json_safe(source),
                "target": json_safe(target),
                "key": json_safe(key),
            }
            edge_entry.update(_flatten_runtime_attrs(attrs, skip_keys=set()))
            if "id" not in edge_entry and edge_entry.get("key") is not None:
                edge_entry["id"] = edge_entry["key"]
            payload["edges"].append(
                _drop_runtime_data_duplicates(
                    edge_entry,
                    protected_keys={"source", "target", "key", "id", "type"},
                )
            )
    else:
        for source, target, attrs in graph.edges(data=True):
            edge_entry = {"source": json_safe(source), "target": json_safe(target)}
            edge_entry.update(_flatten_runtime_attrs(attrs, skip_keys=set()))
            payload["edges"].append(
                _drop_runtime_data_duplicates(
                    edge_entry,
                    protected_keys={"source", "target", "id", "type"},
                )
            )
    return payload


def serialize_model_for_runtime(record: ModelRecord) -> dict[str, Any]:
    return {
        "modelId": str(record.model_id),
        "language": str(record.language),
        "labels": [str(label) for label in record.labels],
        "name": str(record.name or ""),
        "sourcePath": str(record.source_path or ""),
        "rawText": str(record.raw_text or ""),
        "rawXmi": str(record.raw_xmi or ""),
        "metadata": json_safe(record.metadata if isinstance(record.metadata, dict) else {}),
        "graph": serialize_graph_for_runtime(record.graph),
    }


def deserialize_graph_from_runtime(payload: dict[str, Any]):
    nx = require_networkx()
    directed = bool(payload.get("directed", True))
    multigraph = bool(payload.get("multigraph", False))
    graph_cls = (
        nx.MultiDiGraph
        if directed and multigraph
        else nx.DiGraph
        if directed
        else nx.MultiGraph
        if multigraph
        else nx.Graph
    )
    graph = graph_cls()
    graph.graph.update(payload.get("graphAttrs") or {})
    for node in payload.get("nodes") or []:
        node_id = node.get("id")
        attrs: dict[str, Any] = {}
        legacy_attrs = node.get("attrs")
        if isinstance(legacy_attrs, dict):
            attrs.update(legacy_attrs)
        for key, value in (node or {}).items():
            if key in {"id", "attrs"}:
                continue
            attrs[str(key)] = value
        graph.add_node(node_id, **attrs)
    for edge in payload.get("edges") or []:
        source = edge.get("source")
        target = edge.get("target")
        attrs: dict[str, Any] = {}
        legacy_attrs = edge.get("attrs")
        if isinstance(legacy_attrs, dict):
            attrs.update(legacy_attrs)
        for key, value in (edge or {}).items():
            if key in {"source", "target", "key", "attrs"}:
                continue
            attrs[str(key)] = value
        if multigraph:
            edge_key = edge.get("key")
            if edge_key is None:
                edge_key = attrs.get("id")
            graph.add_edge(source, target, key=edge_key, **attrs)
        else:
            graph.add_edge(source, target, **attrs)
    return graph


def deserialize_model_from_runtime(payload: dict[str, Any]) -> ModelRecord:
    graph_payload = payload.get("graph")
    if not isinstance(graph_payload, dict):
        raise ValueError("Persisted model graph payload is missing or invalid.")
    source_path = str(payload.get("sourcePath") or "")
    return ModelRecord(
        model_id=str(payload.get("modelId") or ""),
        language=str(payload.get("language") or ""),
        graph=deserialize_graph_from_runtime(graph_payload),
        labels=tuple(str(label) for label in (payload.get("labels") or [])),
        name=str(payload.get("name") or "") or None,
        source_path=Path(source_path) if source_path else None,
        raw_text=str(payload.get("rawText") or ""),
        raw_xmi=str(payload.get("rawXmi") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )


def persist_dataset_to_runtime(dataset_id: str, dataset: Dataset) -> None:
    dataset_id = str(dataset_id)
    if not dataset_id:
        return
    with RUNTIME_LOCK:
        ensure_runtime_store()
        dataset_dir = RUNTIME_IR_DIR / dataset_id
        shutil.rmtree(dataset_dir, ignore_errors=True)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        seen_files: set[str] = set()
        model_entries: list[dict[str, Any]] = []
        for index, record in enumerate(dataset.records):
            filename = runtime_model_filename(record.model_id, index, seen_files)
            model_payload = serialize_model_for_runtime(record)
            (dataset_dir / filename).write_text(json.dumps(model_payload, ensure_ascii=False), encoding="utf-8")
            model_entries.append({"modelId": str(record.model_id), "file": filename, "language": str(record.language)})
        index_payload = load_runtime_index()
        index_payload["datasets"][dataset_id] = {
            "datasetId": dataset_id,
            "datasetType": str(dataset.dataset_type),
            "createdAt": time.time(),
            "recordCount": len(dataset.records),
            "models": model_entries,
        }
        save_runtime_index(index_payload)


def load_dataset_from_runtime(dataset_id: str) -> Dataset | None:
    dataset_id = str(dataset_id)
    if not dataset_id:
        return None
    with RUNTIME_LOCK:
        index_payload = load_runtime_index()
        dataset_meta = index_payload.get("datasets", {}).get(dataset_id)
        if not isinstance(dataset_meta, dict):
            return None
        dataset_dir = RUNTIME_IR_DIR / dataset_id
        if not dataset_dir.exists():
            return None
        records: list[ModelRecord] = []
        for model_entry in dataset_meta.get("models") or []:
            filename = str((model_entry or {}).get("file") or "")
            if not filename:
                continue
            model_path = dataset_dir / filename
            if not model_path.exists():
                continue
            model_payload = json.loads(model_path.read_text(encoding="utf-8"))
            records.append(deserialize_model_from_runtime(model_payload))
        if not records:
            return None
        return Dataset(records=records, dataset_type=str(dataset_meta.get("datasetType") or "runtime"), root=dataset_dir)


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
    DATASETS.clear()
    for stage_dir in stage_dirs:
        remove_directory_quietly(stage_dir)
    remove_directory_quietly(RUNTIME_DIR)


def read_json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object request body.")
    return data


def read_upload_request() -> dict[str, Any]:
    if request.files or request.form:
        return {
            "language": request.form.get("language", ""),
            "format": request.form.get("format", "json"),
            "includeAttributes": request.form.get("includeAttributes", "true"),
            "includeOperations": request.form.get("includeOperations", "true"),
            "includeParameters": request.form.get("includeParameters", "true"),
            "includeModelRootNode": request.form.get("includeModelRootNode", "false"),
            "files": request.files.getlist("files"),
        }
    return read_json_body()


def run(host: str = "127.0.0.1", port: int = 8765, debug: bool = False, kill_port_process: bool = False) -> None:
    if kill_port_process:
        kill_processes_on_port(port)
    create_app().run(host=host, port=port, debug=debug)


def kill_processes_on_port(port: int) -> list[int]:
    pids = pids_on_port(port)
    current_pid = os.getpid()
    killed: list[int] = []
    for pid in pids:
        if pid == current_pid:
            continue
        LOG.warning("killing_process_on_port port=%s pid=%s signal=SIGKILL", port, pid)
        os.kill(pid, signal.SIGKILL)
        killed.append(pid)
    return killed


def pids_on_port(port: int) -> list[int]:
    command = ["lsof", "-ti", f":{port}"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        LOG.warning("lsof_not_found port=%s", port)
        return []
    if completed.returncode not in {0, 1}:
        LOG.warning("lsof_failed port=%s returncode=%s stderr=%s", port, completed.returncode, completed.stderr.strip())
        return []
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            LOG.warning("invalid_lsof_pid port=%s value=%s", port, line)
    return pids


def parse_form_bool(value: Any, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def representation_profile_from_body(body: dict[str, Any], language: str, data_format: str) -> RepresentationProfile:
    if language != "uml" or data_format != "xmi":
        return RepresentationProfile()
    return RepresentationProfile(
        include_attributes=parse_form_bool(body.get("includeAttributes"), True),
        include_operations=parse_form_bool(body.get("includeOperations"), True),
        include_parameters=parse_form_bool(body.get("includeParameters"), True),
        include_model_root_node=parse_form_bool(body.get("includeModelRootNode"), False),
    )


def validate_language_and_format(language: str, data_format: str) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("language must be one of: uml, ecore, archimate, bpmn")
    if data_format not in SUPPORTED_FORMATS:
        raise ValueError("format must be one of: json, xmi, ecore, signavio")

    allowed_formats = {
        "uml": {"json", "xmi"},
        "archimate": {"json", "xmi"},
        "ecore": {"json", "ecore"},
        "bpmn": {"signavio"},
    }
    if data_format not in allowed_formats.get(language, set()):
        raise ValueError(
            f"format '{data_format}' is not supported for language '{language}'."
        )


def start_upload_session(body: dict[str, Any]) -> dict[str, Any]:
    if has_active_pipeline_run():
        raise ValueError("A pipeline run is already active. Wait for it to complete before starting a new run.")
    reset_pipeline_state()
    language = str(body.get("language") or "").lower()
    data_format = str(body.get("format") or "json").lower()
    validate_language_and_format(language, data_format)
    representation = representation_profile_from_body(body, language, data_format)
    upload_id = uuid.uuid4().hex
    stage_dir = Path(tempfile.mkdtemp(prefix="mcp4cm-upload-"))
    session = {
        "uploadId": upload_id,
        "language": language,
        "format": data_format,
        "representationProfile": representation.as_metadata(),
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


def upload_job_elapsed_ms(job: dict[str, Any], *, finished_at: float | None = None) -> int:
    started_at = float(job.get("startedAt") or time.time())
    return round(((finished_at or time.time()) - started_at) * 1000)


def run_upload_parse_job(upload_id: str, job_id: str) -> None:
    def report(**patch: Any) -> None:
        with UPLOAD_LOCK:
            job = UPLOAD_PARSE_JOBS.get(job_id)
            if not job:
                return
            patch.setdefault("elapsedMs", upload_job_elapsed_ms(job))
            job.update(patch)

    def parse_phase_progress(processed: int, total: int) -> dict[str, Any]:
        percent = round((processed / max(1, total)) * 100)
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
            profile_payload = dict(session["representationProfile"])
            representation = RepresentationProfile(
                include_attributes=bool(profile_payload.get("includeAttributes", True)),
                include_operations=bool(profile_payload.get("includeOperations", True)),
                include_parameters=bool(profile_payload.get("includeParameters", True)),
                include_model_root_node=bool(profile_payload.get("includeModelRootNode", False)),
            )
            staged_files = list(session["files"])

        report(
            status="running",
            stage="parse",
            message="Parsing files.",
            totalFiles=len(staged_files),
            parseTotalFiles=len(staged_files),
        )
        dataset, parse_summary = parse_staged_dataset(
            language,
            data_format,
            representation,
            staged_files,
            progress=lambda processed, total: report(
                status="running",
                **parse_phase_progress(processed, total),
            ),
        )
        if not dataset.records:
            raise ValueError("Parsing produced 0 models. Check parser format and file contents.")

        total_records = len(dataset.records)
        parse_summary["format"] = data_format
        parse_summary["representationProfile"] = representation.as_metadata()

        dataset_id = uuid.uuid4().hex
        DATASETS[dataset_id] = dataset
        persist_dataset_to_runtime(dataset_id, dataset)
        statistics = serialize_statistics(dataset)

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
    language: str,
    data_format: str,
    representation: RepresentationProfile,
    staged_files: list[dict[str, Any]],
    progress=None,
) -> tuple[Dataset, dict[str, Any]]:
    if data_format == "json":
        return parse_staged_json_dataset(language, staged_files, progress=progress)
    return parse_staged_model_files(language, data_format, representation, staged_files, progress=progress)


def parse_staged_json_dataset(
    language: str,
    staged_files: list[dict[str, Any]],
    progress=None,
) -> tuple[Dataset, dict[str, Any]]:
    parser = {"uml": UMLParser(), "ecore": EcoreParser(), "archimate": ArchimateParser()}[language]
    records = []
    summary = empty_upload_summary()
    total_files = len(staged_files)
    for file_index, staged in enumerate(staged_files, start=1):
        relpath = str(staged.get("relativePath") or "")
        source_path = Path(str(staged.get("storedPath") or ""))
        summary["files"] += 1
        if progress:
            progress(file_index - 1, total_files)
        try:
            content = source_path.read_text(encoding="utf-8")
            payloads = parse_json_payloads(content)
        except Exception as exc:
            summary["errors"] += 1
            add_upload_warning(summary, "PARSE_ERROR", f"{relpath} failed to decode: {exc}", path=relpath)
            if progress:
                progress(file_index, total_files)
            continue
        for source_index, payload in enumerate(payloads):
            summary["payloads"] += 1
            for payload_index, model_payload in enumerate_model_payloads(payload):
                if not isinstance(model_payload, dict):
                    summary["errors"] += 1
                    add_upload_warning(
                        summary,
                        "INVALID_PAYLOAD",
                        f"{relpath}:{source_index}:{payload_index} is {type(model_payload).__name__}, expected object.",
                        path=relpath,
                    )
                    continue
                try:
                    record = parser.parse(
                        model_payload,
                        model_id=model_payload.get("ids")
                        or model_payload.get("id")
                        or model_payload.get("archimateId")
                        or f"{relpath}:{source_index}:{payload_index}",
                    )
                except Exception as exc:
                    summary["errors"] += 1
                    add_upload_warning(
                        summary,
                        "PARSE_ERROR",
                        f"{relpath}:{source_index}:{payload_index} failed to parse: {exc}",
                        path=relpath,
                    )
                    continue
                record.source_path = Path(relpath)
                records.append(record)
                summary["records"] += 1
        if progress:
            progress(file_index, total_files)
    return Dataset(records=records, dataset_type=language), finalize_upload_summary(summary, records)


def parse_staged_model_files(
    language: str,
    data_format: str,
    representation: RepresentationProfile,
    staged_files: list[dict[str, Any]],
    progress=None,
) -> tuple[Dataset, dict[str, Any]]:
    parser = extended_parser_for(language, data_format, representation)
    records = []
    summary = empty_upload_summary()
    total_files = len(staged_files)

    for file_index, staged in enumerate(staged_files, start=1):
        relpath = str(staged.get("relativePath") or "")
        source_path = Path(str(staged.get("storedPath") or ""))
        summary["files"] += 1
        summary["payloads"] += 1
        if progress:
            progress(file_index - 1, total_files)
        try:
            record = parser.parse_file(source_path, model_id=Path(relpath).stem)
            record.source_path = Path(relpath)
        except Exception as exc:
            summary["errors"] += 1
            add_upload_warning(summary, "PARSE_ERROR", f"{relpath} failed to parse: {exc}", path=relpath)
            if progress:
                progress(file_index, total_files)
            continue
        records.append(record)
        summary["records"] += 1
        merge_record_warnings(summary, record)
        if progress:
            progress(file_index, total_files)

    return Dataset(records=records, dataset_type=language), finalize_upload_summary(summary, records)


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


def handle_dummy(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(body)
    configs = body.get("filterConfigs")
    evaluation = evaluate_dummy_filters(dataset, filter_configs=configs if isinstance(configs, list) else None)

    filter_rows = [
        {
            "filterName": summary.filter_id,
            "filteredCount": summary.filtered_count,
            "remainingCount": summary.remaining_count,
            "examples": [
                {
                    "modelId": finding.model_id,
                    "reason": finding.reason,
                    "score": finding.score,
                    "evidence": list(finding.evidence),
                }
                for finding in evaluation.findings
                if finding.filter_id == summary.filter_id and finding.decision == "removed"
            ][:10],
        }
        for summary in evaluation.filter_summaries
    ]

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
        "rows": filter_rows,
    }


def start_duplicate_job(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(body)
    selected = selected_duplicate_techniques(body)
    if not selected:
        raise_no_duplicate_technique_error(body)

    job_id = uuid.uuid4().hex
    now = time.time()
    job = {
        "jobId": job_id,
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
        report(
            status="complete",
            progress=100,
            currentTechnique="",
            message="Duplicate detection complete.",
            result=result,
            finishedAt=finished_at,
            elapsedMs=elapsed_ms,
        )
        LOG.info("duplicate_job_complete job_id=%s duplicate_pairs=%s elapsed_ms=%s", job_id, result["duplicatePairs"], elapsed_ms)
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
    return round(((finished_at or time.time()) - started_at) * 1000)


def handle_duplicates(body: dict[str, Any], progress=None) -> dict[str, Any]:
    dataset = get_dataset(body)
    selected_order = selected_duplicate_techniques(body)
    if not selected_order:
        raise_no_duplicate_technique_error(body)

    thresholds = body.get("thresholds") or {}
    min_votes = int(body.get("minVotes", 2))
    mandatory = {
        normalize_duplicate_technique(value)
        for value in (body.get("mandatoryTechniques") or [])
        if normalize_duplicate_technique(value) in DUPLICATE_TECHNIQUE_ORDER
    }
    min_votes = max(min_votes, len(mandatory), 1)

    result_limit = max(1, int(body.get("resultLimit", thresholds.get("resultLimit", 500))))
    projected_dataset = dataset

    evidence: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    technique_counts: dict[str, int] = {}
    model_counts: dict[str, dict[str, int]] = {}
    technique_status: dict[str, dict[str, Any]] = {}
    completed: list[str] = []
    total_steps = len(selected_order)
    last_logged_algorithm_percent: dict[str, int] = {}
    algorithm_started_at: dict[str, float] = {}
    duplicate_started_at = time.perf_counter()

    def report_step_start(technique: str) -> None:
        label = duplicate_technique_label(technique)
        algorithm_started_at[technique] = time.perf_counter()
        LOG.info(
            "duplicate_algorithm_start technique=%s label=%s models=%s step=%s/%s",
            technique,
            label,
            len(projected_dataset),
            len(completed) + 1,
            total_steps,
        )
        if progress:
            progress(
                status="running",
                currentTechnique=technique,
                completedTechniques=list(completed),
                progress=round((len(completed) / total_steps) * 100) if total_steps else 100,
                techniqueProgress=0,
                processedItems=0,
                totalItems=0,
                message=f"Running {label} over {len(projected_dataset)} models.",
            )

    def report_algorithm_progress(technique: str):
        def report(event: dict[str, Any]) -> None:
            technique_percent = int(event.get("percent", 0))
            bucket = technique_percent if technique_percent == 100 else (technique_percent // 10) * 10
            if bucket != last_logged_algorithm_percent.get(technique):
                last_logged_algorithm_percent[technique] = bucket
                LOG.info(
                    "duplicate_algorithm_progress technique=%s label=%s phase=%s progress=%s%% current=%s total=%s message=%s",
                    technique,
                    duplicate_technique_label(technique),
                    event.get("phase", ""),
                    technique_percent,
                    event.get("current", 0),
                    event.get("total", 0),
                    event.get("message", ""),
                )
            if not progress:
                return
            overall = round(((len(completed) + (technique_percent / 100)) / total_steps) * 100) if total_steps else 100
            progress(
                status="running",
                currentTechnique=technique,
                completedTechniques=list(completed),
                progress=overall,
                techniqueProgress=technique_percent,
                processedItems=int(event.get("current", 0)),
                totalItems=int(event.get("total", 0)),
                message=str(event.get("message", "")),
            )

        return report

    def report_step_done(technique: str, pair_count: int, status: str, reason: str = "") -> None:
        completed.append(technique)
        elapsed_ms = round((time.perf_counter() - algorithm_started_at.get(technique, time.perf_counter())) * 1000)
        if technique in model_counts:
            model_counts[technique]["elapsedMs"] = elapsed_ms
        else:
            model_counts[technique] = {
                "duplicateModels": 0,
                "uniqueModels": len(projected_dataset),
                "totalModels": len(projected_dataset),
                "pairCount": 0,
                "elapsedMs": elapsed_ms,
            }
        technique_status[technique] = {
            "status": status,
            "reason": reason,
            "pairCount": pair_count,
            "elapsedMs": elapsed_ms,
        }
        counts = model_counts.get(technique, {})
        LOG.info(
            "duplicate_algorithm_complete technique=%s label=%s status=%s pairs=%s duplicate_models=%s unique_models=%s completed=%s/%s elapsed_ms=%s reason=%s",
            technique,
            duplicate_technique_label(technique),
            status,
            pair_count,
            counts.get("duplicateModels", 0),
            counts.get("uniqueModels", len(projected_dataset)),
            len(completed),
            total_steps,
            elapsed_ms,
            reason,
        )
        if progress:
            label = duplicate_technique_label(technique)
            suffix = f" ({status})" if status != "ok" else ""
            progress(
                status="running",
                currentTechnique="",
                completedTechniques=list(completed),
                progress=round((len(completed) / total_steps) * 100) if total_steps else 100,
                techniqueProgress=100,
                message=f"Completed {label}{suffix}: {pair_count} candidate pair(s).",
            )

    def add_pair_evidence(
        technique: str,
        pairs: list[tuple[str, str, float]],
        *,
        metrics_by_pair: dict[tuple[str, str], dict[str, float]] | None = None,
    ) -> None:
        for left_id, right_id, score in pairs:
            key = pair_key(left_id, right_id)
            entry = evidence.setdefault(key, {"scores": {}, "metrics": {}})
            entry["scores"][technique] = float(score)
            if metrics_by_pair and key in metrics_by_pair:
                entry["metrics"][technique] = metrics_by_pair[key]

    for technique in selected_order:
        report_step_start(technique)
        try:
            if technique == "hash":
                groups = detect_duplicates_by_name_hash(
                    projected_dataset,
                    include_types=parse_form_bool(thresholds.get("hashIncludeTypes"), False),
                    min_named_nodes=int(thresholds.get("minNamedNodes", 0)),
                    deduplicate_name_tokens=parse_form_bool(thresholds.get("deduplicateNameTokens"), False),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = group_pairs(groups)
                add_pair_evidence(technique, technique_pairs)
            elif technique == "tfidf":
                token_mode = parse_tfidf_token_mode(body, thresholds)
                threshold = float(
                    body.get(
                        "tfidfSimilarityThreshold",
                        thresholds.get("tfidfSimilarityThreshold", thresholds.get("tfidfNames", 0.9)),
                    )
                )
                stopwords_mode = parse_stopwords_mode(thresholds.get("stopwordsMode", "none"))
                pairs = tfidf_duplicate_pairs(
                    projected_dataset,
                    token_mode=token_mode,
                    threshold=threshold,
                    max_features=int(thresholds.get("tfidfMaxFeatures", 50_000)),
                    min_df=parse_min_df(thresholds.get("minDf", 1)),
                    ngram_range=parse_ngram_range(thresholds.get("ngramRange", [1, 1])),
                    stopwords_mode=stopwords_mode,
                    progress=report_algorithm_progress(technique),
                    technique=technique,
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                add_pair_evidence(technique, technique_pairs)
            elif technique == "graph_similarity":
                pairs = graph_similarity_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("graphSimilarity", 0.85)),
                    weights=graph_similarity_weights(thresholds),
                    use_directed_metrics=parse_form_bool(thresholds.get("useDirectedMetrics"), False),
                    normalize_parallel_edges=parse_form_bool(thresholds.get("normalizeParallelEdges"), False),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                metrics_by_pair = {
                    pair_key(pair.left_id, pair.right_id): dict(pair.metrics)
                    for pair in pairs
                }
                add_pair_evidence(technique, technique_pairs, metrics_by_pair=metrics_by_pair)
            elif technique == "graph_embedding":
                pairs = graph_embedding_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("graphEmbeddingThreshold", thresholds.get("graphEmbedding", 0.9))),
                    dimensions=int(thresholds.get("graphEmbeddingDimensions", 64)),
                    walk_length=int(thresholds.get("graphEmbeddingWalkLength", 10)),
                    num_walks=int(thresholds.get("graphEmbeddingNumWalks", 20)),
                    workers=int(thresholds.get("graphEmbeddingWorkers", 1)),
                    seed=int(thresholds.get("graphEmbeddingSeed", 42)),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                add_pair_evidence(technique, technique_pairs)
            elif technique == "bert_semantic":
                pairs = bert_semantic_similarity_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("bertSemantic", 0.9)),
                    model_name=str(thresholds.get("bertModelName", "bert-base-uncased")),
                    batch_size=int(thresholds.get("bertBatchSize", 8)),
                    max_length=int(thresholds.get("bertMaxLength", 256)),
                    semantic_text_mode=parse_semantic_text_mode(thresholds.get("semanticTextMode", "names_types_bag")),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                add_pair_evidence(technique, technique_pairs)
            elif technique == "graph_isomorphism":
                pairs = graph_isomorphism_pairs(
                    projected_dataset,
                    mode=parse_isomorphism_mode(thresholds.get("isomorphismMode", "names")),
                    match_edge_types=parse_form_bool(thresholds.get("matchEdgeTypes"), True),
                    ignore_direction=parse_form_bool(thresholds.get("ignoreDirection"), False),
                    match_parallel_edge_multiplicity=parse_form_bool(thresholds.get("matchParallelEdgeMultiplicity"), True),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                add_pair_evidence(technique, technique_pairs)
            else:
                raise ValueError(f"Unsupported technique in execution pipeline: {technique}")

            add_technique_model_counts(model_counts, technique_counts, projected_dataset, technique, technique_pairs)
            report_step_done(technique, len(technique_pairs), "ok")
        except ImportError as exc:
            add_technique_model_counts(model_counts, technique_counts, projected_dataset, technique, [])
            report_step_done(technique, 0, "skipped", str(exc))
        except Exception as exc:
            LOG.exception("duplicate_algorithm_failed technique=%s", technique)
            add_technique_model_counts(model_counts, technique_counts, projected_dataset, technique, [])
            report_step_done(technique, 0, "error", str(exc))

    decisions = []
    for (left_id, right_id), pair_evidence in sorted(evidence.items()):
        score_map = dict(pair_evidence.get("scores", {}))
        present = set(score_map)
        is_duplicate = mandatory.issubset(present) and len(present) >= min_votes
        decisions.append(
            {
                "leftId": left_id,
                "rightId": right_id,
                "isDuplicate": is_duplicate,
                "voteCount": len(present),
                "requiredVotes": min_votes,
                "techniques": sorted(present),
                "scores": score_map,
                "metrics": dict(pair_evidence.get("metrics", {})),
            }
        )

    decisions.sort(key=lambda item: (item["isDuplicate"], item["voteCount"]), reverse=True)
    approved_pairs = sum(1 for decision in decisions if decision["isDuplicate"])
    total_decisions = len(decisions)
    returned_decisions = min(result_limit, total_decisions)
    truncated = returned_decisions < total_decisions

    tfidf_threshold = float(
        body.get(
            "tfidfSimilarityThreshold",
            thresholds.get("tfidfSimilarityThreshold", thresholds.get("tfidfNames", 0.9)),
        )
    )
    config_echo = {
        "selectedTechniques": list(selected_order),
        "mandatoryTechniques": sorted(mandatory),
        "minVotes": min_votes,
        "resultLimit": result_limit,
        "hashIncludeTypes": parse_form_bool(thresholds.get("hashIncludeTypes"), False),
        "minNamedNodes": int(thresholds.get("minNamedNodes", 0)),
        "deduplicateNameTokens": parse_form_bool(thresholds.get("deduplicateNameTokens"), False),
        "tfidfTokenMode": parse_tfidf_token_mode(body, thresholds),
        "tfidfSimilarityThreshold": tfidf_threshold,
        "tfidfMaxFeatures": int(thresholds.get("tfidfMaxFeatures", 50_000)),
        "minDf": parse_min_df(thresholds.get("minDf", 1)),
        "ngramRange": list(parse_ngram_range(thresholds.get("ngramRange", [1, 1]))),
        "stopwordsMode": parse_stopwords_mode(thresholds.get("stopwordsMode", "none")),
    }

    return {
        "techniqueCounts": technique_counts,
        "modelCounts": model_counts,
        "duplicatePairs": total_decisions,
        "votedDuplicatePairs": approved_pairs,
        "candidatePairs": total_decisions,
        "approvedPairs": approved_pairs,
        "totalDecisions": total_decisions,
        "returnedDecisions": returned_decisions,
        "truncated": truncated,
        "truncationLimit": result_limit,
        "decisions": decisions[:result_limit],
        "techniqueStatus": technique_status,
        "configEcho": config_echo,
        "elapsedMs": round((time.perf_counter() - duplicate_started_at) * 1000),
    }


def merge_record_warnings(summary: dict[str, Any], record) -> None:
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    warning_total = int(metadata.get("parse_warnings_total", 0) or 0)
    if warning_total <= 0:
        return
    warning_types = metadata.get("parse_warnings_by_type") or {}
    warning_messages_by_type = metadata.get("parse_warning_messages_by_type") or {}
    warning_messages = metadata.get("parse_warning_messages") or metadata.get("parse_warning_messages_sample") or []
    source_path = str(record.source_path or "")
    model_id = str(record.model_id or "")
    warning_entries_added = 0
    typed_warning_total = 0
    typed_warning_names: list[str] = []
    for warning_type, count in warning_types.items():
        warning_type = str(warning_type)
        warning_count = int(count or 0)
        if warning_count <= 0:
            continue
        typed_warning_total += warning_count
        typed_warning_names.append(warning_type)
        summary["warningsByType"][warning_type] = summary["warningsByType"].get(warning_type, 0) + warning_count
        register_warning_file(summary, source_path, warning_type, warning_count, model_id=model_id)
        type_messages = warning_messages_by_type.get(warning_type) or []
        for message in type_messages:
            append_warning_entry(summary, warning_type, str(message), path=source_path, model_id=model_id)
            warning_entries_added += 1
    summary["warnings"] += warning_total
    fallback_type = typed_warning_names[0] if typed_warning_names else "PARSE_WARNING"
    if warning_entries_added == 0:
        for message in warning_messages:
            append_warning_entry(summary, fallback_type, str(message), path=source_path, model_id=model_id)
            warning_entries_added += 1
    if warning_entries_added < warning_total:
        for _ in range(warning_total - warning_entries_added):
            append_warning_entry(
                summary,
                fallback_type,
                "Warning emitted without a detailed parser message.",
                path=source_path,
                model_id=model_id,
            )
    if typed_warning_total <= 0:
        summary["warningsByType"]["PARSE_WARNING"] = summary["warningsByType"].get("PARSE_WARNING", 0) + warning_total
        register_warning_file(
            summary,
            source_path,
            "PARSE_WARNING",
            warning_total,
            model_id=model_id,
        )


def add_upload_warning(
    summary: dict[str, Any],
    warning_type: str,
    message: str,
    *,
    path: str = "",
    model_id: str = "",
) -> None:
    summary["warnings"] += 1
    summary["warningsByType"][warning_type] = summary["warningsByType"].get(warning_type, 0) + 1
    append_warning_entry(summary, warning_type, message, path=path, model_id=model_id)
    if path:
        register_warning_file(summary, path, warning_type, 1, model_id=model_id)


def empty_upload_summary() -> dict[str, Any]:
    return {
        "files": 0,
        "payloads": 0,
        "records": 0,
        "errors": 0,
        "warnings": 0,
        "warningsByType": {},
        "warningsList": [],
        "warningFiles": [],
        "parsedModels": [],
        "_warningFileIndex": {},
    }


def append_warning_entry(
    summary: dict[str, Any],
    warning_type: str,
    message: str,
    *,
    path: str = "",
    model_id: str = "",
) -> None:
    entry = {
        "type": str(warning_type),
        "message": str(message),
        "path": str(path or ""),
    }
    if model_id:
        entry["modelId"] = str(model_id)
    summary["warningsList"].append(entry)


def register_warning_file(
    summary: dict[str, Any],
    path: str,
    warning_type: str,
    count: int,
    *,
    model_id: str = "",
) -> None:
    if not path:
        return
    warning_file_index = summary.setdefault("_warningFileIndex", {})
    existing_index = warning_file_index.get(path)
    if existing_index is None:
        entry = {
            "path": path,
            "warnings": 0,
            "types": {},
            "modelId": str(model_id or ""),
            "hasDetails": True,
        }
        summary["warningFiles"].append(entry)
        existing_index = len(summary["warningFiles"]) - 1
        warning_file_index[path] = existing_index
    entry = summary["warningFiles"][existing_index]
    if model_id:
        existing_model_id = str(entry.get("modelId") or "")
        if existing_model_id and existing_model_id != model_id:
            entry["modelId"] = ""
        elif not existing_model_id:
            entry["modelId"] = str(model_id)
    entry["warnings"] = int(entry.get("warnings", 0)) + int(count)
    types = entry.setdefault("types", {})
    types[warning_type] = int(types.get(warning_type, 0)) + int(count)


def build_parsed_models_summary(summary: dict[str, Any], records: list[ModelRecord]) -> list[dict[str, Any]]:
    warnings_by_model: dict[str, dict[str, Any]] = {}
    for warning in summary.get("warningsList") or []:
        if not isinstance(warning, dict):
            continue
        model_id = str(warning.get("modelId") or "")
        if not model_id:
            continue
        warning_type = str(warning.get("type") or "PARSE_WARNING")
        row = warnings_by_model.setdefault(model_id, {"warnings": 0, "types": {}})
        row["warnings"] += 1
        row["types"][warning_type] = int(row["types"].get(warning_type, 0)) + 1

    parsed_models: list[dict[str, Any]] = []
    for record in records:
        model_id = str(record.model_id or "")
        warning_info = warnings_by_model.get(model_id, {"warnings": 0, "types": {}})
        parsed_models.append(
            {
                "modelId": model_id,
                "name": str(record.name or ""),
                "path": str(record.source_path or ""),
                "language": str(record.language or ""),
                "warnings": int(warning_info.get("warnings", 0)),
                "types": dict(warning_info.get("types", {})),
            }
        )
    return parsed_models


def finalize_upload_summary(summary: dict[str, Any], records: list[ModelRecord] | None = None) -> dict[str, Any]:
    if records is not None:
        summary["parsedModels"] = build_parsed_models_summary(summary, records)
    else:
        summary.setdefault("parsedModels", [])
    summary.pop("_warningFileIndex", None)
    return summary


def extended_parser_for(language: str, data_format: str, representation: RepresentationProfile):
    mapping = {
        ("uml", "xmi"): UMLXMIModelParser,
        ("archimate", "xmi"): ArchimateArchiModelParser,
        ("ecore", "ecore"): EcoreXMIModelParser,
        ("bpmn", "signavio"): BPMNSignavioModelParser,
    }
    parser_cls = mapping.get((language, data_format))
    if parser_cls is None:
        raise ValueError(f"Unsupported language/format combination: {language}/{data_format}")
    return parser_cls(representation)


def parse_json_payloads(content: str) -> list[Any]:
    try:
        payload = json.loads(content)
        return payload if isinstance(payload, list) else [payload]
    except json.JSONDecodeError:
        payloads = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                payloads.append(json.loads(line))
        return payloads


def enumerate_model_payloads(payload: Any) -> Iterable[tuple[int, Any]]:
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            yield index, item
        return
    yield 0, payload


def serialize_statistics(dataset: Dataset) -> dict[str, Any]:
    return {
        "summary": dataset_summary(dataset),
        "topTypes": top_items(type_counts(dataset), 15),
        "topNames": top_items(name_counts(dataset), 15),
        "sampleModels": [
            {
                "id": record.model_id,
                "language": record.language,
                "nodes": record.node_count,
                "edges": record.edge_count,
                "names": len(node_names(record)),
            }
            for record in dataset.records[:8]
        ],
    }


def top_items(counter, limit: int) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def get_dataset(body: dict[str, Any]) -> Dataset:
    dataset_id = str(body.get("datasetId") or "")
    if dataset_id in DATASETS:
        return DATASETS[dataset_id]
    runtime_dataset = load_dataset_from_runtime(dataset_id)
    if runtime_dataset is not None:
        DATASETS[dataset_id] = runtime_dataset
        return runtime_dataset
    raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")


def get_dataset_by_id(dataset_id: str) -> Dataset:
    dataset_id = str(dataset_id)
    if dataset_id in DATASETS:
        return DATASETS[dataset_id]
    runtime_dataset = load_dataset_from_runtime(dataset_id)
    if runtime_dataset is not None:
        DATASETS[dataset_id] = runtime_dataset
        return runtime_dataset
    raise ValueError("Unknown datasetId. Pipeline state was reset by a new run; please re-upload.")


def parse_positive_int_param(raw_value: Any, field_name: str) -> int | None:
    if raw_value in (None, ""):
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return value


def inspect_dataset_model(
    *,
    dataset_id: str,
    model_id: str,
    node_limit: int | None = None,
    edge_limit: int | None = None,
    include_attrs: bool = True,
) -> dict[str, Any]:
    dataset = get_dataset_by_id(str(dataset_id))
    model_id = str(model_id or "")
    for record in dataset.records:
        if str(record.model_id) != model_id:
            continue

        nodes: list[dict[str, Any]] = []
        for index, (node_id, attrs) in enumerate(record.graph.nodes(data=True)):
            if node_limit is not None and index >= node_limit:
                break
            node_entry: dict[str, Any] = {"id": str(node_id)}
            if include_attrs:
                node_entry["attrs"] = json_safe(attrs)
            nodes.append(node_entry)

        edges: list[dict[str, Any]] = []
        if record.graph.is_multigraph():
            iterable = record.graph.edges(keys=True, data=True)
            for index, (source, target, key, attrs) in enumerate(iterable):
                if edge_limit is not None and index >= edge_limit:
                    break
                edge_entry: dict[str, Any] = {"source": str(source), "target": str(target), "key": str(key)}
                if include_attrs:
                    edge_entry["attrs"] = json_safe(attrs)
                edges.append(edge_entry)
        else:
            iterable = record.graph.edges(data=True)
            for index, (source, target, attrs) in enumerate(iterable):
                if edge_limit is not None and index >= edge_limit:
                    break
                edge_entry = {"source": str(source), "target": str(target)}
                if include_attrs:
                    edge_entry["attrs"] = json_safe(attrs)
                edges.append(edge_entry)

        return {
            "model": {
                "id": str(record.model_id),
                "language": str(record.language),
                "name": str(record.name or ""),
                "sourcePath": str(record.source_path or ""),
                "nodeCount": int(record.node_count),
                "edgeCount": int(record.edge_count),
                "metadata": json_safe(record.metadata),
            },
            "nodes": nodes,
            "edges": edges,
            "truncated": {
                "nodes": node_limit is not None and len(nodes) < int(record.node_count),
                "edges": edge_limit is not None and len(edges) < int(record.edge_count),
            },
        }
    raise ValueError("Unknown modelId for the selected dataset.")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:  # pragma: no cover - best effort only
            return str(value)
    return str(value)


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))  # type: ignore[return-value]


def add_votes(
    votes: dict[tuple[str, str], dict[str, float]],
    pairs: list[tuple[str, str, float]],
    technique: str,
    default_score: float | None = None,
) -> None:
    for left_id, right_id, score in pairs:
        votes.setdefault(pair_key(left_id, right_id), {})[technique] = default_score if default_score is not None else score


def add_technique_model_counts(
    model_counts: dict[str, dict[str, int]],
    technique_counts: dict[str, int],
    dataset: Dataset,
    technique: str,
    pairs: list[tuple[str, str, float]],
) -> None:
    duplicate_ids = {model_id for left_id, right_id, _ in pairs for model_id in (left_id, right_id)}
    total_models = len(dataset)
    technique_counts[technique] = len(pairs)
    model_counts[technique] = {
        "duplicateModels": len(duplicate_ids),
        "uniqueModels": max(total_models - len(duplicate_ids), 0),
        "totalModels": total_models,
        "pairCount": len(pairs),
    }


def graph_similarity_weights(thresholds: dict[str, Any]) -> dict[str, float] | None:
    weights = thresholds.get("graphWeights")
    if not isinstance(weights, dict):
        return None
    parsed = {
        "node_name_jaccard": float(weights.get("nodeNameJaccard", 0.25)),
        "node_type_jaccard": float(weights.get("nodeTypeJaccard", 0.20)),
        "edge_type_jaccard": float(weights.get("edgeTypeJaccard", 0.15)),
        "degree_histogram_similarity": float(weights.get("degreeHistogram", 0.15)),
        "size_similarity": float(weights.get("sizeSimilarity", 0.15)),
        "density_similarity": float(weights.get("densitySimilarity", 0.10)),
    }
    if "inDegreeHistogram" in weights:
        parsed["in_degree_histogram_similarity"] = float(weights.get("inDegreeHistogram", 0.0))
    if "outDegreeHistogram" in weights:
        parsed["out_degree_histogram_similarity"] = float(weights.get("outDegreeHistogram", 0.0))
    return parsed


DUPLICATE_TECHNIQUE_ORDER = (
    "hash",
    "tfidf",
    "graph_similarity",
    "graph_embedding",
    "bert_semantic",
    "graph_isomorphism",
)

DUPLICATE_TECHNIQUE_LABELS = {
    "hash": "Hash",
    "tfidf": "TF-IDF",
    "graph_similarity": "Graph Metrics",
    "graph_embedding": "Graph Embeddings",
    "bert_semantic": "BERT Semantic",
    "graph_isomorphism": "Isomorphism",
}


def selected_duplicate_techniques(body: dict[str, Any]) -> list[str]:
    raw_techniques = raw_duplicate_techniques(body)
    selected = {normalize_duplicate_technique(technique) for technique in raw_techniques}
    LOG.info("duplicate_techniques_received raw=%s normalized=%s", raw_techniques, sorted(selected))
    return [technique for technique in DUPLICATE_TECHNIQUE_ORDER if technique in selected]


def duplicate_technique_label(technique: str) -> str:
    return DUPLICATE_TECHNIQUE_LABELS.get(technique, technique)


DUPLICATE_TECHNIQUE_ALIASES = {
    "hash": "hash",
    "hash_names": "hash",
    "hash_name": "hash",
    "hash_names_types": "hash",
    "hash_names_and_types": "hash",
    "tfidf": "tfidf",
    "tfidf_names": "tfidf",
    "tf_idf_names": "tfidf",
    "tfidf_names_types": "tfidf",
    "tfidf_names_and_types": "tfidf",
    "tf_idf_names_types": "tfidf",
    "tf_idf_names_and_types": "tfidf",
    "graph_similarity": "graph_similarity",
    "graph_metrics": "graph_similarity",
    "graph_embedding": "graph_embedding",
    "graph_embeddings": "graph_embedding",
    "node2vec": "graph_embedding",
    "node2vec_graph_embedding": "graph_embedding",
    "bert": "bert_semantic",
    "bert_semantic": "bert_semantic",
    "bert_similarity": "bert_semantic",
    "bert_semantic_similarity": "bert_semantic",
    "semantic_similarity": "bert_semantic",
    "graph_isomorphism": "graph_isomorphism",
    "isomorphism": "graph_isomorphism",
}


def normalize_duplicate_technique(technique: Any) -> str:
    normalized = "_".join(str(technique or "").strip().lower().replace("-", "_").replace("+", "and").split())
    return DUPLICATE_TECHNIQUE_ALIASES.get(normalized, normalized)


def raw_duplicate_techniques(body: dict[str, Any]) -> list[Any]:
    raw = body.get("techniques")
    if raw is None:
        raw = body.get("selectedTechniques")
    if raw is None:
        raw = body.get("selected")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, dict):
        return [key for key, enabled in raw.items() if enabled]
    if isinstance(raw, list):
        values = []
        for item in raw:
            if isinstance(item, dict):
                values.append(item.get("id") or item.get("value") or item.get("name") or item.get("label") or "")
            else:
                values.append(item)
        return values
    return [raw]


def parse_tfidf_token_mode(body: dict[str, Any], thresholds: dict[str, Any]) -> str:
    raw = body.get("tfidfTokenMode", thresholds.get("tfidfTokenMode"))
    if raw is None:
        include_types = parse_form_bool(thresholds.get("tfidfIncludeTypes"), False)
        return "names_types_bag" if include_types else "names"
    normalized = str(raw).strip().lower()
    aliases = {
        "names": "names",
        "name": "names",
        "names_types_bag": "names_types_bag",
        "names+types": "names_types_bag",
        "names_types": "names_types_bag",
        "typed_name_pairs": "typed_name_pairs",
        "typed_pairs": "typed_name_pairs",
    }
    if normalized not in aliases:
        raise ValueError("tfidfTokenMode must be one of: names, names_types_bag, typed_name_pairs.")
    return aliases[normalized]


def parse_semantic_text_mode(value: Any) -> str:
    normalized = str(value or "names_types_bag").strip().lower()
    aliases = {
        "names": "names",
        "names_types_bag": "names_types_bag",
        "names_types": "names_types_bag",
        "typed_name_pairs": "typed_name_pairs",
    }
    if normalized not in aliases:
        raise ValueError("semanticTextMode must be one of: names, names_types_bag, typed_name_pairs.")
    return aliases[normalized]


def parse_stopwords_mode(value: Any) -> str:
    normalized = str(value or "none").strip().lower()
    aliases = {
        "none": "none",
        "non": "none",
        "english": "english",
    }
    if normalized not in aliases:
        raise ValueError("stopwordsMode must be one of: none, english.")
    return aliases[normalized]


def parse_ngram_range(value: Any) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        first, second = int(value[0]), int(value[1])
    elif isinstance(value, str) and "," in value:
        parts = [item.strip() for item in value.split(",")]
        if len(parts) != 2:
            raise ValueError("ngramRange must contain exactly two numbers.")
        first, second = int(parts[0]), int(parts[1])
    else:
        first, second = 1, 1
    if first < 1 or second < first:
        raise ValueError("ngramRange must satisfy 1 <= min <= max.")
    return first, second


def parse_min_df(value: Any) -> int | float:
    if value is None:
        return 1
    if isinstance(value, (int, float)):
        parsed = value
    else:
        raw = str(value).strip()
        parsed = float(raw) if "." in raw else int(raw)
    if isinstance(parsed, (int, float)) and parsed > 0:
        return parsed
    raise ValueError("minDf must be greater than 0.")


def parse_isomorphism_mode(value: Any) -> str:
    normalized = str(value or "names").strip().lower()
    if normalized not in {"structure", "names", "names_types"}:
        raise ValueError("isomorphismMode must be one of: structure, names, names_types.")
    return normalized


def unsupported_duplicate_techniques(body: dict[str, Any]) -> list[str]:
    unsupported = []
    for technique in raw_duplicate_techniques(body):
        normalized = normalize_duplicate_technique(technique)
        if normalized not in DUPLICATE_TECHNIQUE_ORDER:
            unsupported.append(str(technique))
    return unsupported


def raise_no_duplicate_technique_error(body: dict[str, Any]) -> None:
    unsupported = unsupported_duplicate_techniques(body)
    if unsupported:
        raise ValueError(
            "Unsupported duplicate technique(s): "
            f"{', '.join(unsupported)}. Supported techniques: {', '.join(DUPLICATE_TECHNIQUE_ORDER)}."
        )
    raise ValueError(
        "Select at least one duplicate technique. "
        f"Request contained techniques={raw_duplicate_techniques(body)!r}."
    )


def group_pairs(groups) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    for group in groups:
        ids = list(group.model_ids)
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1 :]:
                pairs.append((left_id, right_id, 1.0))
    return pairs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MCP4CM Flask API server.")
    parser.add_argument("--host", default=os.environ.get("MCP4CM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP4CM_PORT", "8765")))
    parser.add_argument("--debug", action="store_true", default=os.environ.get("MCP4CM_DEBUG") == "1")
    parser.add_argument(
        "--kill-port-process",
        action="store_true",
        default=os.environ.get("MCP4CM_KILL_PORT_PROCESS") == "1",
        help="Run lsof -ti :PORT and kill -9 any process using the server port before starting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run(host=args.host, port=args.port, debug=args.debug, kill_port_process=args.kill_port_process)


if __name__ == "__main__":
    main()
