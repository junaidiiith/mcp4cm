from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
import re
from typing import Literal

from mcp4cm.core import ModelRecord
from mcp4cm.xmi_names import EMPTY_NAME_SENTINEL

NameClassification = Literal["missing", "type_like", "placeholder", "semantic"]
ElementKind = Literal["node"]

PROTECTED_TYPE_ATOMS = frozenset(
    {
        "EClass",
        "EAttribute",
        "EReference",
        "EPackage",
        "EDataType",
        "EEnum",
    }
)

PLACEHOLDER_KEYWORDS = {
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
    "placeholder",
    "untitled",
    "no name",
    "new model",
    "model",
    "class",
    "my class",
    "entity",
    "node",
    "package",
    "component",
    "attribute",
    "control flow",
    "empty name",
    "att",
    "aggregate",
}

PLACEHOLDER_PATTERNS = (
    re.compile(r"^my\s+class\s*\d*$", re.IGNORECASE),
    re.compile(r"^att(\s+[A-Za-z]|\s+\d+|[a-z0-9])?$", re.IGNORECASE),
    re.compile(r"^(class|entity|node|model|package|component|attribute|type|aggregate)[\s_-]*\d*$", re.IGNORECASE),
    re.compile(r"^[A-Za-z]\d$", re.IGNORECASE),
    re.compile(r"^[A-Za-z]\s[A-Za-z]$", re.IGNORECASE),
    re.compile(r"^(private|public|protected|package)\s+(operation|attribute|property|method)$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class NormalizerConfig:
    lowercase: bool = True
    trim: bool = True
    collapse_whitespace: bool = True
    split_identifier_boundaries: bool = True
    protected_type_atoms: tuple[str, ...] = tuple(sorted(PROTECTED_TYPE_ATOMS))


@dataclass(frozen=True, slots=True)
class TokenizerConfig:
    split_camel_case: bool = True
    keep_numeric_tokens: bool = False
    min_token_length: int = 1
    deduplicate: bool = False
    stopwords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LabelPipelineConfig:
    normalizer: NormalizerConfig = field(default_factory=NormalizerConfig)
    tokenizer: TokenizerConfig = field(default_factory=TokenizerConfig)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_LABEL_CONFIG = LabelPipelineConfig()


@dataclass(frozen=True, slots=True)
class ExtractedLabel:
    model_id: str
    element_id: str
    element_kind: ElementKind
    raw_name: str
    raw_type: str
    normalized_name: str
    normalized_type: str
    name_tokens: tuple[str, ...]
    type_tokens: tuple[str, ...]
    classification: NameClassification


def extract_node_labels(record: ModelRecord, config: LabelPipelineConfig = DEFAULT_LABEL_CONFIG) -> list[ExtractedLabel]:
    return [
        extract_node_label(
            model_id=str(record.model_id),
            element_id=str(node_id),
            attrs=attrs,
            config=config,
        )
        for node_id, attrs in record.graph.nodes(data=True)
    ]


def iter_name_slots(record: ModelRecord, config: LabelPipelineConfig = DEFAULT_LABEL_CONFIG) -> Iterator[tuple[str, ExtractedLabel]]:
    for label in extract_node_labels(record, config=config):
        yield label.element_id, label


def extract_node_label(
    *,
    model_id: str,
    element_id: str,
    attrs: dict[str, object],
    config: LabelPipelineConfig = DEFAULT_LABEL_CONFIG,
) -> ExtractedLabel:
    raw_name = raw_node_name(attrs)
    raw_type = raw_node_type(attrs)
    return classify_name_slot(
        raw_name,
        raw_type,
        model_id=model_id,
        element_id=element_id,
        config=config,
    )


def classify_name_slot(
    raw_name: object,
    raw_type: object = "",
    *,
    model_id: str = "",
    element_id: str = "",
    normalized_name: str | None = None,
    normalized_type: str | None = None,
    name_tokens: tuple[str, ...] | None = None,
    type_tokens: tuple[str, ...] | None = None,
    config: LabelPipelineConfig = DEFAULT_LABEL_CONFIG,
) -> ExtractedLabel:
    raw_name_text = str(raw_name or "")
    raw_type_text = str(raw_type or "")
    normalized_name_text = normalize_name(raw_name_text, config.normalizer) if normalized_name is None else normalized_name
    normalized_type_text = normalize_type(raw_type_text, config.normalizer) if normalized_type is None else normalized_type
    name_token_tuple = tokenize_label(normalized_name_text, config.tokenizer) if name_tokens is None else name_tokens
    type_token_tuple = tokenize_label(normalized_type_text, config.tokenizer) if type_tokens is None else type_tokens
    classification = classify_normalized_name(
        raw_name=raw_name_text,
        normalized_name=normalized_name_text,
        normalized_type=normalized_type_text,
        name_tokens=name_token_tuple,
    )
    return ExtractedLabel(
        model_id=model_id,
        element_id=element_id,
        element_kind="node",
        raw_name=raw_name_text,
        raw_type=raw_type_text,
        normalized_name=normalized_name_text,
        normalized_type=normalized_type_text,
        name_tokens=name_token_tuple,
        type_tokens=type_token_tuple,
        classification=classification,
    )


def raw_node_name(attrs: dict[str, object]) -> str:
    return str(attrs.get("name") or "")


def raw_node_type(attrs: dict[str, object]) -> str:
    raw_type = attrs.get("type")
    if raw_type:
        return str(raw_type)
    return str(attrs.get("eClass") or "")


def normalize_name(value: object, config: NormalizerConfig = DEFAULT_LABEL_CONFIG.normalizer) -> str:
    return normalize_label(value, config=config)


def normalize_type(value: object, config: NormalizerConfig = DEFAULT_LABEL_CONFIG.normalizer) -> str:
    raw = str(value or "")
    if raw in set(config.protected_type_atoms):
        return raw.lower()
    return normalize_label(raw, config=config)


def normalize_label(value: object, *, config: NormalizerConfig = DEFAULT_LABEL_CONFIG.normalizer) -> str:
    text = str(value or "")
    if config.trim:
        text = text.strip()
    if not text:
        return ""
    if config.split_identifier_boundaries:
        text = split_identifier_boundaries(text)
    text = re.sub(r"[_\-.]+", " ", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    if config.lowercase:
        text = text.lower()
    if not re.search(r"\w", text, flags=re.UNICODE):
        return ""
    if config.collapse_whitespace:
        text = " ".join(text.split())
    return text


def split_identifier_boundaries(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([A-Z]+)$", r"\1 \2", text)
    return text


def tokenize_label(value: str, config: TokenizerConfig = DEFAULT_LABEL_CONFIG.tokenizer) -> tuple[str, ...]:
    normalized = normalize_label(value) if config.split_camel_case else str(value or "").lower()
    stopwords = {word.lower() for word in config.stopwords}
    tokens: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[^\W_]+", normalized, flags=re.UNICODE):
        token = match.group(0).lower()
        if token.isnumeric() and not config.keep_numeric_tokens:
            continue
        if len(token) < config.min_token_length:
            continue
        if token in stopwords:
            continue
        if config.deduplicate:
            if token in seen:
                continue
            seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def tokenize_name(value: str) -> tuple[str, ...]:
    return tokenize_label(value)


def classify_normalized_name(
    *,
    raw_name: str,
    normalized_name: str,
    normalized_type: str,
    name_tokens: tuple[str, ...],
) -> NameClassification:
    if is_missing_name(raw_name, normalized_name):
        return "missing"
    if is_type_like_name(normalized_name, normalized_type):
        return "type_like"
    if is_placeholder_name(normalized_name, normalized_type=normalized_type, name_tokens=name_tokens):
        return "placeholder"
    return "semantic"


def is_missing_name(raw_name: str, normalized_name: str) -> bool:
    if not str(raw_name or "").strip():
        return True
    return not normalized_name or normalized_name == EMPTY_NAME_SENTINEL


def is_type_like_name(normalized_name: str, normalized_type: str) -> bool:
    compact_name = compact_identifier(normalized_name)
    compact_type = compact_identifier(normalized_type)
    if not compact_name or not compact_type:
        return False
    if compact_name == compact_type:
        return True
    if compact_name.startswith(compact_type):
        suffix = compact_name[len(compact_type) :]
        return bool(suffix) and suffix.isdigit()
    return False


def is_placeholder_name(
    normalized_name: str,
    *,
    normalized_type: str = "",
    name_tokens: tuple[str, ...] = (),
) -> bool:
    if normalized_name in PLACEHOLDER_KEYWORDS:
        return True
    if any(pattern.match(normalized_name) for pattern in PLACEHOLDER_PATTERNS):
        return True
    if normalized_type:
        if normalized_name == f"{normalized_type} copy":
            return True
        if name_tokens == (*tuple(tokenize_label(normalized_type)), "copy"):
            return True
        type_tokens = tokenize_label(normalized_type)
        if len(name_tokens) == len(type_tokens) + 1 and name_tokens[: len(type_tokens)] == type_tokens:
            suffix = name_tokens[-1]
            if len(suffix) == 1 and suffix.isalpha():
                return True
    return False


def compact_identifier(value: str) -> str:
    return re.sub(r"[^\w]", "", value, flags=re.UNICODE).lower()
