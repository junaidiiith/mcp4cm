from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

from mcp4cm.api.services.datasets import get_duplicate_detection_dataset, model_summary_lookup
from mcp4cm.api.state import LOG
from mcp4cm.core import Dataset
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    detect_duplicates_by_name_hash,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs
from mcp4cm.utils import pair_count, pair_key, pair_lookup_key, parse_bool

DUPLICATE_TECHNIQUE_ORDER = (
    "hash",
    "tfidf",
    "graph_similarity",
    "graph_embedding",
    "gnn",
    "bert_semantic",
    "graph_isomorphism",
)

DUPLICATE_TECHNIQUE_LABELS = {
    "hash": "Hash",
    "tfidf": "TF-IDF",
    "graph_similarity": "Graph Metrics",
    "graph_embedding": "Graph Embeddings",
    "gnn": "Contrastive GNN",
    "bert_semantic": "BERT Semantic",
    "graph_isomorphism": "Isomorphism",
}

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
    "gnn": "gnn",
    "contrastive_gnn": "gnn",
    "graphcl": "gnn",
    "bert": "bert_semantic",
    "bert_semantic": "bert_semantic",
    "bert_similarity": "bert_semantic",
    "bert_semantic_similarity": "bert_semantic",
    "semantic_similarity": "bert_semantic",
    "graph_isomorphism": "graph_isomorphism",
    "isomorphism": "graph_isomorphism",
}


def selected_duplicate_techniques(body: dict[str, Any]) -> list[str]:
    raw_techniques = raw_duplicate_techniques(body)
    selected = {normalize_duplicate_technique(technique) for technique in raw_techniques}
    LOG.info("duplicate_techniques_received raw=%s normalized=%s", raw_techniques, sorted(selected))
    return [technique for technique in DUPLICATE_TECHNIQUE_ORDER if technique in selected]


def duplicate_technique_label(technique: str) -> str:
    return DUPLICATE_TECHNIQUE_LABELS.get(technique, technique)


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
        include_types = parse_bool(thresholds.get("tfidfIncludeTypes"), default=False)
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
        f"Select at least one duplicate technique. Request contained techniques={raw_duplicate_techniques(body)!r}."
    )


def group_pairs(groups) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    for group in groups:
        ids = list(group.model_ids)
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1 :]:
                pairs.append((left_id, right_id, 1.0))
    return pairs


def add_votes(
    votes: dict[tuple[str, str], dict[str, float]],
    pairs: list[tuple[str, str, float]],
    technique: str,
    default_score: float | None = None,
) -> None:
    for left_id, right_id, score in pairs:
        votes.setdefault(pair_key(left_id, right_id), {})[technique] = (
            default_score if default_score is not None else score
        )


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


def graph_similarity_weights(
    thresholds: dict[str, Any], *, use_directed_metrics: bool = False
) -> dict[str, float] | None:
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
    if use_directed_metrics:
        parsed["in_degree_histogram_similarity"] = float(weights.get("inDegreeHistogram", 0.15))
        parsed["out_degree_histogram_similarity"] = float(weights.get("outDegreeHistogram", 0.15))
    return parsed


