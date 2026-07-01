# MCP4CM

`mcp4cm` is a Python library for cleansing model-driven engineering datasets such as UML, Ecore, and ArchiMate. It normalizes models into NetworkX graphs, then runs language-independent statistics, dummy-model detection, exact duplicate detection, and TF-IDF near-duplicate detection.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Node2Vec, contrastive GNN, and BERT semantic duplicate detection are optional because they install heavier ML packages:

```bash
pip install -e '.[ml]'
```

## Run the Web UI

Start the Flask backend:

```bash
python -m mcp4cm.api
```

Backend logs are written to stdout by default. Set `MCP4CM_LOG_LEVEL` and `MCP4CM_LOG_FILE` to control verbosity and file logging:

```bash
MCP4CM_LOG_LEVEL=DEBUG MCP4CM_LOG_FILE=backend.log python -m mcp4cm.api
```

In another terminal, start the React development server:

```bash
cd webapp
npm install
npm run dev
```

During development, the React app calls Flask at `http://127.0.0.1:8765`. In a production-style build served by Flask, it calls same-origin `/api/*` routes.

Large uploads are sent as `multipart/form-data` so the browser does not read the full dataset into JavaScript memory.

To serve the built React app from Flask instead:

```bash
cd webapp
npm run build
cd ..
python -m mcp4cm.api
```

Then open `http://127.0.0.1:8765`.

## Download Datasets

EA ModelSet and ModelSet can be downloaded and prepared locally with `scripts/prepare_datasets.py`. The script downloads the datasets, extracts the models, and copies them into `data/` in the layout expected by the application.

```bash
python scripts/prepare_datasets.py
```

To prepare only a subset, use `--only` (for example `eamodelset`, `modelset`, or fine-grained targets such as `modelset-uml-json`). See [docs/DOWNLOAD_DATASETS.md](docs/DOWNLOAD_DATASETS.md) for all options, source layout, and manual preparation steps.

## Parsers

MCP4CM supports UML, Ecore, ArchiMate, and BPMN inputs through parser keys such as `uml/xmi`, `uml/json`, `ecore/ecore`, `ecore/json`, `archimate/json`, `archimate/xmi`, and `bpmn/signavio`. Parsers normalize source files into `ModelRecord` objects backed by NetworkX graphs, so statistics, dummy detection, duplicate detection, and visualization can run across formats.

See [docs/PARSERS.md](docs/PARSERS.md) for supported formats, input examples, dataset sources, parser options, and loading examples.

## Load Datasets

```python
from mcp4cm import DatasetType, load_dataset

uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset-uml-json", format="json")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset-ecore-json", format="json")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset-json", format="json")
```

Filter by language while loading:

```python
# ArchiMate natural language from model.json, for example "en", "de", "es".
english_archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset-json", format="json", language="en")
selected_archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset-json", format="json", language={"en", "de"})
```

Each dataset contains `ModelRecord` objects with a normalized `networkx` graph plus source metadata.

## Statistics

```python
from mcp4cm.statistics import dataset_summary, name_counts, type_counts

summary = dataset_summary(uml)
types = type_counts(archimate)
names = name_counts(ecore)
```

## Dummy Detection

```python
from mcp4cm.dummy import default_filter_configs, detect_dummy_models

# Uses built-in defaults.
findings = detect_dummy_models(uml)

# You can pass customized configs with `filter_configs=...`.
configs = default_filter_configs()
for config in configs:
    if config["id"] == "placeholder_name_ratio":
        config["threshold"] = 0.25
    if config["id"] == "regex_rule":
        config["enabled"] = True
        config["pattern"] = r"^(test|dummy|sample)$"
        config["targetField"] = "name"
        config["scope"] = "all_named_nodes"
        config["minMatches"] = 1

custom_findings = detect_dummy_models(uml, filter_configs=configs)
```

Show how many models each dummy filter removes:

```python
from mcp4cm import Dataset, DatasetType, load_dataset
from mcp4cm.dummy import default_filter_configs, summarize_filters, summarize_filters_by_language

uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset-uml-json", format="json")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset-ecore-json", format="json")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset-json", format="json", language="en")

configs = default_filter_configs()

print("UML")
for row in summarize_filters(uml, filter_configs=configs):
    print(row.filter_id, row.filtered_count, row.remaining_count)

print("Ecore")
for row in summarize_filters(ecore, filter_configs=configs):
    print(row.filter_id, row.filtered_count, row.remaining_count)

print("ArchiMate")
for row in summarize_filters(archimate, filter_configs=configs):
    print(row.filter_id, row.filtered_count, row.remaining_count)

# Combined MODELSET: summarize per language using default filter configs.
combined = Dataset([*uml.records, *ecore.records], "modelset")
for language, rows in summarize_filters_by_language(combined).items():
    print(language)
    for row in rows:
        print(row.filter_id, row.filtered_count, row.remaining_count)
```

## Duplicate Detection

Run exact hash-based duplicate detection on a prepared dataset directly from the command line:

```bash
python3 scripts/run_duplicate_detection.py eamodelset-json
```

