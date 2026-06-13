from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from mcp4cm.api.process_utils import kill_processes_on_port
from mcp4cm.api.routes import datasets, duplicates, dummy, uploads
from mcp4cm.api.state import LOG, WEBAPP_DIST


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


def create_app(webapp_dist: Path | str = WEBAPP_DIST) -> Flask:
    configure_logging()
    app = Flask(__name__)
    dist_path = Path(webapp_dist)

    @app.before_request
    def log_request_start():
        g.request_started_at = time.perf_counter()
        LOG.info("request_start method=%s path=%s content_length=%s", request.method, request.path, request.content_length)
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return "", 204

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

    datasets.register_routes(app)
    uploads.register_routes(app)
    dummy.register_routes(app)
    duplicates.register_routes(app)

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


def run(host: str = "127.0.0.1", port: int = 8765, debug: bool = False, kill_port_process: bool = False) -> None:
    if kill_port_process:
        kill_processes_on_port(port)
    create_app().run(host=host, port=port, debug=debug)


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
