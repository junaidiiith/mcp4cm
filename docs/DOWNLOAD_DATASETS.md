# Downloading and Preparing Datasets

Use `scripts/prepare_datasets.py` to download the datasets, extract them, and copy models into the local `data/` directory.

```bash
python scripts/prepare_datasets.py
```

Common options:

```bash
# Prepare only one dataset group
python scripts/prepare_datasets.py --only eamodelset
python scripts/prepare_datasets.py --only modelset

# Prepare only specific subsets
python scripts/prepare_datasets.py --only eamodelset-json
python scripts/prepare_datasets.py --only modelset-uml-xmi --only modelset-uml-json

# Re-download and replace existing output
python scripts/prepare_datasets.py --force

# Custom output location
python scripts/prepare_datasets.py --data-dir /path/to/data
```

Available `--only` values:


| Value                  | Description                                                          |
| ---------------------- | -------------------------------------------------------------------- |
| `eamodelset`           | Both EA ModelSet outputs (`eamodelset-json`, `eamodelset-archimate`) |
| `eamodelset-json`      | EA ModelSet JSON models only                                         |
| `eamodelset-archimate` | EA ModelSet ArchiMate models only                                    |
| `modelset`             | All ModelSet outputs                                                 |
| `modelset-uml-xmi`     | ModelSet UML XMI models only                                         |
| `modelset-uml-json`    | ModelSet UML JSON models only                                        |
| `modelset-ecore-xmi`   | ModelSet Ecore XMI models only                                       |
| `modelset-ecore-json`  | ModelSet Ecore JSON models only                                      |


Prepared output layout:

```
data/
├── eamodelset-json/
├── eamodelset-archimate/
├── modelset-uml-xmi/
├── modelset-uml-json/
├── modelset-ecore-xmi/
└── modelset-ecore-json/
```

---

## EA ModelSet

Download link: [eamodelset.zip](https://github.com/me-big-tuwien-ac-at/EAModelSet/releases/download/v0.0.3/eamodelset.zip)

### Source structure

Each model has its own directory under `processed-models/`, named by model ID (for example, `model_1/`). Inside each model directory you will find files such as:

- `model.json` — model in JSON format
- `model.archimate` — model in Archi Tool XML format

### Prepared output


| Source file       | Output directory        | Output filename        |
| ----------------- | ----------------------- | ---------------------- |
| `model.json`      | `eamodelset-json/`      | `<model-id>.json`      |
| `model.archimate` | `eamodelset-archimate/` | `<model-id>.archimate` |


### Manual steps

If you prepare the dataset without the script:

1. Download the archive.
2. Extract the ZIP file.
3. Copy each `model.json` into `eamodelset-json/` and rename it to `<model-id>.json`.
4. Copy each `model.archimate` into `eamodelset-archimate/` and rename it to `<model-id>.archimate`.

---

## ModelSet

Download link: [modelset.zip](https://github.com/modelset/modelset-dataset/releases/download/v0.9.4/modelset.zip)

### Source structure

- UML (XMI) raw data: `modelset/raw-data/repo-genmymodel-uml/data/` — one file per model, for example `<model-id>.xmi`
- UML (JSON) graph data: `modelset/graph/repo-genmymodel-uml/data/` — one subdirectory per model, for example `<model-id>.xmi/<model-id>.json`
- Ecore (XMI) raw data: `modelset/raw-data/repo-ecore-all/data/` — models may be nested in subdirectories (for example, `ex1/ex2/ex3/model1.ecore`) and split across multiple files
- Ecore (JSON) graph data: `modelset/graph/repo-ecore-all/data/` — same nested layout as the Ecore XMI data, with `.json` files instead of `.ecore`

### Prepared output


| Source           | Output directory       | Output layout                                 |
| ---------------- | ---------------------- | --------------------------------------------- |
| UML XMI files    | `modelset-uml-xmi/`    | Flat files named `<model-id>.xmi`             |
| UML JSON files   | `modelset-uml-json/`   | Flat files named `<model-id>.json`            |
| Ecore XMI files  | `modelset-ecore-xmi/`  | Preserves the original subdirectory structure |
| Ecore JSON files | `modelset-ecore-json/` | Preserves the original subdirectory structure |


### Manual steps

If you prepare the dataset without the script:

1. Download the archive.
2. Extract the ZIP file.
3. Copy each UML XMI model into `modelset-uml-xmi/` as `<model-id>.xmi`.
4. Copy each UML JSON model into `modelset-uml-json/` as `<model-id>.json`.
5. Copy each Ecore XMI file into `modelset-ecore-xmi/`, preserving the original subdirectory structure.
6. Copy each Ecore JSON file into `modelset-ecore-json/`, preserving the original subdirectory structure.

---

## SAP SAM Signavio (BPMN)

TODO