from __future__ import annotations

from mcp4cm.parsers.base import BaseModelParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, type[BaseModelParser]] = {}

    def register(self, language: str, parser_cls: type[BaseModelParser]) -> None:
        self._parsers[language.lower()] = parser_cls

    def create(self, language: str) -> BaseModelParser:
        try:
            return self._parsers[language.lower()]()
        except KeyError as exc:
            raise ValueError(f"No parser registered for language: {language}") from exc

    def languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._parsers))


registry = ParserRegistry()

