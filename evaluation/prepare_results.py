#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = (
    "modelset-uml-xmi",
    "modelset-ecore-xmi",
    "eamodelset-archimate",
    "sap-sam-bpmn",
)

DATASET_LABELS = {
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "eamodelset-archimate": "EAModelSet",
    "sap-sam-bpmn": "SAP-SAM BPMN",
}

DUMMY_FILTER_LABELS = {
    "min_size": "Minimum size",
    "too_few_named_elements": "Too few named elements",
    "short_median_name_length": "Short median name length",
    "placeholder_name_ratio": "Placeholder-name ratio",
    "low_vocabulary": "Low vocabulary",
    "name_repetition_ratio": "Name-repetition ratio",
    "language": "Language",
    "regex_rule": "Regex rule",
}

DUPLICATE_TECHNIQUE_LABELS = {
    "hash": "Hash",
    "tfidf": "TF-IDF",
    "graph_similarity": "Graph metrics",
    "bert_semantic": "BERT",
    "gnn": "GNN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare evaluation JSON summaries as Markdown tables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python evaluation/prepare_results.py\n"
            "  python evaluation/prepare_results.py --print\n"
            "  python evaluation/prepare_results.py --output evaluation/RESULTS.md\n"
        ),
    )
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=Path("evaluation"),
        help="Directory containing <dataset>-runtime folders (default: evaluation).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown output path (default: <evaluation-dir>/RESULTS.md).",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_stdout",
        help="Also print the generated Markdown to stdout.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def dataset_label(dataset: str) -> str:
    return DATASET_LABELS.get(dataset, dataset)


def technique_label(row: dict[str, Any]) -> str:
    technique = str(row.get("technique") or "")
    return DUPLICATE_TECHNIQUE_LABELS.get(technique, str(row.get("techniqueLabel") or technique))


def dummy_filter_label(row: dict[str, Any]) -> str:
    technique = str(row.get("technique") or "")
    return DUMMY_FILTER_LABELS.get(technique, technique)


def format_int(value: Any) -> str:
    return f"{int(value or 0):,}"


def format_percent(value: Any) -> str:
    return f"{float(value or 0):.2f}"


def format_runtime(value: Any) -> str:
    return f"{float(value or 0) / 1000:.2f} s"


def markdown_table(headers: list[str], rows: list[list[str]], aligns: list[str]) -> str:
    align_map = {"left": ":---", "right": "---:"}
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(align_map[align] for align in aligns) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def grouped_rows(
    rows_by_dataset: list[tuple[str, list[list[str]]]],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for dataset, dataset_rows in rows_by_dataset:
        for index, row in enumerate(dataset_rows):
            rows.append([dataset if index == 0 else "", *row])
    return rows


def load_dataset_summaries(evaluation_dir: Path, filename: str) -> list[tuple[str, dict[str, Any]]]:
    summaries: list[tuple[str, dict[str, Any]]] = []
    for dataset in DEFAULT_TARGETS:
        summary_path = evaluation_dir / f"{dataset}-runtime" / filename
        payload = read_json(summary_path)
        if payload is None:
            continue
        summaries.append((dataset, payload))
    return summaries


def build_dummy_filter_table(summaries: list[tuple[str, dict[str, Any]]]) -> str:
    rows_by_dataset = []
    for dataset, summary in summaries:
        rows = [
            [
                dummy_filter_label(row),
                format_int(row.get("detected")),
                format_percent(row.get("detectedPercent")),
            ]
            for row in summary.get("rows", [])
            if isinstance(row, dict)
        ]
        if rows:
            rows_by_dataset.append((dataset_label(dataset), rows))

    return markdown_table(
        ["Dataset", "Filter", "Models", "Models (%)"],
        grouped_rows(rows_by_dataset),
        ["left", "left", "right", "right"],
    )


def build_dummy_union_table(summaries: list[tuple[str, dict[str, Any]]]) -> str:
    rows_by_dataset = []
    for dataset, summary in summaries:
        rows = [
            [
                str(row.get("filterSet") or row.get("variant") or ""),
                format_int(row.get("removed")),
                format_int(row.get("remaining")),
                format_percent(row.get("removalRate")),
            ]
            for row in summary.get("unionRows", [])
            if isinstance(row, dict)
        ]
        if rows:
            rows_by_dataset.append((dataset_label(dataset), rows))

    return markdown_table(
        ["Dataset", "Filter set", "Removed", "Remaining", "Removed (%)"],
        grouped_rows(rows_by_dataset),
        ["left", "left", "right", "right", "right"],
    )


def build_duplicate_table(summaries: list[tuple[str, dict[str, Any]]]) -> str:
    rows_by_dataset = []
    for dataset, summary in summaries:
        rows = [
            [
                technique_label(row),
                format_int(row.get("detected")),
                format_percent(row.get("detectedPercent")),
                format_int(row.get("pairCount")),
                format_int(row.get("groupCount")),
                format_int(row.get("largestGroupSize")),
                format_runtime(row.get("elapsedMs")),
            ]
            for row in summary.get("rows", [])
            if isinstance(row, dict)
        ]
        if rows:
            rows_by_dataset.append((dataset_label(dataset), rows))

    return markdown_table(
        ["Dataset", "Technique", "Models", "Models (%)", "Pairs", "Groups", "Largest group", "Runtime"],
        grouped_rows(rows_by_dataset),
        ["left", "left", "right", "right", "right", "right", "right", "right"],
    )


def build_markdown(evaluation_dir: Path) -> str:
    dummy_summaries = load_dataset_summaries(evaluation_dir, "dummy_cleansing_summary.json")
    duplicate_summaries = load_dataset_summaries(evaluation_dir, "duplicate_detection_summary.json")

    sections = ["# Evaluation Results"]
    if dummy_summaries:
        sections.extend(
            [
                "## Dummy Detection",
                build_dummy_filter_table(dummy_summaries),
                "## Dummy Detection Unions",
                build_dummy_union_table(dummy_summaries),
            ]
        )
    if duplicate_summaries:
        sections.extend(["## Duplicate Detection", build_duplicate_table(duplicate_summaries)])
    if len(sections) == 1:
        sections.append("No evaluation summary files were found.")
    return "\n\n".join(sections) + "\n"


def main() -> int:
    args = parse_args()
    output_path = args.output or args.evaluation_dir / "RESULTS.md"
    markdown = build_markdown(args.evaluation_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    if args.print_stdout:
        print(markdown, end="")
    else:
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
