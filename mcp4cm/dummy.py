from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from mcp4cm.core import Dataset, ModelRecord

DEFAULT_DUMMY_WORDS = {
    "dummy",
    "test",
    "todo",
    "sample",
    "example",
    "foo",
    "bar",
    "temp",
    "tmp",
    "asdf",
}

UML_DUMMY_KEYWORDS = {
    "my class",
    "class",
    "use case",
    "actor",
    "attribute",
    "association",
    "control flow",
    "activity",
    "decision node",
    "opaque action",
    "lifeline",
    "flow final node",
    "activity final node",
    "join node",
    "fork node",
    "initial node",
    "merge node",
    "action",
    "component",
    "ext point",
    "empty name",
    "package",
}

UML_FREQUENT_DUMMY_NAMES = {"control flow", "control-flow"}

UML_EMPTY_NAME_PATTERN = re.compile(r"empty name", re.IGNORECASE)
UML_EMPTY_CLASS_NAME_PATTERN = re.compile(r"class:\s*empty name", re.IGNORECASE)
UML_COMMENT_PATTERN = re.compile(r"comment:", re.IGNORECASE)
UML_DUMMY_NAME_PATTERN = re.compile(r"^att(\s+[A-Za-z]|\s+\d+|[a-z0-9])?$", re.IGNORECASE)
UML_DUMMY_CLASS_PATTERN = re.compile(r"^class\s?[a-z0-9]$", re.IGNORECASE)
UML_GENERAL_CLASS_PATTERN = re.compile(r"^[a-z]+", re.IGNORECASE)
UML_MYCLASS_PATTERN = re.compile(r"^class:\s*my class\s?(\d+)?$", re.IGNORECASE)
UML_NUMBERED_PATTERN = re.compile(r"(.+?)[\s_]?(\d+)$", re.IGNORECASE)
UML_TWO_CHAR_PATTERN = re.compile(r"^[a-zA-Z]\d$", re.IGNORECASE)
UML_LETTER_SPACE_LETTER_PATTERN = re.compile(r"^[a-zA-Z]\s[a-zA-Z]$", re.IGNORECASE)

UML_SEQUENTIAL_THRESHOLD = 0.75
UML_DUMMY_WORD_THRESHOLD = 0.82
UML_SHORT_DUMMY_WORD_THRESHOLD = 0.3
UML_MIN_MEDIAN_SHORT_NAME_LENGTH = 4
UML_MIN_NAMES_COUNT = 5
UML_VOCABULARY_UNIQUENESS_THRESHOLD = 3
UML_GENERIC_PATTERN_THRESHOLD_COUNT = 2
UML_DUMMY_CLASSES_THRESHOLD = 0.13
UML_DUMMY_NAMES_THRESHOLD = 0.0
UML_TWO_CHAR_NAMES_THRESHOLD = 0.3
UML_SHORT_NAMES_UPPER_THRESHOLD = 0.30
UML_SHORT_NAMES_LOWER_THRESHOLD = 0.25
UML_STOPWORDS_THRESHOLD = 0.4
UML_MIN_SHORT_NAME_LENGTH = 2
UML_MIN_MEDIAN_NAME_LENGTH = 4
UML_TFIDF_DUPLICATE_THRESHOLD = 0.8

ARCHIMATE_DUMMY_KEYWORDS = {
    "(new model)",
    "asdf",
    "bar",
    "default",
    "demo",
    "dummy",
    "empty name",
    "example",
    "foo",
    "ipsum",
    "lorem",
    "my model",
    "new model",
    "no name",
    "placeholder",
    "sample",
    "temp",
    "test",
    "tmp",
    "todo",
    "untitled",
}

ARCHIMATE_NEW_MODEL_NAMES = {"(new model)", "new model", "archimate model", "model"}
ARCHIMATE_GENERIC_NUMBERED_PATTERN = re.compile(
    r"^(aggregate|application service|business role|class|database|entity|method|microservice|node|service|system|table)\s*[-_]?\s*\d+$",
    re.IGNORECASE,
)
ARCHIMATE_CRUD_OR_CODE_PATTERN = re.compile(
    r"^(create|read|update|delete|get|set|return|equals|compare|check)\s*\(?|^[<>]=?$|^[-+*/=]$",
    re.IGNORECASE,
)

