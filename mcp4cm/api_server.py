from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Iterable
from io import TextIOWrapper
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.datastructures import FileStorage

from mcp4cm.core import Dataset
from mcp4cm.dummy import (
    ARCHIMATE_CRUD_OR_CODE_THRESHOLD,
    ARCHIMATE_DUMMY_KEYWORD_THRESHOLD,
    ARCHIMATE_GENERIC_NUMBERED_THRESHOLD,
    ARCHIMATE_MIN_NAMES_COUNT,
    ARCHIMATE_SHORT_NAME_THRESHOLD,
    ARCHIMATE_TYPE_NAME_THRESHOLD,
    ARCHIMATE_VOCABULARY_UNIQUENESS_THRESHOLD,
    ECORE_DUMMY_KEYWORD_THRESHOLD,
    ECORE_GENERIC_NUMBERED_THRESHOLD,
    ECORE_MIN_NAMES_COUNT,
    ECORE_SHORT_NAME_THRESHOLD,
    ECORE_TYPE_NAME_THRESHOLD,
    ECORE_VOCABULARY_UNIQUENESS_THRESHOLD,
    UML_DUMMY_CLASSES_THRESHOLD,
    UML_DUMMY_NAMES_THRESHOLD,
    UML_DUMMY_WORD_THRESHOLD,
    UML_MIN_NAMES_COUNT,
    UML_MIN_MEDIAN_NAME_LENGTH,
    UML_SEQUENTIAL_THRESHOLD,
    UML_SHORT_NAMES_UPPER_THRESHOLD,
    UML_SHORT_NAMES_LOWER_THRESHOLD,
    UML_STOPWORDS_THRESHOLD,
    UML_TWO_CHAR_NAMES_THRESHOLD,
    UML_VOCABULARY_UNIQUENESS_THRESHOLD,
    archimate_crud_or_code_filter,
    archimate_dummy_keyword_filter,
    archimate_generic_numbered_filter,
    archimate_new_model_filter,
    archimate_type_name_filter,
    archimate_vocabulary_uniqueness_filter,
    dummy_word_filter,
    ecore_dummy_keyword_filter,
    ecore_generic_numbered_filter,
    ecore_type_name_filter,
    ecore_vocabulary_uniqueness_filter,
    empty_model_filter,
    generic_sequential_names_filter,
    regex_name_filter,
    short_name_ratio_filter,
    summarize_filters,
    too_few_named_elements_filter,
    uml_empty_class_name_filter,
    uml_empty_name_filter,
    uml_dummy_class_filter,
    uml_dummy_keyword_filter,
    uml_dummy_name_filter,
    uml_generic_class_name_filter,
    uml_median_name_length_filter,
    uml_sequential_numbered_filter,
    uml_short_name_or_control_flow_filter,
    uml_two_character_dummy_name_filter,
    uml_vocabulary_uniqueness_filter,
)
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_by_names,
    tfidf_duplicate_by_names_and_types,
)
from mcp4cm.parsers.archimate import ArchimateParser
from mcp4cm.parsers.modelset import EcoreParser, UMLParser
from mcp4cm.statistics import dataset_summary, name_counts, type_counts, word_counts

DATASETS: dict[str, Dataset] = {}
PREPROCESSED_UPLOADS: dict[str, dict[str, Any]] = {}
DUPLICATE_JOBS: dict[str, dict[str, Any]] = {}
DUPLICATE_JOBS_LOCK = threading.Lock()
WEBAPP_DIST = Path(__file__).resolve().parents[1] / "webapp" / "dist"
LOG = logging.getLogger("mcp4cm.api")


