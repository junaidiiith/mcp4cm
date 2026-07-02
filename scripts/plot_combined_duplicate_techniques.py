#!/usr/bin/env python3
"""Create combined duplicate-technique threshold plots from saved threshold results.

The plot shows duplicate-model percentages and unique-model percentages for
each selected technique in one PNG per dataset directory.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

TECHNIQUE_ORDER = ("tfidf", "graph-similarity", "bert", "gnn")
TECHNIQUE_ALIASES = {
    "bert-similarity": "bert",
}
TECHNIQUE_LABELS = {
    "tfidf": "TF-IDF",
    "graph-similarity": "Graph similarity",
    "bert": "BERT similarity",
    "gnn": "GNN",
}
TECHNIQUE_COLORS = {
    "tfidf": "#1f77b4",
    "graph-similarity": "#ff7f0e",
    "bert": "#d62728",
    "gnn": "#9467bd",
}
DATASET_ALIASES = {
    "sap-sam": "sap-sam-bpmn",
}
DEFAULT_DATASETS = (
    "eamodelset-archimate",
    "modelset-uml-xmi",
    "modelset-ecore-xmi",
    "sap-sam",
)
DATASET_LABELS = {
    "eamodelset-archimate": "EAModelSet",
    "modelset-uml-xmi": "ModelSet UML",
    "modelset-ecore-xmi": "ModelSet Ecore",
    "sap-sam-bpmn": "SAP-SAM BPMN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot duplicate and unique model counts for duplicate detection techniques."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("threshold-results_v1"),
        help="Directory containing one subdirectory per dataset.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help=(
            "Dataset directory or alias to plot. Repeat to select multiple datasets. "
            f"Default: {', '.join(DEFAULT_DATASETS)}."
        ),
    )
    parser.add_argument(
        "--output-name",
        default="combined_duplicate_techniques.png",
        help="Output PNG filename inside each dataset directory.",
    )
    parser.add_argument(
        "--combined-output",
        type=Path,
        help="Optional path for one multi-panel PNG containing all selected datasets.",
    )
    return parser.parse_args()


def canonical_technique(name: str) -> str:
    return TECHNIQUE_ALIASES.get(name, name)


def dataset_dir(results_dir: Path, dataset: str) -> Path:
    return results_dir / DATASET_ALIASES.get(dataset, dataset)


def load_model_counts(path: Path) -> dict[str, int]:
    model_counts: dict[str, int] = {}
    for json_path in sorted(path.glob("*.json")):
        if json_path.name in {
            "duplicate_minus_iso.json",
            "duplicate_minus_iso_reload.json",
            "eam-duplicate-minus-iso.json",
        }:
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        technique = payload.get("technique")
        model_count = payload.get("modelCount")
        if isinstance(technique, str) and isinstance(model_count, int):
            canonical = canonical_technique(technique)
            if canonical in TECHNIQUE_ORDER:
                model_counts[canonical] = model_count
    return model_counts


def load_dataset_rows(path: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    selected: dict[str, list[dict[str, str]]] = {}
    model_counts = load_model_counts(path)
    for csv_path in sorted(path.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows_by_technique: dict[str, list[dict[str, str]]] = {}
            for row in csv.DictReader(handle):
                technique = canonical_technique(row["technique"])
                if technique in TECHNIQUE_ORDER:
                    rows_by_technique.setdefault(technique, []).append(row)

        for technique, rows in rows_by_technique.items():
            if technique not in selected or csv_path.name != "embedding_thresholds.csv":
                selected[technique] = rows
                row_model_counts = {
                    int(row["duplicates"]) + int(row["unique"])
                    for row in rows
                    if row.get("duplicates") and row.get("unique")
                }
                if len(row_model_counts) == 1:
                    model_counts.setdefault(technique, row_model_counts.pop())

    return selected, model_counts


def validate_dataset_rows(path: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    rows_by_technique, model_counts = load_dataset_rows(path)
    missing = [technique for technique in TECHNIQUE_ORDER if technique not in rows_by_technique]
    if missing:
        missing_labels = ", ".join(TECHNIQUE_LABELS[technique] for technique in missing)
        raise FileNotFoundError(f"{path} is missing threshold CSV data for: {missing_labels}")
    missing_counts = [technique for technique in TECHNIQUE_ORDER if technique not in model_counts]
    if missing_counts:
        missing_labels = ", ".join(TECHNIQUE_LABELS[technique] for technique in missing_counts)
        raise FileNotFoundError(f"{path} is missing model-count data for: {missing_labels}")
    return rows_by_technique, model_counts


def draw_dataset(axis, path: Path, title: str) -> None:
    from matplotlib.ticker import PercentFormatter

    rows_by_technique, model_counts = validate_dataset_rows(path)
    for technique in TECHNIQUE_ORDER:
        rows = sorted(rows_by_technique[technique], key=lambda row: float(row["threshold"]))
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

    axis.set_title(title)
    axis.set_xlim(0.05, 1.0)
    axis.set_ylim(0, 100)
    axis.set_xticks([round(index * 0.1, 2) for index in range(1, 11)])
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    axis.grid(True, alpha=0.3)


def plot_dataset(path: Path, output_name: str) -> Path:
    try:
        import matplotlib.lines as mlines
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install it with `pip install matplotlib`.") from exc

    figure, axis = plt.subplots(figsize=(12, 7))
    draw_dataset(axis, path, f"{path.name}: duplicate and unique models by threshold")
    axis.set_xlabel("Similarity threshold")
    axis.set_ylabel("Models (%)")
    axis.set_xticks([round(index * 0.05, 2) for index in range(1, 21)])

    technique_handles = [
        mlines.Line2D(
            [],
            [],
            color=TECHNIQUE_COLORS[technique],
            marker="o",
            linestyle="-",
            label=TECHNIQUE_LABELS[technique],
        )
        for technique in TECHNIQUE_ORDER
    ]
    metric_handles = [
        mlines.Line2D([], [], color="black", marker="o", linestyle="-", label="Duplicate models"),
        mlines.Line2D([], [], color="black", marker="s", linestyle="--", label="Unique models"),
    ]
    figure.legend(
        handles=technique_handles,
        title="Technique",
        loc="lower center",
        ncol=len(TECHNIQUE_ORDER),
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
    output_path = path / output_name
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def legend_handles():
    import matplotlib.lines as mlines

    technique_handles = [
        mlines.Line2D(
            [],
            [],
            color=TECHNIQUE_COLORS[technique],
            marker="o",
            linestyle="-",
            label=TECHNIQUE_LABELS[technique],
        )
        for technique in TECHNIQUE_ORDER
    ]
    metric_handles = [
        mlines.Line2D([], [], color="black", marker="o", linestyle="-", label="Duplicate models"),
        mlines.Line2D([], [], color="black", marker="s", linestyle="--", label="Unique models"),
    ]
    return technique_handles, metric_handles


def plot_all_datasets(paths: list[Path], output_path: Path) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("Plotting requires matplotlib. Install it with `pip install matplotlib`.") from exc

    figure, axes = plt.subplots(2, 2, figsize=(15, 10), sharex=True, sharey=True)
    subplot_labels = ("(a)", "(b)", "(c)", "(d)")
    for axis, path, subplot_label in zip(axes.flat, paths, subplot_labels, strict=False):
        title = DATASET_LABELS.get(path.name, path.name)
        draw_dataset(axis, path, f"{subplot_label} {title}")

    for axis in axes[:, 0]:
        axis.set_ylabel("Models (%)")
    for axis in axes[-1, :]:
        axis.set_xlabel("Similarity threshold")

    technique_handles, metric_handles = legend_handles()
    figure.legend(
        handles=technique_handles,
        title="Technique",
        loc="lower center",
        ncol=len(TECHNIQUE_ORDER),
        frameon=True,
        bbox_to_anchor=(0.38, 0.01),
    )
    figure.legend(
        handles=metric_handles,
        title="Metric",
        loc="lower center",
        ncol=2,
        frameon=True,
        bbox_to_anchor=(0.79, 0.01),
    )
    figure.suptitle("Duplicate and unique models by similarity threshold", y=0.98)
    figure.tight_layout(rect=(0, 0.11, 1, 0.96))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)
    return output_path


def main() -> int:
    args = parse_args()
    datasets = args.datasets or list(DEFAULT_DATASETS)
    output_paths = []
    dataset_paths = []
    for dataset in datasets:
        path = dataset_dir(args.results_dir, dataset)
        if not path.is_dir():
            raise FileNotFoundError(f"Dataset results directory not found: {path}")
        dataset_paths.append(path)
        output_paths.append(plot_dataset(path, args.output_name))
    if args.combined_output:
        output_paths.append(plot_all_datasets(dataset_paths, args.combined_output))

    for output_path in output_paths:
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
