# New Parser Integration Guide

This guide explains how to add future parsers to MCP4CM after the parser refactor.

The application now resolves parsers by `(language, format)` through the canonical parser package:

```text
mcp4cm/parsers/
```

There is no separate "legacy" or "extended" parser architecture. Parsers differ only by source language/format and by whether they parse directly into a `ModelRecord` or first produce IR.

## Current Parser Keys

Registered parser descriptors live in `mcp4cm/parsers/catalog.py`.

Current public keys:

```text
uml/json
uml/xmi
ecore/json
ecore/ecore
archimate/json
archimate/xmi
bpmn/signavio
```

Internal package names can be more precise than the public format name:

```text
archimate/xmi     -> mcp4cm/parsers/archimate_archi/
bpmn/signavio     -> mcp4cm/parsers/bpmn_signavio/
uml/xmi           -> mcp4cm/parsers/uml_xmi/
```

## High-Level Architecture

```text
Upload / library call
    |
    v
resolve_parser(language, format)
    |
    v
ParserDescriptor
    |
    +-- validates extension
    +-- validates options
    +-- creates parser adapter
    |
    v
ParserAdapter.parse_file(...)
    |
    v
ParsedModelResult
    |
    +-- record: ModelRecord
    +-- diagnostics: ModelDiagnostics
    +-- ir: IR | None
```

The batch parser in `mcp4cm/parsers/parse.py` handles:

- ignored upload files such as `.DS_Store`
- unsupported file extensions
- empty files
- parser exceptions
- progress callbacks
- aggregation into records, diagnostics, and file-level issues

The Flask API uses the same batch parser for all formats.

## Choose An Integration Pattern

There are two valid parser implementation styles.

### Pattern A: Direct Graph Parser

Use this when the source already contains a graph-like JSON model and no IR step is useful.

Examples:

- `modelset_json`
- `archimate_json`

Direct graph parsers should return a `ModelRecord` with a NetworkX graph.

```text
JSON file
    |
    v
JsonGraphParserAdapter
    |
    v
ModelRecord
```

Important current rule:

- `format=json` means one `.json` file containing exactly one JSON object.
- JSON arrays, JSONL, and NDJSON are not supported by `json`.

### Pattern B: IR Parser

Use this when parsing a source language/file format benefits from a normalized intermediate representation.

Examples:

- UML XMI
- ArchiMate Archi XML
- Ecore `.ecore`
- BPMN Signavio JSON

Low-level IR parsers extend `BaseParser` and return `(IR, ParserRunStats)`.

```text
source file
    |
    v
BaseParser.parse(filepath)
    |
    v
IR + ParserRunStats
    |
    v
IRParserAdapter
    |
    +-- drops invalid IR edges with missing nodes
    +-- converts IR to NetworkX
    +-- normalizes graph attributes
    +-- applies optional projection
    |
    v
ModelRecord + ModelDiagnostics
```

## Required Data Shapes

### `ModelRecord`

Defined in `mcp4cm/core.py`.

Every successful parser result must produce a `ModelRecord`:

```python
ModelRecord(
    model_id="model-1",
    language="uml",
    graph=networkx_graph,
    labels=(),
    name="Optional Model Name",
    source_path=Path("relative/or/source/path"),
    raw_text="",
    raw_xmi="",
    metadata={},
)
```

Downstream features depend on:

- `record.graph`
- `record.model_id`
- `record.language`
- node attributes such as `name`, `type`, and sometimes `eClass`
- edge attributes such as `type` or `relationship`

### `IR`

Defined in `mcp4cm/parsers/ir.py`.

Use IR for source-file parsers:

```python
IR(
    id="model-1",
    language="MyParserLanguage",
    data={"name": "Model Name"},
    nodes=[
        Node(id="n1", type="Class", name="Customer", data={}),
    ],
    edges=[
        Edge(id="e1", sourceId="n1", targetId="n2", type="Association", data={}),
    ],
)
```

IR requirements:

- `IR.id` should be stable if the source provides a model ID.
- `IR.language` should identify the low-level parser/source language.
- `Node.id` values must be unique.
- `Edge.id` values should be unique.
- Edge endpoints should refer to existing node IDs.

The adapter currently calls `drop_ir_edges_with_missing_nodes()` before converting to NetworkX, but new parsers should still try to emit valid IR.

### `ModelDiagnostics`

