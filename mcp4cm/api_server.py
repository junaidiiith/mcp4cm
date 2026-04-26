from __future__ import annotations

import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mcp4cm.core import Dataset, DatasetType
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
    UML_EMPTY_CLASS_NAME_PATTERN,
    UML_EMPTY_NAME_PATTERN,
    UML_MIN_NAMES_COUNT,
    UML_SEQUENTIAL_THRESHOLD,
    UML_SHORT_NAMES_UPPER_THRESHOLD,
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
    raw_text_pattern_filter,
    regex_name_filter,
    short_name_ratio_filter,
    summarize_filters,
    too_few_named_elements_filter,
    uml_dummy_class_filter,
    uml_dummy_keyword_filter,
    uml_dummy_name_filter,
    uml_sequential_numbered_filter,
    uml_short_name_filter,
    uml_vocabulary_uniqueness_filter,
)
from mcp4cm.duplicates import (
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_by_names,
    tfidf_duplicate_by_names_and_types,
)
from mcp4cm.parsers.archimate import ArchimateParser
from mcp4cm.parsers.modelset import EcoreParser, UMLParser
from mcp4cm.statistics import dataset_summary, name_counts, type_counts, word_counts

DATASETS: dict[str, Dataset] = {}


def default_dummy_filter_configs(language: str) -> list[dict[str, Any]]:
    language = language.lower()
    if language == "uml":
        return [
            {"id": "empty_model", "enabled": True},
            {"id": "uml_empty_class_name", "enabled": True, "pattern": UML_EMPTY_CLASS_NAME_PATTERN.pattern},
            {"id": "uml_empty_name", "enabled": True, "pattern": UML_EMPTY_NAME_PATTERN.pattern},
            {"id": "too_few_names", "enabled": True, "minNames": UML_MIN_NAMES_COUNT},
            {"id": "uml_dummy_class", "enabled": True, "threshold": UML_DUMMY_CLASSES_THRESHOLD},
            {"id": "uml_dummy_name", "enabled": True, "threshold": UML_DUMMY_NAMES_THRESHOLD},
            {"id": "uml_dummy_keyword", "enabled": True, "threshold": UML_DUMMY_WORD_THRESHOLD},
            {"id": "uml_sequential", "enabled": True, "threshold": UML_SEQUENTIAL_THRESHOLD},
            {"id": "uml_short_name", "enabled": True, "threshold": UML_SHORT_NAMES_UPPER_THRESHOLD},
            {"id": "uml_vocabulary", "enabled": True, "minUniqueWords": UML_VOCABULARY_UNIQUENESS_THRESHOLD},
            {"id": "generic_sequential", "enabled": True, "threshold": UML_SEQUENTIAL_THRESHOLD},
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


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), MCP4CMRequestHandler)
    print(f"MCP4CM API listening on http://{host}:{port}")
    server.serve_forever()


class MCP4CMRequestHandler(BaseHTTPRequestHandler):
    server_version = "MCP4CMAPI/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json({"ok": True})
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        try:
            body = self._read_json()
            if self.path == "/api/datasets":
                self._send_json(handle_upload(body))
            elif self.path == "/api/dummy":
                self._send_json(handle_dummy(body))
            elif self.path == "/api/duplicates":
                self._send_json(handle_duplicates(body))
            else:
                self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        if not payload:
            return {}
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object request body.")
        return data

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(encoded)


def handle_upload(body: dict[str, Any]) -> dict[str, Any]:
    language = str(body.get("language") or "").lower()
    files = body.get("files") or []
    if language not in {"uml", "ecore", "archimate"}:
        raise ValueError("language must be one of: uml, ecore, archimate")
    if not isinstance(files, list) or not files:
        raise ValueError("At least one uploaded file is required.")

    dataset = parse_uploaded_dataset(language, files)
    dataset_id = uuid.uuid4().hex
    DATASETS[dataset_id] = dataset
    return {"datasetId": dataset_id, "statistics": serialize_statistics(dataset)}


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


