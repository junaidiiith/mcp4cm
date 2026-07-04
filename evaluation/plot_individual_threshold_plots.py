#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

TECHNIQUE_LABELS = {
    "tfidf": "TF-IDF",
    "graph_similarity": "Graph similarity",
    "bert_semantic": "BERT similarity",
    "gnn": "GNN",
}

TECHNIQUE_COLORS = {
    "tfidf": "#1f77b4",
    "graph_similarity": "#ff7f0e",
    "bert_semantic": "#d62728",
    "gnn": "#9467bd",
}

DATASET_LABELS = {
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "eamodelset-archimate": "EAModelSet",
    "sap-sam-bpmn": "SAP-SAM BPMN",
}

DEFAULT_TECHNIQUE_ORDER = ("tfidf", "graph_similarity", "bert_semantic", "gnn")
AXIS_LABEL_FONT_SIZE = 15
AXIS_TICK_FONT_SIZE = 13


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create one threshold plot per dataset by reading precomputed threshold "
            "CSV/JSON files from evaluation/threshold-plots."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("evaluation/threshold-plots"),
        help="Directory containing <dataset>/<technique>/<technique>.json or .csv files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated plots. Defaults to writing inside each dataset input directory.",
    )
    parser.add_argument(
        "--output-name",
        default="individual_threshold_plot.png",
        help="PNG filename for each dataset plot when --output-dir is omitted.",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="DATASET",
        help="Dataset directory name to plot. Repeatable. Default: every dataset directory in --input-dir.",
    )
    parser.add_argument(
        "--technique",
        action="append",
        choices=DEFAULT_TECHNIQUE_ORDER,
        help="Technique to include. Repeatable. Default: all available techniques.",
    )
    return parser.parse_args()


def discover_datasets(input_dir: Path, selected: list[str] | None) -> list[Path]:
    if selected:
        dataset_dirs = [input_dir / name for name in selected]
    else:
        dataset_dirs = sorted(path for path in input_dir.iterdir() if path.is_dir())

    missing = [path for path in dataset_dirs if not path.is_dir()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing dataset threshold directories: {missing_text}")
    return dataset_dirs


def selected_techniques(techniques: list[str] | None) -> tuple[str, ...]:
    if not techniques:
        return DEFAULT_TECHNIQUE_ORDER
    return tuple(dict.fromkeys(techniques))


def load_json_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results")
    model_count = payload.get("modelCount")
    if not isinstance(rows, list) or not isinstance(model_count, int):
        raise ValueError(f"Invalid threshold JSON structure: {path}")
    return rows, model_count


def load_csv_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError(f"Threshold CSV has no rows: {path}")

    parsed_rows: list[dict[str, Any]] = []
    model_count = 0
    for row in rows:
        parsed_row = {
            "threshold": float(row["threshold"]),
            "duplicates": int(row["duplicates"]),
            "unique": int(row["unique"]),
            "matchingPairs": int(row["matchingPairs"]),
        }
        parsed_rows.append(parsed_row)
        model_count = max(model_count, parsed_row["duplicates"] + parsed_row["unique"])

    return parsed_rows, model_count


def load_technique_rows(
    dataset_dir: Path, techniques: tuple[str, ...]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    rows_by_technique: dict[str, list[dict[str, Any]]] = {}
    model_counts: dict[str, int] = {}

    for technique in techniques:
        technique_dir = dataset_dir / technique
        json_path = technique_dir / f"{technique}.json"
        csv_path = technique_dir / f"{technique}.csv"

        if json_path.exists():
            rows, model_count = load_json_rows(json_path)
        elif csv_path.exists():
            rows, model_count = load_csv_rows(csv_path)
        else:
            continue

        rows_by_technique[technique] = rows
        model_counts[technique] = model_count

    if not rows_by_technique:
        raise FileNotFoundError(f"No threshold CSV/JSON files found in {dataset_dir}")

    return rows_by_technique, model_counts


def plot_dataset(
    *,
    dataset_name: str,
    rows_by_technique: dict[str, list[dict[str, Any]]],
    model_counts: dict[str, int],
    output_path: Path,
) -> Path:
    try:
        import matplotlib.lines as mlines
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install the project plotting dependencies.") from exc

    figure, axis = plt.subplots(figsize=(12, 7))

    for technique in DEFAULT_TECHNIQUE_ORDER:
        rows = sorted(rows_by_technique.get(technique, []), key=lambda row: float(row["threshold"]))
        if not rows:
            continue

        model_count = model_counts[technique]
        thresholds = [float(row["threshold"]) for row in rows]
        duplicates = [int(row["duplicates"]) / model_count * 100.0 for row in rows]
        unique = [int(row["unique"]) / model_count * 100.0 for row in rows]

        axis.plot(
            thresholds,
            duplicates,
            marker="o",
            linewidth=1.9,
            markersize=4.0,
            color=TECHNIQUE_COLORS[technique],
            linestyle="-",
        )
        axis.plot(
            thresholds,
            unique,
            marker="s",
            linewidth=1.9,
            markersize=3.7,
            color=TECHNIQUE_COLORS[technique],
            linestyle="--",
        )

    axis.set_title(f"{DATASET_LABELS.get(dataset_name, dataset_name)}: duplicate and unique models by threshold")
    axis.set_xlabel("Similarity threshold", fontsize=AXIS_LABEL_FONT_SIZE)
    axis.set_ylabel("Models (%)", fontsize=AXIS_LABEL_FONT_SIZE)
    axis.set_xlim(0.05, 1.0)
    axis.set_ylim(0, 100)
    axis.set_xticks([round(index * 0.1, 2) for index in range(1, 11)])
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    axis.tick_params(axis="both", labelsize=AXIS_TICK_FONT_SIZE)
    axis.grid(True, alpha=0.3)

    technique_handles = [
        mlines.Line2D(
            [],
            [],
            color=TECHNIQUE_COLORS[technique],
            marker="o",
            linestyle="-",
            label=TECHNIQUE_LABELS[technique],
        )
        for technique in DEFAULT_TECHNIQUE_ORDER
        if technique in rows_by_technique
    ]
    metric_handles = [
        mlines.Line2D([], [], color="black", marker="o", linestyle="-", label="Duplicate models"),
        mlines.Line2D([], [], color="black", marker="s", linestyle="--", label="Unique models"),
    ]
    figure.legend(
        handles=technique_handles,
        title="Technique",
        loc="lower center",
        ncol=max(len(technique_handles), 1),
        frameon=True,
        bbox_to_anchor=(0.40, 0.0),
    )
    figure.legend(
        handles=metric_handles,
        title="Metric",
        loc="lower center",
        ncol=2,
        frameon=True,
        bbox_to_anchor=(0.80, 0.0),
    )
    figure.tight_layout(rect=(0, 0.12, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def output_path_for_dataset(args: argparse.Namespace, dataset_dir: Path) -> Path:
    if args.output_dir is None:
        return dataset_dir / args.output_name
    return args.output_dir / f"{dataset_dir.name}.png"


def main() -> int:
    args = parse_args()
    dataset_dirs = discover_datasets(args.input_dir, args.only)
    techniques = selected_techniques(args.technique)

    output_paths: list[Path] = []
    for dataset_dir in dataset_dirs:
        rows_by_technique, model_counts = load_technique_rows(dataset_dir, techniques)
        output_paths.append(
            plot_dataset(
                dataset_name=dataset_dir.name,
                rows_by_technique=rows_by_technique,
                model_counts=model_counts,
                output_path=output_path_for_dataset(args, dataset_dir),
            )
        )

    for output_path in output_paths:
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