Defined in `mcp4cm/core.py`.

Parser adapters return parser-neutral diagnostics:

```python
ModelDiagnostics(
    parse_status="success",  # "success", "warning", or "failure"
    warning_count=0,
    warnings_by_type={},
    warning_messages_by_type={},
    error_message="",
    elements_loaded=12,
    elements_skipped=0,
    parse_time_ms=4,
    source_path="models/model-1.xmi",
)
```

`Dataset.diagnostics` stores diagnostics only for successfully parsed models, keyed by `model_id`.

Failed or skipped files are represented as file-level issues in the upload summary, not as `Dataset` entries.

## Parser Run Stats

Low-level IR parsers use `ParserRunStats`, defined in `mcp4cm/parsers/diagnostics.py`.

```python
ParserRunStats(
    elements_skipped=0,
    warning_count=0,
    warnings_by_type={},
    warning_msgs={},
)
```

If your parser extends `BaseParser`, use the built-in helpers:

```python
self._start_run()
self.warn(WarningType.UNHANDLED_ATTRIBUTE, "Kept element but ignored attribute ...")
self.skip_with_warning(WarningType.MISSING_ATTRIBUTE, "Skipped element without id ...")
return ir, self._stats()
```

Use:

- `warn(...)` when the parser keeps the element/model but noticed a quality issue.
- `skip_with_warning(...)` when the parser intentionally skips an element.

`skip_with_warning(...)` increments both:

- `elements_skipped`
- `warning_count`

## Warning Types

Use the existing `WarningType` enum when possible:

```text
UNKNOWN_NODE_TYPE
UNKNOWN_EDGE_TYPE
DUPLICATE_ID
UNRESOLVED_REFERENCE
INVALID_TYPE_REFERENCE
UNSUPPORTED_GENERIC_REFERENCE
MISSING_EDGE_ENDPOINT
COMPATIBILITY_ADAPTATION
MISSING_ATTRIBUTE
MULTIPLE_ROOT_PACKAGES
UNHANDLED_ATTRIBUTE
UNHANDLED_CHILD
DEFERRED_REF_UNRESOLVED
OTHER
```

Choose warning types consistently:

- Missing required XML/JSON IDs: `MISSING_ATTRIBUTE`
- Duplicate source IDs: `DUPLICATE_ID`
- References to missing nodes/types: `UNRESOLVED_REFERENCE` or `INVALID_TYPE_REFERENCE`
- Known source compatibility workaround: `COMPATIBILITY_ADAPTATION`
- Parser does not understand an element type: `UNKNOWN_NODE_TYPE` or `UNKNOWN_EDGE_TYPE`
- Parser intentionally ignores a known but unsupported detail: `UNHANDLED_ATTRIBUTE`, `UNHANDLED_CHILD`, or `OTHER`

Do not silently discard meaningful source elements unless they are truly irrelevant.

## Implementing A Direct JSON Graph Parser

Use this pattern if the source file can be loaded directly into a NetworkX graph.

### 1. Create a parser package

Example:

```text
mcp4cm/parsers/my_language_json/
    __init__.py
    parser.py
```

### 2. Implement a payload parser

```python
from __future__ import annotations

from typing import Any, Mapping

from mcp4cm._deps import require_networkx
from mcp4cm.core import ModelRecord


class MyLanguageJsonParser:
    language = "my_language"

    def parse(self, raw: Mapping[str, Any], *, model_id: str | None = None) -> ModelRecord:
        nx = require_networkx()
        graph = nx.DiGraph(language=self.language)

        for node in raw.get("nodes", []):
            attrs = dict(node)
            node_id = str(attrs.pop("id"))
            graph.add_node(node_id, **attrs)

        for edge in raw.get("edges", []):
            attrs = dict(edge)
            source = attrs.pop("source")
            target = attrs.pop("target")
            graph.add_edge(source, target, **attrs)

        return ModelRecord(
            model_id=model_id or str(raw.get("id") or ""),
            language=self.language,
            graph=graph,
            name=raw.get("name"),
            metadata={"source": "my_language_json"},
        )
```

### 3. Add an adapter

Most direct JSON parsers can subclass `JsonGraphParserAdapter` in `mcp4cm/parsers/catalog.py`.

