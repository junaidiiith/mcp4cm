from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import re
import signal
import tempfile
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from queue import Empty
from typing import Any, Literal
from urllib.parse import quote

from mcp4cm._deps import require_networkx, require_node2vec, require_sentence_transformers, require_sklearn
from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.name_classification import (
    extract_node_labels,
    normalize_label,
    normalize_name,
    normalize_type,
    raw_node_name,
    raw_node_type,
)
from mcp4cm.utils import pair_count, pair_key, progress_percent

IsomorphismMode = Literal["structure"]
TfidfTokenMode = Literal["names", "names_types_bag", "typed_name_pairs"]
StopwordsMode = Literal["none", "english"]
ProgressCallback = Callable[[dict[str, Any]], None]
ISOMORPHISM_TIMEOUT_SECONDS = 120.0
DEFAULT_SENTENCE_SIMILARITY_THRESHOLD = 0.80


class IsomorphismCheckTimeout(TimeoutError):
    """Raised internally when one graph-pair isomorphism check exceeds its budget."""


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
class GraphSimilarityFeatures:
    node_names: frozenset[str]
    node_types: frozenset[str]
    edge_types: frozenset[str]
    degree_histogram: Counter[int]
    node_count: int
    edge_count: int
    density: float
    in_degree_histogram: Counter[int] | None = None
    out_degree_histogram: Counter[int] | None = None


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    left_id: str
    right_id: str
    is_duplicate: bool
    vote_count: int
    required_votes: int
    techniques: tuple[str, ...]
    scores: dict[str, float]


def detect_duplicates_by_name_hash(
    dataset: Dataset,
    *,
    include_types: bool,
    min_named_nodes: int = 0,
    deduplicate_name_tokens: bool = False,
    progress: ProgressCallback | None = None,
) -> list[DuplicateGroup]:
    groups: dict[str, list[str]] = defaultdict(list)
    records = list(dataset)
    total = len(records)
    _report_progress(
        progress, phase="fingerprint", current=0, total=total, message="Computing exact duplicate fingerprints."
    )

    for index, record in enumerate(records, start=1):
        tokens = hashable_name_tokens(
            record,
            include_types=include_types,
            deduplicate_name_tokens=deduplicate_name_tokens,
        )
        if len(tokens) >= max(min_named_nodes, 0) and tokens:
            groups[hash_name_tokens(record, tokens, include_types=include_types)].append(record.model_id)
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


def detect_duplicates_by_node_name_hash(
    dataset: Dataset, progress: ProgressCallback | None = None
) -> list[DuplicateGroup]:
    return detect_duplicates_by_name_hash(dataset, include_types=False, progress=progress)


def detect_duplicates_by_node_name_type_hash(
    dataset: Dataset, progress: ProgressCallback | None = None
) -> list[DuplicateGroup]:
    return detect_duplicates_by_name_hash(dataset, include_types=True, progress=progress)


