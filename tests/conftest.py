from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--uml-xmi-model-count",
        action="store",
        default=3,
        type=int,
        metavar="N",
        help="Number of data/modelset-uml-xmi models used by the structural duplicate-detection test (default: 3).",
    )


@pytest.fixture
def uml_xmi_model_count(request: pytest.FixtureRequest) -> int:
    return int(request.config.getoption("--uml-xmi-model-count"))
