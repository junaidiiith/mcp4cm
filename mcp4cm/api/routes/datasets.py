from __future__ import annotations

from flask import Flask, jsonify, request

from mcp4cm.api.http import parse_positive_int_param
from mcp4cm.api.services.datasets import (
    get_dataset_after_dummy_statistics_response,
    get_dataset_statistics,
    get_dataset_status,
    get_label_pipeline_page,
    inspect_dataset_model,
)
from mcp4cm.runtime_store import list_dataset_models
from mcp4cm.utils import parse_bool


def register_routes(app: Flask) -> None:
    @app.route("/api/datasets/<dataset_id>/models", methods=["GET"])
    def list_models_route(dataset_id: str):
        page = parse_positive_int_param(request.args.get("page", 1), "page") or 1
        page_size = parse_positive_int_param(request.args.get("pageSize", 50), "pageSize") or 50
        return jsonify(
            list_dataset_models(
                dataset_id,
                page=page,
                page_size=page_size,
                query=str(request.args.get("query") or ""),
                sort=str(request.args.get("sort") or "modelId"),
                order=str(request.args.get("order") or "asc"),
                warning_type=str(request.args.get("warningType") or ""),
            )
        )

    @app.route("/api/datasets/<dataset_id>/status", methods=["GET"])
    def dataset_status_route(dataset_id: str):
        return jsonify(get_dataset_status(dataset_id))

    @app.route("/api/datasets/<dataset_id>/statistics", methods=["GET"])
    def dataset_statistics_route(dataset_id: str):
        return jsonify(get_dataset_statistics(dataset_id))

    @app.route("/api/datasets/<dataset_id>/statistics/after-dummy", methods=["GET"])
    def dataset_after_dummy_statistics_route(dataset_id: str):
        return jsonify(get_dataset_after_dummy_statistics_response(dataset_id))

    @app.route("/api/datasets/<dataset_id>/visualizations/label-pipeline", methods=["GET"])
    def dataset_label_pipeline_route(dataset_id: str):
        page = parse_positive_int_param(request.args.get("page", 1), "page") or 1
        page_size = parse_positive_int_param(request.args.get("pageSize", 50), "pageSize") or 50
        return jsonify(
            get_label_pipeline_page(
                dataset_id,
                snapshot=str(request.args.get("snapshot") or "before"),
                page=page,
                page_size=page_size,
                query=str(request.args.get("query") or ""),
                classification=str(request.args.get("classification") or "all"),
                sort=str(request.args.get("sort") or "documentFrequency"),
                order=str(request.args.get("order") or "desc"),
            )
        )

    @app.route("/api/datasets/<dataset_id>/models/<model_id>/inspect", methods=["GET"])
    def inspect_model_route(dataset_id: str, model_id: str):
        include_attrs = parse_bool(request.args.get("includeAttrs"), default=True)
        return jsonify(
            inspect_dataset_model(
                dataset_id=dataset_id,
                model_id=model_id,
                include_attrs=include_attrs,
            )
        )
