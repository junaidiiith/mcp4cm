from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable, Iterable, Literal

from mcp4cm._deps import require_networkx, require_node2vec, require_sklearn, require_transformers_torch
from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.parsers import registry
from mcp4cm.parsers.base import BaseModelParser

HashMode = Literal["names", "names_types", "canonical_graph"]
IsomorphismMode = Literal["structure", "names", "names_types"]
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    fingerprint: str
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SimilarPair:
    left_id: str
    right_id: str
    score: float
    technique: str = ""


@dataclass(frozen=True, slots=True)
class GraphSimilarPair:
    left_id: str
    right_id: str
    score: float
    metrics: dict[str, float]
    technique: str = "graph_similarity"


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    left_id: str
    right_id: str
    is_duplicate: bool
    vote_count: int
    required_votes: int
    techniques: tuple[str, ...]
    scores: dict[str, float]


def detect_duplicates_by_hash(
    dataset: Dataset,
    parser: BaseModelParser | None = None,
    *,
    mode: HashMode = "canonical_graph",
    progress: ProgressCallback | None = None,
) -> list[DuplicateGroup]:
    """Detect exact duplicates by hash.

    ``mode="canonical_graph"`` keeps the original structural hash behavior.
    Use ``mode="names"`` or ``mode="names_types"`` for the two exact-match
    techniques requested by the cleansing pipeline.
    """

    groups: dict[str, list[str]] = defaultdict(list)
    records = list(dataset)
    total = len(records)
    _report_progress(progress, phase="fingerprint", current=0, total=total, message="Computing exact duplicate fingerprints.")
    for index, record in enumerate(records, start=1):
        if mode == "canonical_graph":
            active_parser = parser or parser_for_language(record.language)
            fingerprint = active_parser.canonical_hash(record)
        elif mode == "names":
            fingerprint = node_name_fingerprint(record)
        elif mode == "names_types":
            fingerprint = node_name_type_fingerprint(record)
        else:
            raise ValueError(f"Unsupported hash mode: {mode}")
        groups[fingerprint].append(record.model_id)
        _report_progress(
            progress,
            phase="fingerprint",
            current=index,
            total=total,
            message=f"Computed {index} of {total} fingerprints.",
        )
    return [
        DuplicateGroup(fingerprint=fingerprint, model_ids=tuple(model_ids))
        for fingerprint, model_ids in groups.items()
        if len(model_ids) > 1
    ]


def detect_duplicates_by_node_name_hash(dataset: Dataset, progress: ProgressCallback | None = None) -> list[DuplicateGroup]:
    """Exact duplicate detection from sorted node names only."""

    return detect_duplicates_by_hash(dataset, mode="names", progress=progress)


def detect_duplicates_by_node_name_type_hash(dataset: Dataset, progress: ProgressCallback | None = None) -> list[DuplicateGroup]:
    """Exact duplicate detection from sorted ``node name + node type`` pairs."""

    return detect_duplicates_by_hash(dataset, mode="names_types", progress=progress)


