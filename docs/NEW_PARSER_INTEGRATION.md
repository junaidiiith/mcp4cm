# New Parser Integration

This guide is for developers adding a parser to MCP4CM. For user-facing parser formats and examples, see [PARSERS.md](PARSERS.md).

## Current Parser Flow

All parsers are registered in `mcp4cm/parsers/catalog.py` and resolved by:

```text
(language, format)
```

Current keys:

```text
uml/json
uml/xmi
uml/xml-pyecore
ecore/json
ecore/ecore
archimate/json
archimate/xmi
bpmn/signavio
```

The shared batch parser in `mcp4cm/parsers/parse.py` handles files, extension checks, empty files, ignored upload artifacts, parser exceptions, diagnostics, and progress callbacks. Once a parser is registered, it is available to `parse_file`, `parse_files`, dataset loaders, and the web upload API.

## What A Parser Returns

Every successful parse returns a `ParsedModelResult`:

```python
ParsedModelResult(
    record=ModelRecord(...),
    diagnostics=ModelDiagnostics(...),
    ir=ir_or_none,
)
```

Downstream statistics, dummy detection, duplicate detection, and visualization use `ModelRecord.graph`. Add useful node and edge attributes when the source provides them:

```python
graph.add_node("n1", name="Customer", type="Class")
graph.add_edge("n1", "n2", type="Association")
```

For IR parsers, `convert_to_networkx(...)` and `normalize_graph_attributes(...)` do this normalization for common fields.

## Choose A Parser Pattern

### Direct `ModelRecord` Parser

Use this when the input is already graph-like JSON.

Existing examples:

- `mcp4cm/parsers/modelset_json/parser.py`
- `mcp4cm/parsers/archimate_json/parser.py`

Implement a small payload parser that returns `ModelRecord`, then add a `JsonGraphParserAdapter` subclass in `catalog.py`.

```python
class MyJsonAdapter(JsonGraphParserAdapter):
    def __init__(self):
        self.parser = MyJsonParser()

    def parse_payload(self, payload: dict[str, Any], *, model_id: str) -> ModelRecord:
        payload_id = payload.get("id") or model_id
        return self.parser.parse(payload, model_id=str(payload_id))
```

`JsonGraphParserAdapter` already reads the file, requires one JSON object, sets `record.source_path`, and creates success diagnostics.

### IR Parser

Use this for XML, XMI, `.ecore`, tool-specific JSON, or formats where a normalized intermediate representation is useful.

Existing examples:

- `mcp4cm/parsers/uml_xmi/parser.py`
- `mcp4cm/parsers/ecore_ecore/parser.py`
- `mcp4cm/parsers/bpmn_signavio/parser.py`

Implement a parser that returns `(IR, ParserRunStats)`, then add an `IRParserAdapter` subclass in `catalog.py`.

```python
from mcp4cm.parsers.base import BaseParser
from mcp4cm.parsers.diagnostics import ParserRunStats
from mcp4cm.parsers.ir import IR, Node


class MyToolParser(BaseParser):
    language = "MyTool"

    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        self._start_run()
        ir = IR(id="model-1", language=self.language, data={"name": "Example"})
        ir.nodes.append(Node(id="n1", type="Class", name="Customer", data={}))
        return ir, self._stats()
```

```python
class MyToolAdapter(IRParserAdapter):
    metadata_language = "my_language"
    format_name = "tool"

    def create_parser(self, options: ParserOptions):
        _ = options
        return MyToolParser()
```

`IRParserAdapter` handles invalid-edge dropping, NetworkX conversion, graph attribute normalization, `ModelRecord` creation, and diagnostics conversion.

## Register The Parser

Add a descriptor in `mcp4cm/parsers/catalog.py`:

```python
register_descriptor(
    ParserDescriptor(
        language="my_language",
        format="tool",
        parser_id="my-language-tool",
        extensions=(".tool",),
        adapter_factory=MyToolAdapter,
    )
)
```

If the parser has options, declare them on the descriptor:

```python
ParserDescriptor(
    language="my_language",
    format="tool",
    parser_id="my-language-tool",
    extensions=(".tool",),
    adapter_factory=MyToolAdapter,
    option_specs=(
        OptionSpec("includeDetails", "include_details", True, bool_option),
    ),
)
```

External option names are API/frontend names, usually camelCase. Adapters read normalized snake_case options:

```python
include_details = bool(options.get("include_details", True))
```

Unsupported option keys are rejected automatically.

## Frontend Upload

If users should upload the new format in the web UI, add it to `webapp/src/config.ts`:

```ts
export const formatOptionsByLanguage = {
  my_language: [
    { value: "tool", label: "My Tool", directoryPreferred: true, accept: ".tool" },
  ],
};
```

If the parser needs user-selectable options, add the controls to the upload flow and send them as the parser option names declared in `OptionSpec`.

## Diagnostics

For IR parsers, use `BaseParser` helpers:

```python
self.warn(WarningType.UNHANDLED_ATTRIBUTE, "Ignored unsupported attribute x.")
self.skip_with_warning(WarningType.MISSING_ATTRIBUTE, "Skipped element without id.")
```

Use warnings when the model can still be parsed. Use skips when an element is intentionally omitted. Avoid silently dropping source elements that affect model meaning.

Common warning types are defined in `mcp4cm/parsers/diagnostics.py`, including:

- `MISSING_ATTRIBUTE`
- `DUPLICATE_ID`
- `UNRESOLVED_REFERENCE`
- `INVALID_TYPE_REFERENCE`
- `UNKNOWN_NODE_TYPE`
- `UNKNOWN_EDGE_TYPE`
- `UNHANDLED_ATTRIBUTE`
- `UNHANDLED_CHILD`
- `OTHER`

File-level parse failures are reported by the batch parser as upload issues. Do not store diagnostics in `ModelRecord.metadata`.

## Tests To Add

Add focused tests in `tests/` for:

- `resolve_parser(language, format)` returns the descriptor.
- Supported extensions parse successfully.
- Unsupported extensions are skipped by `parse_staged_files(...)`.
- Invalid input reports a parse error or raises the parser's expected exception.
- Valid input returns a `ModelRecord` with expected node and edge counts.
- Diagnostics contain useful counts and warnings.
- Parser options are accepted, defaulted, and rejected when unsupported.

For IR parsers, also test:

- The low-level parser returns expected `IR` nodes and edges.
- Missing references are warned about or skipped.
- Graph conversion produces expected NetworkX attributes.

For JSON graph parsers, also test:

- One JSON object per file succeeds.
- Node and edge attributes are preserved.
- Unsupported JSON shapes fail clearly.

## Integration Checklist

1. Create `mcp4cm/parsers/<language>_<format_or_tool>/`.
2. Implement the parser.
3. Add an adapter in `mcp4cm/parsers/catalog.py`.
4. Register a `ParserDescriptor`.
5. Add tests.
6. Add a web upload option in `webapp/src/config.ts` if needed.
7. Update [PARSERS.md](PARSERS.md) with the new user-facing format.
