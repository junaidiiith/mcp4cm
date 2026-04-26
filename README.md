# MCP4CM

`mcp4cm` is a Python library for cleansing model-driven engineering datasets such as UML, Ecore, and ArchiMate. It normalizes models into NetworkX graphs, then runs language-independent statistics, dummy-model detection, exact duplicate detection, and TF-IDF near-duplicate detection.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

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
from mcp4cm.statistics import dataset_summary, type_counts, word_counts

summary = dataset_summary(uml)
types = type_counts(archimate)
words = word_counts(ecore)
```

## Dummy Detection

```python
from mcp4cm.dummy import detect_dummy_models, dummy_word_filter, uml_filters

# Uses language-aware defaults. UML records get the UML-specific pattern set.
findings = detect_dummy_models(uml)

# You can also pass the UML preset explicitly.
uml_findings = detect_dummy_models(uml, filters=uml_filters())
custom = detect_dummy_models(uml, filters=[dummy_word_filter({"test", "dummy", "example"})])
```

Show how many models each dummy filter removes:

```python
from mcp4cm import DatasetType, load_dataset
from mcp4cm.dummy import (
    archimate_filters,
    ecore_filters,
    summarize_filters,
    summarize_filters_by_language,
    uml_filters,
)

uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset", language="en")

print("UML")
for row in summarize_filters(uml, filters=uml_filters()):
    print(row.filter_name, row.filtered_count, row.remaining_count)

print("Ecore")
for row in summarize_filters(ecore, filters=ecore_filters()):
    print(row.filter_name, row.filtered_count, row.remaining_count)

print("ArchiMate")
for row in summarize_filters(archimate, filters=archimate_filters()):
    print(row.filter_name, row.filtered_count, row.remaining_count)

# Combined MODELSET: apply UML filters to UML records and Ecore filters to Ecore records.
modelset = load_dataset(DatasetType.MODELSET, "data/modelset")
for language, rows in summarize_filters_by_language(modelset).items():
    print(language)
    for row in rows:
        print(row.filter_name, row.filtered_count, row.remaining_count)
```

## Duplicate Detection

```python
from mcp4cm.duplicates import (
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    duplicate_model_ids_from_votes,
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

# 6. Exact graph isomorphism. Modes: "structure", "types", or "names_types".
same_structure = graph_isomorphism_pairs(uml, mode="types", match_edge_types=True)

# 7. Voting across hash, TF-IDF, graph metrics, and graph isomorphism.
decisions = vote_duplicate_pairs(
    uml,
    min_votes=3,
    tfidf_name_threshold=0.90,
    tfidf_name_type_threshold=0.90,
    graph_threshold=0.85,
    isomorphism_mode="types",
)
duplicate_model_ids = duplicate_model_ids_from_votes(decisions)
```

## Extending With a New Modeling Language

Add a parser that extends `BaseModelParser` and returns a `ModelRecord` with a NetworkX graph. Register it with `mcp4cm.parsers.registry.register("bpmn", BPMNParser)`. Once the parser maps raw data into nodes, edges, names, types, and metadata, the generic cleansing tools work without language-specific changes.