ARCHIMATE_MIN_NAMES_COUNT = 5
ARCHIMATE_DUMMY_KEYWORD_THRESHOLD = 0.70
ARCHIMATE_TYPE_NAME_THRESHOLD = 0.60
ARCHIMATE_GENERIC_NUMBERED_THRESHOLD = 0.25
ARCHIMATE_CRUD_OR_CODE_THRESHOLD = 0.25
ARCHIMATE_VOCABULARY_UNIQUENESS_THRESHOLD = 3
ARCHIMATE_SHORT_NAME_THRESHOLD = 0.35

ECORE_DUMMY_KEYWORDS = {
    "asdf",
    "bar",
    "default",
    "demo",
    "dummy",
    "empty name",
    "example",
    "foo",
    "ipsum",
    "lorem",
    "my class",
    "my model",
    "new model",
    "no name",
    "placeholder",
    "sample",
    "temp",
    "test",
    "tmp",
    "todo",
    "untitled",
}

ECORE_GENERIC_NUMBERED_PATTERN = re.compile(
    r"^(attribute|class|datatype|element|entity|enum|literal|model|operation|package|parameter|reference|type)\s*[-_]?\s*\d+$",
    re.IGNORECASE,
)

ECORE_MIN_NAMES_COUNT = 5
ECORE_DUMMY_KEYWORD_THRESHOLD = 0.50
ECORE_GENERIC_NUMBERED_THRESHOLD = 0.30
ECORE_TYPE_NAME_THRESHOLD = 0.60
ECORE_VOCABULARY_UNIQUENESS_THRESHOLD = 3
ECORE_SHORT_NAME_THRESHOLD = 0.40


@dataclass(frozen=True, slots=True)
class DummyFinding:
    model_id: str
    reason: str
    score: float
    evidence: tuple[str, ...] = ()


Filter = Callable[[ModelRecord], DummyFinding | None]


@dataclass(frozen=True, slots=True)
class FilterSummary:
    filter_name: str
    filtered_count: int
    remaining_count: int
    findings: tuple[DummyFinding, ...]


def detect_dummy_models(dataset: Dataset, filters: Iterable[Filter] | None = None) -> list[DummyFinding]:
    shared_filters = tuple(filters) if filters is not None else None
    findings: list[DummyFinding] = []
    for record in dataset:
        active_filters = shared_filters or filters_for_language(record.language)
        for filter_fn in active_filters:
            finding = filter_fn(record)
            if finding:
                findings.append(finding)
                break
    return findings


def summarize_filters(dataset: Dataset, filters: Iterable[Filter] | None = None, cumulative: bool = True) -> list[FilterSummary]:
    """Count how many models are caught by each dummy filter."""

    records = list(dataset)
    active_filters = tuple(filters) if filters is not None else _dataset_filters(records)
    remaining = records
    summaries: list[FilterSummary] = []
    for filter_fn in active_filters:
        findings = [finding for record in remaining if (finding := filter_fn(record))]
        if cumulative:
            filtered_ids = {finding.model_id for finding in findings}
            remaining = [record for record in remaining if record.model_id not in filtered_ids]
            remaining_count = len(remaining)
        else:
            remaining_count = len(records) - len(findings)
        summaries.append(
            FilterSummary(
                filter_name=filter_name(filter_fn),
                filtered_count=len(findings),
                remaining_count=remaining_count,
                findings=tuple(findings),
            )
        )
    return summaries


def summarize_filters_by_language(dataset: Dataset, cumulative: bool = True) -> dict[str, list[FilterSummary]]:
    """Count dummy-filter matches with each language's own filter chain."""

    groups: dict[str, list[ModelRecord]] = {}
    for record in dataset:
        groups.setdefault(record.language.lower(), []).append(record)
    return {
        language: summarize_filters(
            Dataset(records=records, dataset_type=dataset.dataset_type, root=dataset.root),
            filters=filters_for_language(language),
            cumulative=cumulative,
        )
        for language, records in sorted(groups.items())
    }


def default_filters() -> tuple[Filter, ...]:
    return (
        empty_model_filter(),
        too_few_named_elements_filter(min_names=2),
        dummy_word_filter(),
        generic_sequential_names_filter(),
        short_name_ratio_filter(),
    )


