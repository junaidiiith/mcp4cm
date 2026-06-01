from __future__ import annotations

from collections import Counter
import math
import re
import warnings
from statistics import mean, median
from typing import Any

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.xmi_names import EMPTY_NAME_SENTINEL, normalize_identifier


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    node_counts = [record.node_count for record in dataset]
    edge_counts = [record.edge_count for record in dataset]
    model_name_counts = [len(node_names(record)) for record in dataset]
    return {
        "models": len(dataset),
        "languages": dict(Counter(record.language for record in dataset)),
        "labels": dict(Counter(label for record in dataset for label in record.labels)),
        "nodes": _distribution(node_counts),
        "edges": _distribution(edge_counts),
        "names": _distribution(model_name_counts),
    }


def type_counts(dataset: Dataset) -> Counter[str]:
    return Counter(type_name for record in dataset for type_name in record.types if type_name)


def name_counts(dataset: Dataset) -> Counter[str]:
    return Counter(name.strip() for record in dataset for name in node_names(record) if name.strip())


def model_statistics(record: ModelRecord) -> dict[str, Any]:
    return {
        "id": record.model_id,
        "language": record.language,
        "labels": record.labels,
        "nodes": record.node_count,
        "edges": record.edge_count,
        "names": len(node_names(record)),
        "types": dict(Counter(record.types)),
    }


def node_names(record: ModelRecord) -> list[str]:
    extracted_names = record.metadata.get("extracted_names") if isinstance(record.metadata, dict) else None
    if isinstance(extracted_names, list):
        return [str(name) for name in extracted_names if str(name).strip()]
    return [str(attrs.get("name")) for _, attrs in record.graph.nodes(data=True) if attrs.get("name")]


def dataset_visualizations(dataset: Dataset) -> dict[str, Any]:
    """Build visualization data without writing intermediate text files."""
    models = [_model_visualization_row(record) for record in dataset]
    entries = [entry for model in models for entry in model["entries"]]
    valid_entries = [entry for entry in entries if not entry["missing"]]
    filtered_entries = [entry for entry in valid_entries if not entry["typePlaceholder"]]
    name_slots = [model["nameSlots"] for model in models]
    missing_ratios = [model["missingNameRatio"] for model in models if model["nameSlots"]]

    return {
        "missingNameRatioHistogram": histogram(missing_ratios, bins=30, minimum=0, maximum=1),
        "missingNamesByType": counter_items(Counter(entry["type"] for entry in entries if entry["missing"])),
        "topConcepts": counter_items(Counter(entry["name"] for entry in valid_entries)),
        "topConceptDocumentFrequency": document_frequency(models, exclude_type_placeholders=False),
        "topConceptsWithoutTypePlaceholders": counter_items(Counter(entry["name"] for entry in filtered_entries)),
        "topConceptDocumentFrequencyWithoutTypePlaceholders": document_frequency(models, exclude_type_placeholders=True),
        "elementTypeTreemap": counter_items(Counter(entry["type"] for entry in entries), 40),
        "vocabularyHeatmap": vocabulary_heatmap(filtered_entries),
        "typeConceptLinks": type_concept_links(filtered_entries),
        "modelVocabularyScatter": [
            {
                "id": model["id"],
                "namedElements": model["namedElements"],
                "uniqueNames": model["uniqueNames"],
                "tokens": model["tokens"],
                "uniqueTokens": model["uniqueTokens"],
                "nameSlots": model["nameSlots"],
                "missingNames": model["missingNames"],
                "missingNameRatio": model["missingNameRatio"],
            }
            for model in models
        ],
        "topicModel": topic_model(models),
        "nameCountBoxplot": boxplot_summary(name_slots),
        "nameCountHistogramLog": histogram(name_slots, bins=30, log_counts=True),
        "fewNamesHistogram": histogram([count for count in name_slots if count < 5], bins=20),
        "topNamesPerModel": unique_name_frequency(models),
        "languageDistribution": counter_items(Counter(record.language for record in dataset), 25),
    }


def _model_visualization_row(record: ModelRecord) -> dict[str, Any]:
    entries = typed_name_entries(record)
    names = [entry["name"] for entry in entries if not entry["missing"]]
    tokens = [token for name in names for token in name.split()]
    missing_names = sum(1 for entry in entries if entry["missing"])
    return {
        "id": str(record.model_id),
        "entries": entries,
        "nameSlots": len(entries),
        "missingNames": missing_names,
        "namedElements": len(entries) - missing_names,
        "missingNameRatio": missing_names / len(entries) if entries else 0,
        "uniqueNames": len(set(names)),
        "tokens": len(tokens),
        "uniqueTokens": len(set(tokens)),
        "text": " ".join(tokens),
    }


def typed_name_entries(record: ModelRecord) -> list[dict[str, Any]]:
    typed_names = record.metadata.get("extracted_typed_names") if isinstance(record.metadata, dict) else None
    if isinstance(typed_names, list):
        pairs = [split_typed_name(str(value)) for value in typed_names]
    else:
        pairs = [
            (
                normalize_identifier(attrs.get("type") or attrs.get("eClass") or "unknown"),
                normalize_identifier(attrs.get("name")),
            )
            for _, attrs in record.graph.nodes(data=True)
            if "name" in attrs
        ]
    return [
        {
            "type": element_type or "unknown",
            "name": name,
            "missing": name == EMPTY_NAME_SENTINEL or not name,
            "typePlaceholder": is_type_placeholder_name(element_type, name),
        }
        for element_type, name in pairs
    ]


