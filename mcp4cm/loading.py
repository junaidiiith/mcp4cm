from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mcp4cm.core import Dataset, DatasetType, ModelRecord
from mcp4cm.parsers import ArchimateParser, EcoreParser, UMLParser
from mcp4cm.parsers.base import BaseModelParser


def load_dataset(dataset_type: DatasetType | str, root: str | Path, language: str | Iterable[str] | None = None) -> Dataset:
    dataset_type = DatasetType(dataset_type)
    root = Path(root)
    if dataset_type == DatasetType.MODELSET:
        records = [
            *load_modelset(root / "uml.jsonl", UMLParser(), DatasetType.MODELSET_UML, language=language).records,
            *load_modelset(root / "ecore.jsonl", EcoreParser(), DatasetType.MODELSET_ECORE, language=language).records,
        ]
        return Dataset(records=records, dataset_type=DatasetType.MODELSET, root=root)
    if dataset_type == DatasetType.MODELSET_UML:
        return load_modelset(root / "uml.jsonl", UMLParser(), DatasetType.MODELSET_UML, language=language)
    if dataset_type == DatasetType.MODELSET_ECORE:
        return load_modelset(root / "ecore.jsonl", EcoreParser(), DatasetType.MODELSET_ECORE, language=language)
    if dataset_type == DatasetType.EAMODELSET:
        processed = root / "processed-models" if (root / "processed-models").exists() else root
        return load_eamodelset(processed, language=language)
    raise ValueError(f"Unsupported dataset type: {dataset_type}")


def load_modelset(
    path: str | Path,
    parser: BaseModelParser | None = None,
    dataset_type: DatasetType | str | None = None,
    language: str | Iterable[str] | None = None,
) -> Dataset:
    path = Path(path)
    if parser is None:
        lower_name = path.name.lower()
        parser = EcoreParser() if "ecore" in lower_name else UMLParser()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected MODELSET file to contain a JSON array: {path}")

    records = []
    for item in payload:
        record = parser.parse(item)
        record.source_path = path
        if _matches_language(record, language):
            records.append(record)
    return Dataset(records=records, dataset_type=dataset_type or parser.language, root=path)


def load_eamodelset(
    root: str | Path,
    parser: ArchimateParser | None = None,
    language: str | Iterable[str] | None = None,
) -> Dataset:
    root = Path(root)
    parser = parser or ArchimateParser()
    records = []
    for model_path in sorted(root.glob("*/model.json")):
        raw = _load_json_object(model_path)
        record = parser.parse(raw, model_id=model_path.parent.name)
        record.source_path = model_path
        if _matches_language(record, language):
            records.append(record)
    return Dataset(records=records, dataset_type=DatasetType.EAMODELSET, root=root)


def _load_json_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _matches_language(record: ModelRecord, language: str | Iterable[str] | None) -> bool:
    if language is None:
        return True
    allowed = _normalize_languages(language)
    natural_language = record.metadata.get("language")
    candidates = {record.language.lower()}
    if natural_language:
        candidates.add(str(natural_language).lower())
    return bool(candidates & allowed)


def _normalize_languages(language: str | Iterable[str]) -> set[str]:
    if isinstance(language, str):
        return {language.lower()}
    return {str(item).lower() for item in language}
