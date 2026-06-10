#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from tqdm import tqdm


EA_MODELSET_URL = (
    "https://github.com/me-big-tuwien-ac-at/EAModelSet/releases/download/"
    "v0.0.3/eamodelset.zip"
)
MODELSET_URL = (
    "https://github.com/modelset/modelset-dataset/releases/download/"
    "v0.9.4/modelset.zip"
)

ALL_TARGETS = (
    "eamodelset-json",
    "eamodelset-archimate",
    "modelset-uml-xmi",
    "modelset-uml-json",
    "modelset-ecore-xmi",
    "modelset-ecore-json",
)

TARGET_GROUPS: dict[str, tuple[str, ...]] = {
    "eamodelset": ("eamodelset-json", "eamodelset-archimate"),
    "modelset": (
        "modelset-uml-xmi",
        "modelset-uml-json",
        "modelset-ecore-xmi",
        "modelset-ecore-json",
    ),
}

PARSER_CHOICES = tuple(TARGET_GROUPS) + ALL_TARGETS


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

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)


@dataclass(frozen=True)
class TargetSpec:
    name: str
    label: str
    output_dir: str
    source: str


TARGET_SPECS: dict[str, TargetSpec] = {
    "eamodelset-json": TargetSpec(
        name="eamodelset-json",
        label="EA ModelSet JSON",
        output_dir="eamodelset-json",
        source="EA ModelSet",
    ),
    "eamodelset-archimate": TargetSpec(
        name="eamodelset-archimate",
        label="EA ModelSet ArchiMate",
        output_dir="eamodelset-archimate",
        source="EA ModelSet",
    ),
    "modelset-uml-xmi": TargetSpec(
        name="modelset-uml-xmi",
        label="ModelSet UML XMI",
        output_dir="modelset-uml-xmi",
        source="ModelSet",
    ),
    "modelset-uml-json": TargetSpec(
        name="modelset-uml-json",
        label="ModelSet UML JSON",
        output_dir="modelset-uml-json",
        source="ModelSet",
    ),
    "modelset-ecore-xmi": TargetSpec(
        name="modelset-ecore-xmi",
        label="ModelSet Ecore XMI",
        output_dir="modelset-ecore-xmi",
        source="ModelSet",
    ),
    "modelset-ecore-json": TargetSpec(
        name="modelset-ecore-json",
        label="ModelSet Ecore JSON",
        output_dir="modelset-ecore-json",
        source="ModelSet",
    ),
}


class DownloadProgress:
    def __init__(self, label: str) -> None:
        self.label = label
        self.bar: tqdm | None = None

    def __call__(self, block_num: int, block_size: int, total_size: int) -> None:
        if self.bar is None:
            self.bar = tqdm(
                total=total_size if total_size > 0 else None,
                desc=self.label,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
            )

        downloaded = block_num * block_size
        self.bar.update(downloaded - self.bar.n)

        if total_size > 0 and downloaded >= total_size:
            self.bar.close()


