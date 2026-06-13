from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from mcp4cm.core import Dataset, DatasetType, ModelRecord
from mcp4cm.parsers.parse import parse_files


def load_dataset(
    dataset_type: DatasetType | str,
    root: str | Path,
    language: str | Iterable[str] | None = None,
    format: str | None = None,
) -> Dataset:
    dataset_type = DatasetType(dataset_type)
    root = Path(root)
    if dataset_type == DatasetType.MODELSET:
        records: list[ModelRecord] = []
        diagnostics = {}
        for parser_language in ("uml", "ecore"):
            dataset = load_modelset(
                root / parser_language,
                language=parser_language,
                format=format or "json",
                dataset_type=f"modelset_{parser_language}",
                filter_language=language,
            )
            records.extend(dataset.records)
            diagnostics.update(dataset.diagnostics)
        return Dataset(records=records, dataset_type=DatasetType.MODELSET, root=root, diagnostics=diagnostics)
    if dataset_type == DatasetType.MODELSET_UML:
        return load_modelset(
            root,
            language="uml",
            format=format or "json",
            dataset_type=DatasetType.MODELSET_UML,
            filter_language=language,
        )
    if dataset_type == DatasetType.MODELSET_ECORE:
        return load_modelset(
            root,
            language="ecore",
            format=format or "json",
            dataset_type=DatasetType.MODELSET_ECORE,
            filter_language=language,
        )
    if dataset_type == DatasetType.EAMODELSET:
        processed = root / "processed-models" if (root / "processed-models").exists() else root
        return load_eamodelset(processed, natural_language=language, format=format or "json")
    raise ValueError(f"Unsupported dataset type: {dataset_type}")


def load_modelset(
    path: str | Path,
    *,
    language: str = "uml",
    format: str = "json",
    dataset_type: DatasetType | str | None = None,
    filter_language: str | Iterable[str] | None = None,
) -> Dataset:
    source = Path(path)
    filepaths = sorted(source.rglob("*.json")) if source.is_dir() else [source]
    parsed = parse_files(filepaths, language=language, format=format)
    records = [record for record in parsed.records if _matches_language(record, filter_language)]
    diagnostics = {
        record.model_id: parsed.diagnostics[record.model_id]
        for record in records
        if record.model_id in parsed.diagnostics
    }
    return Dataset(records=records, dataset_type=dataset_type or language, root=source, diagnostics=diagnostics)


def load_eamodelset(
    root: str | Path,
    *,
    language: str | Iterable[str] | None = None,
    format: str = "json",
    natural_language: str | Iterable[str] | None = None,
) -> Dataset:
    root = Path(root)
    filter_language = natural_language if natural_language is not None else language
    filepaths = sorted([*root.glob("*.json"), *root.glob("*/model.json")])
    parsed = parse_files(filepaths, language="archimate", format=format)
    records = [record for record in parsed.records if _matches_language(record, filter_language)]
    diagnostics = {
        record.model_id: parsed.diagnostics[record.model_id]
        for record in records
        if record.model_id in parsed.diagnostics
    }
    return Dataset(records=records, dataset_type=DatasetType.EAMODELSET, root=root, diagnostics=diagnostics)


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
