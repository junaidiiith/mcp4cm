from __future__ import annotations

from collections import Counter
import math
import warnings
from statistics import mean, median
from typing import Any

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.name_classification import classify_name_slot


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
    return [str(attrs.get("name")) for _, attrs in record.graph.nodes(data=True) if attrs.get("name")]


def _model_visualization_row(record: ModelRecord) -> dict[str, Any]:
    entries = typed_name_entries(record)
    names = [entry["name"] for entry in entries if not entry["missing"]]
    semantic_names = [entry["name"] for entry in entries if entry["classification"] == "semantic"]
    tokens = [token for name in names for token in name.split()]
    missing_names = sum(1 for entry in entries if entry["missing"])
    classification_counts = Counter(str(entry["classification"]) for entry in entries)
    name_counts = Counter(names)
    dominant_name, dominant_count = name_counts.most_common(1)[0] if name_counts else ("", 0)
    named_count = len(names)
    return {
        "id": str(record.model_id),
        "entries": entries,
        "nameSlots": len(entries),
        "missingNames": missing_names,
        "namedElements": len(entries) - missing_names,
        "missingNameRatio": missing_names / len(entries) if entries else 0,
        "semanticNameCount": len(semantic_names),
        "classificationCounts": classification_counts,
        "dominantName": dominant_name,
        "dominantNameCount": dominant_count,
        "dominantNameRatio": dominant_count / named_count if named_count else 0,
        "uniqueNames": len(set(names)),
        "tokens": len(tokens),
        "uniqueTokens": len(set(tokens)),
        "text": " ".join(tokens),
    }


def typed_name_entries(record: ModelRecord) -> list[dict[str, Any]]:
    entries = []
    for _, attrs in record.graph.nodes(data=True):
        if "name" not in attrs:
            continue
        result = classify_name_slot(attrs.get("name"), attrs.get("type") or attrs.get("eClass") or "unknown")
        entries.append(
            {
                "type": result.normalized_type or "unknown",
                "name": result.normalized_name,
                "missing": result.missing,
                "typePlaceholder": result.type_like,
                "classification": result.classification,
            }
        )
    return entries


def counter_items(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


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


def ratio_bands(values: list[float], *, bands: tuple[float, ...] = (0, 0.01, 0.1, 0.3, 0.7, 1.0)) -> list[dict[str, Any]]:
    if not values:
        return []
    counts = [0] * (len(bands) - 1)
    for value in values:
        for index in range(len(bands) - 1):
            lower, upper = bands[index], bands[index + 1]
            if lower <= value <= upper if index == len(bands) - 2 else lower <= value < upper:
                counts[index] += 1
                break
    return [
        {
            "start": bands[index],
            "end": bands[index + 1],
            "count": count,
            "displayCount": count,
        }
        for index, count in enumerate(counts)
    ]


def semantic_name_count_bands(values: list[int]) -> list[dict[str, Any]]:
    labels = [("0", 0, 1), ("1-4", 1, 5), ("5-9", 5, 10), ("10-24", 10, 25), ("25+", 25, math.inf)]
    return [
        {"label": label, "count": sum(1 for value in values if lower <= value < upper)}
        for label, lower, upper in labels
    ]


def ratio_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"models": 0, "zero": 0, "median": 0, "p90": 0, "above30": 0, "above70": 0}
    ordered = sorted(values)
    return {
        "models": len(values),
        "zero": sum(1 for value in values if value == 0),
        "median": percentile_float(ordered, 0.5),
        "p90": percentile_float(ordered, 0.9),
        "above30": sum(1 for value in values if value >= 0.3),
        "above70": sum(1 for value in values if value >= 0.7),
    }


def percentile_float(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(values[lower], 6)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 6)


def classification_items(counter: Counter[str]) -> list[dict[str, Any]]:
    labels = (("semantic", "Semantic"), ("missing", "Missing"), ("placeholder", "Placeholder"), ("type_like", "Type-like"))
    return [{"label": label, "key": key, "count": int(counter.get(key, 0))} for key, label in labels]


