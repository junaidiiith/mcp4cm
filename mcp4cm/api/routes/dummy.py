from __future__ import annotations

import uuid
from typing import Any

from flask import Flask, jsonify

from mcp4cm.api.http import read_json_body
from mcp4cm.api.jobs.dummy_job import (
    dummy_response_payload,
    get_dummy_job,
    start_after_dummy_statistics_job,
    start_dummy_job,
)
from mcp4cm.api.services.datasets import get_dataset
from mcp4cm.core import Dataset
from mcp4cm.dummy import evaluate_dummy_filters


def handle_dummy(body: dict[str, Any]) -> dict[str, Any]:
    dataset_id = str(body.get("datasetId") or "")
    configs = body.get("filterConfigs")
    dataset = get_dataset(body)
    records = list(dataset)
    evaluation_dataset = Dataset(records, getattr(dataset, "dataset_type", "runtime"), getattr(dataset, "root", None))
    evaluation = evaluate_dummy_filters(evaluation_dataset, filter_configs=configs if isinstance(configs, list) else None)
    retained_model_ids = {outcome.model_id for outcome in evaluation.model_outcomes if not outcome.removed}
    statistics_job_id = uuid.uuid4().hex
    if dataset_id:
        start_after_dummy_statistics_job(
            dataset_id=dataset_id,
            job_id=statistics_job_id,
            records=records,
            retained_model_ids=retained_model_ids,
        )
    return dummy_response_payload(evaluation, statistics_job_id if dataset_id else "")


def register_routes(app: Flask) -> None:
    @app.route("/api/dummy", methods=["POST"])
    def dummy_filters():
        return jsonify(handle_dummy(read_json_body()))

    @app.route("/api/dummy/jobs", methods=["POST"])
    def start_dummy_job_route():
        return jsonify(start_dummy_job(read_json_body()))

    @app.route("/api/dummy/jobs/<job_id>", methods=["GET"])
    def get_dummy_job_route(job_id: str):
        return jsonify(get_dummy_job(job_id))