def split_typed_name(value: str) -> tuple[str, str]:
    element_type, separator, name = value.partition(":")
    return (element_type.strip() or "unknown", name.strip() if separator else element_type.strip())


def is_type_placeholder_name(element_type: str, name: str) -> bool:
    if not element_type or not name or name == EMPTY_NAME_SENTINEL:
        return False
    normalized_type = normalize_identifier(element_type)
    normalized_name = normalize_identifier(name)
    if normalized_name == normalized_type:
        return True
    return bool(re.fullmatch(rf"{re.escape(normalized_type.replace(' ', ''))}\d+", normalized_name.replace(" ", "")))


def counter_items(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def document_frequency(models: list[dict[str, Any]], *, exclude_type_placeholders: bool) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for model in models:
        counter.update(
            {
                entry["name"]
                for entry in model["entries"]
                if not entry["missing"] and (not exclude_type_placeholders or not entry["typePlaceholder"])
            }
        )
    return counter_items(counter)


def unique_name_frequency(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for model in models:
        counter.update({entry["name"] for entry in model["entries"] if not entry["missing"]})
    return counter_items(counter, 20)


def histogram(values: list[float | int], *, bins: int, minimum: float | None = None, maximum: float | None = None, log_counts: bool = False) -> list[dict[str, Any]]:
    if not values:
        return []
    low = min(values) if minimum is None else minimum
    high = max(values) if maximum is None else maximum
    if high <= low:
        high = low + 1
    width = (high - low) / max(bins, 1)
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / width), bins - 1)
        counts[max(index, 0)] += 1
    return [
        {
            "start": round(low + index * width, 4),
            "end": round(low + (index + 1) * width, 4),
            "count": count,
            "displayCount": round(math.log10(count + 1), 4) if log_counts else count,
        }
        for index, count in enumerate(counts)
    ]


def boxplot_summary(values: list[int]) -> dict[str, float]:
    if not values:
        return {"min": 0, "q1": 0, "median": 0, "q3": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "q1": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.5),
        "q3": percentile(ordered, 0.75),
        "max": ordered[-1],
    }


def percentile(values: list[int], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def vocabulary_heatmap(entries: list[dict[str, Any]]) -> dict[str, Any]:
    type_counter = Counter(entry["type"] for entry in entries)
    types = [label for label, _ in type_counter.most_common(10)]
    token_counter = Counter(token for entry in entries if entry["type"] in types for token in entry["name"].split())
    tokens = [label for label, _ in token_counter.most_common(25)]
    rows = []
    for element_type in types:
        counts = Counter(token for entry in entries if entry["type"] == element_type for token in entry["name"].split())
        total = sum(counts.values()) or 1
        rows.append({"label": element_type, "values": [round(counts[token] / total, 5) for token in tokens]})
    return {"tokens": tokens, "rows": rows}


def type_concept_links(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    major_types = [label for label, _ in Counter(entry["type"] for entry in entries).most_common(6)]
    links: list[dict[str, Any]] = []
    for element_type in major_types:
        concepts = Counter(entry["name"] for entry in entries if entry["type"] == element_type)
        links.extend(
            {"type": element_type, "concept": concept, "count": count}
            for concept, count in concepts.most_common(8)
        )
    return links


def topic_model(models: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [model["text"] for model in models]
    if len(texts) < 2 or not any(texts):
        return {"available": False, "reason": "Topic modeling requires at least two models with named elements."}
    try:
        import numpy as np
        from sklearn.decomposition import NMF, TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=1.0, sublinear_tf=True)
        matrix = vectorizer.fit_transform(texts)
        topic_count = min(8, matrix.shape[0], matrix.shape[1])
        if topic_count < 1:
            return {"available": False, "reason": "Topic modeling found no usable vocabulary."}
        model = NMF(n_components=topic_count, init="nndsvda", random_state=42, max_iter=600)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            weights = model.fit_transform(matrix)
        feature_names = np.array(vectorizer.get_feature_names_out())
        labels = [
            f"Topic {index}: {', '.join(feature_names[np.argsort(row)[::-1][:4]])}"
            for index, row in enumerate(model.components_)
        ]
        if matrix.shape[0] >= 2 and matrix.shape[1] >= 2:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                projection = TruncatedSVD(n_components=2, random_state=42).fit_transform(matrix)
        else:
            projection = np.column_stack((np.arange(matrix.shape[0]), np.zeros(matrix.shape[0])))
        return {
            "available": True,
            "projectionMethod": "TruncatedSVD",
            "points": [
                {
                    "id": models[index]["id"],
                    "x": round(float(projection[index, 0]), 6),
                    "y": round(float(projection[index, 1]), 6),
                    "topic": labels[int(weights[index].argmax())],
                    "topicStrength": round(float(weights[index].max()), 6),
                    "namedElements": models[index]["namedElements"],
                    "uniqueNames": models[index]["uniqueNames"],
                }
                for index in range(len(models))
            ],
            "prevalence": [
                {"label": label, "count": round(float(value), 6)}
                for label, value in zip(labels, weights.mean(axis=0), strict=True)
            ],
        }
    except Exception as exc:
        return {"available": False, "reason": f"Topic modeling unavailable: {exc}"}


def _distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "median": median(values),
    }