def default_dummy_filter_configs(language: str) -> list[dict[str, Any]]:
    language = language.lower()
    if language == "uml":
        return [
            {"id": "empty_model", "enabled": True},
            {"id": "uml_empty_class_name", "enabled": True},
            {"id": "uml_empty_name", "enabled": True},
            {"id": "too_few_names", "enabled": True, "minNames": UML_MIN_NAMES_COUNT},
            {"id": "uml_median_name_length", "enabled": True, "minMedianLength": UML_MIN_MEDIAN_NAME_LENGTH},
            {
                "id": "uml_short_name_or_control_flow",
                "enabled": True,
                "maxLength": 2,
                "threshold": UML_SHORT_NAMES_UPPER_THRESHOLD,
                "lowThreshold": UML_SHORT_NAMES_LOWER_THRESHOLD,
                "controlFlowThreshold": UML_STOPWORDS_THRESHOLD,
            },
            {"id": "uml_dummy_class", "enabled": True, "threshold": UML_DUMMY_CLASSES_THRESHOLD},
            {"id": "uml_generic_class_name", "enabled": True, "thresholdCount": 2},
            {"id": "uml_dummy_name", "enabled": True, "threshold": UML_DUMMY_NAMES_THRESHOLD},
            {"id": "uml_two_character_dummy_name", "enabled": True, "threshold": UML_TWO_CHAR_NAMES_THRESHOLD},
            {"id": "uml_dummy_keyword", "enabled": True, "threshold": UML_DUMMY_WORD_THRESHOLD},
            {"id": "uml_sequential", "enabled": True, "threshold": UML_SEQUENTIAL_THRESHOLD},
            {"id": "uml_vocabulary", "enabled": True, "minUniqueWords": UML_VOCABULARY_UNIQUENESS_THRESHOLD},
        ]
    if language == "ecore":
        return [
            {"id": "empty_model", "enabled": True},
            {"id": "too_few_names", "enabled": True, "minNames": ECORE_MIN_NAMES_COUNT},
            {"id": "ecore_type_name", "enabled": True, "threshold": ECORE_TYPE_NAME_THRESHOLD},
            {"id": "ecore_numbered", "enabled": True, "threshold": ECORE_GENERIC_NUMBERED_THRESHOLD},
            {"id": "ecore_dummy_keyword", "enabled": True, "threshold": ECORE_DUMMY_KEYWORD_THRESHOLD},
            {"id": "ecore_vocabulary", "enabled": True, "minUniqueWords": ECORE_VOCABULARY_UNIQUENESS_THRESHOLD},
            {"id": "short_names", "enabled": True, "maxLength": 2, "threshold": ECORE_SHORT_NAME_THRESHOLD},
        ]
    if language == "archimate":
        return [
            {"id": "empty_model", "enabled": True},
            {"id": "too_few_names", "enabled": True, "minNames": ARCHIMATE_MIN_NAMES_COUNT},
            {"id": "archimate_new_model", "enabled": True},
            {"id": "archimate_type_name", "enabled": True, "threshold": ARCHIMATE_TYPE_NAME_THRESHOLD},
            {"id": "archimate_numbered", "enabled": True, "threshold": ARCHIMATE_GENERIC_NUMBERED_THRESHOLD},
            {"id": "archimate_dummy_keyword", "enabled": True, "threshold": ARCHIMATE_DUMMY_KEYWORD_THRESHOLD},
            {"id": "archimate_crud_code", "enabled": True, "threshold": ARCHIMATE_CRUD_OR_CODE_THRESHOLD},
            {"id": "archimate_vocabulary", "enabled": True, "minUniqueWords": ARCHIMATE_VOCABULARY_UNIQUENESS_THRESHOLD},
            {"id": "short_names", "enabled": True, "maxLength": 2, "threshold": ARCHIMATE_SHORT_NAME_THRESHOLD},
        ]
    return [
        {"id": "empty_model", "enabled": True},
        {"id": "too_few_names", "enabled": True, "minNames": 2},
        {"id": "dummy_words", "enabled": True, "threshold": 0.35},
        {"id": "generic_sequential", "enabled": True, "threshold": 0.5},
        {"id": "short_names", "enabled": True, "maxLength": 2, "threshold": 0.6},
    ]


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

    @app.route("/api/datasets", methods=["POST"])
    def upload_dataset():
        return jsonify(handle_upload(read_upload_request()))

    @app.route("/api/datasets/preprocess", methods=["POST"])
    def preprocess_dataset():
        return jsonify(handle_preprocess_upload(read_upload_request()))

    @app.route("/api/dummy", methods=["POST"])
    def dummy_filters():
        return jsonify(handle_dummy(read_json_body()))

    @app.route("/api/duplicates", methods=["POST"])
    def duplicates():
        return jsonify(handle_duplicates(read_json_body()))

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
            "files": request.files.getlist("files"),
            "modelLimit": request.form.get("modelLimit", ""),
            "preprocessId": request.form.get("preprocessId", ""),
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