def tfidf_near_duplicate_detector(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    include_types: bool = True,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    technique = "tfidf_names_types" if include_types else "tfidf_names"
    return _tfidf_pairs(
        dataset,
        threshold=threshold,
        include_types=include_types,
        max_features=max_features,
        technique=technique,
        progress=progress,
    )


def tfidf_duplicate_by_names(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    return _tfidf_pairs(
        dataset,
        threshold=threshold,
        include_types=False,
        max_features=max_features,
        technique="tfidf_names",
        progress=progress,
    )


def tfidf_duplicate_by_names_and_types(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    return _tfidf_pairs(
        dataset,
        threshold=threshold,
        include_types=True,
        max_features=max_features,
        technique="tfidf_names_types",
        progress=progress,
    )


def graph_similarity_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.85,
    weights: dict[str, float] | None = None,
    progress: ProgressCallback | None = None,
) -> list[GraphSimilarPair]:
    """Find near-duplicates using several lightweight graph similarity metrics."""

    records = list(dataset)
    if len(records) < 2:
        return []
    weights = weights or {
        "node_name_jaccard": 0.25,
        "node_type_jaccard": 0.20,
        "edge_type_jaccard": 0.15,
        "degree_histogram_similarity": 0.15,
        "size_similarity": 0.15,
        "density_similarity": 0.10,
    }

    pairs: list[GraphSimilarPair] = []
    total_pairs = pair_count(len(records))
    _report_progress(progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning graph similarity pairs.")
    for index, (left, right) in enumerate(combinations(records, 2), start=1):
        metrics = graph_similarity_metrics(left, right)
        score = weighted_score(metrics, weights)
        if score >= threshold:
            pairs.append(GraphSimilarPair(left.model_id, right.model_id, score, metrics))
        _report_pair_progress(progress, index, total_pairs, "graph similarity pair(s) scanned")
    pairs.sort(key=lambda pair: pair.score, reverse=True)
    _report_progress(progress, phase="done", current=total_pairs, total=total_pairs, message=f"Graph similarity found {len(pairs)} pairs.")
    return pairs


def graph_isomorphism_pairs(
    dataset: Dataset,
    *,
    mode: IsomorphismMode = "names",
    match_edge_types: bool = True,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    """Detect exact graph isomorphism with optional node and edge attribute matching.

    ``mode="structure"`` ignores node attributes and checks only topology.
    ``mode="names"`` also requires matching node names.
    ``mode="names_types"`` requires matching node names and node types.
    Edge types are matched by default when present.
    """

    records = list(dataset)
    if len(records) < 2:
        return []

    pairs: list[SimilarPair] = []
    buckets = _isomorphism_candidate_buckets(records)
    total_pairs = sum(pair_count(len(bucket)) for bucket in buckets.values())
    _report_progress(progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning graph isomorphism candidates.")
    checked = 0
    for bucket in buckets.values():
        for left, right in combinations(bucket, 2):
            checked += 1
            if are_graphs_isomorphic(left, right, mode=mode, match_edge_types=match_edge_types):
                pairs.append(SimilarPair(left.model_id, right.model_id, 1.0, f"graph_isomorphism_{mode}"))
            _report_pair_progress(progress, checked, total_pairs, "isomorphism candidate pair(s) checked")
    _report_progress(progress, phase="done", current=total_pairs, total=total_pairs, message=f"Graph isomorphism found {len(pairs)} pairs.")
    return pairs


def graph_embedding_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    dimensions: int = 64,
    walk_length: int = 10,
    num_walks: int = 20,
    workers: int = 1,
    seed: int = 42,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    """Detect duplicates from Node2Vec graph embeddings averaged per model."""

    records = list(dataset)
    if len(records) < 2:
        return []

    Node2Vec = require_node2vec()
    np = _require_numpy()
    embeddings: list[Any] = []
    _report_progress(progress, phase="embedding", current=0, total=len(records), message="Computing Node2Vec graph embeddings.")
    for index, record in enumerate(records, start=1):
        embeddings.append(
            _node2vec_graph_embedding(
                record,
                Node2Vec,
                np,
                dimensions=dimensions,
                walk_length=walk_length,
                num_walks=num_walks,
                workers=workers,
                seed=seed,
            )
        )
        _report_progress(
            progress,
            phase="embedding",
            current=index,
            total=len(records),
            message=f"Computed {index} of {len(records)} Node2Vec graph embeddings.",
        )

    pairs = _embedding_similarity_pairs(
        records,
        embeddings,
        threshold=threshold,
        technique="graph_embedding",
        progress=progress,
        message="graph embedding pair(s) scanned",
    )
    _report_progress(progress, phase="done", current=pair_count(len(records)), total=pair_count(len(records)), message=f"Graph embeddings found {len(pairs)} pairs.")
    return pairs


def bert_semantic_similarity_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    model_name: str = "bert-base-uncased",
    batch_size: int = 8,
    max_length: int = 256,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    """Detect semantic duplicates using mean-pooled bert-base-uncased embeddings."""

    records = list(dataset)
    if len(records) < 2:
        return []

    AutoTokenizer, AutoModel, torch = require_transformers_torch()
    np = _require_numpy()
    _report_progress(progress, phase="load_model", current=0, total=1, message=f"Loading {model_name}.")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    _report_progress(progress, phase="load_model", current=1, total=1, message=f"Loaded {model_name}.")

    texts = [record.text_for_similarity(include_types=True) or record_text(record, include_types=True) for record in records]
    embeddings = []
    total_batches = math.ceil(len(records) / batch_size)
    _report_progress(progress, phase="embedding", current=0, total=total_batches, message="Computing BERT semantic embeddings.")
    with torch.no_grad():
        for batch_index, start in enumerate(range(0, len(texts), batch_size), start=1):
            batch = texts[start : start + batch_size]
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            output = model(**encoded)
            batch_embeddings = _mean_pool_bert(output.last_hidden_state, encoded["attention_mask"], torch)
            embeddings.extend(batch_embeddings.cpu().numpy())
            _report_progress(
                progress,
                phase="embedding",
                current=batch_index,
                total=total_batches,
                message=f"Computed {batch_index} of {total_batches} BERT embedding batches.",
            )

    pairs = _embedding_similarity_pairs(
        records,
        [np.asarray(embedding, dtype=float) for embedding in embeddings],
        threshold=threshold,
        technique="bert_semantic",
        progress=progress,
        message="BERT semantic pair(s) scanned",
    )
    _report_progress(progress, phase="done", current=pair_count(len(records)), total=pair_count(len(records)), message=f"BERT semantic similarity found {len(pairs)} pairs.")
    return pairs


def are_graphs_isomorphic(
    left: ModelRecord,
    right: ModelRecord,
    *,
    mode: IsomorphismMode = "names",
    match_edge_types: bool = True,
) -> bool:
    if left.node_count != right.node_count or left.edge_count != right.edge_count:
        return False
    nx = require_networkx()
    node_match = _isomorphism_node_match(nx, mode)
    edge_match = _isomorphism_edge_match(nx) if match_edge_types else None
    return nx.is_isomorphic(left.graph, right.graph, node_match=node_match, edge_match=edge_match)


def graph_similarity_metrics(left: ModelRecord, right: ModelRecord) -> dict[str, float]:
    return {
        "node_name_jaccard": jaccard(node_names(left), node_names(right)),
        "node_type_jaccard": jaccard(node_types(left), node_types(right)),
        "edge_type_jaccard": jaccard(edge_types(left), edge_types(right)),
        "degree_histogram_similarity": cosine_counter(degree_histogram(left), degree_histogram(right)),
        "size_similarity": size_similarity(left, right),
        "density_similarity": density_similarity(left, right),
    }


def vote_duplicate_pairs(
    dataset: Dataset,
    *,
    min_votes: int = 3,
    tfidf_name_threshold: float = 0.9,
    tfidf_name_type_threshold: float = 0.9,
    graph_threshold: float = 0.85,
    isomorphism_mode: IsomorphismMode = "names",
) -> list[DuplicateDecision]:
    """Vote across exact hash, TF-IDF, graph similarity, and graph isomorphism."""

    votes: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)

    _add_group_votes(votes, detect_duplicates_by_node_name_hash(dataset), "hash_names", 1.0)
    _add_group_votes(votes, detect_duplicates_by_node_name_type_hash(dataset), "hash_names_types", 1.0)
    _add_pair_votes(votes, tfidf_duplicate_by_names(dataset, threshold=tfidf_name_threshold))
    _add_pair_votes(votes, tfidf_duplicate_by_names_and_types(dataset, threshold=tfidf_name_type_threshold))
    _add_graph_votes(votes, graph_similarity_pairs(dataset, threshold=graph_threshold))
    _add_pair_votes(votes, graph_isomorphism_pairs(dataset, mode=isomorphism_mode))

    decisions = [
        DuplicateDecision(
            left_id=left_id,
            right_id=right_id,
            is_duplicate=len(scores) >= min_votes,
            vote_count=len(scores),
            required_votes=min_votes,
            techniques=tuple(sorted(scores)),
            scores=dict(sorted(scores.items())),
        )
        for (left_id, right_id), scores in votes.items()
    ]
    decisions.sort(key=lambda decision: (decision.is_duplicate, decision.vote_count), reverse=True)
    return decisions


def duplicate_model_ids_from_votes(decisions: Iterable[DuplicateDecision]) -> set[str]:
    return {
        model_id
        for decision in decisions
        if decision.is_duplicate
        for model_id in (decision.left_id, decision.right_id)
    }


def node_name_fingerprint(record: ModelRecord, algorithm: str = "sha256") -> str:
    return hash_tokens(node_names(record), algorithm=algorithm)


def node_name_type_fingerprint(record: ModelRecord, algorithm: str = "sha256") -> str:
    pairs = []
    for _, attrs in record.graph.nodes(data=True):
        name = normalize(attrs.get("name"))
        node_type = normalize(attrs.get("type") or attrs.get("eClass"))
        if name or node_type:
            pairs.append(f"{name}\t{node_type}")
    return hash_tokens(sorted(pairs), algorithm=algorithm)


def parser_for_language(language: str) -> BaseModelParser:
    return registry.create(language)


def flatten_duplicate_groups(groups: Iterable[DuplicateGroup]) -> set[str]:
    return {model_id for group in groups for model_id in group.model_ids}


def _tfidf_pairs(
    dataset: Dataset,
    *,
    threshold: float,
    include_types: bool,
    max_features: int | None,
    technique: str,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    records = list(dataset)
    if len(records) < 2:
        return []
    TfidfVectorizer, cosine_similarity = require_sklearn()
    _report_progress(progress, phase="corpus", current=0, total=len(records), message="Building TF-IDF corpus.")
    corpus = [record_text(record, include_types=include_types) for record in records]
    if not any(text.strip() for text in corpus):
        return []
    vectorizer = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b\w+\b", max_features=max_features)
    try:
        _report_progress(progress, phase="vectorize", current=0, total=1, message="Vectorizing model names.")
        matrix = vectorizer.fit_transform(corpus)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return []
        raise
    _report_progress(progress, phase="similarity", current=0, total=1, message="Computing cosine similarity matrix.")
    similarity = cosine_similarity(matrix)

    pairs: list[SimilarPair] = []
    total_pairs = pair_count(len(records))
    _report_progress(progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning TF-IDF pair similarities.")
    for index, (left, right) in enumerate(combinations(range(len(records)), 2), start=1):
        score = float(similarity[left, right])
        if score >= threshold:
            pairs.append(SimilarPair(records[left].model_id, records[right].model_id, score, technique))
        _report_pair_progress(progress, index, total_pairs, "TF-IDF pair(s) scanned")
    pairs.sort(key=lambda pair: pair.score, reverse=True)
    _report_progress(progress, phase="done", current=total_pairs, total=total_pairs, message=f"TF-IDF found {len(pairs)} pairs.")
    return pairs


def _node2vec_graph_embedding(
    record: ModelRecord,
    Node2Vec,
    np,
    *,
    dimensions: int,
    walk_length: int,
    num_walks: int,
    workers: int,
    seed: int,
):
    nx = require_networkx()
    graph = nx.Graph()
    graph.add_nodes_from(str(node) for node in record.graph.nodes())
    graph.add_edges_from((str(left), str(right)) for left, right in record.graph.edges())
    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        return np.zeros(dimensions, dtype=float)

    node2vec = Node2Vec(
        graph,
        dimensions=dimensions,
        walk_length=walk_length,
        num_walks=num_walks,
        workers=workers,
        quiet=True,
        seed=seed,
    )
    model = node2vec.fit(window=5, min_count=1, batch_words=4, seed=seed)
    vectors = [model.wv[str(node)] for node in graph.nodes() if str(node) in model.wv]
    if not vectors:
        return np.zeros(dimensions, dtype=float)
    return np.mean(vectors, axis=0)


def _embedding_similarity_pairs(
    records: list[ModelRecord],
    embeddings: list[Any],
    *,
    threshold: float,
    technique: str,
    progress: ProgressCallback | None,
    message: str,
) -> list[SimilarPair]:
    np = _require_numpy()
    pairs: list[SimilarPair] = []
    total_pairs = pair_count(len(records))
    _report_progress(progress, phase="pair_scan", current=0, total=total_pairs, message=f"Scanning {message}.")
    for index, (left_index, right_index) in enumerate(combinations(range(len(records)), 2), start=1):
        score = cosine_embedding(embeddings[left_index], embeddings[right_index], np)
        if score >= threshold:
            pairs.append(SimilarPair(records[left_index].model_id, records[right_index].model_id, score, technique))
        _report_pair_progress(progress, index, total_pairs, message)
    pairs.sort(key=lambda pair: pair.score, reverse=True)
    return pairs


def _mean_pool_bert(last_hidden_state, attention_mask, torch):
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def cosine_embedding(left, right, np) -> float:
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    left_norm = np.linalg.norm(left_array)
    right_norm = np.linalg.norm(right_array)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left_array, right_array) / (left_norm * right_norm))


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "Embedding duplicate detection requires numpy. Install dependencies with "
            "`pip install -r requirements.txt` or `pip install -e .`."
        ) from exc
    return np


def record_text(record: ModelRecord, *, include_types: bool) -> str:
    tokens = node_names(record)
    if include_types:
        tokens = [*tokens, *node_types(record)]
    return " ".join(tokens)


def node_names(record: ModelRecord) -> list[str]:
    return sorted(
        normalize(attrs.get("name"))
        for _, attrs in record.graph.nodes(data=True)
        if normalize(attrs.get("name"))
    )


def node_types(record: ModelRecord) -> list[str]:
    return sorted(
        normalize(attrs.get("type") or attrs.get("eClass"))
        for _, attrs in record.graph.nodes(data=True)
        if normalize(attrs.get("type") or attrs.get("eClass"))
    )


def edge_types(record: ModelRecord) -> list[str]:
    return sorted(
        normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))
        for _, _, attrs in record.graph.edges(data=True)
        if normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))
    )