def filters_for_language(language: str) -> tuple[Filter, ...]:
    if language.lower() == "uml":
        return uml_filters()
    if language.lower() == "ecore":
        return ecore_filters()
    if language.lower() == "archimate":
        return archimate_filters()
    return default_filters()


def uml_filters() -> tuple[Filter, ...]:
    return (
        empty_model_filter(),
        uml_empty_class_name_filter(),
        uml_empty_name_filter(),
        too_few_named_elements_filter(min_names=UML_MIN_NAMES_COUNT),
        uml_median_name_length_filter(),
        uml_short_name_or_control_flow_filter(),
        uml_dummy_class_filter(),
        uml_generic_class_name_filter(),
        uml_dummy_name_filter(),
        uml_two_character_dummy_name_filter(),
        uml_dummy_keyword_filter(),
        uml_sequential_numbered_filter(),
        uml_vocabulary_uniqueness_filter(),
    )


def archimate_filters() -> tuple[Filter, ...]:
    return (
        empty_model_filter(),
        too_few_named_elements_filter(min_names=ARCHIMATE_MIN_NAMES_COUNT),
        archimate_new_model_filter(),
        archimate_type_name_filter(),
        archimate_generic_numbered_filter(),
        archimate_dummy_keyword_filter(),
        archimate_crud_or_code_filter(),
        archimate_vocabulary_uniqueness_filter(),
        short_name_ratio_filter(max_length=2, threshold=ARCHIMATE_SHORT_NAME_THRESHOLD),
    )


def ecore_filters() -> tuple[Filter, ...]:
    return (
        empty_model_filter(),
        too_few_named_elements_filter(min_names=ECORE_MIN_NAMES_COUNT),
        ecore_type_name_filter(),
        ecore_generic_numbered_filter(),
        ecore_dummy_keyword_filter(),
        ecore_vocabulary_uniqueness_filter(),
        short_name_ratio_filter(max_length=2, threshold=ECORE_SHORT_NAME_THRESHOLD),
    )


def empty_model_filter() -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        if record.node_count == 0:
            return DummyFinding(record.model_id, "empty_graph", 1.0)
        return None

    return named_filter(check, "empty_model_filter")


def raw_text_pattern_filter(pattern: re.Pattern[str], reason: str) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        matches = tuple(match.group(0) for match in pattern.finditer(record.raw_text))
        if matches:
            return DummyFinding(record.model_id, reason, 1.0, matches[:10])
        return None

    return named_filter(check, reason)


def too_few_named_elements_filter(min_names: int = 2) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = [name for name in record.names if name.strip()]
        if len(names) < min_names:
            return DummyFinding(record.model_id, "too_few_named_elements", 1.0, tuple(names))
        return None

    return named_filter(check, f"too_few_named_elements_filter_min_{min_names}")


