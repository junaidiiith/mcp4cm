# Parsers

MCP4CM parses modeling files into a common `ModelRecord`: a model id, language, metadata, and a NetworkX graph. The same parsers are used by the Python API, dataset loaders, and web upload flow. ss

For dataset download and preparation instructions, see [DOWNLOAD_DATASETS.md](DOWNLOAD_DATASETS.md).

## Table of Contents

- [Parsers](#parsers)
  - [Table of Contents](#table-of-contents)
  - [Supported Parsers](#supported-parsers)
  - [Downloadable Datasets](#downloadable-datasets)
  - [Loading Examples](#loading-examples)
  - [Input Examples](#input-examples)
    - [UML JSON and Ecore JSON](#uml-json-and-ecore-json)
    - [UML XMI](#uml-xmi)
    - [UML XML with PyEcore](#uml-xml-with-pyecore)
    - [Ecore](#ecore)
    - [ArchiMate JSON](#archimate-json)
    - [ArchiMate Archi XML](#archimate-archi-xml)
    - [BPMN Signavio JSON](#bpmn-signavio-json)
  - [Output Shape](#output-shape)
  - [Upload Notes](#upload-notes)

## Supported Parsers


| Language  | Format key    | File extensions        | Typical source             | Notes                                                               |
| --------- | ------------- | ---------------------- | -------------------------- | ------------------------------------------------------------------- |
| UML       | `json`        | `.json`                | ModelSet UML graph JSON    | Reads one graph JSON object per file.                               |
| UML       | `xmi`         | `.xmi`, `.xml`         | ModelSet UML XMI, UML2 XMI | Native UML XMI parser with options for feature projection.          |
| UML       | `xml-pyecore` | `.xmi`, `.uml`, `.xml` | UML XML/XMI                | Alternative parser using PyEcore.                                   |
| Ecore     | `json`        | `.json`                | ModelSet Ecore graph JSON  | Reads one graph JSON object per file, including nested directories. |
| Ecore     | `ecore`       | `.ecore`               | ModelSet Ecore raw files   | Parses Ecore metamodel files using PyEcore.                         |
| ArchiMate | `json`        | `.json`                | EA ModelSet JSON           | Reads EA ModelSet's normalized JSON structure.                      |
| ArchiMate | `xmi`         | `.archimate`, `.xml`   | Archi Tool files           | Parses Archi `.archimate` XML exports.                              |
| BPMN      | `signavio`    | `.json`                | Signavio/Oryx JSON         | Expects a top-level `BPMNDiagram` stencil.                          |


Parser keys are passed as `language` and `format`, for example `language="uml", format="xmi"`.

## Downloadable Datasets

The preparation script writes data into the layout expected by the loaders:

```bash
python scripts/prepare_datasets.py
```

Common prepared directories:


| Directory                    | Parser           |
| ---------------------------- | ---------------- |
| `data/eamodelset-json/`      | `archimate/json` |
| `data/eamodelset-archimate/` | `archimate/xmi`  |
| `data/modelset-uml-xmi/`     | `uml/xmi`        |
| `data/modelset-uml-json/`    | `uml/json`       |
| `data/modelset-ecore-xmi/`   | `ecore/ecore`    |
| `data/modelset-ecore-json/`  | `ecore/json`     |


Source archives:

- EA ModelSet: `https://github.com/me-big-tuwien-ac-at/EAModelSet/releases/download/v0.0.3/eamodelset.zip`
- ModelSet: `https://github.com/modelset/modelset-dataset/releases/download/v0.9.4/modelset.zip`

See [DOWNLOAD_DATASETS.md](DOWNLOAD_DATASETS.md) for `--only` values, source layouts, and manual preparation steps.

## Loading Examples

Load one file:

```python
from mcp4cm.parsers.parse import parse_file

result = parse_file(
    "data/modelset-uml-json/_kJ3-sL17EeedTfUoC-GfaA.json",
    language="uml",
    format="json",
)

record = result.record
print(record.model_id, record.node_count, record.edge_count)
```

Load a directory:

```python
from mcp4cm.loading import load_modelset, load_eamodelset

uml_json = load_modelset("data/modelset-uml-json", language="uml", format="json")
ecore_json = load_modelset("data/modelset-ecore-json", language="ecore", format="json")
archimate_json = load_eamodelset("data/eamodelset-json")
```

Load by dataset type:

```python
from mcp4cm import DatasetType, load_dataset

uml = load_dataset(DatasetType.MODELSET_UML, "data/modelset-uml-json", format="json")
ecore = load_dataset(DatasetType.MODELSET_ECORE, "data/modelset-ecore-json", format="json")
archimate = load_dataset(DatasetType.EAMODELSET, "data/eamodelset-json", format="json")
```

Filter EA ModelSet by natural language:

```python
english = load_eamodelset("data/eamodelset-json", language="en")
selected = load_eamodelset("data/eamodelset-json", language={"en", "de"})
```

## Input Examples

The examples below show the expected shape, not every supported field.

### UML JSON and Ecore JSON

ModelSet UML and Ecore JSON files are graph exports. The parser accepts graph fields at the top level:

```json
{
  "directed": true,
  "multigraph": true,
  "nodes": [
    { "id": 1, "name": "User", "eClass": "Actor" },
    { "id": 2, "name": "Login", "eClass": "UseCase" }
  ],
  "links": [
    { "source": 1, "target": 2, "type": "Association" }
  ]
}
```

It also accepts the older wrapped shape:

```json
{
  "ids": "model-1",
  "graph": {
    "directed": true,
    "nodes": [{ "id": "A", "name": "Customer", "type": "Class" }],
    "edges": []
  }
}
```

Use:

```python
parse_file("model.json", language="uml", format="json")
parse_file("model.json", language="ecore", format="json")
```

### UML XMI

The UML XMI parser reads UML2-style XMI/XML files:

```xml
<xmi:XMI
  xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="Example">
    <packagedElement xsi:type="uml:Class" xmi:id="Customer" name="Customer"/>
    <packagedElement xsi:type="uml:Class" xmi:id="Order" name="Order"/>
    <packagedElement xsi:type="uml:Association" xmi:id="A1" memberEnd="end1 end2"/>
  </uml:Model>
</xmi:XMI>
```

Use:

```python
parse_file("model.xmi", language="uml", format="xmi")
```

Options:


| Option                 | Default | Meaning                                            |
| ---------------------- | ------- | -------------------------------------------------- |
| `includeAttributes`    | `true`  | Add UML attributes as synthetic graph nodes.       |
| `includeOperations`    | `true`  | Add UML operations as synthetic graph nodes.       |
| `includeParameters`    | `true`  | Add operation parameters as synthetic graph nodes. |
| `includeModelRootNode` | `true`  | Include the UML model root node.                   |


Example:

```python
parse_file(
    "model.xmi",
    language="uml",
    format="xmi",
    options={"includeAttributes": False},
)
```

### UML XML with PyEcore

The `uml/xml-pyecore` parser accepts `.xmi`, `.uml`, and `.xml` UML files and uses PyEcore for loading:

```python
parse_file("model.uml", language="uml", format="xml-pyecore")
```

Use this parser when you want to compare the native UML XMI parser against PyEcore loading behavior.

### Ecore

The Ecore parser reads Ecore metamodel files:

```xml
<ecore:EPackage
  xmlns:ecore="http://www.eclipse.org/emf/2002/Ecore"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  name="shop"
  nsURI="http://example/shop"
  nsPrefix="shop">
  <eClassifiers xsi:type="ecore:EClass" name="Customer"/>
  <eClassifiers xsi:type="ecore:EClass" name="Order"/>
</ecore:EPackage>
```

Use:

```python
parse_file("model.ecore", language="ecore", format="ecore")
```

Options:


| Option                | Default | Meaning                                   |
| --------------------- | ------- | ----------------------------------------- |
| `resolveExternalRefs` | `true`  | Try to resolve external Ecore references. |


### ArchiMate JSON

EA ModelSet JSON contains model metadata plus `elements` and `relationships`:

```json
{
  "archimateId": "model-1",
  "name": "Example",
  "language": "en",
  "elements": [
    {
      "id": "app",
      "name": "Application",
      "type": "ApplicationComponent",
      "layer": "application"
    },
    {
      "id": "data",
      "name": "Customer data",
      "type": "DataObject",
      "layer": "application"
    }
  ],
  "relationships": [
    {
      "id": "rel-1",
      "sourceId": "app",
      "targetId": "data",
      "type": "Access"
    }
  ],
  "views": []
}
```

Use:

```python
parse_file("model.json", language="archimate", format="json")
```

### ArchiMate Archi XML

Archi `.archimate` files are XML exports from the Archi tool:

```xml
<archimate:model
  xmlns:archimate="http://www.archimatetool.com/archimate"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <folder type="application">
    <element id="app" xsi:type="archimate:ApplicationComponent" name="Application"/>
    <element id="data" xsi:type="archimate:DataObject" name="Customer data"/>
  </folder>
  <folder type="relations">
    <element id="rel-1" xsi:type="archimate:AccessRelationship" source="app" target="data"/>
  </folder>
</archimate:model>
```

Use:

```python
parse_file("model.archimate", language="archimate", format="xmi")
```

### BPMN Signavio JSON

The BPMN parser expects Signavio/Oryx JSON with a top-level `BPMNDiagram` stencil:

```json
{
  "resourceId": "diagram-1",
  "stencil": { "id": "BPMNDiagram" },
  "properties": { "name": "Order process" },
  "childShapes": [
    {
      "resourceId": "start",
      "stencil": { "id": "StartNoneEvent" },
      "properties": { "name": "Start" },
      "outgoing": [{ "resourceId": "flow-1" }]
    },
    {
      "resourceId": "flow-1",
      "stencil": { "id": "SequenceFlow" },
      "target": { "resourceId": "task" }
    }
  ]
}
```

Use:

```python
parse_file("diagram.json", language="bpmn", format="signavio")
```

## Output Shape

Every parser returns a `ParsedModelResult`:

```python
result.record       # ModelRecord
result.diagnostics  # ModelDiagnostics
result.ir           # IR for source-file parsers, otherwise None
```

`ModelRecord.graph` is a NetworkX graph. Nodes usually expose `name`, `type`, or `eClass`; edges usually expose `type` or source-specific relationship fields.

```python
for node_id, attrs in result.record.graph.nodes(data=True):
    print(node_id, attrs.get("name"), attrs.get("type") or attrs.get("eClass"))
```

## Upload Notes

The web UI uses the same parser keys. Choose a language and format, then upload files or a directory. The batch parser skips unsupported extensions and empty files, and reports parse errors in the upload summary.

For JSON formats, one file must contain one JSON object.