```python
class MyLanguageJsonAdapter(JsonGraphParserAdapter):
    def __init__(self):
        self.parser = MyLanguageJsonParser()

    def parse_payload(self, payload: dict[str, Any], *, model_id: str) -> ModelRecord:
        payload_id = payload.get("id") or model_id
        return self.parser.parse(payload, model_id=str(payload_id))
```

`JsonGraphParserAdapter.parse_file(...)` already handles:

- reading the file
- requiring a single JSON object
- setting `record.source_path`
- computing success diagnostics
- returning `ParsedModelResult(record, diagnostics, ir=None)`

## Implementing An IR Parser

Use this pattern if you parse XML, XMI, Ecore, tool-specific JSON, or another structured source where IR is useful.

### 1. Create a parser package

Example:

```text
mcp4cm/parsers/my_language_tool/
    __init__.py
    parser.py
    utils.py
```

### 2. Implement a low-level parser

```python
from __future__ import annotations

from pathlib import Path

from mcp4cm.parsers.base import BaseParser, register_parser
from mcp4cm.parsers.diagnostics import CannotParseError, ParserRunStats, WarningType
from mcp4cm.parsers.ir import Edge, IR, Node


@register_parser
class MyLanguageToolParser(BaseParser):
    language = "MyLanguage-Tool"

    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        self._start_run()

        path = Path(filepath)
        if not path.exists():
            raise CannotParseError(f"File does not exist: {filepath}")

        ir = IR(
            id=path.stem,
            language=self.language,
            data={"source_path": str(path)},
        )

        # Parse source contents here.
        # Add nodes and edges to ir.nodes / ir.edges.
        ir.nodes.append(Node(id="n1", type="ExampleType", name="Example", data={}))

        if not ir.nodes:
            self.warn(WarningType.OTHER, "Model contains no parsed nodes.")

        return ir, self._stats()
```

### 3. Add an adapter

Most IR parsers can subclass `IRParserAdapter` in `mcp4cm/parsers/catalog.py`.

```python
class MyLanguageToolAdapter(IRParserAdapter):
    metadata_language = "my_language"
    format_name = "tool"

    def create_parser(self, options: ParserOptions):
        _ = options
        return MyLanguageToolParser()
```

`IRParserAdapter.parse_file(...)` already handles:

- creating the low-level parser
- parsing `IR + ParserRunStats`
- dropping IR edges with missing endpoints and recording skips
- converting IR to NetworkX
- normalizing top-level `name` and `type` graph attributes
- creating `ModelRecord`
- converting `ParserRunStats` to `ModelDiagnostics`
- returning `ParsedModelResult(record, diagnostics, ir=ir)`

Override `apply_projection(...)` only when the parser has format-specific graph-shaping options.

## Parser Options

Parser options are declared on the `ParserDescriptor`.

External option names should match the API/frontend payload, usually camelCase.
Internal option names should be snake_case.

Example from UML XMI:

```python
ParserDescriptor(
    language="uml",
    format="xmi",
    parser_id="uml-xmi",
    extensions=(".xmi", ".xml"),
    adapter_factory=UMLXMIAdapter,
    option_specs=(
        OptionSpec("includeAttributes", "include_attributes", True, bool_option),
        OptionSpec("includeOperations", "include_operations", True, bool_option),
        OptionSpec("includeParameters", "include_parameters", True, bool_option),
        OptionSpec("includeModelRootNode", "include_model_root_node", False, bool_option),
    ),
)
```

Option behavior:

- Unsupported option keys are rejected.
- Defaults are applied by the descriptor.
- Adapters receive normalized snake_case options through `ParserOptions`.

Read options inside adapters with:

```python
enabled = bool(options.get("some_option", False))
```

## Registering The Parser

Add a `ParserDescriptor` registration in `mcp4cm/parsers/catalog.py`.

```python
register_descriptor(
    ParserDescriptor(
        language="my_language",
        format="tool",
        parser_id="my-language-tool",
        extensions=(".tool",),
        adapter_factory=MyLanguageToolAdapter,
    )
)
```

The public parser key becomes:

```text
my_language/tool
```

The frontend/backend upload flow will use this descriptor for:

- language/format validation
- extension matching
- parser option validation
- adapter creation

## File Extension Policy

Each descriptor declares allowed extensions:

```python
extensions=(".json",)
```

The batch parser skips unsupported file extensions with a file-level warning:

```text
SKIPPED_UNSUPPORTED_EXTENSION
```

