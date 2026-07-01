"""Unsupervised GraphCL-style graph embeddings for duplicate detection.

This module is intentionally separate from the Node2Vec detector.  Node and edge
text are sentence-encoded, then an edge-aware message-passing network is trained
against two augmented views of each graph using an NT-Xent contrastive objective.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mcp4cm._deps import require_gnn_dependencies
from mcp4cm.core import Dataset
from mcp4cm.name_classification import normalize_name, normalize_type
from mcp4cm.utils import pair_count, progress_percent

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class GNNTrainingConfig:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 128
    layers: int = 2
    epochs: int = 20
    learning_rate: float = 1e-3
    temperature: float = 0.2
    edge_dropout: float = 0.15
    feature_mask_rate: float = 0.10
    batch_size: int = 32
    seed: int = 42
    device: str = "auto"

    def validate(self) -> None:
        if self.embedding_dim < 1 or self.layers < 1 or self.epochs < 1 or self.batch_size < 1:
            raise ValueError("GNN embedding_dim, layers, epochs, and batch_size must be greater than 0.")
        if self.learning_rate <= 0 or self.temperature <= 0:
            raise ValueError("GNN learning_rate and temperature must be greater than 0.")
        if not 0 <= self.edge_dropout < 1 or not 0 <= self.feature_mask_rate < 1:
            raise ValueError("GNN edge_dropout and feature_mask_rate must be in [0, 1).")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("GNN device must be one of: auto, cpu, cuda.")


def gnn_graph_embeddings(
    dataset: Dataset,
    *,
    config: GNNTrainingConfig | None = None,
    embedding_cache_dir: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Train/reload one normalized vector per graph; cache scope is whole corpus."""
    config = config or GNNTrainingConfig()
    config.validate()
    records = list(dataset)
    if not records:
        return {}
    corpus = _fingerprint("|".join(_record_fingerprint(record) for record in records))
    metadata = {"version": 1, "technique": "contrastive_gnn", "corpus": corpus, "config": asdict(config)}
    cached = {
        record.model_id: _load_vector(_cache_path(embedding_cache_dir, dataset, record), metadata)
        for record in records
    }
    if all(vector is not None for vector in cached.values()):
        _report(progress, "embedding", len(records), len(records), "Reloaded cached contrastive GNN graph embeddings.")
        return cached  # type: ignore[return-value]

    torch, SentenceTransformer = require_gnn_dependencies()
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    device = _resolve_device(torch, config.device)
    _report(progress, "text_embedding", 0, 1, f"Loading sentence encoder {config.model_name}.")
    text_encoder = SentenceTransformer(config.model_name, device=str(device))
    graphs, input_dim = _tensorize_graphs(records, text_encoder, torch, device, config.batch_size)
    _report(progress, "text_embedding", 1, 1, "Created sentence-transformer node and edge embeddings.")
    encoder = _edge_aware_encoder(torch, input_dim, config.embedding_dim, config.layers).to(device)
    optimizer = torch.optim.AdamW(encoder.parameters(), lr=config.learning_rate, weight_decay=1e-5)
    encoder.train()
    batches = [graphs[index:index + config.batch_size] for index in range(0, len(graphs), config.batch_size)]
    for epoch in range(1, config.epochs + 1):
        total_loss = 0.0
        for batch in batches:
            left = torch.stack([encoder(graph, config.edge_dropout, config.feature_mask_rate) for graph in batch])
            right = torch.stack([encoder(graph, config.edge_dropout, config.feature_mask_rate) for graph in batch])
            loss = (
                1 - torch.nn.functional.cosine_similarity(left[0], right[0], dim=0)
                if len(batch) == 1
                else _nt_xent(torch, left, right, config.temperature)
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach().cpu())
        _report(
            progress,
            "training",
            epoch,
            config.epochs,
            f"Trained contrastive GNN epoch {epoch}/{config.epochs}; loss={total_loss / len(batches):.4f}.",
        )
    encoder.eval()
    result: dict[str, Any] = {}
    with torch.no_grad():
        for index, (record, graph) in enumerate(zip(records, graphs, strict=True), start=1):
            vector = encoder(graph, 0.0, 0.0).detach().cpu().numpy()
            result[record.model_id] = vector
            _save_vector(_cache_path(embedding_cache_dir, dataset, record), vector, metadata)
            _report(progress, "embedding", index, len(records), f"Generated GNN embedding {index}/{len(records)}.")
    return result


