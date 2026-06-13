from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.name_classification import iter_name_slots

DEFAULT_MIN_NODES = 5
DEFAULT_MIN_EDGES = 4
DEFAULT_MIN_NAMES = 5
DEFAULT_MIN_MEDIAN_LENGTH = 4
DEFAULT_PLACEHOLDER_THRESHOLD = 0.30
DEFAULT_MIN_UNIQUE_WORDS = 3
DEFAULT_NAME_REPETITION_THRESHOLD = 0.50
DEFAULT_REGEX_MIN_MATCHES = 1

FILTER_ORDER: tuple[str, ...] = (
    "min_size",
    "too_few_named_elements",
    "short_median_name_length",
    "placeholder_name_ratio",
    "low_vocabulary",
    "name_repetition_ratio",
    "regex_rule",
)


@dataclass(frozen=True, slots=True)
class DerivedNode:
    node_id: str
    raw_name: str
    node_type: str
    normalized_name: str
    normalized_type: str
    classification: str
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DummyFinding:
    model_id: str
    filter_id: str
    reason: str
    score: float
    threshold: float
    decision: str
    evidence: tuple[str, ...] = ()
    evidence_nodes: tuple[str, ...] = ()
    metrics: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    model_id: str
    removed: bool
    primary_removal_reason: str | None
    all_triggered_filters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FilterSummary:
    filter_id: str
    filtered_count: int
    remaining_count: int
    triggered_model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunSummary:
    total_models: int
    removed_models: int
    remaining_models: int
    removal_rate: float


@dataclass(frozen=True, slots=True)
class DummyEvaluationResult:
    run_summary: RunSummary
    filter_summaries: tuple[FilterSummary, ...]
    model_outcomes: tuple[ModelOutcome, ...]
    findings: tuple[DummyFinding, ...]


def default_filter_configs() -> list[dict[str, Any]]:
    return [
        {"id": "min_size", "enabled": True, "minNodes": DEFAULT_MIN_NODES, "minEdges": DEFAULT_MIN_EDGES},
        {"id": "too_few_named_elements", "enabled": True, "minNames": DEFAULT_MIN_NAMES},
        {
            "id": "short_median_name_length",
            "enabled": True,
            "minMedianLength": DEFAULT_MIN_MEDIAN_LENGTH,
        },
        {
            "id": "placeholder_name_ratio",
            "enabled": True,
            "threshold": DEFAULT_PLACEHOLDER_THRESHOLD,
        },
        {"id": "low_vocabulary", "enabled": True, "minUniqueWords": DEFAULT_MIN_UNIQUE_WORDS},
        {
            "id": "name_repetition_ratio",
            "enabled": True,
            "threshold": DEFAULT_NAME_REPETITION_THRESHOLD,
        },
        {
            "id": "regex_rule",
            "enabled": False,
            "pattern": "",
            "targetField": "name",
            "scope": "eligible_only",
            "minMatches": DEFAULT_REGEX_MIN_MATCHES,
        },
    ]


def detect_dummy_models(dataset: Dataset, filter_configs: list[dict[str, Any]] | None = None) -> list[DummyFinding]:
    result = evaluate_dummy_filters(dataset, filter_configs=filter_configs)
    findings_by_model: dict[str, list[DummyFinding]] = {}
    for finding in result.findings:
        findings_by_model.setdefault(finding.model_id, []).append(finding)
    primary: list[DummyFinding] = []
    for outcome in result.model_outcomes:
        if not outcome.primary_removal_reason:
            continue
        matching = [
            finding
            for finding in findings_by_model.get(outcome.model_id, [])
            if finding.filter_id == outcome.primary_removal_reason and finding.decision == "removed"
        ]
        if matching:
            primary.append(matching[0])
    return primary


def summarize_filters(
    dataset: Dataset,
    filter_configs: list[dict[str, Any]] | None = None,
    cumulative: bool = True,
) -> list[FilterSummary]:
    result = evaluate_dummy_filters(dataset, filter_configs=filter_configs, cumulative=cumulative)
    return list(result.filter_summaries)


def summarize_filters_by_language(dataset: Dataset, cumulative: bool = True) -> dict[str, list[FilterSummary]]:
    groups: dict[str, list[ModelRecord]] = {}
    for record in dataset:
        groups.setdefault(record.language.lower(), []).append(record)
    result: dict[str, list[FilterSummary]] = {}
    for language, records in sorted(groups.items()):
        eval_result = evaluate_dummy_filters(
            Dataset(records=records, dataset_type=dataset.dataset_type, root=dataset.root),
            filter_configs=default_filter_configs(),
            cumulative=cumulative,
        )
        result[language] = list(eval_result.filter_summaries)
    return result