The dataset argument is the directory name under `data/`. The script writes a JSON report to standard output. Run several
methods in one invocation, for example `--technique hash tfidf graph-similarity`; the available methods are `hash`,
`tfidf`, `graph-similarity`, `node2vec`, `gnn`, `bert-similarity`, and `isomorphism`. Use `--output report.json` to save
the report. Node2Vec, GNN, and BERT require the optional ML dependencies: `pip install -e '.[ml]'`.

Each method result contains only `initialTotalModels`, `duplicateModelsRemoved`, and `uniqueModelsRemaining`. Runtime
statistics are in the separate `timingsMs` object; progress and timing are logged to stderr. Use `--log-level DEBUG` for
more verbose output. Terminal progress bars are shown for every selected method; use `--no-progress` for non-interactive
runs.

```python
from mcp4cm.duplicates import (
    bert_semantic_similarity_pairs,
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    duplicate_model_ids_from_votes,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_by_names,
    tfidf_duplicate_by_names_and_types,
    vote_duplicate_pairs,
)

# 1. Exact hash from sorted node names.
same_names = detect_duplicates_by_node_name_hash(uml)

# 2. Exact hash from sorted node name + node type pairs.
same_names_and_types = detect_duplicates_by_node_name_type_hash(uml)

# 3. TF-IDF near-duplicates using names only.
near_by_names = tfidf_duplicate_by_names(uml, threshold=0.90)

# 4. TF-IDF near-duplicates using names and types.
near_by_names_and_types = tfidf_duplicate_by_names_and_types(uml, threshold=0.90)

# 5. Graph similarity using node-name, node-type, edge-type, degree, size, and density metrics.
near_by_graph = graph_similarity_pairs(uml, threshold=0.85)

# 6. Node2Vec graph embedding similarity. Requires `pip install -e '.[ml]'`.
near_by_graph_embeddings = graph_embedding_pairs(uml, threshold=0.90)

# 7. GraphCL-style contrastive GNN similarity over sentence-encoded node/edge text.
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs
near_by_gnn = gnn_duplicate_pairs(uml, threshold=0.85, config=GNNTrainingConfig(epochs=20))

# 8. BERT semantic similarity over model names and types. Requires `pip install -e '.[ml]'`.
near_by_bert = bert_semantic_similarity_pairs(uml, threshold=0.90)

# 9. Exact graph isomorphism. Modes: "structure", "names", or "names_types".
same_structure = graph_isomorphism_pairs(uml, mode="names", match_edge_types=True)

# 10. Voting across hash, TF-IDF, graph metrics, and graph isomorphism.
decisions = vote_duplicate_pairs(
    uml,
    min_votes=3,
    tfidf_name_threshold=0.90,
    tfidf_name_type_threshold=0.90,
    graph_threshold=0.85,
    isomorphism_mode="names",
)
duplicate_model_ids = duplicate_model_ids_from_votes(decisions)
```

Node2Vec, contrastive GNN, and BERT vectors are cached as
`.mcp4cm_embeddings/<dataset_name>/<graph_id>/node2vec.npz`, `contrastive_gnn.npz`, and `bert.npz`.
Pass `embedding_cache_dir` to either detector to select a cache root. The batch
runner defaults to `<data-dir>/.mcp4cm_embeddings` and accepts
`--embedding-cache-dir`. To verify first-run persistence and the subsequent
reload against a prepared dataset, run:

```bash
python3 scripts/test_embedding_cache.py eamodelset-json --data-dir data
```

Plot duplicate-model removal and unique-model counts for TF-IDF, contrastive GNN,
and BERT over the 20 thresholds from `0.05` through `1.00`. TF-IDF is vectorized
once and GNN/BERT vectors are trained or loaded once:

```bash
python3 scripts/plot_embedding_thresholds.py eamodelset-json --data-dir data
```

The script writes one JSON, CSV, and two-line PNG chart per technique to
`embedding-threshold-results/<dataset>/`; filenames include both names, such as
`gnn_eamodelset-json.json`. It requires the ML dependencies and the optional
plotting dependency: `pip install -e '.[ml,plot]'`.

To inspect vector collisions, cosine-score percentiles, and the connected
components that turn matched pairs into duplicate removals without recomputing
embeddings, run:

```bash
python3 scripts/diagnose_embedding_similarity.py eamodelset-json --data-dir data
```

## Extending Parsers

Parsers are resolved by `(language, format)` through `mcp4cm.parsers.catalog`.
Current parser keys are:

- `uml/json`
- `uml/xmi`
- `uml/xml-pyecore`
- `ecore/json`
- `ecore/ecore`
- `archimate/json`
- `archimate/xmi`
- `bpmn/signavio`

Add a parser package under `mcp4cm/parsers/`, register a `ParserDescriptor`, and return a `ParsedModelResult` containing a `ModelRecord` plus `ModelDiagnostics`. JSON graph parsers may build `ModelRecord` directly; source-file parsers can emit IR and convert it through the shared graph utilities.

See [docs/NEW_PARSER_INTEGRATION.md](docs/NEW_PARSER_INTEGRATION.md) for the developer checklist.