def gnn_duplicate_pairs(
    dataset: Dataset,
    *,
    threshold: float = 0.85,
    config: GNNTrainingConfig | None = None,
    embedding_cache_dir: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> list[tuple[str, str, float]]:
    if not 0 <= threshold <= 1:
        raise ValueError("gnnThreshold must be between 0 and 1.")
    records = list(dataset)
    if len(records) < 2:
        return []
    vectors = gnn_graph_embeddings(dataset, config=config, embedding_cache_dir=embedding_cache_dir, progress=progress)
    pairs = []
    total = pair_count(len(records))
    for index, (left, right) in enumerate(combinations(records, 2), start=1):
        score = _cosine(vectors[left.model_id], vectors[right.model_id])
        if score >= threshold:
            pairs.append((left.model_id, right.model_id, score))
        _report(progress, "pair_scan", index, total, "GNN graph embedding pair(s) scanned.")
    return sorted(pairs, key=lambda item: item[2], reverse=True)


def _tensorize_graphs(records, text_encoder, torch, device, batch_size):
    import numpy as np

    node_texts, edge_texts, layouts = [], [], []
    for record in records:
        nodes = list(record.graph.nodes(data=True))
        lookup = {node: index for index, (node, _) in enumerate(nodes)}
        node_start, edge_start = len(node_texts), len(edge_texts)
        node_texts.extend(_node_text(attrs) for _, attrs in nodes)
        edges = [
            (lookup[source], lookup[target], attrs)
            for source, target, attrs in record.graph.edges(data=True)
            if source in lookup and target in lookup
        ]
        edge_texts.extend(_edge_text(attrs) for _, _, attrs in edges)
        layouts.append((len(nodes), edges, node_start, edge_start))
    node_vectors = text_encoder.encode(
        node_texts or [""], batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
    )
    edge_vectors = text_encoder.encode(
        edge_texts or [""], batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
    )
    input_dim, graphs = int(node_vectors.shape[1]), []
    for node_count, edges, node_start, edge_start in layouts:
        x = torch.tensor(node_vectors[node_start:node_start + node_count], dtype=torch.float32, device=device)
        if not node_count:
            x = torch.zeros((1, input_dim), dtype=torch.float32, device=device)
        indices, features = [], []
        for offset, (source, target, _attrs) in enumerate(edges):
            feature = edge_vectors[edge_start + offset]
            indices.extend(((source, target), (target, source)))
            features.extend((feature, feature))
        if indices:
            edge_index = torch.tensor(indices, dtype=torch.long, device=device).t().contiguous()
            edge_attr = torch.tensor(np.asarray(features, dtype=np.float32), dtype=torch.float32, device=device)
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long, device=device)
            edge_attr = torch.empty((0, input_dim), dtype=torch.float32, device=device)
        graphs.append((x, edge_index, edge_attr))
    return graphs, input_dim