def evaluate_dummy_filters(
    dataset: Dataset,
    filter_configs: list[dict[str, Any]] | None = None,
    cumulative: bool = True,
) -> DummyEvaluationResult:
    configs = normalized_filter_configs(filter_configs)
    records = list(dataset)
    all_findings: list[DummyFinding] = []
    outcomes: list[ModelOutcome] = []

    findings_by_filter: dict[str, dict[str, DummyFinding]] = {config["id"]: {} for config in configs}

    for record in records:
        model_findings: list[DummyFinding] = []
        derived_nodes = derive_nodes(record)
        for config in configs:
            finding = evaluate_filter(record, derived_nodes, config)
            model_findings.append(finding)
            findings_by_filter[config["id"]][record.model_id] = finding
        triggered = tuple(f.filter_id for f in model_findings if f.decision == "removed")
        outcomes.append(
            ModelOutcome(
                model_id=record.model_id,
                removed=bool(triggered),
                primary_removal_reason=triggered[0] if triggered else None,
                all_triggered_filters=triggered,
            )
        )
        all_findings.extend(model_findings)

    filter_summaries = summarize_findings(records, configs, findings_by_filter, cumulative=cumulative)
    removed_models = sum(1 for outcome in outcomes if outcome.removed)
    total_models = len(records)
    run_summary = RunSummary(
        total_models=total_models,
        removed_models=removed_models,
        remaining_models=total_models - removed_models,
        removal_rate=(removed_models / total_models) if total_models else 0.0,
    )
    return DummyEvaluationResult(
        run_summary=run_summary,
        filter_summaries=tuple(filter_summaries),
        model_outcomes=tuple(outcomes),
        findings=tuple(all_findings),
    )


