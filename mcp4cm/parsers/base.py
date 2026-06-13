"""Canonical parser contracts and low-level parser registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from mcp4cm.parsers.diagnostics import ParserRunStats, WarningType
from mcp4cm.parsers.ir import IR


class BaseParser(ABC):
    """Base interface for low-level source-file parsers that emit IR."""

    language: str
    version: str = "1.0.0"

    def __init__(self):
        self._run_stats: ParserRunStats | None = None

    @property
    def parser_id(self) -> str:
        return f"{self.language.lower()}@{self.version}"

    def _start_run(self) -> None:
        self._run_stats = ParserRunStats()

    def _stats(self) -> ParserRunStats:
        assert self._run_stats is not None, "No active parsing run. Call _start_run() first."
        return self._run_stats

    def warn(self, warning_type: WarningType, message: str) -> None:
        self._stats().add_warning(warning_type, message)

    def skip_with_warning(self, warning_type: WarningType, message: str) -> None:
        self._stats().add_skip(warning_type, message)

    @abstractmethod
    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        """Parse one source file into IR and parser run stats."""


_LOW_LEVEL_PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def register_parser(parser_class: type[BaseParser]) -> type[BaseParser]:
    """Register a low-level parser class by its native parser language name."""
    parser_instance = parser_class()
    _LOW_LEVEL_PARSER_REGISTRY[parser_instance.language] = parser_class
    return parser_class


def get_parser(language: str) -> type[BaseParser] | None:
    return _LOW_LEVEL_PARSER_REGISTRY.get(language)


def get_all_parsers() -> list[type[BaseParser]]:
    return list(_LOW_LEVEL_PARSER_REGISTRY.values())


@runtime_checkable
class ParserAdapter(Protocol):
    """Catalog-facing parser adapter.

    Every adapter consumes exactly one source file and returns one parsed model
    record plus diagnostics. Adapters may internally use direct JSON graph
    loading or low-level IR parsers.
    """

    def parse_file(self, path: Path, *, model_id: str, options: Any) -> Any: ...