def build_duplicate_groups(
    decisions: list[dict[str, Any]],
    model_summaries: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    adjacency: dict[str, set[str]] = {}
    approved_lookup: dict[str, dict[str, Any]] = {}
    decision_lookup: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        left_id = str(decision.get("leftId") or "")
        right_id = str(decision.get("rightId") or "")
        if not left_id or not right_id:
            continue
        lookup = pair_lookup_key(left_id, right_id)
        decision_lookup[lookup] = decision
        if decision.get("isDuplicate") is True:
            approved_lookup[lookup] = decision
            adjacency.setdefault(left_id, set()).add(right_id)
            adjacency.setdefault(right_id, set()).add(left_id)

    visited: set[str] = set()
    components: list[list[str]] = []
    for model_id in sorted(adjacency):
        if model_id in visited:
            continue
        stack = [model_id]
        component: list[str] = []
        visited.add(model_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component) > 1:
            components.append(sorted(component))

    groups: list[dict[str, Any]] = []
    pair_group_lookup: dict[str, str] = {}
    for index, model_ids in enumerate(sorted(components, key=lambda item: (-len(item), item)), start=1):
        group_id = f"group-{index}"
        approved_internal = 0
        rejected_internal = 0
        vote_counts: list[int] = []
        techniques: set[str] = set()
        score_values: list[float] = []
        internal_decision_keys: list[str] = []
        for left_index, left_id in enumerate(model_ids):
            for right_id in model_ids[left_index + 1 :]:
                lookup = pair_lookup_key(left_id, right_id)
                decision = decision_lookup.get(lookup)
                if not decision:
                    continue
                internal_decision_keys.append(lookup)
                pair_group_lookup[lookup] = group_id
                if decision.get("isDuplicate") is True:
                    approved_internal += 1
                    vote_counts.append(int(decision.get("voteCount") or 0))
                else:
                    rejected_internal += 1
                techniques.update(str(item) for item in decision.get("techniques", []))
                for score in (decision.get("scores") or {}).values():
                    with suppress(TypeError, ValueError):
                        score_values.append(float(score))

        possible_pairs = pair_count(len(model_ids))
        missing_pairs = max(possible_pairs - approved_internal - rejected_internal, 0)
        density = approved_internal / possible_pairs if possible_pairs else 0
        canonical_model_id = propose_canonical_model(model_ids, model_summaries)
        confidence = duplicate_group_confidence(
            possible_pairs=possible_pairs,
            approved_internal=approved_internal,
            rejected_internal=rejected_internal,
            missing_pairs=missing_pairs,
            vote_counts=vote_counts,
        )
        warnings = duplicate_group_warnings(
            confidence=confidence,
            rejected_internal=rejected_internal,
            missing_pairs=missing_pairs,
            vote_counts=vote_counts,
        )
        groups.append(
            {
                "groupId": group_id,
                "modelIds": model_ids,
                "size": len(model_ids),
                "approvedInternalPairs": approved_internal,
                "candidateRejectedInternalPairs": rejected_internal,
                "missingInternalPairs": missing_pairs,
                "possibleInternalPairs": possible_pairs,
                "density": density,
                "confidence": confidence,
                "warnings": warnings,
                "techniques": sorted(techniques),
                "canonicalModelId": canonical_model_id,
                "canonicalReason": "largest graph, then most named elements, then stable model id",
                "scoreStats": score_stats(score_values),
                "modelSummaries": [model_summaries.get(model_id, {"modelId": model_id}) for model_id in model_ids],
                "decisionKeys": internal_decision_keys,
            }
        )

    return groups, pair_group_lookup


def propose_canonical_model(model_ids: list[str], model_summaries: dict[str, dict[str, Any]]) -> str:
    def sort_key(model_id: str) -> tuple[int, int, str]:
        summary = model_summaries.get(model_id, {})
        graph_size = int(summary.get("nodeCount") or 0) + int(summary.get("edgeCount") or 0)
        named_elements = int(summary.get("namedElements") or 0)
        return (-graph_size, -named_elements, str(model_id))

    return sorted(model_ids, key=sort_key)[0] if model_ids else ""


def duplicate_group_confidence(
    *,
    possible_pairs: int,
    approved_internal: int,
    rejected_internal: int,
    missing_pairs: int,
    vote_counts: list[int],
) -> str:
    if possible_pairs and approved_internal == possible_pairs and rejected_internal == 0:
        return "complete"
    if rejected_internal:
        return "mixed"
    if vote_counts and min(vote_counts) <= 1:
        return "weak"
    if missing_pairs:
        return "linked"
    return "linked"


def duplicate_group_warnings(
    *,
    confidence: str,
    rejected_internal: int,
    missing_pairs: int,
    vote_counts: list[int],
) -> list[str]:
    warnings: list[str] = []
    if confidence == "mixed":
        warnings.append(f"{rejected_internal} internal candidate pair(s) were not approved.")
    if missing_pairs:
        warnings.append(f"{missing_pairs} internal pair(s) have no direct candidate evidence.")
    if vote_counts and min(vote_counts) <= 1:
        warnings.append("At least one approved link has only one technique vote.")
    return warnings


def score_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
    }


