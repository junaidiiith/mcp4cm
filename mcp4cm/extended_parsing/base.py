"""Base parser interface and registry."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from mcp4cm.extended_ir.types import IR
from mcp4cm.extended_parsing.types import CannotParseError
from mcp4cm.extended_parsing.types import WarningType
from mcp4cm.extended_parsing.types import ParserRunStats

# Global registry for parsers
_PARSER_REGISTRY: Dict[str, type] = {}

def register_parser(parser_class: type) -> type:
    """Decorator to register a parser class."""
    parser_instance = parser_class()
    _PARSER_REGISTRY[parser_instance.language] = parser_class
    return parser_class


def get_parser(language: str) -> Optional[type]:
    """Get parser class by language name."""
    return _PARSER_REGISTRY.get(language)


def get_all_parsers() -> List[type]:
    """Get all registered parser classes."""
    return list(_PARSER_REGISTRY.values())


class BaseParser(ABC):
    """Base interface for model parsers."""

    language: str
    version: str = "1.0.0"  # Parser version identifier
    
    def __init__(self):
        """Initialize parser with run stats tracking."""
        self._run_stats: Optional[ParserRunStats] = None

    @property
    def parser_id(self) -> str:
        """Get parser identifier (language@version)."""
        return f"{self.language.lower()}@{self.version}"
    
    def _start_run(self):
        """Start a new parsing run and initialize stats tracking."""
        self._run_stats = ParserRunStats()
    
    def _stats(self) -> ParserRunStats:
        """Get current run stats. Raises AssertionError if no run is active."""
        assert self._run_stats is not None, "No active parsing run. Call _start_run() first."
        return self._run_stats
    
    def warn(self, warning_type: WarningType, message: str):
        """
        Record a warning for an element that is kept but has issues.
        
        Args:
            warning_type: Type of warning
            message: Warning message
        """
        # warn(message)
        self._stats().add_warning(warning_type, message)
    
    def skip_with_warning(self, warning_type: WarningType, message: str):
        """
        Record a skipped element with a warning.
        
        Args:
            warning_type: Type of warning
            message: Warning message explaining why element was skipped
        """
        # warn(message)
        self._stats().add_skip(warning_type, message)

    @abstractmethod
    def parse(self, filepath: str) -> Tuple[IR, ParserRunStats]:
        """
        Parse a model file into IR.

        Args:
            filepath: Path to the model file

        Returns:
            Tuple of (IR object, ParserRunStats)

        Raises:
            CannotParseError: If the file is not in this parser's format
                (e.g., wrong XML root/namespace)
        """
        pass
