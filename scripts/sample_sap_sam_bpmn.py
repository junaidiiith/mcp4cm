#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

from tqdm import tqdm

# Replace with your path to the SAP-SAM dataset
DEFAULT_SOURCE_DIR = Path("/Users/philipp/Projects/datasets/sap-sam")
DEFAULT_OUTPUT_DIR = Path("data/sap-sam-bpmn")
DEFAULT_SAMPLE_SIZE = 5_000
DEFAULT_SEED = 42
DEFAULT_EXTENSIONS = (".json",)
BPMN_DIAGRAM_MARKER = b'"BPMNDiagram"'
VALIDATION_READ_BYTES = 256 * 1024


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


def normalize_extensions(extensions: list[str]) -> tuple[str, ...]:
    return tuple(ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions)


def resolve_models_dir(source_dir: Path) -> Path:
    extracted_models = source_dir / "extracted_models"
    if extracted_models.is_dir():
        return extracted_models
    return source_dir


def iter_model_files(source_dir: Path, extensions: tuple[str, ...]) -> Iterator[Path]:
    """Yield model files without materializing the full source tree."""
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        files.sort()

        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() in extensions:
                yield path


def is_valid_bpmn_diagram(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(VALIDATION_READ_BYTES)
            if BPMN_DIAGRAM_MARKER in chunk:
                return True
            if len(chunk) == VALIDATION_READ_BYTES:
                return False
    except OSError:
        return False

    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(payload, dict):
        return False
    stencil = payload.get("stencil")
    if not isinstance(stencil, dict):
        return False
    return stencil.get("id") == "BPMNDiagram"


def sample_files(
    source_dir: Path,
    sample_size: int,
    seed: int,
    extensions: tuple[str, ...],
    random_sample: bool,
) -> tuple[list[Path], int, int]:
    rng = random.Random(seed)
    sample: list[Path] = []
    scanned = 0
    valid_seen = 0

    models = iter_model_files(source_dir, extensions)
    progress = tqdm(models, desc="scan SAP-SAM", unit="model")
    for source in progress:
        scanned += 1
        if not is_valid_bpmn_diagram(source):
            if scanned % 1000 == 0:
                progress.set_postfix(valid=valid_seen, skipped=scanned - valid_seen)
            continue

        valid_seen += 1
        if scanned % 1000 == 0:
            progress.set_postfix(valid=valid_seen, skipped=scanned - valid_seen)
        if len(sample) < sample_size:
            sample.append(source)
            if not random_sample and len(sample) >= sample_size:
                progress.set_postfix(valid=valid_seen, skipped=scanned - valid_seen)
                break
            continue

        index = rng.randrange(valid_seen)
        if index < sample_size:
            sample[index] = source

    sample.sort(key=lambda path: path.relative_to(source_dir).as_posix())
    return sample, valid_seen, scanned


def copy_sample(source_dir: Path, output_dir: Path, sample: list[Path], force: bool) -> None:
    if output_dir.exists() and force:
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    for source in tqdm(sample, desc="copy sample", unit="model"):
        target = output_dir / source.relative_to(source_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Randomly sample valid extracted BPMN JSON diagrams from SAP-SAM into data/sap-sam-bpmn.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/sample_sap_sam_bpmn.py\n"
            "  python scripts/sample_sap_sam_bpmn.py --seed 7 --force\n"
            "  python scripts/sample_sap_sam_bpmn.py --random-sample --force\n"
            "  python scripts/sample_sap_sam_bpmn.py --extension json\n"
        ),
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"SAP-SAM source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Sample output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Number of models to sample (default: {DEFAULT_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducible sampling (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--extension",
        action="append",
        default=None,
        help="File extension to include. Repeatable. Default: .json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory before copying.",
    )
    parser.add_argument(
        "--random-sample",
        action="store_true",
        help="Scan all candidate files and use reservoir sampling across every valid BPMN diagram.",
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

    source_dir = args.source_dir
    models_dir = resolve_models_dir(source_dir)
    output_dir = args.output_dir
    sample_size = args.sample_size
    extensions = normalize_extensions(args.extension or list(DEFAULT_EXTENSIONS))

    if sample_size <= 0:
        raise ValueError("--sample-size must be greater than 0")
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Could not find SAP-SAM source directory: {source_dir}")
    if not models_dir.is_dir():
        raise FileNotFoundError(f"Could not find SAP-SAM models directory: {models_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise FileExistsError(f"Output directory is not empty: {output_dir}. Use --force to replace it.")

    print(style.bold(style.blue("SAP-SAM BPMN sample")))
    print(style.dim(f"  Source: {source_dir.resolve()}"))
    print(style.dim(f"  Models: {models_dir.resolve()}"))
    print(style.dim(f"  Output: {output_dir.resolve()}"))
    print(style.dim(f"  Sample size: {sample_size}"))
    print(style.dim(f"  Seed: {args.seed}"))
    print()

    sample, valid_candidates, scanned_candidates = sample_files(
        models_dir,
        sample_size,
        args.seed,
        extensions,
        args.random_sample,
    )
    invalid_candidates = scanned_candidates - valid_candidates
    if valid_candidates < sample_size:
        print(style.dim(f"Only found {valid_candidates} valid BPMN diagrams; copying all of them."))

    copy_sample(models_dir, output_dir, sample, args.force)

    print()
    print(style.bold(style.green("Done")))
    print(style.dim(f"  Scanned {scanned_candidates} candidate files."))
    print(style.dim(f"  Skipped {invalid_candidates} files without top-level stencil.id=BPMNDiagram."))
    if args.random_sample:
        print(style.dim(f"  Copied {len(sample)} of {valid_candidates} valid BPMN diagrams."))
    else:
        print(style.dim(f"  Copied {len(sample)} valid BPMN diagrams."))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        style = Style(enabled=sys.stderr.isatty())
        print(style.red(f"error: {error}"), file=sys.stderr)
        raise SystemExit(1) from None
