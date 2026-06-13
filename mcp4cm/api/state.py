from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from mcp4cm.core import Dataset
from mcp4cm.parsers.catalog import parser_descriptors
from mcp4cm.runtime_store import RuntimeDataset

DATASETS: dict[str, Dataset | RuntimeDataset] = {}
DUPLICATE_JOBS: dict[str, dict[str, Any]] = {}
DUMMY_JOBS: dict[str, dict[str, Any]] = {}
UPLOAD_SESSIONS: dict[str, dict[str, Any]] = {}
UPLOAD_PARSE_JOBS: dict[str, dict[str, Any]] = {}
AFTER_DUMMY_STATISTICS_JOBS: dict[str, dict[str, Any]] = {}
DUPLICATE_JOBS_LOCK = threading.Lock()
DUMMY_JOBS_LOCK = threading.Lock()
UPLOAD_LOCK = threading.Lock()
AFTER_DUMMY_STATISTICS_LOCK = threading.Lock()
WEBAPP_DIST = Path(__file__).resolve().parents[2] / "webapp" / "dist"
LOG = logging.getLogger("mcp4cm.api")
SUPPORTED_LANGUAGES = {descriptor.language for descriptor in parser_descriptors()}
SUPPORTED_FORMATS = {descriptor.format for descriptor in parser_descriptors()}