def node_type_attr(attrs: dict[str, object]) -> str:
    return normalize(attrs.get("type") or attrs.get("eClass"))


def node_name_attr(attrs: dict[str, object]) -> str:
    return normalize(attrs.get("name"))


def edge_type_attr(attrs: dict[str, object]) -> str:
    return normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))


def _isomorphism_candidate_buckets(records: list[ModelRecord]) -> dict[tuple[int, int, str], list[ModelRecord]]:
    buckets: dict[tuple[int, int, str], list[ModelRecord]] = defaultdict(list)
    for record in records:
        buckets[(record.node_count, record.edge_count, record.graph.__class__.__name__)].append(record)
    return buckets


def _isomorphism_node_match(nx, mode: IsomorphismMode):
    if mode == "structure":
        return None
    if mode == "names":
        return lambda left, right: node_name_attr(left) == node_name_attr(right)
    if mode == "names_types":
        return lambda left, right: (
            node_name_attr(left) == node_name_attr(right)
            and node_type_attr(left) == node_type_attr(right)
        )
    raise ValueError(f"Unsupported isomorphism mode: {mode}")


def _isomorphism_edge_match(nx):
    return lambda left, right: edge_type_attr(left) == edge_type_attr(right)


def degree_histogram(record: ModelRecord) -> Counter[int]:
    return Counter(dict(record.graph.degree()).values())