The upload job succeeds if at least one model parses.
If zero models parse, the job ends with status `error` and includes an `uploadSummary`.

## Model IDs

The batch parser passes `model_id=Path(relpath).stem` into the adapter.

Adapters may override that with a source-provided ID:

```python
payload_id = payload.get("id") or model_id
```

Recommended behavior:

- Prefer stable IDs from the source file when available.
- Fall back to the filename stem.
- Ensure IDs are strings.

## Metadata Guidelines

`ModelRecord.metadata` should contain source/model metadata only.

Do not store parser diagnostics in `ModelRecord.metadata`.

Diagnostics belong in:

```python
ParsedModelResult.diagnostics
Dataset.diagnostics[model_id]
runtime parseDiagnostics
inspect response diagnostics
```

Useful metadata examples:

- source tool name
- format name
- model-level source fields
- extracted vocabulary used by downstream duplicate detection

## Graph Attribute Guidelines

Downstream cleansing and visualization work best when nodes and edges expose normalized fields.

For nodes:

```python
graph.add_node(node_id, name="Customer", type="Class")
```

For edges:

```python
graph.add_edge(source, target, type="Association")
```

If using IR, `convert_to_networkx(...)` creates nodes with:

```python
id
type
name
data
```

Then `normalize_graph_attributes(...)` promotes `data["name"]` and `data["type"]` to top-level graph attributes when needed.

## Projection Hooks

Projection means changing graph shape after parsing but before creating the final `ModelRecord`.

Current example:

- `uml/xmi` can expand attributes, operations, and parameters into synthetic nodes.

Projection is implemented by overriding:

```python
def apply_projection(self, graph, options: ParserOptions) -> None:
    ...
```

Only add projection when it is intentionally part of the parser descriptor behavior.

Keep source parsing and graph projection conceptually separate:

- parser: read source semantics
- projection: shape the graph for cleansing/analysis

## Runtime And API Integration

Once registered, a parser is automatically available to:

- `mcp4cm.parsers.parse.parse_file(...)`
- `mcp4cm.parsers.parse.parse_files(...)`
- the upload API
- runtime persistence
- model inspection

The upload flow stores:

```text
Dataset.records
Dataset.diagnostics
runtime/ir/{dataset_id}/{model_id}.json
```

Runtime model files include:

```text
graph
metadata
parseDiagnostics
```

Model inspection responses include:

```text
diagnostics
nodes
edges
model metadata
```

## Testing Checklist

Add focused tests for every new parser.

Minimum tests:

- descriptor resolves with `resolve_parser(language, format)`
- supported extensions are accepted
- unsupported extensions are skipped by `parse_staged_files(...)`
- unsupported options are rejected
- valid source file returns one `ParsedModelResult`
- result contains a `ModelRecord`
- result diagnostics has correct status/counts
- parser warnings are reflected in diagnostics
- invalid source produces a parse issue or `CannotParseError`

For IR parsers, also test:

- low-level parser returns valid `IR`
- duplicate IDs are handled predictably
- missing references produce warnings/skips
- `ParserRunStats` counts skipped/warned elements correctly
- IR conversion creates expected NetworkX nodes/edges

For JSON graph parsers, also test:

- one JSON object per file succeeds
- JSON arrays fail
- JSONL/NDJSON files are skipped by extension if not registered separately
- graph node/edge attributes are preserved

## Common Mistakes

Avoid these:

- Adding a parser without a `ParserDescriptor`.
- Accepting unsupported options silently.
- Returning multiple models from one file.
- Storing parse warnings in `ModelRecord.metadata`.
- Emitting edges to missing node IDs without recording warnings.
- Omitting node `name`/`type` attributes when the source has them.
- Using a generic internal package name when a tool-specific name is clearer.

## Quick Integration Template

```text
1. Create mcp4cm/parsers/<language>_<source>/
2. Implement parser.py
3. If direct graph JSON:
     - implement payload parser -> ModelRecord
     - add JsonGraphParserAdapter subclass
4. If source/IR parser:
     - implement BaseParser.parse(filepath) -> (IR, ParserRunStats)
     - add IRParserAdapter subclass
5. Register ParserDescriptor in catalog.py
6. Add tests
7. If frontend upload should expose it:
     - add language/format option in webapp/src/config.ts
     - add typed options if needed
```