def handle_upload(body: dict[str, Any]) -> dict[str, Any]:
    language = str(body.get("language") or "").lower()
    files = body.get("files") or []
    if language not in {"uml", "ecore", "archimate"}:
        raise ValueError("language must be one of: uml, ecore, archimate")
    LOG.info(
        "upload_start language=%s file_count=%s preprocess_id=%s",
        language,
        len(files) if isinstance(files, list) else "invalid",
        body.get("preprocessId") or "",
    )
    dataset, parse_summary = dataset_from_upload_or_preprocess(language, files, body.get("preprocessId"))
    if not dataset.records:
        raise ValueError(
            "Upload parsed 0 models. Check that the selected modeling language matches the file and that the file "
            "contains JSON objects or JSONL lines with model objects."
        )
    total_records = len(dataset.records)
    model_limit = normalized_model_limit(body.get("modelLimit"), total_records)
    if model_limit < total_records:
        dataset = Dataset(records=dataset.records[:model_limit], dataset_type=dataset.dataset_type, root=dataset.root)
    parse_summary["totalRecords"] = total_records
    parse_summary["usedRecords"] = len(dataset.records)
    parse_summary["modelLimit"] = model_limit
    dataset_id = uuid.uuid4().hex
    DATASETS[dataset_id] = dataset
    statistics = serialize_statistics(dataset)
    LOG.info(
        "upload_complete dataset_id=%s models=%s total_records=%s model_limit=%s payloads=%s skipped=%s errors=%s",
        dataset_id,
        len(dataset.records),
        total_records,
        model_limit,
        parse_summary["payloads"],
        parse_summary["skipped"],
        parse_summary["errors"],
    )
    return {"datasetId": dataset_id, "statistics": statistics, "uploadSummary": parse_summary}


def handle_preprocess_upload(body: dict[str, Any]) -> dict[str, Any]:
    language = str(body.get("language") or "").lower()
    files = body.get("files") or []
    LOG.info("preprocess_start language=%s file_count=%s", language, len(files) if isinstance(files, list) else "invalid")
    if language not in {"uml", "ecore", "archimate"}:
        raise ValueError("language must be one of: uml, ecore, archimate")
    if not isinstance(files, list) or not files:
        raise ValueError("At least one uploaded file is required.")

    dataset, parse_summary = parse_uploaded_dataset(language, files)
    if not dataset.records:
        raise ValueError(
            "Preprocessing parsed 0 models. Check that the selected modeling language matches the file and that the "
            "file contains JSON objects or JSONL lines with model objects."
        )
    total_records = len(dataset.records)
    preprocess_id = uuid.uuid4().hex
    parse_summary["totalRecords"] = total_records
    parse_summary["usedRecords"] = 0
    parse_summary["modelLimit"] = total_records
    PREPROCESSED_UPLOADS[preprocess_id] = {
        "language": language,
        "dataset": dataset,
        "summary": dict(parse_summary),
        "createdAt": time.time(),
    }
    LOG.info(
        "preprocess_complete preprocess_id=%s language=%s total_records=%s payloads=%s skipped=%s errors=%s",
        preprocess_id,
        language,
        total_records,
        parse_summary["payloads"],
        parse_summary["skipped"],
        parse_summary["errors"],
    )
    return {"preprocessId": preprocess_id, "uploadSummary": parse_summary}


def dataset_from_upload_or_preprocess(
    language: str,
    files: Any,
    preprocess_id: Any,
) -> tuple[Dataset, dict[str, int]]:
    preprocess_id = str(preprocess_id or "")
    if preprocess_id:
        cached = PREPROCESSED_UPLOADS.get(preprocess_id)
        if cached is None:
            raise ValueError("Unknown preprocessId. Upload the dataset again.")
        if cached["language"] != language:
            raise ValueError("preprocessId language does not match the selected modeling language.")
        return cached["dataset"], dict(cached["summary"])

    if not isinstance(files, list) or not files:
        raise ValueError("At least one uploaded file or preprocessId is required.")
    return parse_uploaded_dataset(language, files)


def normalized_model_limit(raw_limit: Any, total_records: int) -> int:
    if total_records <= 0:
        return 0
    min_limit = min(10, total_records)
    if raw_limit in (None, ""):
        return total_records
    try:
        requested = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("modelLimit must be an integer.") from exc
    return max(min_limit, min(requested, total_records))