def resolve_targets(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(ALL_TARGETS)

    resolved: list[str] = []
    for item in selected:
        if item in TARGET_GROUPS:
            resolved.extend(TARGET_GROUPS[item])
            continue
        if item not in ALL_TARGETS:
            raise ValueError(f"Unknown target: {item}")
        resolved.append(item)

    return list(dict.fromkeys(resolved))


def needs_eamodelset(targets: Iterable[str]) -> bool:
    return any(target.startswith("eamodelset-") for target in targets)


def needs_modelset(targets: Iterable[str]) -> bool:
    return any(target.startswith("modelset-") for target in targets)


def print_banner(style: Style) -> None:
    print(style.bold(style.cyan("Dataset preparation")))
    print(style.dim("Download archives, extract models, and copy into data/."))
    print()


def print_step(style: Style, title: str, detail: str | None = None) -> None:
    print(style.bold(style.blue(f"▸ {title}")))
    if detail:
        print(style.dim(f"  {detail}"))


def print_skip(style: Style, message: str) -> None:
    print(style.yellow(f"  skip  {message}"))


def print_action(style: Style, message: str) -> None:
    print(style.green(f"  {message}"))


def print_summary(style: Style, data_dir: Path, counts: dict[str, int]) -> None:
    label_width = max(len(spec.label) for spec in TARGET_SPECS.values())
    count_width = max(len(str(count)) for count in counts.values()) if counts else 1

    print()
    print(style.bold(style.green("✓ Done")))
    print(style.dim(f"  Output directory: {data_dir.resolve()}"))
    print()
    print(style.bold("Results"))
    print(style.dim("  " + "─" * (label_width + count_width + 10)))

    for target in ALL_TARGETS:
        if target not in counts:
            continue
        spec = TARGET_SPECS[target]
        count = counts[target]
        print(
            f"  {spec.label:<{label_width}}  "
            f"{style.bold(str(count).rjust(count_width))}  "
            f"{style.dim(spec.output_dir + '/')}"
        )

    print()


def download(url: str, target: Path, force: bool, style: Style) -> None:
    if target.exists() and not force:
        print_skip(style, f"already downloaded: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    print_action(style, f"downloading {target.name}")

    progress = DownloadProgress(f"download {target.name}")
    urllib.request.urlretrieve(url, target, reporthook=progress)

    if progress.bar is not None:
        progress.bar.close()


def unzip(zip_path: Path, target_dir: Path, force: bool, style: Style) -> None:
    if target_dir.exists() and force:
        shutil.rmtree(target_dir)

    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        print_skip(style, f"already extracted: {target_dir}")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    print_action(style, f"extracting {zip_path.name}")

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()

        for member in tqdm(members, desc=f"extract {zip_path.name}", unit="file"):
            archive.extract(member, target_dir)


def ensure_dirs(paths: Iterable[Path], force: bool) -> None:
    for path in paths:
        if path.exists() and force:
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def remove_cache(cache_dir: Path, style: Style) -> None:
    if not cache_dir.exists():
        return

    print_step(style, "Cleaning up cache", str(cache_dir.resolve()))
    shutil.rmtree(cache_dir)
    print_action(style, "removed cache directory")


def first_existing(paths: Iterable[Path], label: str) -> Path:
    paths = list(paths)

    for path in paths:
        if path.is_dir():
            return path

    tried = "\n  - ".join(str(path) for path in paths)
    raise FileNotFoundError(f"Could not find {label}. Tried:\n  - {tried}")


def require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"Could not find {label}: {path}")


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prepare_eamodelset_json(extract_dir: Path, data_dir: Path) -> int:
    processed_dir = first_existing(
        [
            extract_dir / "dataset" / "processed-models",
            extract_dir / "processed-models",
            extract_dir / "eamodelset" / "processed-models",
            extract_dir / "EAModelSet" / "processed-models",
        ],
        "EA ModelSet processed-models directory",
    )

    json_dir = data_dir / "eamodelset-json"
    model_dirs = [p for p in sorted(processed_dir.iterdir()) if p.is_dir()]
    json_count = 0

    for model_dir in tqdm(model_dirs, desc="copy EA ModelSet JSON", unit="model"):
        model_json = model_dir / "model.json"
        if model_json.is_file():
            copy(model_json, json_dir / f"{model_dir.name}.json")
            json_count += 1

    return json_count


def prepare_eamodelset_archimate(extract_dir: Path, data_dir: Path) -> int:
    processed_dir = first_existing(
        [
            extract_dir / "dataset" / "processed-models",
            extract_dir / "processed-models",
            extract_dir / "eamodelset" / "processed-models",
            extract_dir / "EAModelSet" / "processed-models",
        ],
        "EA ModelSet processed-models directory",
    )

    archimate_dir = data_dir / "eamodelset-archimate"
    model_dirs = [p for p in sorted(processed_dir.iterdir()) if p.is_dir()]
    archimate_count = 0

    for model_dir in tqdm(model_dirs, desc="copy EA ModelSet ArchiMate", unit="model"):
        model_archimate = model_dir / "model.archimate"
        if model_archimate.is_file():
            copy(model_archimate, archimate_dir / f"{model_dir.name}.archimate")
            archimate_count += 1

    return archimate_count


def prepare_modelset_uml_xmi(extract_dir: Path, data_dir: Path) -> int:
    root = first_existing(
        [extract_dir / "modelset", extract_dir],
        "ModelSet root directory",
    )
    uml_xmi = root / "raw-data" / "repo-genmymodel-uml" / "data"
    require_dir(uml_xmi, "UML XMI source")
    return copy_flat(uml_xmi, data_dir / "modelset-uml-xmi", "*.xmi", "copy UML XMI")


def prepare_modelset_uml_json(extract_dir: Path, data_dir: Path) -> int:
    root = first_existing(
        [extract_dir / "modelset", extract_dir],
        "ModelSet root directory",
    )
    uml_json = root / "graph" / "repo-genmymodel-uml" / "data"
    require_dir(uml_json, "UML JSON source")
    return copy_nested_uml_json(uml_json, data_dir / "modelset-uml-json")


def prepare_modelset_ecore_xmi(extract_dir: Path, data_dir: Path) -> int:
    root = first_existing(
        [extract_dir / "modelset", extract_dir],
        "ModelSet root directory",
    )
    ecore_xmi = root / "raw-data" / "repo-ecore-all" / "data"
    require_dir(ecore_xmi, "Ecore XMI source")
    return copy_tree(ecore_xmi, data_dir / "modelset-ecore-xmi", "*.ecore", "copy Ecore XMI")


def prepare_modelset_ecore_json(extract_dir: Path, data_dir: Path) -> int:
    root = first_existing(
        [extract_dir / "modelset", extract_dir],
        "ModelSet root directory",
    )
    ecore_json = root / "graph" / "repo-ecore-all" / "data"
    require_dir(ecore_json, "Ecore JSON source")
    return copy_tree(ecore_json, data_dir / "modelset-ecore-json", "*.json", "copy Ecore JSON")


TARGET_HANDLERS: dict[str, Callable[[Path, Path], int]] = {
    "eamodelset-json": prepare_eamodelset_json,
    "eamodelset-archimate": prepare_eamodelset_archimate,
    "modelset-uml-xmi": prepare_modelset_uml_xmi,
    "modelset-uml-json": prepare_modelset_uml_json,
    "modelset-ecore-xmi": prepare_modelset_ecore_xmi,
    "modelset-ecore-json": prepare_modelset_ecore_json,
}


def copy_flat(source_dir: Path, target_dir: Path, pattern: str, label: str) -> int:
    files = [p for p in sorted(source_dir.glob(pattern)) if p.is_file()]

    for source in tqdm(files, desc=label, unit="file"):
        copy(source, target_dir / source.name)

    return len(files)


def copy_nested_uml_json(source_dir: Path, target_dir: Path) -> int:
    """Copy UML JSON from <model-id>.xmi/<model-id>.json into a flat target dir."""
    files: list[Path] = []

    for model_dir in sorted(source_dir.iterdir()):
        if not model_dir.is_dir():
            continue

        model_id = model_dir.stem
        json_file = model_dir / f"{model_id}.json"

        if json_file.is_file():
            files.append(json_file)

    for source in tqdm(files, desc="copy UML JSON", unit="file"):
        copy(source, target_dir / f"{source.stem}.json")

    return len(files)


def copy_tree(source_dir: Path, target_dir: Path, pattern: str, label: str) -> int:
    files = [p for p in sorted(source_dir.rglob(pattern)) if p.is_file()]

    for source in tqdm(files, desc=label, unit="file"):
        copy(source, target_dir / source.relative_to(source_dir))

    return len(files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and prepare EA ModelSet and ModelSet datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/prepare_datasets.py\n"
            "  python scripts/prepare_datasets.py --only eamodelset\n"
            "  python scripts/prepare_datasets.py --only modelset-uml-xmi --only modelset-uml-json\n"
            "  python scripts/prepare_datasets.py --only eamodelset-json --data-dir data --force\n"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=PARSER_CHOICES,
        metavar="TARGET",
        help=(
            "Prepare only the selected dataset or subset. "
            "Use dataset groups (eamodelset, modelset) or fine-grained targets "
            f"({', '.join(ALL_TARGETS)}). Repeatable. Default: all."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory for prepared dataset output (default: data).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".dataset-cache"),
        help="Temporary download/extract directory (removed after success).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download archives, re-extract, and replace existing output directories.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    style = Style(enabled=sys.stdout.isatty() and not args.no_color)

    targets = resolve_targets(args.only)
    data_dir = args.data_dir
    cache_dir = args.cache_dir
    force = args.force

    print_banner(style)
    print_step(
        style,
        "Selected targets",
        ", ".join(targets) if args.only else "all datasets",
    )
    print()

    output_dirs = [data_dir / TARGET_SPECS[target].output_dir for target in targets]
    ensure_dirs(output_dirs, force)

    ea_dir = cache_dir / "eamodelset-extracted"
    modelset_dir = cache_dir / "modelset-extracted"
    counts: dict[str, int] = {}

    if needs_eamodelset(targets):
        print_step(style, "EA ModelSet")
        download(EA_MODELSET_URL, cache_dir / "eamodelset.zip", force, style)
        unzip(cache_dir / "eamodelset.zip", ea_dir, force, style)
        print()

    if needs_modelset(targets):
        print_step(style, "ModelSet")
        download(MODELSET_URL, cache_dir / "modelset.zip", force, style)
        unzip(cache_dir / "modelset.zip", modelset_dir, force, style)
        print()

    for target in targets:
        spec = TARGET_SPECS[target]
        print_step(style, spec.label, spec.output_dir + "/")
        extract_dir = ea_dir if target.startswith("eamodelset-") else modelset_dir
        counts[target] = TARGET_HANDLERS[target](extract_dir, data_dir)
        print()

    print_summary(style, data_dir, counts)
    remove_cache(cache_dir, style)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        style = Style(enabled=sys.stderr.isatty())
        print(style.red(f"error: {error}"), file=sys.stderr)
        raise SystemExit(1)
