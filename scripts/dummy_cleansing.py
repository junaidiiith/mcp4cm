#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tqdm import tqdm

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.dummy import default_filter_configs, evaluate_dummy_filters, normalized_filter_configs
from mcp4cm.runtime_store import deserialize_model_from_runtime, json_safe

DEFAULT_TARGETS = (
    "modelset-uml-xmi",
    "modelset-ecore-xmi",
    "eamodelset-archimate",
    "sap-sam-bpmn",
)

TARGET_GROUPS: dict[str, tuple[str, ...]] = {
    "all": DEFAULT_TARGETS,
    "modelset": ("modelset-uml-xmi", "modelset-ecore-xmi"),
}

TARGET_CHOICES = tuple(TARGET_GROUPS) + DEFAULT_TARGETS
DEFAULT_RETAINED_LANGUAGES = ("en",)


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)


def resolve_targets(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(DEFAULT_TARGETS)

    resolved: list[str] = []
    for item in selected:
        if item in TARGET_GROUPS:
            resolved.extend(TARGET_GROUPS[item])
            continue
        if item not in DEFAULT_TARGETS:
            raise ValueError(f"Unknown target: {item}")
        resolved.append(item)

    return list(dict.fromkeys(resolved))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def load_runtime_index(runtime_dir: Path) -> dict[str, Any]:
    index_path = runtime_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing runtime index: {index_path}")
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Runtime index is not a JSON object: {index_path}")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError(f"Runtime index does not contain a models list: {index_path}")
    return payload


def load_records(runtime_dir: Path, index_payload: dict[str, Any]) -> list[ModelRecord]:
    ir_dir = runtime_dir / "ir"
    records: list[ModelRecord] = []
    model_entries = [entry for entry in index_payload.get("models") or [] if isinstance(entry, dict)]
    for entry in tqdm(model_entries, desc=runtime_dir.name, unit="model"):
        filename = str(entry.get("file") or "")
        if not filename:
            raise ValueError(f"Runtime index entry is missing a file value in {runtime_dir / 'index.json'}")
        model_path = ir_dir / filename
        if not model_path.exists():
            raise FileNotFoundError(f"Runtime model file is missing: {model_path}")
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Runtime model file is not a JSON object: {model_path}")
        records.append(deserialize_model_from_runtime(payload))
    return records


def serialize_evaluation(
    *,
    dataset_name: str,
    runtime_dir: Path,
    dataset_type: str,
    total_models: int,
    started_at: float,
    finished_at: float,
    evaluation,
    filter_configs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "dataset": dataset_name,
        "datasetType": dataset_type,
        "runtimeDir": str(runtime_dir),
        "techniqueMode": "independent",
        "cumulative": False,
        "filterConfigs": filter_configs,
        "runSummary": asdict(evaluation.run_summary),
        "filterSummaries": [
            {
                "filterId": summary.filter_id,
                "filteredCount": summary.filtered_count,
                "remainingCount": summary.remaining_count,
                "detectedPercent": (summary.filtered_count / total_models * 100.0) if total_models else 0.0,
                "triggeredModelIds": list(summary.triggered_model_ids),
            }
            for summary in evaluation.filter_summaries
        ],
        "modelOutcomes": [
            {
                "modelId": outcome.model_id,
                "removed": outcome.removed,
                "primaryRemovalReason": outcome.primary_removal_reason,
                "allTriggeredFilters": list(outcome.all_triggered_filters),
            }
            for outcome in evaluation.model_outcomes
        ],
        "findings": [
            {
                "modelId": finding.model_id,
                "filterId": finding.filter_id,
                "reason": finding.reason,
                "score": finding.score,
                "threshold": finding.threshold,
                "decision": finding.decision,
                "evidence": list(finding.evidence),
                "evidenceNodes": list(finding.evidence_nodes),
                "metrics": finding.metrics or {},
            }
            for finding in evaluation.findings
        ],
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedMs": int((finished_at - started_at) * 1000),
    }


def summarize_dataset(result_payload: dict[str, Any]) -> dict[str, Any]:
    total_models = int(result_payload.get("runSummary", {}).get("total_models") or 0)
    rows = [
        {
            "dataset": result_payload["dataset"],
            "type": "Dummy Filtering",
            "technique": summary["filterId"],
            "detected": summary["filteredCount"],
            "detectedPercent": summary["detectedPercent"],
            "totalModels": total_models,
        }
        for summary in result_payload["filterSummaries"]
    ]
    return {
        "version": 1,
        "dataset": result_payload["dataset"],
        "datasetType": result_payload["datasetType"],
        "totalModels": total_models,
        "rows": rows,
        "generatedAt": result_payload["finishedAt"],
    }


def build_filter_configs(languages: list[str] | None) -> list[dict[str, Any]]:
    configs = default_filter_configs()
    selected_languages = list(
        dict.fromkeys(
            language.strip().lower() for language in languages or DEFAULT_RETAINED_LANGUAGES if language.strip()
        )
    )
    return [
        {**config, "enabled": True, "languages": selected_languages} if config.get("id") == "language" else config
        for config in configs
    ]


def cleanse_dataset(
    *,
    dataset_name: str,
    evaluation_dir: Path,
    filter_configs: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_dir = evaluation_dir / f"{dataset_name}-runtime"
    if not runtime_dir.is_dir():
        raise FileNotFoundError(f"Missing runtime directory: {runtime_dir}")

    index_payload = load_runtime_index(runtime_dir)
    dataset_type = str(index_payload.get("datasetType") or "runtime")
    started_at = time.time()
    records = load_records(runtime_dir, index_payload)
    dataset = Dataset(records=records, dataset_type=dataset_type, root=runtime_dir / "ir")
    evaluation = evaluate_dummy_filters(
        dataset, filter_configs=normalized_filter_configs(filter_configs), cumulative=False
    )
    finished_at = time.time()

    result_payload = serialize_evaluation(
        dataset_name=dataset_name,
        runtime_dir=runtime_dir,
        dataset_type=dataset_type,
        total_models=len(records),
        started_at=started_at,
        finished_at=finished_at,
        evaluation=evaluation,
        filter_configs=filter_configs,
    )
    summary_payload = summarize_dataset(result_payload)
    write_json(runtime_dir / "dummy_cleansing.json", result_payload)
    write_json(runtime_dir / "dummy_cleansing_summary.json", summary_payload)
    return summary_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run non-cumulative dummy cleansing over parsed evaluation runtime datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/dummy_cleansing.py\n"
            "  python scripts/dummy_cleansing.py --only modelset-uml-xmi\n"
            "  python scripts/dummy_cleansing.py --evaluation-dir evaluation-runs\n"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=TARGET_CHOICES,
        metavar="TARGET",
        help=(
            "Run only the selected dataset or group. "
            f"Groups: {', '.join(TARGET_GROUPS)}. Targets: {', '.join(DEFAULT_TARGETS)}. "
            "Repeatable. Default: evaluation targets from docs/EVALUATION_CLEANSING.md."
        ),
    )
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=Path("evaluation"),
        help="Directory containing <dataset>-runtime folders (default: evaluation).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output.",
    )
    parser.add_argument(
        "--language",
        action="append",
        metavar="ISO639_1",
        help=("Retain models detected in this ISO 639-1 language. Repeatable. Default: en (English)."),
    )
    return parser.parse_args()