def handle_dummy(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(body)
    language = dataset.records[0].language if dataset.records else str(dataset.dataset_type)
    filters = build_dummy_filters(language, body.get("filterConfigs"))
    custom = body.get("customRegex")
    if custom and custom.get("pattern"):
        filters.insert(
            0,
            regex_name_filter(
                str(custom["pattern"]),
                float(custom.get("threshold", 0.5)),
                include_types=str(custom.get("target", "names")) == "names_types",
            ),
        )
    rows = summarize_filters(dataset, filters=filters)
    return {
        "rows": [
            {
                "filterName": row.filter_name,
                "filteredCount": row.filtered_count,
                "remainingCount": row.remaining_count,
                "examples": [
                    {
                        "modelId": finding.model_id,
                        "reason": finding.reason,
                        "score": finding.score,
                        "evidence": list(finding.evidence),
                    }
                    for finding in row.findings[:10]
                ],
            }
            for row in rows
        ]
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
            raise ValueError("Unknown duplicate detection job.")
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
    selected = set(selected_order)
    mandatory = set(body.get("mandatoryTechniques") or [])
    min_votes = int(body.get("minVotes", 2))
    thresholds = body.get("thresholds") or {}
    if not selected:
        raise_no_duplicate_technique_error(body)

    votes: dict[tuple[str, str], dict[str, float]] = {}
    technique_counts: dict[str, int] = {}
    model_counts: dict[str, dict[str, int]] = {}
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
            len(dataset),
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
                message=f"Running {duplicate_technique_label(technique)} over {len(dataset)} models.",
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

    def report_step_done(technique: str, pair_count: int) -> None:
        completed.append(technique)
        elapsed_ms = round((time.perf_counter() - algorithm_started_at.get(technique, time.perf_counter())) * 1000)
        if technique in model_counts:
            model_counts[technique]["elapsedMs"] = elapsed_ms
        counts = model_counts.get(technique, {})
        LOG.info(
            "duplicate_algorithm_complete technique=%s label=%s pairs=%s duplicate_models=%s unique_models=%s completed=%s/%s elapsed_ms=%s",
            technique,
            duplicate_technique_label(technique),
            pair_count,
            counts.get("duplicateModels", 0),
            counts.get("uniqueModels", len(dataset)),
            len(completed),
            total_steps,
            elapsed_ms,
        )
        if progress:
            progress(
                status="running",
                currentTechnique="",
                completedTechniques=list(completed),
                progress=round((len(completed) / total_steps) * 100) if total_steps else 100,
                techniqueProgress=100,
                message=f"Completed {duplicate_technique_label(technique)}: {pair_count} duplicate pair(s).",
            )

    if "hash_names" in selected:
        report_step_start("hash_names")
        pairs = group_pairs(detect_duplicates_by_node_name_hash(dataset, progress=report_algorithm_progress("hash_names")))
        add_votes(votes, pairs, "hash_names", 1.0)
        add_technique_model_counts(model_counts, technique_counts, dataset, "hash_names", pairs)
        report_step_done("hash_names", len(pairs))
    if "hash_names_types" in selected:
        report_step_start("hash_names_types")
        pairs = group_pairs(detect_duplicates_by_node_name_type_hash(dataset, progress=report_algorithm_progress("hash_names_types")))
        add_votes(votes, pairs, "hash_names_types", 1.0)
        add_technique_model_counts(model_counts, technique_counts, dataset, "hash_names_types", pairs)
        report_step_done("hash_names_types", len(pairs))
    if "tfidf_names" in selected:
        report_step_start("tfidf_names")
        pairs = tfidf_duplicate_by_names(
            dataset,
            threshold=float(thresholds.get("tfidfNames", 0.9)),
            max_features=int(thresholds.get("tfidfMaxFeatures", 50_000)),
            progress=report_algorithm_progress("tfidf_names"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "tfidf_names")
        add_technique_model_counts(model_counts, technique_counts, dataset, "tfidf_names", technique_pairs)
        report_step_done("tfidf_names", len(technique_pairs))
    if "tfidf_names_types" in selected:
        report_step_start("tfidf_names_types")
        pairs = tfidf_duplicate_by_names_and_types(
            dataset,
            threshold=float(thresholds.get("tfidfNamesTypes", 0.9)),
            max_features=int(thresholds.get("tfidfMaxFeatures", 50_000)),
            progress=report_algorithm_progress("tfidf_names_types"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "tfidf_names_types")
        add_technique_model_counts(model_counts, technique_counts, dataset, "tfidf_names_types", technique_pairs)
        report_step_done("tfidf_names_types", len(technique_pairs))
    if "graph_similarity" in selected:
        report_step_start("graph_similarity")
        pairs = graph_similarity_pairs(
            dataset,
            threshold=float(thresholds.get("graphSimilarity", 0.85)),
            weights=graph_similarity_weights(thresholds),
            progress=report_algorithm_progress("graph_similarity"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "graph_similarity")
        add_technique_model_counts(model_counts, technique_counts, dataset, "graph_similarity", technique_pairs)
        report_step_done("graph_similarity", len(technique_pairs))
    if "graph_embedding" in selected:
        report_step_start("graph_embedding")
        pairs = graph_embedding_pairs(
            dataset,
            threshold=float(thresholds.get("graphEmbedding", 0.9)),
            dimensions=int(thresholds.get("graphEmbeddingDimensions", 64)),
            walk_length=int(thresholds.get("graphEmbeddingWalkLength", 10)),
            num_walks=int(thresholds.get("graphEmbeddingNumWalks", 20)),
            workers=int(thresholds.get("graphEmbeddingWorkers", 1)),
            seed=int(thresholds.get("graphEmbeddingSeed", 42)),
            progress=report_algorithm_progress("graph_embedding"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "graph_embedding")
        add_technique_model_counts(model_counts, technique_counts, dataset, "graph_embedding", technique_pairs)
        report_step_done("graph_embedding", len(technique_pairs))
    if "bert_semantic" in selected:
        report_step_start("bert_semantic")
        pairs = bert_semantic_similarity_pairs(
            dataset,
            threshold=float(thresholds.get("bertSemantic", 0.9)),
            model_name=str(thresholds.get("bertModelName", "bert-base-uncased")),
            batch_size=int(thresholds.get("bertBatchSize", 8)),
            max_length=int(thresholds.get("bertMaxLength", 256)),
            progress=report_algorithm_progress("bert_semantic"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "bert_semantic")
        add_technique_model_counts(model_counts, technique_counts, dataset, "bert_semantic", technique_pairs)
        report_step_done("bert_semantic", len(technique_pairs))
    if "graph_isomorphism" in selected:
        report_step_start("graph_isomorphism")
        pairs = graph_isomorphism_pairs(
            dataset,
            mode=str(thresholds.get("isomorphismMode", "names")),
            match_edge_types=bool(thresholds.get("matchEdgeTypes", True)),
            progress=report_algorithm_progress("graph_isomorphism"),
        )
        technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
        add_votes(votes, technique_pairs, "graph_isomorphism")
        add_technique_model_counts(model_counts, technique_counts, dataset, "graph_isomorphism", technique_pairs)
        report_step_done("graph_isomorphism", len(technique_pairs))

    decisions = []
    for (left_id, right_id), scores in sorted(votes.items()):
        present = set(scores)
        required = mandatory or set()
        is_duplicate = required.issubset(present) and len(present) >= min_votes
        decisions.append(
            {
                "leftId": left_id,
                "rightId": right_id,
                "isDuplicate": is_duplicate,
                "voteCount": len(present),
                "techniques": sorted(present),
                "scores": scores,
            }
        )
    decisions.sort(key=lambda item: (item["isDuplicate"], item["voteCount"]), reverse=True)
    voted_duplicate_pairs = sum(1 for decision in decisions if decision["isDuplicate"])
    return {
        "techniqueCounts": technique_counts,
        "modelCounts": model_counts,
        "duplicatePairs": len(decisions),
        "votedDuplicatePairs": voted_duplicate_pairs,
        "decisions": decisions[:500],
        "elapsedMs": round((time.perf_counter() - duplicate_started_at) * 1000),
    }


def build_dummy_filters(language: str, configs: Any) -> list:
    active_configs = configs if isinstance(configs, list) else default_dummy_filter_configs(language)
    filters = []
    for config in active_configs:
        if not isinstance(config, dict) or not config.get("enabled", True):
            continue
        filter_fn = build_dummy_filter(config)
        if filter_fn is not None:
            filters.append(filter_fn)
    return filters


def build_dummy_filter(config: dict[str, Any]):
    filter_id = str(config.get("id") or "")
    threshold = float(config.get("threshold", 0.5))
    if filter_id == "empty_model":
        return empty_model_filter()
    if filter_id == "too_few_names":
        return too_few_named_elements_filter(min_names=int(config.get("minNames", 2)))
    if filter_id == "dummy_words":
        return dummy_word_filter(threshold=threshold)
    if filter_id == "generic_sequential":
        return generic_sequential_names_filter(threshold=threshold)
    if filter_id == "short_names":
        return short_name_ratio_filter(max_length=int(config.get("maxLength", 2)), threshold=threshold)
    if filter_id == "uml_empty_class_name":
        return uml_empty_class_name_filter()
    if filter_id == "uml_empty_name":
        return uml_empty_name_filter()
    if filter_id == "uml_median_name_length":
        return uml_median_name_length_filter(min_median_length=int(config.get("minMedianLength", 4)))
    if filter_id == "uml_short_name_or_control_flow":
        return uml_short_name_or_control_flow_filter(
            max_length=int(config.get("maxLength", 2)),
            high_short_threshold=threshold,
            low_short_threshold=float(config.get("lowThreshold", 0.25)),
            control_flow_threshold=float(config.get("controlFlowThreshold", 0.4)),
        )
    if filter_id == "uml_dummy_class":
        return uml_dummy_class_filter(threshold=threshold)
    if filter_id == "uml_generic_class_name":
        return uml_generic_class_name_filter(threshold_count=int(config.get("thresholdCount", 2)))
    if filter_id == "uml_dummy_name":
        return uml_dummy_name_filter(threshold=threshold)
    if filter_id == "uml_two_character_dummy_name":
        return uml_two_character_dummy_name_filter(threshold=threshold)
    if filter_id == "uml_dummy_keyword":
        return uml_dummy_keyword_filter(threshold=threshold)
    if filter_id == "uml_sequential":
        return uml_sequential_numbered_filter(threshold=threshold)
    if filter_id == "uml_vocabulary":
        return uml_vocabulary_uniqueness_filter(min_unique_words=int(config.get("minUniqueWords", 3)))
    if filter_id == "ecore_type_name":
        return ecore_type_name_filter(threshold=threshold)
    if filter_id == "ecore_numbered":
        return ecore_generic_numbered_filter(threshold=threshold)
    if filter_id == "ecore_dummy_keyword":
        return ecore_dummy_keyword_filter(threshold=threshold)
    if filter_id == "ecore_vocabulary":
        return ecore_vocabulary_uniqueness_filter(min_unique_words=int(config.get("minUniqueWords", 3)))
    if filter_id == "archimate_new_model":
        return archimate_new_model_filter()
    if filter_id == "archimate_type_name":
        return archimate_type_name_filter(threshold=threshold)
    if filter_id == "archimate_numbered":
        return archimate_generic_numbered_filter(threshold=threshold)
    if filter_id == "archimate_dummy_keyword":
        return archimate_dummy_keyword_filter(threshold=threshold)
    if filter_id == "archimate_crud_code":
        return archimate_crud_or_code_filter(threshold=threshold)
    if filter_id == "archimate_vocabulary":
        return archimate_vocabulary_uniqueness_filter(min_unique_words=int(config.get("minUniqueWords", 3)))
    return None


def parse_uploaded_dataset(language: str, files: list[dict[str, Any] | FileStorage]) -> tuple[Dataset, dict[str, int]]:
    parser = {"uml": UMLParser(), "ecore": EcoreParser(), "archimate": ArchimateParser()}[language]
    records = []
    summary = {"files": 0, "payloads": 0, "records": 0, "skipped": 0, "errors": 0}
    for file_item in files:
        name, payloads = uploaded_payloads(file_item)
        summary["files"] += 1
        LOG.info("parse_file_start language=%s filename=%s", language, name)
        file_records_before = len(records)
        for source_index, payload in payloads:
            summary["payloads"] += 1
            for payload_index, model_payload in enumerate_model_payloads(payload):
                if not isinstance(model_payload, dict):
                    summary["skipped"] += 1
                    LOG.warning(
                        "parse_skip filename=%s source_index=%s payload_index=%s type=%s",
                        name,
                        source_index,
                        payload_index,
                        type(model_payload).__name__,
                    )
                    continue
                try:
                    record = parser.parse(
                        model_payload,
                        model_id=model_payload.get("ids")
                        or model_payload.get("id")
                        or model_payload.get("archimateId")
                        or f"{name}:{source_index}:{payload_index}",
                    )
                except Exception:
                    summary["errors"] += 1
                    LOG.exception("parse_error filename=%s source_index=%s payload_index=%s", name, source_index, payload_index)
                    continue
                record.source_path = Path(name)
                records.append(record)
                summary["records"] += 1
        LOG.info("parse_file_end language=%s filename=%s records=%s", language, name, len(records) - file_records_before)
    return Dataset(records=records, dataset_type=language), summary


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


def uploaded_payloads(file_item: dict[str, Any] | FileStorage) -> tuple[str, Iterable[tuple[int, Any]]]:
    if isinstance(file_item, FileStorage):
        name = file_item.filename or "upload.json"
        return name, parse_file_storage_payloads(file_item)

    name = str(file_item.get("name") or "upload.json")
    content = str(file_item.get("content") or "")
    return name, enumerate(parse_json_payloads(content))


def parse_file_storage_payloads(file_item: FileStorage) -> Iterable[tuple[int, Any]]:
    filename = (file_item.filename or "").lower()
    if filename.endswith((".jsonl", ".ndjson")):
        yield from parse_jsonl_stream(file_item)
        return

    stream = file_item.stream
    stream.seek(0)
    try:
        payload = json.load(TextIOWrapper(stream, encoding="utf-8"))
    except json.JSONDecodeError:
        stream.seek(0)
        yield from parse_jsonl_stream(file_item)
        return

    items = payload if isinstance(payload, list) else [payload]
    for index, item in enumerate(items):
        yield index, item


def parse_jsonl_stream(file_item: FileStorage) -> Iterable[tuple[int, Any]]:
    file_item.stream.seek(0)
    text_stream = TextIOWrapper(file_item.stream, encoding="utf-8")
    parsed_index = 0
    for line in text_stream:
        line = line.strip()
        if line:
            yield parsed_index, json.loads(line)
            parsed_index += 1


def serialize_statistics(dataset: Dataset) -> dict[str, Any]:
    return {
        "summary": dataset_summary(dataset),
        "topTypes": top_items(type_counts(dataset), 15),
        "topNames": top_items(name_counts(dataset), 15),
        "topWords": top_items(word_counts(dataset), 15),
        "sampleModels": [
            {
                "id": record.model_id,
                "language": record.language,
                "nodes": record.node_count,
                "edges": record.edge_count,
                "names": len(record.names),
            }
            for record in dataset.records[:8]
        ],
    }


def top_items(counter, limit: int) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def get_dataset(body: dict[str, Any]) -> Dataset:
    dataset_id = str(body.get("datasetId") or "")
    try:
        return DATASETS[dataset_id]
    except KeyError as exc:
        raise ValueError("Unknown datasetId. Upload a dataset first.") from exc


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
    return {
        "node_name_jaccard": float(weights.get("nodeNameJaccard", 0.25)),
        "node_type_jaccard": float(weights.get("nodeTypeJaccard", 0.20)),
        "edge_type_jaccard": float(weights.get("edgeTypeJaccard", 0.15)),
        "degree_histogram_similarity": float(weights.get("degreeHistogram", 0.15)),
        "size_similarity": float(weights.get("sizeSimilarity", 0.15)),
        "density_similarity": float(weights.get("densitySimilarity", 0.10)),
    }


DUPLICATE_TECHNIQUE_ORDER = (
    "hash_names",
    "hash_names_types",
    "tfidf_names",
    "tfidf_names_types",
    "graph_similarity",
    "graph_embedding",
    "bert_semantic",
    "graph_isomorphism",
)

DUPLICATE_TECHNIQUE_LABELS = {
    "hash_names": "Hash: Names",
    "hash_names_types": "Hash: Names + Types",
    "tfidf_names": "TF-IDF: Names",
    "tfidf_names_types": "TF-IDF: Names + Types",
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
    "hash_names": "hash_names",
    "hash_name": "hash_names",
    "hash_names_types": "hash_names_types",
    "hash_names_and_types": "hash_names_types",
    "tfidf_names": "tfidf_names",
    "tf_idf_names": "tfidf_names",
    "tfidf_names_types": "tfidf_names_types",
    "tfidf_names_and_types": "tfidf_names_types",
    "tf_idf_names_types": "tfidf_names_types",
    "tf_idf_names_and_types": "tfidf_names_types",
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