def tfidf_near_duplicate_detector(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    include_types: bool = True,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    return tfidf_duplicate_pairs(
        dataset,
        token_mode="names_types_bag" if include_types else "names",
        threshold=threshold,
        max_features=max_features,
        progress=progress,
        technique="tfidf_names_types" if include_types else "tfidf_names",
    )


def tfidf_duplicate_pairs(
    dataset: Dataset,
    *,
    token_mode: TfidfTokenMode = "names",
    threshold: float = 0.9,
    max_features: int | None = 50_000,
    min_df: int | float = 1,
    ngram_range: tuple[int, int] = (1, 1),
    stopwords_mode: StopwordsMode = "none",
    progress: ProgressCallback | None = None,
    technique: str = "tfidf",
) -> list[SimilarPair]:
    records = list(dataset)
    if len(records) < 2:
        return []

    TfidfVectorizer, cosine_similarity = require_sklearn()
    _report_progress(progress, phase="corpus", current=0, total=len(records), message="Building TF-IDF corpus.")
    corpus = [" ".join(record_tokens(record, token_mode=token_mode)) for record in records]
    if not any(text.strip() for text in corpus):
        return []

    stop_words = "english" if stopwords_mode == "english" else None
    vectorizer = TfidfVectorizer(
        lowercase=True,
        token_pattern=r"(?u)\b\w+\b",
        max_features=max_features,
        min_df=min_df,
        ngram_range=ngram_range,
        stop_words=stop_words,
    )
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
    _report_progress(
        progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning TF-IDF pair similarities."
    )
    for index, (left, right) in enumerate(combinations(range(len(records)), 2), start=1):
        score = float(similarity[left, right])
        if score >= threshold:
            pairs.append(SimilarPair(records[left].model_id, records[right].model_id, score, technique))
        _report_pair_progress(progress, index, total_pairs, "TF-IDF pair(s) scanned")

    pairs.sort(key=lambda pair: pair.score, reverse=True)
    _report_progress(
        progress, phase="done", current=total_pairs, total=total_pairs, message=f"TF-IDF found {len(pairs)} pairs."
    )
    return pairs


def tfidf_duplicate_by_names(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    return tfidf_duplicate_pairs(
        dataset,
        token_mode="names",
        threshold=threshold,
        max_features=max_features,
        progress=progress,
        technique="tfidf_names",
    )


def tfidf_duplicate_by_names_and_types(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    max_features: int | None = 50_000,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    return tfidf_duplicate_pairs(
        dataset,
        token_mode="names_types_bag",
        threshold=threshold,
        max_features=max_features,
        progress=progress,
        technique="tfidf_names_types",
    )


def graph_similarity_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.85,
    weights: dict[str, float] | None = None,
    use_directed_metrics: bool = False,
    normalize_parallel_edges: bool = False,
    progress: ProgressCallback | None = None,
) -> list[GraphSimilarPair]:
    records = list(dataset)
    if len(records) < 2:
        return []

    if normalize_parallel_edges:
        records = [_with_compacted_parallel_edges(record) for record in records]

    weights = weights or default_graph_similarity_weights(use_directed_metrics=use_directed_metrics)

    feature_cache: dict[str, GraphSimilarityFeatures] = {}
    total_records = len(records)
    _report_progress(
        progress,
        phase="features",
        current=0,
        total=total_records,
        message="Computing graph similarity features.",
    )
    for index, record in enumerate(records, start=1):
        feature_cache[record.model_id] = graph_similarity_features(
            record,
            use_directed_metrics=use_directed_metrics,
        )
        _report_progress(
            progress,
            phase="features",
            current=index,
            total=total_records,
            message=f"Computed {index} of {total_records} feature sets.",
        )

    pairs: list[GraphSimilarPair] = []
    total_pairs = pair_count(len(records))
    _report_progress(
        progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning graph similarity pairs."
    )
    for index, (left, right) in enumerate(combinations(records, 2), start=1):
        metrics = graph_similarity_metrics_from_features(
            feature_cache[left.model_id],
            feature_cache[right.model_id],
            use_directed_metrics=use_directed_metrics,
        )
        score = weighted_score(metrics, weights)
        if score >= threshold:
            pairs.append(GraphSimilarPair(left.model_id, right.model_id, score, metrics))
        _report_pair_progress(progress, index, total_pairs, "graph similarity pair(s) scanned")

    pairs.sort(key=lambda pair: pair.score, reverse=True)
    _report_progress(
        progress,
        phase="done",
        current=total_pairs,
        total=total_pairs,
        message=f"Graph similarity found {len(pairs)} pairs.",
    )
    return pairs


def graph_isomorphism_pairs(
    dataset: Dataset,
    *,
    mode: IsomorphismMode = "structure",
    ignore_direction: bool = False,
    match_parallel_edge_multiplicity: bool = True,
    timeout_seconds: float = ISOMORPHISM_TIMEOUT_SECONDS,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    """Find topologically identical graphs, skipping individual timed-out checks."""
    if timeout_seconds <= 0:
        raise ValueError("isomorphism timeout_seconds must be greater than 0.")
    records = list(dataset)
    if len(records) < 2:
        return []

    prepared_records = [
        (
            record,
            _graph_for_isomorphism(
                record.graph,
                ignore_direction=ignore_direction,
                match_parallel_edge_multiplicity=match_parallel_edge_multiplicity,
            ),
        )
        for record in records
    ]
    buckets: dict[tuple[int, int], list[tuple[ModelRecord, Any]]] = defaultdict(list)
    for record, graph in prepared_records:
        # Equal node and edge counts are necessary (but not sufficient) for
        # isomorphism, so never compare models across these size buckets.
        buckets[(graph.number_of_nodes(), graph.number_of_edges())].append((record, graph))

    candidates = [pair for bucket in buckets.values() for pair in combinations(bucket, 2)]
    pairs: list[SimilarPair] = []
    total_pairs = len(candidates)
    _report_progress(
        progress, phase="pair_scan", current=0, total=total_pairs, message="Scanning graph isomorphism candidates."
    )
    timed_out = 0
    for checked, ((left, left_graph), (right, right_graph)) in enumerate(candidates, start=1):
        isomorphic = _prepared_graphs_are_isomorphic_with_timeout(left_graph, right_graph, timeout_seconds)
        if isomorphic is None:
            timed_out += 1
        elif isomorphic:
            pairs.append(SimilarPair(left.model_id, right.model_id, 1.0, "graph_isomorphism_structure"))
        suffix = f"; {timed_out} timed out" if timed_out else ""
        _report_pair_progress(progress, checked, total_pairs, f"isomorphism candidate pair(s) checked{suffix}")

    _report_progress(
        progress,
        phase="done",
        current=total_pairs,
        total=total_pairs,
        message=f"Graph isomorphism found {len(pairs)} pairs; skipped {timed_out} timed-out check(s).",
    )
    return pairs


def graph_embedding_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.9,
    dimensions: int = 32,
    walk_length: int = 5,
    num_walks: int = 5,
    workers: int = 1,
    seed: int = 42,
    embedding_cache_dir: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    """Train or reload vectors from one shared Node2Vec feature graph.

    Vectors are stored under ``.mcp4cm_embeddings/<dataset>/<graph_id>/node2vec.npz``
    by default.  Pass ``embedding_cache_dir`` to select the directory that contains
    the dataset folders.
    """
    records = list(dataset)
    if len(records) < 2:
        return []

    np = _require_numpy()
    _validate_graph_embedding_parameters(
        threshold=threshold,
        dimensions=dimensions,
        walk_length=walk_length,
        num_walks=num_walks,
        workers=workers,
    )
    _report_progress(
        progress,
        phase="embedding",
        current=0,
        total=len(records),
        message="Loading or training one shared Node2Vec model.",
    )
    corpus_fingerprint = _cache_fingerprint("|".join(_graph_cache_fingerprint(record) for record in records))
    metadata = _node2vec_cache_metadata(corpus_fingerprint, dimensions, walk_length, num_walks, workers, seed)
    embeddings = []
    for record in records:
        cache_path = _embedding_cache_path(embedding_cache_dir, dataset, record, "node2vec")
        embedding = _load_embedding(cache_path, metadata, np)
        embeddings.append(embedding)
    if any(embedding is None for embedding in embeddings):
        graph, model_nodes = _shared_node2vec_graph(records)
        Node2Vec = require_node2vec()
        if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
            embeddings = [np.zeros(dimensions, dtype=float) for _ in records]
        else:
            print("Training one shared Node2Vec model for all graphs with total nodes:", graph.number_of_nodes(), "total edges:", graph.number_of_edges())
            model = Node2Vec(graph, dimensions=dimensions, walk_length=walk_length, num_walks=num_walks, workers=workers, quiet=True, seed=seed).fit(window=5, min_count=1, batch_words=4, seed=seed)
            embeddings = [_pooled_node_embeddings(model, model_nodes[record.model_id], np, dimensions) for record in records]
        for record, embedding in zip(records, embeddings, strict=True):
            _save_embedding(_embedding_cache_path(embedding_cache_dir, dataset, record, "node2vec"), embedding, metadata, np)
        action = "Trained shared"
    else:
        action = "Reloaded shared"
    for index, record in enumerate(records, start=1):
        _report_progress(
            progress,
            phase="embedding",
            current=index,
            total=len(records),
            message=(
                f"{action} Node2Vec for {index} of {len(records)} graph(s) "
                f"({_compact_count(record.node_count)} node(s), {_compact_count(record.edge_count)} edge(s))."
            ),
        )

    pairs = _embedding_similarity_pairs(
        records,
        embeddings,
        threshold=threshold,
        technique="graph_embedding",
        progress=progress,
        message="graph embedding pair(s) scanned",
    )
    _report_progress(
        progress,
        phase="done",
        current=pair_count(len(records)),
        total=pair_count(len(records)),
        message=f"Graph embeddings found {len(pairs)} pairs.",
    )
    return pairs


def _validate_graph_embedding_parameters(
    *,
    threshold: float,
    dimensions: int,
    walk_length: int,
    num_walks: int,
    workers: int,
) -> None:
    if not 0 <= threshold <= 1:
        raise ValueError("graphEmbeddingThreshold must be between 0 and 1.")
    if dimensions < 1:
        raise ValueError("graphEmbeddingDimensions must be greater than 0.")
    if walk_length < 1:
        raise ValueError("graphEmbeddingWalkLength must be greater than 0.")
    if num_walks < 1:
        raise ValueError("graphEmbeddingNumWalks must be greater than 0.")
    if workers < 1:
        raise ValueError("graphEmbeddingWorkers must be greater than 0.")


def bert_semantic_similarity_pairs(
    dataset: Dataset,
    *,
    threshold: float = DEFAULT_SENTENCE_SIMILARITY_THRESHOLD,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    batch_size: int = 8,
    max_length: int = 256,
    semantic_text_mode: TfidfTokenMode = "names_types_bag",
    embedding_cache_dir: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> list[SimilarPair]:
    records = list(dataset)
    if len(records) < 2:
        return []
    if batch_size < 1:
        raise ValueError("bertBatchSize must be greater than 0.")
    if max_length < 1:
        raise ValueError("bertMaxLength must be greater than 0.")

    np = _require_numpy()

    texts = [
        " ".join(record_tokens(record, token_mode=semantic_text_mode))
        or record.text_for_similarity(include_types=True)
        or record_text(record, include_types=True)
        for record in records
    ]
    embeddings: list[Any | None] = []
    missing: list[tuple[int, ModelRecord, str, Path, dict[str, Any]]] = []
    for index, (record, text) in enumerate(zip(records, texts, strict=True)):
        metadata = _bert_cache_metadata(record, text, model_name, max_length, semantic_text_mode)
        cache_path = _embedding_cache_path(embedding_cache_dir, dataset, record, "bert")
        embedding = _load_embedding(cache_path, metadata, np)
        embeddings.append(embedding)
        if embedding is None:
            missing.append((index, record, text, cache_path, metadata))

    total_batches = math.ceil(len(missing) / batch_size)
    _report_progress(
        progress,
        phase="embedding",
        current=0,
        total=total_batches,
        message=(
            "Reloaded all BERT semantic embeddings."
            if not missing
            else "Loading or computing BERT semantic embeddings."
        ),
    )
    if missing:
        SentenceTransformer = require_sentence_transformers()
        _report_progress(progress, phase="load_model", current=0, total=1, message=f"Loading {model_name}.")
        model = SentenceTransformer(model_name)
        model.max_seq_length = max_length
        _report_progress(progress, phase="load_model", current=1, total=1, message=f"Loaded {model_name}.")
        for batch_index, start in enumerate(range(0, len(missing), batch_size), start=1):
            batch_items = missing[start : start + batch_size]
            batch_embeddings = model.encode(
                [item[2] for item in batch_items], batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
            )
            for item, embedding in zip(batch_items, batch_embeddings, strict=True):
                index, _record, _text, cache_path, metadata = item
                vector = np.asarray(embedding, dtype=float)
                embeddings[index] = vector
                _save_embedding(cache_path, vector, metadata, np)
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
    _report_progress(
        progress,
        phase="done",
        current=pair_count(len(records)),
        total=pair_count(len(records)),
        message=f"BERT semantic similarity found {len(pairs)} pairs.",
    )
    return pairs


def are_graphs_isomorphic(
    left: ModelRecord,
    right: ModelRecord,
    *,
    mode: IsomorphismMode = "structure",
    ignore_direction: bool = False,
    match_parallel_edge_multiplicity: bool = True,
    timeout_seconds: float = ISOMORPHISM_TIMEOUT_SECONDS,
) -> bool:
    if timeout_seconds <= 0:
        raise ValueError("isomorphism timeout_seconds must be greater than 0.")
    left_graph = _graph_for_isomorphism(
        left.graph,
        ignore_direction=ignore_direction,
        match_parallel_edge_multiplicity=match_parallel_edge_multiplicity,
    )
    right_graph = _graph_for_isomorphism(
        right.graph,
        ignore_direction=ignore_direction,
        match_parallel_edge_multiplicity=match_parallel_edge_multiplicity,
    )

    return _prepared_graphs_are_isomorphic_with_timeout(left_graph, right_graph, timeout_seconds) is True


def _prepared_graphs_are_isomorphic(left_graph: Any, right_graph: Any) -> bool:
    if (
        left_graph.number_of_nodes() != right_graph.number_of_nodes()
        or left_graph.number_of_edges() != right_graph.number_of_edges()
    ):
        return False
    return require_networkx().is_isomorphic(left_graph, right_graph)


def _prepared_graphs_are_isomorphic_with_timeout(
    left_graph: Any, right_graph: Any, timeout_seconds: float
) -> bool | None:
    """Return ``None`` when a single pair exceeds the isomorphism time budget."""
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer"):
        return _isomorphism_with_signal_timeout(left_graph, right_graph, timeout_seconds)
    return _isomorphism_with_process_timeout(left_graph, right_graph, timeout_seconds)


def _isomorphism_with_signal_timeout(left_graph: Any, right_graph: Any, timeout_seconds: float) -> bool | None:
    def raise_timeout(_signum, _frame) -> None:
        raise IsomorphismCheckTimeout

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    started = time.monotonic()
    try:
        return _prepared_graphs_are_isomorphic(left_graph, right_graph)
    except IsomorphismCheckTimeout:
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        previous_delay, previous_interval = previous_timer
        if previous_delay:
            remaining_delay = max(previous_delay - (time.monotonic() - started), 0.0)
            signal.setitimer(signal.ITIMER_REAL, remaining_delay, previous_interval)


def _isomorphism_in_child(left_graph: Any, right_graph: Any, result_queue) -> None:
    try:
        result_queue.put(("result", _prepared_graphs_are_isomorphic(left_graph, right_graph)))
    except Exception as exc:  # pragma: no cover - exercised only from worker-thread callers
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _isomorphism_with_process_timeout(left_graph: Any, right_graph: Any, timeout_seconds: float) -> bool | None:
    """Use a child process where signal-based interruption is unavailable (for example a web worker thread)."""
    context = multiprocessing.get_context()
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_isomorphism_in_child, args=(left_graph, right_graph, result_queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        return None
    try:
        status, value = result_queue.get(timeout=1)
    except Empty as exc:
        raise RuntimeError("Isomorphism worker exited without a result.")
    finally:
        result_queue.close()
    if status == "error":
        raise RuntimeError(f"Isomorphism worker failed: {value}")
    return bool(value)


def graph_similarity_features(
    record: ModelRecord,
    *,
    use_directed_metrics: bool = False,
) -> GraphSimilarityFeatures:
    labels = extract_node_labels(record)
    node_name_set = frozenset(label.normalized_name for label in labels if label.normalized_name)
    node_type_set = frozenset(label.normalized_type for label in labels if label.normalized_type)
    edge_type_set = frozenset(edge_types(record))
    in_degree: Counter[int] | None = None
    out_degree: Counter[int] | None = None
    if use_directed_metrics:
        in_degree = in_degree_histogram(record)
        out_degree = out_degree_histogram(record)
    return GraphSimilarityFeatures(
        node_names=node_name_set,
        node_types=node_type_set,
        edge_types=edge_type_set,
        degree_histogram=degree_histogram(record),
        node_count=record.node_count,
        edge_count=record.edge_count,
        density=graph_density(record),
        in_degree_histogram=in_degree,
        out_degree_histogram=out_degree,
    )


def graph_similarity_metrics_from_features(
    left: GraphSimilarityFeatures,
    right: GraphSimilarityFeatures,
    *,
    use_directed_metrics: bool = False,
) -> dict[str, float]:
    metrics = {
        "node_name_jaccard": jaccard(left.node_names, right.node_names),
        "node_type_jaccard": jaccard(left.node_types, right.node_types),
        "edge_type_jaccard": jaccard(left.edge_types, right.edge_types),
        "degree_histogram_similarity": cosine_counter(left.degree_histogram, right.degree_histogram),
        "size_similarity": cached_size_similarity(left, right),
        "density_similarity": cached_density_similarity(left, right),
    }
    if use_directed_metrics:
        metrics["in_degree_histogram_similarity"] = cosine_counter(
            left.in_degree_histogram or Counter(),
            right.in_degree_histogram or Counter(),
        )
        metrics["out_degree_histogram_similarity"] = cosine_counter(
            left.out_degree_histogram or Counter(),
            right.out_degree_histogram or Counter(),
        )
    return metrics


def graph_similarity_metrics(
    left: ModelRecord,
    right: ModelRecord,
    *,
    use_directed_metrics: bool = False,
) -> dict[str, float]:
    return graph_similarity_metrics_from_features(
        graph_similarity_features(left, use_directed_metrics=use_directed_metrics),
        graph_similarity_features(right, use_directed_metrics=use_directed_metrics),
        use_directed_metrics=use_directed_metrics,
    )


def default_graph_similarity_weights(*, use_directed_metrics: bool = False) -> dict[str, float]:
    if use_directed_metrics:
        return {
            "node_name_jaccard": 0.20,
            "node_type_jaccard": 0.15,
            "edge_type_jaccard": 0.15,
            "degree_histogram_similarity": 0.10,
            "in_degree_histogram_similarity": 0.15,
            "out_degree_histogram_similarity": 0.15,
            "size_similarity": 0.15,
            "density_similarity": 0.10,
        }
    return {
        "node_name_jaccard": 0.25,
        "node_type_jaccard": 0.20,
        "edge_type_jaccard": 0.15,
        "degree_histogram_similarity": 0.15,
        "size_similarity": 0.15,
        "density_similarity": 0.10,
    }


def vote_duplicate_pairs(
    dataset: Dataset,
    *,
    min_votes: int = 3,
    tfidf_name_threshold: float = 0.9,
    tfidf_name_type_threshold: float = 0.9,
    graph_threshold: float = 0.85,
    isomorphism_mode: IsomorphismMode = "structure",
) -> list[DuplicateDecision]:
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


def _with_compacted_parallel_edges(record: ModelRecord) -> ModelRecord:
    nx = require_networkx()
    return ModelRecord(
        model_id=record.model_id,
        language=record.language,
        graph=_compact_parallel_edges(record.graph, nx),
        labels=record.labels,
        name=record.name,
        source_path=record.source_path,
        raw_text=record.raw_text,
        raw_xmi=record.raw_xmi,
        metadata=dict(record.metadata),
    )


def node_name_fingerprint(record: ModelRecord, algorithm: str = "sha256") -> str:
    return hash_tokens(hashable_name_tokens(record, include_types=False), algorithm=algorithm)


def node_name_type_fingerprint(record: ModelRecord, algorithm: str = "sha256") -> str:
    return hash_tokens(hashable_name_tokens(record, include_types=True), algorithm=algorithm)


def flatten_duplicate_groups(groups: Iterable[DuplicateGroup]) -> set[str]:
    return {model_id for group in groups for model_id in group.model_ids}


def hashable_name_tokens(
    record: ModelRecord,
    *,
    include_types: bool,
    deduplicate_name_tokens: bool = False,
) -> list[str]:
    tokens: list[str] = []
    for label in extract_node_labels(record):
        if not label.normalized_name:
            continue
        if include_types:
            tokens.append(f"{label.normalized_name}\t{label.normalized_type}")
        else:
            tokens.append(label.normalized_name)
    tokens = sorted(set(tokens)) if deduplicate_name_tokens else sorted(tokens)
    return tokens


def record_tokens(record: ModelRecord, *, token_mode: TfidfTokenMode) -> list[str]:
    if token_mode == "names":
        return node_names(record)

    if token_mode == "names_types_bag":
        pairs = sorted(node_name_type_pairs(record))
        tokens: list[str] = []
        for name, node_type in pairs:
            tokens.append(name)
            if node_type:
                tokens.append(node_type)
        tokens.extend(edge_types(record))
        return tokens

    if token_mode == "typed_name_pairs":
        pairs = sorted(node_name_type_pairs(record))
        return [typed_name_pair_token(name, node_type) for name, node_type in pairs]

    raise ValueError(f"Unsupported TF-IDF token mode: {token_mode}")


def typed_name_pair_token(name: str, node_type: str) -> str:
    return f"type_{tfidf_atomic_token(node_type or 'untyped')}__name_{tfidf_atomic_token(name)}"


def tfidf_atomic_token(value: str) -> str:
    token = re.sub(r"\W+", "_", value.strip(), flags=re.UNICODE).strip("_")
    return token or "empty"


def node_name_type_pairs(record: ModelRecord) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for label in extract_node_labels(record):
        if not label.normalized_name:
            continue
        pairs.append((label.normalized_name, label.normalized_type))
    return pairs


def hash_name_tokens(record: ModelRecord, tokens: Iterable[str], *, include_types: bool) -> str:
    return hash_tokens(tokens)


def _embedding_cache_path(
    embedding_cache_dir: Path | str | None, dataset: Dataset, record: ModelRecord, technique: str
) -> Path:
    """Return a path scoped to dataset and graph, without permitting path traversal."""
    root = Path(embedding_cache_dir) if embedding_cache_dir is not None else Path(".mcp4cm_embeddings")
    return root / quote(str(dataset.dataset_type), safe="._-") / quote(record.model_id, safe="._-") / f"{technique}.npz"


def _node2vec_cache_metadata(
    corpus_fingerprint: str, dimensions: int, walk_length: int, num_walks: int, workers: int, seed: int
) -> dict[str, Any]:
    return {
        "version": 2,
        "technique": "node2vec_shared",
        "corpus": corpus_fingerprint,
        "dimensions": dimensions,
        "walk_length": walk_length,
        "num_walks": num_walks,
        "workers": workers,
        "seed": seed,
    }


def _bert_cache_metadata(
    record: ModelRecord, text: str, model_name: str, max_length: int, semantic_text_mode: str
) -> dict[str, Any]:
    return {
        "version": 2,
        "technique": "sentence_transformer",
        "model_name": model_name,
        "max_length": max_length,
        "semantic_text_mode": semantic_text_mode,
        "text": _cache_fingerprint(text),
        "model_id": record.model_id,
    }


def _graph_cache_fingerprint(record: ModelRecord) -> str:
    graph = record.graph
    payload = {
        "directed": graph.is_directed(),
        # Node2Vec consumes the graph's iteration order, so retain it in the
        # fingerprint instead of treating equivalent reordered graphs as cache hits.
        "nodes": [str(node) for node in graph.nodes()],
        "edges": [(str(left), str(right)) for left, right in graph.edges()],
    }
    return _cache_fingerprint(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _cache_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_embedding(path: Path, expected_metadata: dict[str, Any], np):
    try:
        with np.load(path, allow_pickle=False) as payload:
            metadata = json.loads(str(payload["metadata"].item()))
            if metadata != expected_metadata:
                return None
            return np.asarray(payload["embedding"], dtype=float)
    except (FileNotFoundError, KeyError, OSError, ValueError, json.JSONDecodeError):
        return None


def _save_embedding(path: Path, embedding, metadata: dict[str, Any], np) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".npz", dir=path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        np.savez_compressed(
            temporary_path,
            embedding=np.asarray(embedding, dtype=float),
            metadata=json.dumps(metadata, sort_keys=True),
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _shared_node2vec_graph(records: list[ModelRecord]):
    nx = require_networkx()
    graph = nx.DiGraph() if any(record.graph.is_directed() for record in records) else nx.Graph()
    model_nodes: dict[str, list[str]] = {}
    for record in records:
        lookup: dict[object, str] = {}
        nodes: list[str] = []
        for node_id, attrs in record.graph.nodes(data=True):
            node = _embedded_model_node_id(record.model_id, node_id)
            lookup[node_id] = node
            nodes.append(node)
            graph.add_node(node)
            for kind, value in (("name", node_name_attr(attrs)), ("type", node_type_attr(attrs))):
                if value:
                    feature = _embedding_feature_node(kind, value)
                    graph.add_edge(node, feature)
                    if graph.is_directed():
                        graph.add_edge(feature, node)
        for source, target, attrs in record.graph.edges(data=True):
            if source in lookup and target in lookup:
                graph.add_edge(lookup[source], lookup[target])
                edge_type = edge_type_attr(attrs)
                if edge_type:
                    feature = _embedding_feature_node("edge_type", edge_type)
                    graph.add_edge(lookup[source], feature)
                    graph.add_edge(feature, lookup[target])
        model_nodes[record.model_id] = nodes
    return graph, model_nodes


def _embedded_model_node_id(model_id: str, node_id: object) -> str:
    return f"model::{model_id}::node::{node_id}"


def _embedding_feature_node(kind: str, value: str) -> str:
    return f"feature::{kind}::{value}"


def _pooled_node_embeddings(model, nodes: list[str], np, dimensions: int):
    vectors = [model.wv[node] for node in nodes if node in model.wv]
    return np.mean(vectors, axis=0) if vectors else np.zeros(dimensions, dtype=float)


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
    graph = nx.DiGraph() if record.graph.is_directed() else nx.Graph()
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
    return sorted(label.normalized_name for label in extract_node_labels(record) if label.normalized_name)


def node_types(record: ModelRecord) -> list[str]:
    return sorted(label.normalized_type for label in extract_node_labels(record) if label.normalized_type)


def edge_types(record: ModelRecord) -> list[str]:
    return sorted(
        normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))
        for _, _, attrs in record.graph.edges(data=True)
        if normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))
    )


def node_type_attr(attrs: dict[str, object]) -> str:
    return normalize_type(raw_node_type(attrs))


def node_name_attr(attrs: dict[str, object]) -> str:
    return normalize_name(raw_node_name(attrs))


def edge_type_attr(attrs: dict[str, object]) -> str:
    return normalize(attrs.get("type") or attrs.get("relationship") or attrs.get("label"))


def _graph_for_isomorphism(
    graph: Any,
    *,
    ignore_direction: bool,
    match_parallel_edge_multiplicity: bool,
):
    nx = require_networkx()
    prepared = graph.copy(as_view=False)

    if ignore_direction and prepared.is_directed():
        prepared = nx.MultiGraph(prepared) if prepared.is_multigraph() else nx.Graph(prepared)

    if match_parallel_edge_multiplicity:
        return prepared

    collapsed = nx.DiGraph() if prepared.is_directed() else nx.Graph()

    collapsed.add_nodes_from(prepared.nodes(data=True))
    for source, target, attrs in prepared.edges(data=True):
        edge_type = edge_type_attr(attrs)
        if collapsed.has_edge(source, target):
            existing_type = edge_type_attr(collapsed.edges[source, target])
            if existing_type == edge_type:
                continue
        collapsed.add_edge(source, target, type=edge_type)

    return collapsed


def _compact_parallel_edges(graph: Any, nx):
    if not graph.is_multigraph():
        return graph

    compact = nx.MultiDiGraph() if graph.is_directed() else nx.MultiGraph()
    compact.add_nodes_from(graph.nodes(data=True))
    grouped: dict[tuple[Any, Any, str], dict[str, Any]] = {}

    for source, target, _, attrs in graph.edges(keys=True, data=True):
        edge_type = edge_type_attr(attrs)
        key_left, key_right = (source, target) if graph.is_directed() else tuple(sorted((source, target)))
        dedupe_key = (key_left, key_right, edge_type)
        if dedupe_key not in grouped:
            grouped[dedupe_key] = {"attrs": dict(attrs), "count": 0, "source": source, "target": target}
        grouped[dedupe_key]["count"] += 1

    for item in grouped.values():
        attrs = dict(item["attrs"])
        attrs["parallelMultiplicity"] = int(item["count"])
        compact.add_edge(item["source"], item["target"], **attrs)

    return compact


def degree_histogram(record: ModelRecord) -> Counter[int]:
    return Counter(dict(record.graph.degree()).values())


def in_degree_histogram(record: ModelRecord) -> Counter[int]:
    if not record.graph.is_directed():
        return degree_histogram(record)
    return Counter(dict(record.graph.in_degree()).values())


def out_degree_histogram(record: ModelRecord) -> Counter[int]:
    if not record.graph.is_directed():
        return degree_histogram(record)
    return Counter(dict(record.graph.out_degree()).values())


def size_similarity(left: ModelRecord, right: ModelRecord) -> float:
    node_score = ratio_similarity(left.node_count, right.node_count)
    edge_score = ratio_similarity(left.edge_count, right.edge_count)
    return (node_score + edge_score) / 2


def density_similarity(left: ModelRecord, right: ModelRecord) -> float:
    left_density = graph_density(left)
    right_density = graph_density(right)
    denominator = max(left_density, right_density, 1e-12)
    return 1 - (abs(left_density - right_density) / denominator)


def cached_size_similarity(left: GraphSimilarityFeatures, right: GraphSimilarityFeatures) -> float:
    node_score = ratio_similarity(left.node_count, right.node_count)
    edge_score = ratio_similarity(left.edge_count, right.edge_count)
    return (node_score + edge_score) / 2


def cached_density_similarity(left: GraphSimilarityFeatures, right: GraphSimilarityFeatures) -> float:
    denominator = max(left.density, right.density, 1e-12)
    return 1 - (abs(left.density - right.density) / denominator)


def graph_density(record: ModelRecord) -> float:
    node_count = record.node_count
    if node_count <= 1:
        return 0.0
    directed_denominator = node_count * (node_count - 1)
    if record.graph.is_directed():
        return record.edge_count / directed_denominator
    undirected_denominator = node_count * (node_count - 1) / 2
    return record.edge_count / max(undirected_denominator, 1)


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
    return sum(metrics.get(name, 0.0) * weight for name, weight in weights.items()) / total_weight


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
    progress(
        {
            "phase": phase,
            "current": current,
            "total": total,
            "percent": progress_percent(current, total, clamp=True),
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


def _compact_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def hash_tokens(tokens: Iterable[str], algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    for token in sorted(tokens):
        hasher.update(token.encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def hash_tokens_in_order(tokens: Iterable[str], algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    for token in tokens:
        hasher.update(token.encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def normalize(value: object) -> str:
    return normalize_label(value)


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