def vocabulary_ranking_items(
    occurrence_counter: Counter[str],
    document_frequency_counter: Counter[str],
    classification_counters: dict[str, Counter[str]],
    *,
    model_count: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for name, occurrences in occurrence_counter.most_common(limit):
        doc_frequency = int(document_frequency_counter.get(name, 0))
        counts = classification_counters.get(name, Counter())
        semantic = int(counts.get("semantic", 0))
        placeholder = int(counts.get("placeholder", 0))
        type_like = int(counts.get("type_like", 0))
        rows.append(
            {
                "name": name,
                "occurrences": int(occurrences),
                "documentFrequency": doc_frequency,
                "coverage": round(doc_frequency / model_count, 6) if model_count else 0,
                "occurrencesPerModel": round(occurrences / model_count, 6) if model_count else 0,
                "occurrencesPerUsedModel": round(occurrences / doc_frequency, 6) if doc_frequency else 0,
                "semantic": semantic,
                "placeholder": placeholder,
                "typeLike": type_like,
                "classification": vocabulary_classification_label(semantic, placeholder, type_like),
            }
        )
    return rows


def vocabulary_classification_label(semantic: int, placeholder: int, type_like: int) -> str:
    counts = {"semantic": semantic, "placeholder": placeholder, "typeLike": type_like}
    non_zero = [key for key, value in counts.items() if value > 0]
    if not non_zero:
        return "unknown"
    if len(non_zero) > 1:
        return "mixed"
    return non_zero[0]


def vocabulary_summary(
    occurrence_counter: Counter[str],
    document_frequency_counter: Counter[str],
    classification_counters: dict[str, Counter[str]],
) -> dict[str, Any]:
    semantic_names = sum(1 for counts in classification_counters.values() if counts.get("semantic", 0) > 0)
    placeholder_or_type_like_names = sum(
        1
        for counts in classification_counters.values()
        if counts.get("placeholder", 0) > 0 or counts.get("type_like", 0) > 0
    )
    most_reused_name, most_reused_count = document_frequency_counter.most_common(1)[0] if document_frequency_counter else ("", 0)
    return {
        "uniqueNames": len(occurrence_counter),
        "totalOccurrences": int(sum(occurrence_counter.values())),
        "semanticNames": semantic_names,
        "placeholderOrTypeLikeNames": placeholder_or_type_like_names,
        "singletonNames": sum(1 for count in document_frequency_counter.values() if count == 1),
        "mostReusedName": most_reused_name,
        "mostReusedDocumentFrequency": int(most_reused_count),
    }


def name_reuse_distribution(document_frequency_counter: Counter[str], model_count: int) -> list[dict[str, Any]]:
    if not document_frequency_counter:
        return []
    dynamic_upper = max(100, model_count)
    bands = [
        ("1", 1, 2),
        ("2-5", 2, 6),
        ("6-20", 6, 21),
        ("21-100", 21, 101),
        ("101+", 101, dynamic_upper + 1),
    ]
    values = list(document_frequency_counter.values())
    return [
        {"label": label, "count": sum(1 for value in values if lower <= value < upper)}
        for label, lower, upper in bands
    ]


def type_quality_items(
    type_counters: dict[str, Counter[str]],
    total_counter: Counter[str],
    *,
    sort_counter: Counter[str] | None = None,
    sort_classification: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = []
    labels = list(total_counter.keys())
    if sort_classification:
        labels.sort(
            key=lambda label: (
                type_counters.get(label, Counter()).get(sort_classification, 0),
                total_counter.get(label, 0),
                label,
            ),
            reverse=True,
        )
    elif sort_counter:
        labels.sort(key=lambda label: (sort_counter.get(label, 0), total_counter.get(label, 0), label), reverse=True)
    else:
        labels = [label for label, _ in total_counter.most_common()]
    if limit is not None:
        labels = labels[:limit]
    for element_type in labels:
        counts = type_counters.get(element_type, Counter())
        total = total_counter.get(element_type, sum(counts.values()))
        rows.append(
            {
                "type": element_type,
                "total": int(total),
                "semantic": int(counts.get("semantic", 0)),
                "missing": int(counts.get("missing", 0)),
                "placeholder": int(counts.get("placeholder", 0)),
                "typeLike": int(counts.get("type_like", 0)),
            }
        )
    return rows


def model_quality_watchlists(rows: list[dict[str, Any]], *, limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    return {
        "fewSemanticNames": sorted(
            rows,
            key=lambda item: (item["semanticNames"], -item["missingRatio"], item["id"]),
        )[:limit],
        "highMissingRatio": sorted(
            rows,
            key=lambda item: (item["missingRatio"], item["nameSlots"], item["id"]),
            reverse=True,
        )[:limit],
        "highNameDominance": sorted(
            [row for row in rows if row["dominantName"]],
            key=lambda item: (item["dominantNameRatio"], item["nameSlots"], item["id"]),
            reverse=True,
        )[:limit],
    }


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


TOPIC_MODEL_MODEL_LIMIT = 500
SCATTER_POINT_LIMIT = 2000


def model_summary_fields(record: ModelRecord) -> dict[str, Any]:
    row = _model_visualization_row(record)
    return {
        "modelId": str(record.model_id or ""),
        "name": str(record.name or ""),
        "path": str(record.source_path or ""),
        "language": str(record.language or ""),
        "nodeCount": int(record.node_count),
        "edgeCount": int(record.edge_count),
        "nameSlots": int(row["nameSlots"]),
        "missingNames": int(row["missingNames"]),
        "missingNameRatio": float(row["missingNameRatio"]),
        "namedElements": int(row["namedElements"]),
        "uniqueNames": int(row["uniqueNames"]),
        "tokens": int(row["tokens"]),
        "uniqueTokens": int(row["uniqueTokens"]),
    }


class CorpusStatisticsAccumulator:
    """Collect corpus-level statistics while models are already in memory during parse."""

    def __init__(self) -> None:
        self.node_counts: list[int] = []
        self.edge_counts: list[int] = []
        self.name_slot_counts: list[int] = []
        self.name_count_values: list[int] = []
        self.missing_ratios: list[float] = []
        self.languages: Counter[str] = Counter()
        self.labels: Counter[str] = Counter()
        self.type_counter: Counter[str] = Counter()
        self.name_counter: Counter[str] = Counter()
        self.entry_type_counter: Counter[str] = Counter()
        self.classification_counter: Counter[str] = Counter()
        self.type_quality_counter: dict[str, Counter[str]] = {}
        self.semantic_name_counts: list[int] = []
        self.model_quality_rows: list[dict[str, Any]] = []
        self.concept_counter: Counter[str] = Counter()
        self.filtered_concept_counter: Counter[str] = Counter()
        self.concept_doc_freq: Counter[str] = Counter()
        self.filtered_concept_doc_freq: Counter[str] = Counter()
        self.concept_classification_counter: dict[str, Counter[str]] = {}
        self.type_concept_counter: dict[str, Counter[str]] = {}
        self.type_token_counter: dict[str, Counter[str]] = {}
        self.scatter_rows: list[dict[str, Any]] = []
        self.topic_model_rows: list[dict[str, Any]] = []
        self.sample_models: list[dict[str, Any]] = []
        self.unique_name_doc_freq: Counter[str] = Counter()

    def add(self, record: ModelRecord) -> None:
        self.node_counts.append(record.node_count)
        self.edge_counts.append(record.edge_count)
        self.languages[record.language] += 1
        for label in record.labels:
            self.labels[label] += 1
        for type_name in record.types:
            if type_name:
                self.type_counter[str(type_name)] += 1
        for name in node_names(record):
            stripped = name.strip()
            if stripped:
                self.name_counter[stripped] += 1

        row = _model_visualization_row(record)
        self.name_slot_counts.append(int(row["nameSlots"]))
        self.semantic_name_counts.append(int(row["semanticNameCount"]))
        self.name_count_values.append(len(node_names(record)))
        if row["nameSlots"]:
            self.missing_ratios.append(float(row["missingNameRatio"]))
        for classification, count in row["classificationCounts"].items():
            self.classification_counter[str(classification)] += int(count)

        if row["nameSlots"] or record.node_count:
            self.model_quality_rows.append(
                {
                    "id": str(record.model_id),
                    "nameSlots": int(row["nameSlots"]),
                    "semanticNames": int(row["semanticNameCount"]),
                    "missingRatio": round(float(row["missingNameRatio"]), 4),
                    "dominantName": str(row["dominantName"]),
                    "dominantNameRatio": round(float(row["dominantNameRatio"]), 4),
                }
            )

        if len(self.scatter_rows) < SCATTER_POINT_LIMIT:
            self.scatter_rows.append(
                {
                    "id": row["id"],
                    "namedElements": row["namedElements"],
                    "uniqueNames": row["uniqueNames"],
                    "tokens": row["tokens"],
                    "uniqueTokens": row["uniqueTokens"],
                    "nameSlots": row["nameSlots"],
                    "missingNames": row["missingNames"],
                    "missingNameRatio": row["missingNameRatio"],
                }
            )

        if len(self.topic_model_rows) < TOPIC_MODEL_MODEL_LIMIT:
            self.topic_model_rows.append(row)

        if len(self.sample_models) < 8:
            self.sample_models.append(
                {
                    "id": str(record.model_id),
                    "language": str(record.language),
                    "nodes": record.node_count,
                    "edges": record.edge_count,
                    "names": len(node_names(record)),
                }
            )

        model_concepts: set[str] = set()
        filtered_concepts: set[str] = set()
        model_names: set[str] = set()
        for entry in row["entries"]:
            element_type = str(entry["type"])
            classification = str(entry["classification"])
            self.entry_type_counter[element_type] += 1
            type_quality = self.type_quality_counter.setdefault(element_type, Counter())
            type_quality[classification] += 1
            if entry["missing"]:
                continue
            concept = str(entry["name"])
            self.concept_counter[concept] += 1
            concept_classifications = self.concept_classification_counter.setdefault(concept, Counter())
            concept_classifications[classification] += 1
            model_names.add(concept)
            type_concepts = self.type_concept_counter.setdefault(element_type, Counter())
            type_concepts[concept] += 1
            token_counter = self.type_token_counter.setdefault(element_type, Counter())
            for token in concept.split():
                token_counter[token] += 1
            model_concepts.add(concept)
            if not entry["typePlaceholder"]:
                self.filtered_concept_counter[concept] += 1
                filtered_concepts.add(concept)
        for concept in model_concepts:
            self.concept_doc_freq[concept] += 1
        for concept in filtered_concepts:
            self.filtered_concept_doc_freq[concept] += 1
        self.unique_name_doc_freq.update(model_names)

    def build_payload(self, *, skip_topic_model: bool = False, topic_model_skip_reason: str = "") -> dict[str, Any]:
        model_count = len(self.node_counts)
        return {
            "summary": {
                "models": model_count,
                "languages": dict(self.languages),
                "labels": dict(self.labels),
                "nodes": _distribution(self.node_counts),
                "edges": _distribution(self.edge_counts),
                "names": _distribution(self.name_count_values),
            },
            "topTypes": counter_items(self.type_counter),
            "topNames": counter_items(self.name_counter),
            "visualizations": self._build_visualizations(
                model_count,
                skip_topic_model=skip_topic_model,
                topic_model_skip_reason=topic_model_skip_reason,
            ),
            "sampleModels": self.sample_models,
        }

    def _build_visualizations(
        self,
        model_count: int,
        *,
        skip_topic_model: bool = False,
        topic_model_skip_reason: str = "",
    ) -> dict[str, Any]:
        major_types = [label for label, _ in self.entry_type_counter.most_common(6)]
        type_links: list[dict[str, Any]] = []
        for element_type in major_types:
            concepts = self.type_concept_counter.get(element_type, Counter())
            type_links.extend(
                {"type": element_type, "concept": concept, "count": count}
                for concept, count in concepts.most_common(8)
            )

        type_counter = self.entry_type_counter
        heatmap_types = [label for label, _ in type_counter.most_common(10)]
        token_counter: Counter[str] = Counter()
        for element_type in heatmap_types:
            token_counter.update(self.type_token_counter.get(element_type, Counter()))
        heatmap_tokens = [label for label, _ in token_counter.most_common(25)]
        heatmap_rows = []
        for element_type in heatmap_types:
            counts = self.type_token_counter.get(element_type, Counter())
            total = sum(counts.values()) or 1
            heatmap_rows.append(
                {
                    "label": element_type,
                    "values": [round(counts[token] / total, 5) for token in heatmap_tokens],
                }
            )

        topic_result: dict[str, Any]
        if skip_topic_model:
            topic_result = {
                "available": False,
                "reason": topic_model_skip_reason or "Topic modeling skipped for this statistics snapshot.",
            }
        elif model_count > TOPIC_MODEL_MODEL_LIMIT:
            topic_result = {
                "available": False,
                "reason": f"Topic modeling skipped for datasets with more than {TOPIC_MODEL_MODEL_LIMIT} models.",
            }
        else:
            topic_result = topic_model(self.topic_model_rows)

        scatter_points = self.scatter_rows
        if model_count > len(scatter_points):
            scatter_note = f"Showing {len(scatter_points)} of {model_count} models."
        else:
            scatter_note = ""

        return {
            "missingNameRatioHistogram": histogram(self.missing_ratios, bins=30, minimum=0, maximum=1),
            "missingNameRatioBands": ratio_bands(self.missing_ratios),
            "missingNameRatioSummary": ratio_summary(self.missing_ratios),
            "nameClassificationOverview": classification_items(self.classification_counter),
            "elementTypeQualityMatrix": type_quality_items(
                self.type_quality_counter,
                self.entry_type_counter,
                sort_classification="semantic",
            ),
            "semanticNameCountHistogram": semantic_name_count_bands(self.semantic_name_counts),
            "modelQualityWatchlists": model_quality_watchlists(self.model_quality_rows),
            "topConcepts": counter_items(self.concept_counter),
            "topConceptDocumentFrequency": counter_items(self.concept_doc_freq),
            "topConceptsWithoutTypePlaceholders": counter_items(self.filtered_concept_counter),
            "topConceptDocumentFrequencyWithoutTypePlaceholders": counter_items(self.filtered_concept_doc_freq),
            "vocabularySummary": vocabulary_summary(
                self.concept_counter,
                self.concept_doc_freq,
                self.concept_classification_counter,
            ),
            "vocabularyRanking": vocabulary_ranking_items(
                self.concept_counter,
                self.concept_doc_freq,
                self.concept_classification_counter,
                model_count=model_count,
            ),
            "nameReuseDistribution": name_reuse_distribution(self.concept_doc_freq, model_count),
            "elementTypeTreemap": counter_items(self.entry_type_counter, 40),
            "vocabularyHeatmap": {"tokens": heatmap_tokens, "rows": heatmap_rows},
            "typeConceptLinks": type_links,
            "modelVocabularyScatter": scatter_points,
            "scatterNote": scatter_note,
            "topicModel": topic_result,
            "nameCountBoxplot": boxplot_summary(self.name_slot_counts),
            "nameCountHistogramLog": histogram(self.name_slot_counts, bins=30, log_counts=True),
            "fewNamesHistogram": histogram([count for count in self.name_slot_counts if count < 5], bins=20),
            "topNamesPerModel": counter_items(self.unique_name_doc_freq, 20),
            "languageDistribution": counter_items(self.languages, 25),
        }
