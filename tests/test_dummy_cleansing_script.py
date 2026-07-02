from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_dummy_cleansing_script() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "evaluation" / "dummy_cleansing.py"
    spec = importlib.util.spec_from_file_location("dummy_cleansing_script", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_dummy_filter_unions_excludes_language_only_models() -> None:
    script = load_dummy_cleansing_script()
    result_payload = {
        "dataset": "sample",
        "runSummary": {"total_models": 4},
        "modelOutcomes": [
            {"allTriggeredFilters": ["language"]},
            {"allTriggeredFilters": ["language", "placeholder_name_ratio"]},
            {"allTriggeredFilters": ["too_few_named_elements"]},
            {"allTriggeredFilters": []},
        ],
    }

    rows = script.summarize_dummy_filter_unions(result_payload)

    assert rows == [
        {
            "dataset": "sample",
            "variant": "all_enabled",
            "filterSet": "All enabled filters",
            "excludedFilterId": None,
            "totalModels": 4,
            "removed": 3,
            "remaining": 1,
            "removalRate": 75.0,
        },
        {
            "dataset": "sample",
            "variant": "without_language",
            "filterSet": "Without language filter",
            "excludedFilterId": "language",
            "totalModels": 4,
            "removed": 2,
            "remaining": 2,
            "removalRate": 50.0,
        },
    ]
