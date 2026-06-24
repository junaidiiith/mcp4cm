#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.duplicates import (
    DuplicateGroup,
    GraphSimilarPair,
    SimilarPair,
    detect_duplicates_by_name_hash,
    graph_similarity_pairs,
    tfidf_duplicate_pairs,
)
from mcp4cm.runtime_store import deserialize_model_from_runtime, json_safe
from mcp4cm.utils import pair_count, pair_key

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


@dataclass(frozen=True, slots=True)
class TechniqueSpec:
    id: str
    label: str
    config: dict[str, Any]
    runner: Callable[
        [Dataset, Callable[[dict[str, Any]], None] | None], tuple[list[dict[str, Any]], list[dict[str, Any]]]
    ]


def run_hash(
    dataset: Dataset,
    progress: Callable[[dict[str, Any]], None] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = detect_duplicates_by_name_hash(dataset, include_types=False, progress=progress)
    return serialize_hash_groups(groups)


def run_tfidf(
    dataset: Dataset,
    progress: Callable[[dict[str, Any]], None] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs = tfidf_duplicate_pairs(dataset, progress=progress, technique="tfidf")
    return serialize_pair_groups(pairs)


def run_graph_similarity(
    dataset: Dataset,
    progress: Callable[[dict[str, Any]], None] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs = graph_similarity_pairs(dataset, progress=progress)
    return serialize_pair_groups(pairs)


# Comment out entries here to disable techniques for a run.
# Node2Vec graph embeddings, BERT semantic similarity, and graph isomorphism are intentionally excluded.
DUPLICATE_TECHNIQUES = (
    TechniqueSpec(
        id="hash",
        label="Hash",
        config={"includeTypes": False, "minNamedNodes": 0, "deduplicateNameTokens": False},
        runner=run_hash,
    ),
    TechniqueSpec(
        id="tfidf",
        label="TF-IDF",
        config={
            "tokenMode": "names",
            "similarityThreshold": 0.9,
            "maxFeatures": 50_000,
            "minDf": 1,
            "ngramRange": [1, 1],
            "stopwordsMode": "none",
        },
        runner=run_tfidf,
    ),
    TechniqueSpec(
        id="graph_similarity",
        label="Graph Metrics",
        config={
            "similarityThreshold": 0.85,
            "weights": None,
            "useDirectedMetrics": False,
            "normalizeParallelEdges": False,
        },
        runner=run_graph_similarity,
    ),
)


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


def serialize_hash_groups(groups: list[DuplicateGroup]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    serialized_groups = [
        {
            "groupId": f"group-{index}",
            "fingerprint": group.fingerprint,
            "modelIds": list(group.model_ids),
            "size": len(group.model_ids),
            "pairCount": pair_count(len(group.model_ids)),
        }
        for index, group in enumerate(sorted(groups, key=lambda item: (-len(item.model_ids), item.model_ids)), start=1)
    ]
    pairs = []
    for group in serialized_groups:
        model_ids = list(group["modelIds"])
        for left_index, left_id in enumerate(model_ids):
            for right_id in model_ids[left_index + 1 :]:
                pairs.append(
                    {
                        "leftId": left_id,
                        "rightId": right_id,
                        "score": 1.0,
                        "groupId": group["groupId"],
                    }
                )
    return pairs, serialized_groups


def serialize_pair_groups(
    pairs: list[SimilarPair] | list[GraphSimilarPair],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    serialized_pairs = [
        {
            "leftId": pair.left_id,
            "rightId": pair.right_id,
            "score": pair.score,
            "metrics": dict(pair.metrics) if isinstance(pair, GraphSimilarPair) else {},
        }
        for pair in pairs
    ]
    groups = connected_pair_groups(serialized_pairs)
    group_lookup = {
        pair_key(left_id, right_id): group["groupId"]
        for group in groups
        for left_index, left_id in enumerate(group["modelIds"])
        for right_id in group["modelIds"][left_index + 1 :]
    }
    for pair in serialized_pairs:
        group_id = group_lookup.get(pair_key(str(pair["leftId"]), str(pair["rightId"])))
        if group_id:
            pair["groupId"] = group_id
    return serialized_pairs, groups


def connected_pair_groups(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        left_id = str(pair["leftId"])
        right_id = str(pair["rightId"])
        adjacency.setdefault(left_id, set()).add(right_id)
        adjacency.setdefault(right_id, set()).add(left_id)

    visited: set[str] = set()
    components: list[list[str]] = []
    for model_id in sorted(adjacency):
        if model_id in visited:
            continue
        stack = [model_id]
        visited.add(model_id)
        component: list[str] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component) > 1:
            components.append(sorted(component))

    groups = []
    for index, model_ids in enumerate(sorted(components, key=lambda item: (-len(item), item)), start=1):
        internal_pairs = {
            pair_key(str(pair["leftId"]), str(pair["rightId"]))
            for pair in pairs
            if str(pair["leftId"]) in model_ids and str(pair["rightId"]) in model_ids
        }
        groups.append(
            {
                "groupId": f"group-{index}",
                "modelIds": model_ids,
                "size": len(model_ids),
                "pairCount": len(internal_pairs),
                "possiblePairCount": pair_count(len(model_ids)),
                "density": len(internal_pairs) / pair_count(len(model_ids)) if len(model_ids) > 1 else 0,
            }
        )
    return groups


def summarize_scores(pairs: list[dict[str, Any]]) -> dict[str, float]:
    scores = [float(pair["score"]) for pair in pairs]
    if not scores:
        return {"min": 0, "max": 0, "avg": 0}
    return {"min": min(scores), "max": max(scores), "avg": sum(scores) / len(scores)}


def run_technique(dataset: Dataset, technique: TechniqueSpec) -> dict[str, Any]:
    started_at = time.time()
    current_phase = ""
    last_rendered = 0

    with tqdm(total=1, desc=technique.id, unit="item") as progress_bar:

        def progress(event: dict[str, Any]) -> None:
            nonlocal current_phase, last_rendered
            phase = str(event.get("phase") or "run")
            current = int(event.get("current") or 0)
            total = max(int(event.get("total") or 0), 1)
            if phase == "done":
                progress_bar.n = progress_bar.total or total
                progress_bar.refresh()
                return
            if phase != current_phase or total != progress_bar.total:
                current_phase = phase
                last_rendered = 0
                progress_bar.reset(total=total)
                progress_bar.set_description(f"{technique.id}:{phase}")
            redraw_step = max(1, total // 100)
            if current < total and current - last_rendered < redraw_step:
                return
            progress_bar.n = min(current, total)
            last_rendered = progress_bar.n
            progress_bar.refresh()

        try:
            pairs, groups = technique.runner(dataset, progress)
            status = "ok"
            reason = ""
        except ImportError as err:
            pairs = []
            groups = []
            status = "skipped"
            reason = str(err)
        except Exception as err:
            pairs = []
            groups = []
            status = "error"
            reason = str(err)

        if progress_bar.n < (progress_bar.total or 1):
            progress_bar.n = progress_bar.total or 1
            progress_bar.refresh()

    finished_at = time.time()
    detected_model_ids = sorted(
        {
            model_id
            for pair in pairs
            for model_id in (str(pair.get("leftId") or ""), str(pair.get("rightId") or ""))
            if model_id
        }
    )
    return {
        "techniqueId": technique.id,
        "label": technique.label,
        "status": status,
        "reason": reason,
        "config": technique.config,
        "pairCount": len(pairs),
        "detectedModelCount": len(detected_model_ids),
        "detectedModelIds": detected_model_ids,
        "groupCount": len(groups),
        "largestGroupSize": max((int(group.get("size") or 0) for group in groups), default=0),
        "scoreStats": summarize_scores(pairs),
        "pairs": pairs,
        "groups": groups,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedMs": int((finished_at - started_at) * 1000),
    }


def summarize_dataset(result_payload: dict[str, Any]) -> dict[str, Any]:
    total_models = int(result_payload.get("totalModels") or 0)
    rows = [
        {
            "dataset": result_payload["dataset"],
            "type": "Duplicate Filtering",
            "technique": result["techniqueId"],
            "techniqueLabel": result["label"],
            "status": result["status"],
            "detected": result["detectedModelCount"],
            "detectedPercent": (result["detectedModelCount"] / total_models * 100.0) if total_models else 0.0,
            "pairCount": result["pairCount"],
            "groupCount": result["groupCount"],
            "largestGroupSize": result["largestGroupSize"],
            "totalModels": total_models,
            "elapsedMs": result["elapsedMs"],
        }
        for result in result_payload["techniqueResults"]
    ]
    return {
        "version": 1,
        "dataset": result_payload["dataset"],
        "datasetType": result_payload["datasetType"],
        "totalModels": total_models,
        "totalPairs": result_payload["totalPairs"],
        "rows": rows,
        "generatedAt": result_payload["finishedAt"],
    }


def evaluate_dataset(*, dataset_name: str, evaluation_dir: Path) -> dict[str, Any]:
    runtime_dir = evaluation_dir / f"{dataset_name}-runtime"
    if not runtime_dir.is_dir():
        raise FileNotFoundError(f"Missing runtime directory: {runtime_dir}")

    index_payload = load_runtime_index(runtime_dir)
    dataset_type = str(index_payload.get("datasetType") or "runtime")
    records = load_records(runtime_dir, index_payload)
    dataset = Dataset(records=records, dataset_type=dataset_type, root=runtime_dir / "ir")

    started_at = time.time()
    technique_results = [run_technique(dataset, technique) for technique in DUPLICATE_TECHNIQUES]
    finished_at = time.time()
    result_payload = {
        "version": 1,
        "dataset": dataset_name,
        "datasetType": dataset_type,
        "runtimeDir": str(runtime_dir),
        "techniqueMode": "independent",
        "ignoredTechniques": ["graph_embedding", "bert_semantic", "graph_isomorphism"],
        "totalModels": len(records),
        "totalPairs": pair_count(len(records)),
        "techniqueResults": technique_results,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedMs": int((finished_at - started_at) * 1000),
    }
    summary_payload = summarize_dataset(result_payload)
    write_json(runtime_dir / "duplicate_detection.json", result_payload)
    write_json(runtime_dir / "duplicate_detection_summary.json", summary_payload)
    return summary_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run duplicate detection techniques over parsed evaluation runtime datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/duplicate_detection.py\n"
            "  python scripts/duplicate_detection.py --only modelset-uml-xmi\n"
            "  python scripts/duplicate_detection.py --evaluation-dir evaluation-runs\n"
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
        status = f" {row['status']}" if row["status"] != "ok" else ""
        print(
            f"  {str(row['dataset']):<{dataset_width}}  "
            f"{str(row['technique']):<{technique_width}}  "
            f"{style.bold(str(row['detected']))}/{row['totalModels']}  "
            f"{row['detectedPercent']:.2f}%  "
            f"{row['pairCount']} pairs{status}"
        )


def main() -> int:
    args = parse_args()
    style = Style(enabled=sys.stdout.isatty() and not args.no_color)
    targets = resolve_targets(args.only)

    print(style.bold(style.blue("Duplicate detection evaluation")))
    print(style.dim(f"  Targets: {', '.join(targets)}"))
    print(style.dim(f"  Evaluation directory: {args.evaluation_dir.resolve()}"))
    print(style.dim(f"  Techniques: {', '.join(technique.id for technique in DUPLICATE_TECHNIQUES)}"))
    print()

    summaries: list[dict[str, Any]] = []
    for target in targets:
        print(style.bold(style.blue(target)))
        summaries.append(evaluate_dataset(dataset_name=target, evaluation_dir=args.evaluation_dir))
        print()

    aggregate = {
        "version": 1,
        "type": "Duplicate Filtering",
        "techniqueMode": "independent",
        "ignoredTechniques": ["graph_embedding", "bert_semantic", "graph_isomorphism"],
        "datasets": summaries,
        "rows": [row for summary in summaries for row in summary["rows"]],
        "generatedAt": time.time(),
    }
    write_json(args.evaluation_dir / "duplicate_detection_summary.json", aggregate)
    print_summary(style, aggregate)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        style = Style(enabled=sys.stderr.isatty())
        print(style.red(f"error: {error}"), file=sys.stderr)
        raise SystemExit(1) from None
