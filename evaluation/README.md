# Evaluation

This directory contains the evaluation drivers and their generated JSON artifacts.
Run all commands from the repository root, not from inside `evaluation/`. The scripts use relative default paths such as
`data/` and `evaluation/`.

## Prerequisites

Install development and ML dependencies:

```bash
uv sync --extra dev --extra ml
```

The evaluation expects prepared input datasets below `data/`:

- `data/modelset-uml-xmi`
- `data/modelset-ecore-xmi`
- `data/eamodelset-archimate`
- `data/sap-sam-bpmn`

`modelset-uml-xmi`, `modelset-ecore-xmi`, and `eamodelset-archimate` can be downloaded and prepared with `scripts/prepare_datasets.py`.
See [docs/DOWNLOAD_DATASETS.md](../docs/DOWNLOAD_DATASETS.md) for the full dataset download instructions:

```bash
uv run python scripts/prepare_datasets.py --only modelset-uml-xmi --only modelset-ecore-xmi --only eamodelset-archimate
```

SAP-SAM BPMN is not downloaded by `prepare_datasets.py`. Download SAP-SAM from the [`signavio/sap-sam`](https://github.com/signavio/sap-sam) repository and follow that repository's README to fully download and extract the dataset.
After the SAP-SAM dataset is available locally, use `evaluation/sample_sap_sam_bpmn.py` to sample 5,000 valid BPMN models into `data/sap-sam-bpmn`:

```bash
uv run python evaluation/sample_sap_sam_bpmn.py --source-dir /path/to/sap-sam --force
```

The sampler also has a `DEFAULT_SOURCE_DIR` constant for local convenience. Adjust it if you want to run the script without `--source-dir`; for example it currently points to a local path like:

```python
DEFAULT_SOURCE_DIR = Path("/Users/philipp/Projects/datasets/sap-sam")
```

## Run The Evaluation

From the repository root, run the following commands.

Parse the source datasets into runtime IR:

```bash
uv run python evaluation/parse_datasets.py --force
```

Run independent dummy-cleansing filters on the parsed runtime datasets:

```bash
uv run python evaluation/dummy_cleansing.py
```

Run independent duplicate-detection techniques on the parsed runtime datasets:

```bash
uv run python evaluation/duplicate_detection.py
```

Prepare the generated JSON summaries as Markdown tables:

```bash
uv run python evaluation/prepare_results.py
```

To run only one dataset or dataset group, pass `--only` to any script:

```bash
uv run python evaluation/parse_datasets.py --only modelset --force
uv run python evaluation/dummy_cleansing.py --only sap-sam-bpmn
uv run python evaluation/duplicate_detection.py --only modelset-uml-xmi
```

## Outputs

Parsing writes one runtime directory per dataset:

```text
evaluation/<dataset>-runtime/
  index.json
  parse_result.json
  statistics.json
  upload_summary.json
  ir/*.json
```

Dummy cleansing writes:

```text
evaluation/<dataset>-runtime/dummy_cleansing.json
evaluation/<dataset>-runtime/dummy_cleansing_summary.json
evaluation/dummy_cleansing_summary.json
```

Duplicate detection writes:

```text
evaluation/<dataset>-runtime/duplicate_detection.json
evaluation/<dataset>-runtime/duplicate_detection_summary.json
evaluation/duplicate_detection_summary.json
```

Result preparation writes:

```text
evaluation/results.md
```

Files ending in `_old.json` are retained comparison artifacts and are not used by the current evaluation scripts.

## Current Duplicate Thresholds

The duplicate-detection evaluation uses pipeline defaults for Hash, TF-IDF, and Graph metrics. BERT and GNN use stricter standalone-reporting thresholds to avoid giant connected components:

- BERT semantic: `0.95`
- Contrastive GNN: `0.97`

These thresholds are recorded in the generated duplicate-detection JSON configs.

## Verification

After changing the Python evaluation scripts, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
