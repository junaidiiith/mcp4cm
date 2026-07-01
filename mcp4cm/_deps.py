from __future__ import annotations


def require_networkx():
    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError(
            "mcp4cm requires networkx for graph loading. Install dependencies with "
            "`pip install -r requirements.txt` or `pip install -e .`."
        ) from exc
    return nx


def require_sklearn():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise ImportError(
            "TF-IDF duplicate detection requires scikit-learn. Install dependencies with "
            "`pip install -r requirements.txt` or `pip install -e .`."
        ) from exc
    return TfidfVectorizer, cosine_similarity


def require_node2vec():
    try:
        from node2vec import Node2Vec
    except ImportError as exc:
        raise ImportError(
            "Graph embedding duplicate detection requires node2vec. Install ML dependencies with "
            "`pip install -e '.[ml]'`."
        ) from exc
    return Node2Vec


def require_transformers_torch():
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise ImportError(
            "BERT semantic duplicate detection requires transformers and torch. Install ML dependencies with "
            "`pip install -e '.[ml]'`."
        ) from exc
    return AutoTokenizer, AutoModel, torch


def require_sentence_transformers():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "Semantic duplicate detection requires sentence-transformers. Install ML dependencies with "
            "`pip install -e '.[ml]'`."
        ) from exc
    return SentenceTransformer


def require_gnn_dependencies():
    """Load the optional dependencies used by the contrastive GNN pipeline."""
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "GNN duplicate detection requires torch and sentence-transformers. Install ML dependencies with "
            "`pip install -e '.[ml]'`."
        ) from exc
    return torch, SentenceTransformer