def uml_empty_name_filter() -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        hits = [name for name in names if name == "empty name"]
        if not hits and UML_EMPTY_NAME_PATTERN.search(record.raw_text):
            hits = [match.group(0) for match in UML_EMPTY_NAME_PATTERN.finditer(record.raw_text)]
        if hits:
            return DummyFinding(record.model_id, "uml_empty_name", 1.0, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_empty_name_filter")


def uml_empty_class_name_filter() -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        hits = [f"class: {name}" for name in class_names(record) if normalize_name(name) == "empty name"]
        if not hits and UML_EMPTY_CLASS_NAME_PATTERN.search(record.raw_text):
            hits = [match.group(0) for match in UML_EMPTY_CLASS_NAME_PATTERN.finditer(record.raw_text)]
        if hits:
            return DummyFinding(record.model_id, "uml_empty_class_name", 1.0, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_empty_class_name_filter")


def uml_median_name_length_filter(min_median_length: int = UML_MIN_MEDIAN_NAME_LENGTH) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = [name.strip() for name in record.names if name.strip()]
        if not names:
            return None
        lengths = sorted(len(name) for name in names)
        mid = len(lengths) // 2
        median_length = lengths[mid] if len(lengths) % 2 else (lengths[mid - 1] + lengths[mid]) / 2
        if median_length < min_median_length:
            return DummyFinding(record.model_id, "uml_median_name_length_too_short", median_length, tuple(names[:10]))
        return None

    return named_filter(check, "uml_median_name_length_filter")


def uml_short_name_or_control_flow_filter(
    max_length: int = UML_MIN_SHORT_NAME_LENGTH,
    high_short_threshold: float = UML_SHORT_NAMES_UPPER_THRESHOLD,
    low_short_threshold: float = UML_SHORT_NAMES_LOWER_THRESHOLD,
    control_flow_threshold: float = UML_STOPWORDS_THRESHOLD,
) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        short_names = [name for name in names if len(name.strip()) <= max_length]
        control_flow_names = [name for name in names if "control flow" in name]
        short_ratio = len(short_names) / len(names)
        control_flow_ratio = len(control_flow_names) / len(names)
        if short_ratio >= high_short_threshold:
            return DummyFinding(record.model_id, "uml_many_short_names", short_ratio, tuple(short_names[:10]))
        if short_ratio >= low_short_threshold and control_flow_ratio >= control_flow_threshold:
            return DummyFinding(
                record.model_id,
                "uml_short_names_with_control_flow",
                max(short_ratio, control_flow_ratio),
                tuple([*short_names[:5], *control_flow_names[:5]]),
            )
        return None

    return named_filter(check, "uml_short_name_or_control_flow_filter")


def uml_dummy_keyword_filter(
    words: set[str] | None = None,
    threshold: float = UML_DUMMY_WORD_THRESHOLD,
) -> Filter:
    words = {normalize_name(word) for word in (words or UML_DUMMY_KEYWORDS | UML_FREQUENT_DUMMY_NAMES)}

    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if name in words]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "uml_dummy_keywords", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_dummy_keyword_filter")


def uml_dummy_name_filter(threshold: float = UML_DUMMY_NAMES_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if UML_DUMMY_NAME_PATTERN.match(name)]
        if hits:
            ratio = len(hits) / len(names)
            if ratio >= threshold:
                return DummyFinding(record.model_id, "uml_att_dummy_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_dummy_name_filter")


def uml_dummy_class_filter(threshold: float = UML_DUMMY_CLASSES_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = [normalize_name(name) for name in class_names(record)]
        if not names:
            return None
        hits = [name for name in names if UML_DUMMY_CLASS_PATTERN.match(name)]
        ratio = len(hits) / len(names)
        if ratio > threshold:
            return DummyFinding(record.model_id, "uml_dummy_classes", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_dummy_class_filter")


def uml_generic_class_name_filter(threshold_count: int = UML_GENERIC_PATTERN_THRESHOLD_COUNT) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        hits = [f"class: {name}" for name in class_names(record) if normalize_name(name).startswith("my class")]
        if len(hits) > threshold_count:
            return DummyFinding(record.model_id, "uml_generic_my_class_names", float(len(hits)), tuple(hits[:10]))
        return None

    return named_filter(check, "uml_generic_class_name_filter")


def uml_two_character_dummy_name_filter(threshold: float = UML_TWO_CHAR_NAMES_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [
            name
            for name in names
            if UML_TWO_CHAR_PATTERN.match(name) or UML_LETTER_SPACE_LETTER_PATTERN.match(name)
        ]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "uml_two_character_dummy_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_two_character_dummy_name_filter")


def uml_sequential_numbered_filter(threshold: float = UML_SEQUENTIAL_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if UML_NUMBERED_PATTERN.match(name)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "uml_sequential_numbered_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "uml_sequential_numbered_filter")


def uml_short_name_filter(
    min_length: int = UML_MIN_SHORT_NAME_LENGTH,
    threshold: float = UML_SHORT_NAMES_UPPER_THRESHOLD,
) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        short_names = [name for name in names if len(name.replace(" ", "")) <= min_length]
        ratio = len(short_names) / len(names)
        if ratio > threshold:
            return DummyFinding(record.model_id, "uml_short_names", ratio, tuple(short_names[:10]))
        return None

    return named_filter(check, "uml_short_name_filter")


def uml_vocabulary_uniqueness_filter(min_unique_words: int = UML_VOCABULARY_UNIQUENESS_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        words = set()
        for name in record.names:
            words.update(tokenize_name(name))
        if len(words) <= min_unique_words:
            return DummyFinding(record.model_id, "uml_low_vocabulary_uniqueness", 1.0, tuple(sorted(words)))
        return None

    return named_filter(check, "uml_vocabulary_uniqueness_filter")


def archimate_new_model_filter() -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        evidence = tuple(name for name in names[:3] if name in ARCHIMATE_NEW_MODEL_NAMES)
        if evidence:
            return DummyFinding(record.model_id, "archimate_new_model_placeholder", 1.0, evidence)
        return None

    return named_filter(check, "archimate_new_model_filter")


def archimate_type_name_filter(threshold: float = ARCHIMATE_TYPE_NAME_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        comparable: list[tuple[str, str]] = []
        for _, attrs in record.graph.nodes(data=True):
            name = attrs.get("name")
            node_type = attrs.get("type") or attrs.get("eClass")
            if name and node_type:
                comparable.append((normalize_name(str(name)), normalize_name(split_camel_case(str(node_type)))))
        if not comparable:
            return None
        hits = [name for name, node_type in comparable if name == node_type]
        ratio = len(hits) / len(comparable)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "archimate_type_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "archimate_type_name_filter")


def archimate_generic_numbered_filter(threshold: float = ARCHIMATE_GENERIC_NUMBERED_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if ARCHIMATE_GENERIC_NUMBERED_PATTERN.match(name)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "archimate_generic_numbered_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "archimate_generic_numbered_filter")


def archimate_dummy_keyword_filter(threshold: float = ARCHIMATE_DUMMY_KEYWORD_THRESHOLD) -> Filter:
    words = {normalize_name(word) for word in ARCHIMATE_DUMMY_KEYWORDS}

    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if name in words]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "archimate_dummy_keywords", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "archimate_dummy_keyword_filter")


def archimate_crud_or_code_filter(threshold: float = ARCHIMATE_CRUD_OR_CODE_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if ARCHIMATE_CRUD_OR_CODE_PATTERN.match(name)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "archimate_crud_or_code_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "archimate_crud_or_code_filter")


def archimate_vocabulary_uniqueness_filter(min_unique_words: int = ARCHIMATE_VOCABULARY_UNIQUENESS_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        words = set()
        for name in record.names:
            words.update(tokenize_name(name))
        if len(words) < min_unique_words:
            return DummyFinding(record.model_id, "archimate_low_vocabulary_uniqueness", 1.0, tuple(sorted(words)))
        return None

    return named_filter(check, "archimate_vocabulary_uniqueness_filter")


def ecore_type_name_filter(threshold: float = ECORE_TYPE_NAME_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        comparable: list[tuple[str, str]] = []
        for _, attrs in record.graph.nodes(data=True):
            name = attrs.get("name")
            node_type = attrs.get("eClass")
            if name and node_type:
                comparable.append((normalize_name(str(name)), normalize_ecore_type_name(str(node_type))))
        if not comparable:
            return None
        hits = [name for name, node_type in comparable if name == node_type]
        ratio = len(hits) / len(comparable)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "ecore_type_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "ecore_type_name_filter")


def ecore_generic_numbered_filter(threshold: float = ECORE_GENERIC_NUMBERED_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if ECORE_GENERIC_NUMBERED_PATTERN.match(name)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "ecore_generic_numbered_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "ecore_generic_numbered_filter")


def ecore_dummy_keyword_filter(threshold: float = ECORE_DUMMY_KEYWORD_THRESHOLD) -> Filter:
    words = {normalize_name(word) for word in ECORE_DUMMY_KEYWORDS}

    def check(record: ModelRecord) -> DummyFinding | None:
        names = normalized_names(record)
        if not names:
            return None
        hits = [name for name in names if name in words]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "ecore_dummy_keywords", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "ecore_dummy_keyword_filter")


def ecore_vocabulary_uniqueness_filter(min_unique_words: int = ECORE_VOCABULARY_UNIQUENESS_THRESHOLD) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        words = set()
        for name in record.names:
            words.update(tokenize_name(name))
        if len(words) < min_unique_words:
            return DummyFinding(record.model_id, "ecore_low_vocabulary_uniqueness", 1.0, tuple(sorted(words)))
        return None

    return named_filter(check, "ecore_vocabulary_uniqueness_filter")


def dummy_word_filter(words: set[str] | None = None, threshold: float = 0.35) -> Filter:
    words = {word.lower() for word in (words or DEFAULT_DUMMY_WORDS)}

    def check(record: ModelRecord) -> DummyFinding | None:
        names = [name.lower() for name in record.names if name.strip()]
        if not names:
            return None
        hits = [name for name in names if any(word in tokenize_name(name) for word in words)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "dummy_words", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "dummy_word_filter")


def regex_name_filter(pattern: str, threshold: float, include_types: bool = False, flags: int = re.IGNORECASE) -> Filter:
    """Create a dummy filter from a user-provided regex.

    The regex is evaluated against each node name by default. When
    ``include_types`` is true, the tested text is ``"<name> <type>"``.
    A model is flagged when the fraction of matching nodes reaches
    ``threshold``.
    """

    compiled = re.compile(pattern, flags)

    def check(record: ModelRecord) -> DummyFinding | None:
        values = regex_filter_values(record, include_types=include_types)
        if not values:
            return None
        hits = [value for value in values if compiled.search(value)]
        ratio = len(hits) / len(values)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "regex_name_filter", ratio, tuple(hits[:10]))
        return None

    target = "names_types" if include_types else "names"
    return named_filter(check, f"regex_name_filter_{target}")


def generic_sequential_names_filter(threshold: float = 0.5) -> Filter:
    pattern = re.compile(r"^(class|node|element|package|model|entity|attribute|relation|relationship|process|task)\d*$", re.I)

    def check(record: ModelRecord) -> DummyFinding | None:
        names = [compact_name(name) for name in record.names if name.strip()]
        if not names:
            return None
        hits = [name for name in names if pattern.match(name)]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "generic_sequential_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "generic_sequential_names_filter")


def short_name_ratio_filter(max_length: int = 2, threshold: float = 0.6) -> Filter:
    def check(record: ModelRecord) -> DummyFinding | None:
        names = [name.strip() for name in record.names if name.strip()]
        if not names:
            return None
        hits = [name for name in names if len(name) <= max_length]
        ratio = len(hits) / len(names)
        if ratio >= threshold:
            return DummyFinding(record.model_id, "mostly_short_names", ratio, tuple(hits[:10]))
        return None

    return named_filter(check, "short_name_ratio_filter")


def class_names(record: ModelRecord) -> list[str]:
    names: list[str] = []
    for _, attrs in record.graph.nodes(data=True):
        node_type = str(attrs.get("eClass") or attrs.get("type") or "").lower()
        name = attrs.get("name")
        if name and "class" in node_type:
            names.append(str(name))
    return names


def normalized_names(record: ModelRecord) -> list[str]:
    return [normalize_name(name) for name in record.names if name.strip()]


def regex_filter_values(record: ModelRecord, include_types: bool = False) -> list[str]:
    values: list[str] = []
    for _, attrs in record.graph.nodes(data=True):
        name = normalize_name(str(attrs.get("name") or ""))
        if not name:
            continue
        if include_types:
            node_type = normalize_name(str(attrs.get("type") or attrs.get("eClass") or ""))
            values.append(f"{name} {node_type}".strip())
        else:
            values.append(name)
    return values


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def split_camel_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", value).replace("_", " ").replace("-", " ")


def normalize_ecore_type_name(value: str) -> str:
    value = split_camel_case(value)
    value = re.sub(r"^e\s+", "", value, flags=re.IGNORECASE)
    return normalize_name(value)


def named_filter(filter_fn: Filter, name: str) -> Filter:
    setattr(filter_fn, "_mcp4cm_filter_name", name)
    return filter_fn


def filter_name(filter_fn: Filter) -> str:
    return str(getattr(filter_fn, "_mcp4cm_filter_name", getattr(filter_fn, "__name__", "filter")))


def _dataset_filters(records: list[ModelRecord]) -> tuple[Filter, ...]:
    languages = {record.language.lower() for record in records}
    if len(languages) == 1:
        return filters_for_language(next(iter(languages)))
    return default_filters()


def tokenize_name(value: str) -> set[str]:
    return {match.group(0).lower() for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", value)}


def compact_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).lower()