def size_similarity(left: ModelRecord, right: ModelRecord) -> float:
    node_score = ratio_similarity(left.node_count, right.node_count)
    edge_score = ratio_similarity(left.edge_count, right.edge_count)
    return (node_score + edge_score) / 2


def density_similarity(left: ModelRecord, right: ModelRecord) -> float:
    left_density = graph_density(left)
    right_density = graph_density(right)
    denominator = max(left_density, right_density, 1e-12)
    return 1 - (abs(left_density - right_density) / denominator)


def graph_density(record: ModelRecord) -> float:
    node_count = record.node_count
    if node_count <= 1:
        return 0.0
    return record.edge_count / (node_count * (node_count - 1))


def ratio_similarity(left: int, right: int) -> float:
    if left == right == 0:
        return 1.0
    return min(left, right) / max(left, right)


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def cosine_counter(left: Counter[int], right: Counter[int]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    keys = set(left) | set(right)
    dot = sum(left[key] * right[key] for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def weighted_score(metrics: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Graph similarity weights must sum to a positive number.")
    return sum(metrics[name] * weight for name, weight in weights.items()) / total_weight


def pair_count(item_count: int) -> int:
    return item_count * (item_count - 1) // 2


def _report_progress(
    progress: ProgressCallback | None,
    *,
    phase: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress is None:
        return
    percent = round((current / total) * 100) if total else 100
    progress(
        {
            "phase": phase,
            "current": current,
            "total": total,
            "percent": min(max(percent, 0), 100),
            "message": message,
        }
    )


def _report_pair_progress(progress: ProgressCallback | None, current: int, total: int, unit: str) -> None:
    if progress is None:
        return
    if current == total or current % max(1, total // 100) == 0:
        _report_progress(
            progress,
            phase="pair_scan",
            current=current,
            total=total,
            message=f"{current} of {total} {unit}.",
        )


def hash_tokens(tokens: Iterable[str], algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    for token in sorted(tokens):
        hasher.update(token.encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))  # type: ignore[return-value]


def _add_group_votes(
    votes: dict[tuple[str, str], dict[str, float]],
    groups: Iterable[DuplicateGroup],
    technique: str,
    score: float,
) -> None:
    for group in groups:
        for left_id, right_id in combinations(group.model_ids, 2):
            votes[pair_key(left_id, right_id)][technique] = score


def _add_pair_votes(votes: dict[tuple[str, str], dict[str, float]], pairs: Iterable[SimilarPair]) -> None:
    for pair in pairs:
        votes[pair_key(pair.left_id, pair.right_id)][pair.technique] = pair.score


def _add_graph_votes(votes: dict[tuple[str, str], dict[str, float]], pairs: Iterable[GraphSimilarPair]) -> None:
    for pair in pairs:
        votes[pair_key(pair.left_id, pair.right_id)][pair.technique] = pair.score