def normalized_filter_configs(filter_configs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    base = default_filter_configs()
    by_id = {entry["id"]: dict(entry) for entry in base}
    if isinstance(filter_configs, list):
        for config in filter_configs:
            if not isinstance(config, dict):
                continue
            filter_id = str(config.get("id") or "").strip()
            if filter_id not in by_id:
                continue
            merged = {**by_id[filter_id], **config}
            merged["id"] = filter_id
            by_id[filter_id] = merged
    ordered: list[dict[str, Any]] = []
    for filter_id in FILTER_ORDER:
        config = by_id.get(filter_id)
        if config and config.get("enabled", True):
            ordered.append(config)
    return ordered


def summarize_findings(
    records: list[ModelRecord],
    configs: list[dict[str, Any]],
    findings_by_filter: dict[str, dict[str, DummyFinding]],
    cumulative: bool,
) -> list[FilterSummary]:
    remaining = {record.model_id for record in records}
    summaries: list[FilterSummary] = []
    for config in configs:
        filter_id = str(config["id"])
        per_model = findings_by_filter.get(filter_id, {})
        if cumulative:
            triggered_ids = tuple(
                model_id
                for model_id in sorted(remaining)
                if per_model.get(model_id) and per_model[model_id].decision == "removed"
            )
            remaining -= set(triggered_ids)
            remaining_count = len(remaining)
        else:
            triggered_ids = tuple(
                model_id for model_id in sorted(per_model) if per_model[model_id].decision == "removed"
            )
            remaining_count = len(records) - len(triggered_ids)
        summaries.append(
            FilterSummary(
                filter_id=filter_id,
                filtered_count=len(triggered_ids),
                remaining_count=remaining_count,
                triggered_model_ids=triggered_ids,
            )
        )
    return summaries


def evaluate_filter(record: ModelRecord, derived_nodes: list[DerivedNode], config: dict[str, Any]) -> DummyFinding:
    filter_id = str(config.get("id") or "")
    if filter_id == "min_size":
        return _eval_min_size(record, filter_id, config)
    if filter_id == "too_few_named_elements":
        return _eval_too_few_named_elements(record, derived_nodes, filter_id, config)
    if filter_id == "short_median_name_length":
        return _eval_short_median_name_length(record, derived_nodes, filter_id, config)
    if filter_id == "placeholder_name_ratio":
        return _eval_placeholder_name_ratio(record, derived_nodes, filter_id, config)
    if filter_id == "low_vocabulary":
        return _eval_low_vocabulary(record, derived_nodes, filter_id, config)
    if filter_id == "name_repetition_ratio":
        return _eval_name_repetition(record, derived_nodes, filter_id, config)
    if filter_id == "regex_rule":
        return _eval_regex_rule(record, derived_nodes, filter_id, config)
    return _kept_finding(record.model_id, filter_id, "unknown_filter", 0.0, 1.0)


def _eval_min_size(record: ModelRecord, filter_id: str, config: dict[str, Any]) -> DummyFinding:
    min_nodes = int(config.get("minNodes", DEFAULT_MIN_NODES))
    min_edges = int(config.get("minEdges", DEFAULT_MIN_EDGES))
    node_count = record.node_count
    edge_count = record.edge_count
    too_small = node_count < min_nodes or edge_count < min_edges
    if too_small:
        return _removed_finding(
            record.model_id,
            filter_id,
            "graph_below_min_size",
            score=min(node_count / max(1, min_nodes), edge_count / max(1, min_edges)),
            threshold=1.0,
            metrics={
                "nodeCount": node_count,
                "edgeCount": edge_count,
                "minNodes": min_nodes,
                "minEdges": min_edges,
            },
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "graph_meets_min_size",
        score=1.0,
        threshold=1.0,
        metrics={"nodeCount": node_count, "edgeCount": edge_count, "minNodes": min_nodes, "minEdges": min_edges},
    )


def _eval_too_few_named_elements(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    min_names = int(config.get("minNames", DEFAULT_MIN_NAMES))
    eligible = semantic_nodes(derived_nodes)
    count = len(eligible)
    if count < min_names:
        return _removed_finding(
            record.model_id,
            filter_id,
            "too_few_semantic_names",
            score=float(count),
            threshold=float(min_names),
            evidence=tuple(node.normalized_name for node in eligible[:10]),
            evidence_nodes=tuple(node.node_id for node in eligible[:10]),
            metrics={"eligibleNameCount": count, "minNames": min_names},
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "enough_semantic_names",
        score=float(count),
        threshold=float(min_names),
        metrics={"eligibleNameCount": count, "minNames": min_names},
    )


def _eval_short_median_name_length(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    min_median = int(config.get("minMedianLength", DEFAULT_MIN_MEDIAN_LENGTH))
    eligible = semantic_nodes(derived_nodes)
    lengths = sorted(len(node.normalized_name) for node in eligible)
    if not lengths:
        return _removed_finding(
            record.model_id,
            filter_id,
            "no_eligible_names_for_median",
            score=0.0,
            threshold=float(min_median),
            metrics={"eligibleNameCount": 0, "minMedianLength": min_median},
        )
    median = _median(lengths)
    if median < min_median:
        return _removed_finding(
            record.model_id,
            filter_id,
            "median_name_length_below_minimum",
            score=float(median),
            threshold=float(min_median),
            evidence=tuple(node.normalized_name for node in eligible[:10]),
            evidence_nodes=tuple(node.node_id for node in eligible[:10]),
            metrics={"medianNameLength": median, "minMedianLength": min_median, "eligibleNameCount": len(eligible)},
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "median_name_length_ok",
        score=float(median),
        threshold=float(min_median),
        metrics={"medianNameLength": median, "minMedianLength": min_median, "eligibleNameCount": len(eligible)},
    )


def _eval_placeholder_name_ratio(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    threshold = float(config.get("threshold", DEFAULT_PLACEHOLDER_THRESHOLD))
    named = named_nodes(derived_nodes)
    placeholders = [node for node in named if node.classification == "placeholder"]
    ratio = len(placeholders) / len(named) if named else 0.0
    if named and ratio >= threshold:
        return _removed_finding(
            record.model_id,
            filter_id,
            "placeholder_ratio_above_threshold",
            score=ratio,
            threshold=threshold,
            evidence=tuple(node.normalized_name for node in placeholders[:10]),
            evidence_nodes=tuple(node.node_id for node in placeholders[:10]),
            metrics={"placeholderHits": len(placeholders), "namedNodes": len(named), "ratio": ratio},
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "placeholder_ratio_ok",
        score=ratio,
        threshold=threshold,
        metrics={"placeholderHits": len(placeholders), "namedNodes": len(named), "ratio": ratio},
    )


def _eval_low_vocabulary(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    min_unique_words = int(config.get("minUniqueWords", DEFAULT_MIN_UNIQUE_WORDS))
    eligible = semantic_nodes(derived_nodes)
    tokens = sorted({token for node in eligible for token in node.tokens})
    token_count = len(tokens)
    if token_count < min_unique_words:
        return _removed_finding(
            record.model_id,
            filter_id,
            "vocabulary_below_minimum",
            score=float(token_count),
            threshold=float(min_unique_words),
            evidence=tuple(tokens[:10]),
            metrics={"uniqueTokenCount": token_count, "minUniqueWords": min_unique_words},
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "vocabulary_ok",
        score=float(token_count),
        threshold=float(min_unique_words),
        metrics={"uniqueTokenCount": token_count, "minUniqueWords": min_unique_words},
    )


def _eval_name_repetition(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    threshold = float(config.get("threshold", DEFAULT_NAME_REPETITION_THRESHOLD))
    named = [node.normalized_name for node in named_nodes(derived_nodes)]
    if not named:
        return _kept_finding(
            record.model_id,
            filter_id,
            "no_named_nodes",
            score=0.0,
            threshold=threshold,
            metrics={"namedNodes": 0, "ratio": 0.0},
        )
    counts = Counter(named)
    most_name, most_count = counts.most_common(1)[0]
    ratio = most_count / len(named)
    if ratio >= threshold:
        return _removed_finding(
            record.model_id,
            filter_id,
            "name_repetition_above_threshold",
            score=ratio,
            threshold=threshold,
            evidence=(most_name,),
            metrics={
                "mostFrequentName": most_name,
                "mostFrequentCount": most_count,
                "namedNodes": len(named),
                "ratio": ratio,
            },
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "name_repetition_ok",
        score=ratio,
        threshold=threshold,
        metrics={
            "mostFrequentName": most_name,
            "mostFrequentCount": most_count,
            "namedNodes": len(named),
            "ratio": ratio,
        },
    )


def _eval_regex_rule(
    record: ModelRecord,
    derived_nodes: list[DerivedNode],
    filter_id: str,
    config: dict[str, Any],
) -> DummyFinding:
    pattern = str(config.get("pattern") or "").strip()
    min_matches = int(config.get("minMatches", DEFAULT_REGEX_MIN_MATCHES))
    target_field = str(config.get("targetField") or "name")
    scope = str(config.get("scope") or "eligible_only")
    if not pattern:
        return _kept_finding(
            record.model_id, filter_id, "regex_not_configured", score=0.0, threshold=float(min_matches)
        )

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return _kept_finding(
            record.model_id,
            filter_id,
            "invalid_regex_pattern",
            score=0.0,
            threshold=float(min_matches),
            metrics={"error": str(exc), "pattern": pattern},
        )

    pool = semantic_nodes(derived_nodes) if scope == "eligible_only" else named_nodes(derived_nodes)
    values: list[tuple[DerivedNode, str]] = []
    for node in pool:
        if target_field == "type":
            values.append((node, node.normalized_type))
        elif target_field == "name+type":
            values.append((node, f"{node.normalized_name} {node.normalized_type}".strip()))
        else:
            values.append((node, node.normalized_name))

    hits = [(node, value) for node, value in values if value and compiled.search(value)]
    if len(hits) >= min_matches:
        return _removed_finding(
            record.model_id,
            filter_id,
            "regex_rule_matched",
            score=float(len(hits)),
            threshold=float(min_matches),
            evidence=tuple(value for _, value in hits[:10]),
            evidence_nodes=tuple(node.node_id for node, _ in hits[:10]),
            metrics={
                "matchCount": len(hits),
                "minMatches": min_matches,
                "scope": scope,
                "targetField": target_field,
                "pattern": pattern,
            },
        )
    return _kept_finding(
        record.model_id,
        filter_id,
        "regex_rule_not_matched",
        score=float(len(hits)),
        threshold=float(min_matches),
        metrics={
            "matchCount": len(hits),
            "minMatches": min_matches,
            "scope": scope,
            "targetField": target_field,
            "pattern": pattern,
        },
    )


def derive_nodes(record: ModelRecord) -> list[DerivedNode]:
    return [
        DerivedNode(
            node_id=node_id,
            raw_name=result.raw_name,
            node_type=result.raw_type,
            normalized_name=result.normalized_name,
            normalized_type=result.normalized_type,
            classification=result.classification,
            tokens=result.name_tokens,
        )
        for node_id, result in iter_name_slots(record)
    ]


def named_nodes(nodes: list[DerivedNode]) -> list[DerivedNode]:
    return [node for node in nodes if node.classification != "missing"]


def semantic_nodes(nodes: list[DerivedNode]) -> list[DerivedNode]:
    return [node for node in nodes if node.classification == "semantic"]


def _removed_finding(
    model_id: str,
    filter_id: str,
    reason: str,
    score: float,
    threshold: float,
    evidence: tuple[str, ...] = (),
    evidence_nodes: tuple[str, ...] = (),
    metrics: dict[str, Any] | None = None,
) -> DummyFinding:
    return DummyFinding(
        model_id=model_id,
        filter_id=filter_id,
        reason=reason,
        score=score,
        threshold=threshold,
        decision="removed",
        evidence=evidence,
        evidence_nodes=evidence_nodes,
        metrics=metrics,
    )


def _kept_finding(
    model_id: str,
    filter_id: str,
    reason: str,
    score: float,
    threshold: float,
    evidence: tuple[str, ...] = (),
    evidence_nodes: tuple[str, ...] = (),
    metrics: dict[str, Any] | None = None,
) -> DummyFinding:
    return DummyFinding(
        model_id=model_id,
        filter_id=filter_id,
        reason=reason,
        score=score,
        threshold=threshold,
        decision="kept",
        evidence=evidence,
        evidence_nodes=evidence_nodes,
        metrics=metrics,
    )


def _median(values: list[int]) -> float:
    length = len(values)
    if not length:
        return 0.0
    mid = length // 2
    if length % 2 == 1:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2