def handle_duplicates(body: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(body)
    selected = set(body.get("techniques") or [])
    mandatory = set(body.get("mandatoryTechniques") or [])
    min_votes = int(body.get("minVotes", 2))
    thresholds = body.get("thresholds") or {}
    if not selected:
        raise ValueError("Select at least one duplicate technique.")

    votes: dict[tuple[str, str], dict[str, float]] = {}
    technique_counts: dict[str, int] = {}

    if "hash_names" in selected:
        pairs = group_pairs(detect_duplicates_by_node_name_hash(dataset))
        add_votes(votes, pairs, "hash_names", 1.0)
        technique_counts["hash_names"] = len(pairs)
    if "hash_names_types" in selected:
        pairs = group_pairs(detect_duplicates_by_node_name_type_hash(dataset))
        add_votes(votes, pairs, "hash_names_types", 1.0)
        technique_counts["hash_names_types"] = len(pairs)
    if "tfidf_names" in selected:
        pairs = tfidf_duplicate_by_names(dataset, threshold=float(thresholds.get("tfidfNames", 0.9)))
        add_votes(votes, [(pair.left_id, pair.right_id, pair.score) for pair in pairs], "tfidf_names")
        technique_counts["tfidf_names"] = len(pairs)
    if "tfidf_names_types" in selected:
        pairs = tfidf_duplicate_by_names_and_types(dataset, threshold=float(thresholds.get("tfidfNamesTypes", 0.9)))
        add_votes(votes, [(pair.left_id, pair.right_id, pair.score) for pair in pairs], "tfidf_names_types")
        technique_counts["tfidf_names_types"] = len(pairs)
    if "graph_similarity" in selected:
        pairs = graph_similarity_pairs(dataset, threshold=float(thresholds.get("graphSimilarity", 0.85)))
        add_votes(votes, [(pair.left_id, pair.right_id, pair.score) for pair in pairs], "graph_similarity")
        technique_counts["graph_similarity"] = len(pairs)
    if "graph_isomorphism" in selected:
        pairs = graph_isomorphism_pairs(
            dataset,
            mode=str(thresholds.get("isomorphismMode", "types")),
            match_edge_types=bool(thresholds.get("matchEdgeTypes", True)),
        )
        add_votes(votes, [(pair.left_id, pair.right_id, pair.score) for pair in pairs], "graph_isomorphism")
        technique_counts["graph_isomorphism"] = len(pairs)

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
    return {
        "techniqueCounts": technique_counts,
        "duplicatePairs": sum(1 for decision in decisions if decision["isDuplicate"]),
        "decisions": decisions[:500],
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
        pattern = re.compile(str(config.get("pattern") or UML_EMPTY_CLASS_NAME_PATTERN.pattern), re.IGNORECASE)
        return raw_text_pattern_filter(pattern, "uml_empty_class_name")
    if filter_id == "uml_empty_name":
        pattern = re.compile(str(config.get("pattern") or UML_EMPTY_NAME_PATTERN.pattern), re.IGNORECASE)
        return raw_text_pattern_filter(pattern, "uml_empty_name")
    if filter_id == "uml_dummy_class":
        return uml_dummy_class_filter(threshold=threshold)
    if filter_id == "uml_dummy_name":
        return uml_dummy_name_filter(threshold=threshold)
    if filter_id == "uml_dummy_keyword":
        return uml_dummy_keyword_filter(threshold=threshold)
    if filter_id == "uml_sequential":
        return uml_sequential_numbered_filter(threshold=threshold)
    if filter_id == "uml_short_name":
        return uml_short_name_filter(threshold=threshold)
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


def parse_uploaded_dataset(language: str, files: list[dict[str, Any]]) -> Dataset:
    parser = {"uml": UMLParser(), "ecore": EcoreParser(), "archimate": ArchimateParser()}[language]
    records = []
    for file_item in files:
        name = str(file_item.get("name") or "upload.json")
        content = str(file_item.get("content") or "")
        payloads = parse_json_payloads(content)
        for index, payload in enumerate(payloads):
            if not isinstance(payload, dict):
                continue
            record = parser.parse(payload, model_id=payload.get("ids") or payload.get("archimateId") or f"{name}:{index}")
            record.source_path = Path(name)
            records.append(record)
    return Dataset(records=records, dataset_type=language)


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


def group_pairs(groups) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    for group in groups:
        ids = list(group.model_ids)
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1 :]:
                pairs.append((left_id, right_id, 1.0))
    return pairs


if __name__ == "__main__":
    run()