def print_summary(style: Style, aggregate: dict[str, Any]) -> None:
    rows = aggregate["rows"]
    if not rows:
        return

    dataset_width = max(len(str(row["dataset"])) for row in rows)
    technique_width = max(len(str(row["technique"])) for row in rows)
    print()
    print(style.bold(style.green("Done")))
    for row in rows:
        print(
            f"  {str(row['dataset']):<{dataset_width}}  "
            f"{str(row['technique']):<{technique_width}}  "
            f"{style.bold(str(row['detected']))}/{row['totalModels']}  "
            f"{row['detectedPercent']:.2f}%"
        )


def main() -> int:
    args = parse_args()
    style = Style(enabled=sys.stdout.isatty() and not args.no_color)
    targets = resolve_targets(args.only)
    filter_configs = build_filter_configs(args.language)

    print(style.bold(style.blue("Dummy cleansing evaluation")))
    print(style.dim(f"  Targets: {', '.join(targets)}"))
    print(style.dim(f"  Evaluation directory: {args.evaluation_dir.resolve()}"))
    retained_languages = [config["languages"] for config in filter_configs if config.get("id") == "language"][0]
    print(style.dim(f"  Natural languages retained: {', '.join(retained_languages)}"))
    print()

    summaries: list[dict[str, Any]] = []
    for target in targets:
        print(style.bold(style.blue(target)))
        summaries.append(
            cleanse_dataset(dataset_name=target, evaluation_dir=args.evaluation_dir, filter_configs=filter_configs)
        )
        print()

    aggregate = {
        "version": 1,
        "type": "Dummy Filtering",
        "techniqueMode": "independent",
        "cumulative": False,
        "datasets": summaries,
        "rows": [row for summary in summaries for row in summary["rows"]],
        "generatedAt": time.time(),
    }
    write_json(args.evaluation_dir / "dummy_cleansing_summary.json", aggregate)
    print_summary(style, aggregate)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        style = Style(enabled=sys.stderr.isatty())
        print(style.red(f"error: {error}"), file=sys.stderr)
        raise SystemExit(1) from None
