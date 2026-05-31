# MCP4CM

`mcp4cm` is a Python library for cleansing model-driven engineering datasets such as UML, Ecore, and ArchiMate. It normalizes models into NetworkX graphs, then runs language-independent statistics, dummy-model detection, exact duplicate detection, and TF-IDF near-duplicate detection.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Node2Vec graph embeddings and BERT semantic duplicate detection are optional because they install heavier ML packages:

```bash
pip install -e '.[ml]'
```

## Run the Web UI

Start the Flask backend:

```bash
python -m mcp4cm.api_server
```

Backend logs are written to stdout by default. Set `MCP4CM_LOG_LEVEL` and `MCP4CM_LOG_FILE` to control verbosity and file logging:

```bash
MCP4CM_LOG_LEVEL=DEBUG MCP4CM_LOG_FILE=backend.log python -m mcp4cm.api_server
```

In another terminal, start the React development server:

```bash
cd webapp
npm install
npm run dev
```

During development, the React app calls Flask at `http://127.0.0.1:8765`. In a production-style build served by Flask, it calls same-origin `/api/*` routes.

Large uploads are sent as `multipart/form-data` so the browser does not read the full dataset into JavaScript memory. For very large datasets, prefer `.jsonl` or `.ndjson`; Flask streams those files line by line while parsing.

To serve the built React app from Flask instead:

```bash
cd webapp
npm run build
cd ..
python -m mcp4cm.api_server
```

Then open `http://127.0.0.1:8765`.

## Load Datasets

```python
from mcp4cm import DatasetType, load_dataset

modelset = load_dataset(DatasetType.MODELSET, "data/modelset")
uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset")
```

Filter by language while loading:

```python
# ArchiMate natural language from model.json, for example "en", "de", "es".
english_archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset", language="en")
selected_archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset", language={"en", "de"})

# For combined MODELSET loading, this can also select the modeling language.
uml_only = load_dataset(DatasetType.MODELSET, "data/modelset", language="uml")
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
from mcp4cm import DatasetType, load_dataset
from mcp4cm.dummy import default_filter_configs, summarize_filters, summarize_filters_by_language

uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset", language="en")

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
modelset = load_dataset(DatasetType.MODELSET, "data/modelset")
for language, rows in summarize_filters_by_language(modelset).items():
    print(language)
    for row in rows:
        print(row.filter_id, row.filtered_count, row.remaining_count)
```

## Duplicate Detection

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

# 7. BERT semantic similarity over model names and types. Requires `pip install -e '.[ml]'`.
near_by_bert = bert_semantic_similarity_pairs(uml, threshold=0.90)

# 8. Exact graph isomorphism. Modes: "structure", "names", or "names_types".
same_structure = graph_isomorphism_pairs(uml, mode="names", match_edge_types=True)

# 9. Voting across hash, TF-IDF, graph metrics, and graph isomorphism.
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

## Extending With a New Modeling Language

Add a parser that extends `BaseModelParser` and returns a `ModelRecord` with a NetworkX graph. Register it with `mcp4cm.parsers.registry.register("bpmn", BPMNParser)`. Once the parser maps raw data into nodes, edges, names, types, and metadata, the generic cleansing tools work without language-specific changes.