def _edge_aware_encoder(torch, input_dim, output_dim, layers):
    class Encoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.node_input = torch.nn.Linear(input_dim, output_dim)
            self.edge_input = torch.nn.Linear(input_dim, output_dim)
            self.layers = torch.nn.ModuleList(
                [torch.nn.Sequential(torch.nn.Linear(output_dim, output_dim), torch.nn.ReLU()) for _ in range(layers)]
            )
            self.project = torch.nn.Sequential(
                torch.nn.Linear(output_dim * 2, output_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(output_dim, output_dim),
            )

        def forward(self, graph, edge_dropout, feature_mask_rate):
            x, edge_index, edge_attr = graph
            x = self.node_input(x)
            if self.training and feature_mask_rate:
                x = x * (torch.rand_like(x) >= feature_mask_rate)
            edge = self.edge_input(edge_attr) if edge_attr.numel() else edge_attr.new_empty((0, x.shape[1]))
            for layer in self.layers:
                messages = x.new_zeros(x.shape)
                if edge_index.shape[1]:
                    keep = torch.ones(edge_index.shape[1], dtype=torch.bool, device=x.device)
                    if self.training and edge_dropout:
                        keep = torch.rand(edge_index.shape[1], device=x.device) >= edge_dropout
                    source, target = edge_index[:, keep]
                    messages.index_add_(0, target, x[source] + edge[keep])
                    degree = x.new_zeros((x.shape[0], 1))
                    degree.index_add_(0, target, torch.ones((target.shape[0], 1), device=x.device))
                    messages = messages / degree.clamp_min(1)
                x = layer(x + messages)
            pooled = torch.cat((x.mean(dim=0), x.max(dim=0).values))
            return torch.nn.functional.normalize(self.project(pooled), dim=0)
    return Encoder()


def _nt_xent(torch, left, right, temperature):
    vectors = torch.cat((left, right), dim=0)
    similarity = vectors @ vectors.T / temperature
    count = left.shape[0]
    diagonal = torch.eye(2 * count, dtype=torch.bool, device=similarity.device)
    similarity = similarity.masked_fill(diagonal, -float("inf"))
    targets = torch.cat(
        (torch.arange(count, 2 * count, device=similarity.device), torch.arange(count, device=similarity.device))
    )
    return torch.nn.functional.cross_entropy(similarity, targets)


def _node_text(attrs):
    node_type = normalize_type(str(attrs.get("type") or attrs.get("eClass") or "")) or "unknown"
    name = normalize_name(str(attrs.get("name") or attrs.get("label") or "")) or "unnamed"
    return f"node type: {node_type}; name: {name}"


def _edge_text(attrs):
    edge_type = normalize_type(str(attrs.get("type") or attrs.get("relationship") or attrs.get("label") or ""))
    return f"edge type: {edge_type or 'related'}"


def _record_fingerprint(record):
    payload = {
        "nodes": [(str(node), _node_text(attrs)) for node, attrs in record.graph.nodes(data=True)],
        "edges": [
            (str(source), str(target), _edge_text(attrs))
            for source, target, attrs in record.graph.edges(data=True)
        ],
    }
    return _fingerprint(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _cache_path(root, dataset, record):
    base = Path(root) if root is not None else Path(".mcp4cm_embeddings")
    return base / quote(str(dataset.dataset_type), safe="._-") / quote(
        record.model_id, safe="._-"
    ) / "contrastive_gnn.npz"


def _fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_device(torch, requested):
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("GNN CUDA was requested but no CUDA device is available.")
    use_cuda = requested == "cuda" or (requested == "auto" and torch.cuda.is_available())
    return torch.device("cuda" if use_cuda else "cpu")


def _cosine(left, right):
    import numpy as np

    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    return float(np.dot(left, right) / denominator) if denominator else 0.0


def _report(callback, phase, current, total, message):
    if callback:
        callback(
            {
                "phase": phase,
                "current": current,
                "total": total,
                "percent": progress_percent(current, total),
                "message": message,
            }
        )


def _load_vector(path, expected):
    try:
        import numpy as np

        with np.load(path, allow_pickle=False) as payload:
            metadata = json.loads(str(payload["metadata"].item()))
            return payload["embedding"] if metadata == expected else None
    except (FileNotFoundError, KeyError, OSError, ValueError, json.JSONDecodeError):
        return None


def _save_vector(path, vector, metadata):
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".contrastive_gnn-", suffix=".npz", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        np.savez_compressed(temporary, embedding=vector, metadata=json.dumps(metadata, sort_keys=True))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
