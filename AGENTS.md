# MCP4CM agent instructions

Python library + Flask API + React web UI for cleansing model-driven engineering datasets (UML, Ecore, ArchiMate, BPMN).

- Python package: `mcp4cm/`
- API: `mcp4cm/api/`
- Web UI: `webapp/`
- Tests: `tests/`
- Lint config: `pyproject.toml` (`[tool.ruff]`)

Requires **Python >= 3.11**.

## Setup

From the repo root:

```bash
uv sync --extra dev
```

Alternative (venv + pip):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Optional ML extras (Node2Vec, BERT duplicate detection):

```bash
uv sync --extra dev --extra ml
```

Web UI dependencies:

```bash
cd webapp && npm install
```

## Lint and format (Ruff)

Run from the repo root. Ruff is configured in `pyproject.toml` (line length 120; rules: E, F, I, B, UP, SIM).

```bash
uv run ruff check .
uv run ruff format --check .
```

Auto-fix:

```bash
uv run ruff check . --fix
uv run ruff format .
```

Check a single rule or file:

```bash
uv run ruff check . --select F841
uv run ruff check mcp4cm/parsers/ecore_ecore/parser.py
```

## Tests

Run the full Python test suite from the repo root:

```bash
uv run pytest
```

Useful variants:

```bash
uv run pytest -q
uv run pytest tests/test_smoke.py
uv run pytest tests/test_api_server.py -k test_flask_health_route
```

Some parser tests require `pyecore` and skip automatically when it is unavailable.

## Build

### Python package

```bash
uv build
```

Editable install for local development:

```bash
uv sync --extra dev
```

### Web UI

```bash
cd webapp
npm run typecheck
npm run build
```

Production-style run (Flask serves the built React app):

```bash
cd webapp && npm run build
cd .. && uv run python -m mcp4cm.api
```

Development run (two terminals):

```bash
# terminal 1
uv run python -m mcp4cm.api

# terminal 2
cd webapp && npm run dev
```

## Full verification (definition of done)

Before finishing Python changes, run from the repo root:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

After web UI changes, also run:

```bash
cd webapp && npm run typecheck && npm run build
```

Do not mark work complete if any of these commands fail.

## Coding conventions

- Match existing style in the file you edit; keep diffs focused.
- Prefer `StrEnum` over `class Foo(str, Enum)` (Python 3.11+).
- In `except` blocks, use `raise ... from err` or `raise ... from None`.
- Prefer `contextlib.suppress(...)` over `try` / `except` / `pass`.
- Prefer combined conditions over nested `if` when Ruff suggests it (SIM102).
- Split long log format strings and f-strings across adjacent string literals; do not switch lazy `%s` logging to f-strings.
- Only create git commits when explicitly asked.

## Scope notes

- Parser work: `mcp4cm/parsers/`
- API routes and jobs: `mcp4cm/api/`
- Duplicate / dummy / statistics logic: `mcp4cm/duplicates.py`, `mcp4cm/dummy.py`, `mcp4cm/statistics.py`
- Notebooks (`*.ipynb`) and `docs/` are exploratory; do not treat them as the source of truth for production code.
