from __future__ import annotations

from flask import Flask, jsonify, request

from mcp4cm.api.http import read_json_body
from mcp4cm.api.jobs.duplicate_job import (
    get_duplicate_group_detail,
    get_duplicate_groups_page,
    get_duplicate_job,
    get_duplicate_pairs_page,
    start_duplicate_job,
)


def register_routes(app: Flask) -> None:
    @app.route("/api/duplicates/jobs", methods=["POST"])
    def start_duplicates_job():
        return jsonify(start_duplicate_job(read_json_body()))

    @app.route("/api/duplicates/jobs/<job_id>", methods=["GET"])
    def get_duplicates_job(job_id: str):
        return jsonify(get_duplicate_job(job_id))

    @app.route("/api/duplicates/jobs/<job_id>/groups", methods=["GET"])
    def get_duplicate_groups_route(job_id: str):
        return jsonify(get_duplicate_groups_page(job_id, request.args))

    @app.route("/api/duplicates/jobs/<job_id>/groups/<group_id>", methods=["GET"])
    def get_duplicate_group_route(job_id: str, group_id: str):
        return jsonify(get_duplicate_group_detail(job_id, group_id))

    @app.route("/api/duplicates/jobs/<job_id>/pairs", methods=["GET"])
    def get_duplicate_pairs_route(job_id: str):
        return jsonify(get_duplicate_pairs_page(job_id, request.args))