def handle_duplicates(body: dict[str, Any], progress=None) -> dict[str, Any]:
    dataset = get_duplicate_detection_dataset(body)
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
                    "duplicate_algorithm_progress technique=%s label=%s phase=%s "
                    "progress=%s%% current=%s total=%s message=%s",
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
            "duplicate_algorithm_complete technique=%s label=%s status=%s pairs=%s "
            "duplicate_models=%s unique_models=%s completed=%s/%s elapsed_ms=%s reason=%s",
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
                    include_types=parse_bool(thresholds.get("hashIncludeTypes"), default=False),
                    min_named_nodes=int(thresholds.get("minNamedNodes", 0)),
                    deduplicate_name_tokens=parse_bool(thresholds.get("deduplicateNameTokens"), default=False),
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
                use_directed_metrics = parse_bool(thresholds.get("useDirectedMetrics"), default=False)
                pairs = graph_similarity_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("graphSimilarity", 0.85)),
                    weights=graph_similarity_weights(thresholds, use_directed_metrics=use_directed_metrics),
                    use_directed_metrics=use_directed_metrics,
                    normalize_parallel_edges=parse_bool(thresholds.get("normalizeParallelEdges"), default=False),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                metrics_by_pair = {pair_key(pair.left_id, pair.right_id): dict(pair.metrics) for pair in pairs}
                add_pair_evidence(technique, technique_pairs, metrics_by_pair=metrics_by_pair)
            elif technique == "graph_embedding":
                pairs = graph_embedding_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("graphEmbeddingThreshold", thresholds.get("graphEmbedding", 0.9))),
                    dimensions=int(thresholds.get("graphEmbeddingDimensions", 32)),
                    walk_length=int(thresholds.get("graphEmbeddingWalkLength", 5)),
                    num_walks=int(thresholds.get("graphEmbeddingNumWalks", 5)),
                    workers=int(thresholds.get("graphEmbeddingWorkers", 1)),
                    seed=int(thresholds.get("graphEmbeddingSeed", 42)),
                    progress=report_algorithm_progress(technique),
                )
                technique_pairs = [(pair.left_id, pair.right_id, pair.score) for pair in pairs]
                add_pair_evidence(technique, technique_pairs)
            elif technique == "gnn":
                config = GNNTrainingConfig(
                    model_name=str(thresholds.get("gnnModelName", "sentence-transformers/all-MiniLM-L6-v2")),
                    embedding_dim=int(thresholds.get("gnnDimensions", 128)),
                    layers=int(thresholds.get("gnnLayers", 2)),
                    epochs=int(thresholds.get("gnnEpochs", 20)),
                    learning_rate=float(thresholds.get("gnnLearningRate", 1e-3)),
                    temperature=float(thresholds.get("gnnTemperature", 0.2)),
                    edge_dropout=float(thresholds.get("gnnEdgeDropout", 0.15)),
                    feature_mask_rate=float(thresholds.get("gnnFeatureMaskRate", 0.1)),
                    batch_size=int(thresholds.get("gnnBatchSize", 32)),
                    seed=int(thresholds.get("gnnSeed", 42)),
                    device=str(thresholds.get("gnnDevice", "auto")),
                )
                pairs = gnn_duplicate_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("gnnThreshold", 0.85)),
                    config=config,
                    progress=report_algorithm_progress(technique),
                )
                add_pair_evidence(technique, pairs)
            elif technique == "bert_semantic":
                pairs = bert_semantic_similarity_pairs(
                    projected_dataset,
                    threshold=float(thresholds.get("bertSemantic", 0.8)),
                    model_name=str(thresholds.get("bertModelName", "sentence-transformers/all-MiniLM-L6-v2")),
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
                    ignore_direction=parse_bool(thresholds.get("ignoreDirection"), default=False),
                    match_parallel_edge_multiplicity=parse_bool(
                        thresholds.get("matchParallelEdgeMultiplicity"), default=True
                    ),
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
    model_summaries = model_summary_lookup(projected_dataset)
    groups, pair_group_lookup = build_duplicate_groups(decisions, model_summaries)
    for decision in decisions:
        group_id = pair_group_lookup.get(pair_lookup_key(str(decision.get("leftId")), str(decision.get("rightId"))))
        if group_id:
            decision["groupId"] = group_id

    affected_model_ids = sorted({model_id for group in groups for model_id in group.get("modelIds", [])})
    largest_group_size = max((int(group.get("size") or 0) for group in groups), default=0)
    group_summary = {
        "totalGroups": len(groups),
        "affectedModels": len(affected_model_ids),
        "largestGroupSize": largest_group_size,
        "completeGroups": sum(1 for group in groups if group.get("confidence") == "complete"),
        "linkedGroups": sum(1 for group in groups if group.get("confidence") == "linked"),
        "mixedGroups": sum(1 for group in groups if group.get("confidence") == "mixed"),
        "weakGroups": sum(1 for group in groups if group.get("confidence") == "weak"),
    }

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
        "hashIncludeTypes": parse_bool(thresholds.get("hashIncludeTypes"), default=False),
        "minNamedNodes": int(thresholds.get("minNamedNodes", 0)),
        "deduplicateNameTokens": parse_bool(thresholds.get("deduplicateNameTokens"), default=False),
        "tfidfTokenMode": parse_tfidf_token_mode(body, thresholds),
        "tfidfSimilarityThreshold": tfidf_threshold,
        "tfidfMaxFeatures": int(thresholds.get("tfidfMaxFeatures", 50_000)),
        "minDf": parse_min_df(thresholds.get("minDf", 1)),
        "ngramRange": list(parse_ngram_range(thresholds.get("ngramRange", [1, 1]))),
        "stopwordsMode": parse_stopwords_mode(thresholds.get("stopwordsMode", "none")),
        "graphSimilarity": float(thresholds.get("graphSimilarity", 0.85)),
        "graphWeights": graph_similarity_weights(
            thresholds,
            use_directed_metrics=parse_bool(thresholds.get("useDirectedMetrics"), default=False),
        ),
        "useDirectedMetrics": parse_bool(thresholds.get("useDirectedMetrics"), default=False),
        "normalizeParallelEdges": parse_bool(thresholds.get("normalizeParallelEdges"), default=False),
        "graphEmbeddingThreshold": float(
            thresholds.get("graphEmbeddingThreshold", thresholds.get("graphEmbedding", 0.9))
        ),
        "graphEmbeddingDimensions": int(thresholds.get("graphEmbeddingDimensions", 32)),
        "graphEmbeddingWalkLength": int(thresholds.get("graphEmbeddingWalkLength", 5)),
        "graphEmbeddingNumWalks": int(thresholds.get("graphEmbeddingNumWalks", 5)),
        "graphEmbeddingWorkers": int(thresholds.get("graphEmbeddingWorkers", 1)),
        "graphEmbeddingSeed": int(thresholds.get("graphEmbeddingSeed", 42)),
        "gnnThreshold": float(thresholds.get("gnnThreshold", 0.85)),
        "gnnDimensions": int(thresholds.get("gnnDimensions", 128)),
        "gnnLayers": int(thresholds.get("gnnLayers", 2)),
        "gnnEpochs": int(thresholds.get("gnnEpochs", 20)),
        "gnnLearningRate": float(thresholds.get("gnnLearningRate", 1e-3)),
        "gnnTemperature": float(thresholds.get("gnnTemperature", 0.2)),
        "gnnEdgeDropout": float(thresholds.get("gnnEdgeDropout", 0.15)),
        "gnnFeatureMaskRate": float(thresholds.get("gnnFeatureMaskRate", 0.1)),
        "gnnBatchSize": int(thresholds.get("gnnBatchSize", 32)),
        "gnnModelName": str(thresholds.get("gnnModelName", "sentence-transformers/all-MiniLM-L6-v2")),
        "gnnSeed": int(thresholds.get("gnnSeed", 42)),
        "gnnDevice": str(thresholds.get("gnnDevice", "auto")),
    }

    return {
        "techniqueCounts": technique_counts,
        "modelCounts": model_counts,
        "duplicatePairs": total_decisions,
        "votedDuplicatePairs": approved_pairs,
        "candidatePairs": total_decisions,
        "approvedPairs": approved_pairs,
        "duplicateGroups": len(groups),
        "affectedModels": len(affected_model_ids),
        "largestGroupSize": largest_group_size,
        "groupSummary": group_summary,
        "totalDecisions": total_decisions,
        "decisions": decisions,
        "groups": groups,
        "pairGroupLookup": pair_group_lookup,
        "modelSummaries": model_summaries,
        "techniqueStatus": technique_status,
        "configEcho": config_echo,
        "elapsedMs": round((time.perf_counter() - duplicate_started_at) * 1000),
    }
