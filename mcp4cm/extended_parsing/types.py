"""Types used by parser integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from mcp4cm.extended_ir.types import IR


class CannotParseError(Exception):
    """Raised when a parser cannot parse a file in its expected format."""


class WarningType(str, Enum):
    """Types of warnings that can occur during parsing."""

    UNKNOWN_NODE_TYPE = "UNKNOWN_NODE_TYPE"
    UNKNOWN_EDGE_TYPE = "UNKNOWN_EDGE_TYPE"
    DUPLICATE_ID = "DUPLICATE_ID"
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    INVALID_TYPE_REFERENCE = "INVALID_TYPE_REFERENCE"
    UNSUPPORTED_GENERIC_REFERENCE = "UNSUPPORTED_GENERIC_REFERENCE"
    MISSING_EDGE_ENDPOINT = "MISSING_EDGE_ENDPOINT"
    COMPATIBILITY_ADAPTATION = "COMPATIBILITY_ADAPTATION"
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"
    MULTIPLE_ROOT_PACKAGES = "MULTIPLE_ROOT_PACKAGES"
    UNHANDLED_ATTRIBUTE = "UNHANDLED_ATTRIBUTE"
    UNHANDLED_CHILD = "UNHANDLED_CHILD"
    DEFERRED_REF_UNRESOLVED = "DEFERRED_REF_UNRESOLVED"
    OTHER = "OTHER"


ParseStatus = Literal["success", "warning", "failure"]


@dataclass
class ParserRunStats:
    """Statistics collected during a parser run."""

    elements_skipped: int = 0
    warning_count: int = 0
    warnings_by_type: Dict[WarningType, int] = field(default_factory=dict)
    warning_msgs: Dict[WarningType, List[str]] = field(default_factory=dict)

    def add_skip(self, warning_type: WarningType, message: str = "") -> None:
        """Record a skipped element with a warning."""
        self.elements_skipped += 1
        self.add_warning(warning_type, message)

    def add_warning(self, warning_type: WarningType, message: str = "") -> None:
        """Record a warning."""
        self.warning_count += 1
        self.warnings_by_type[warning_type] = self.warnings_by_type.get(warning_type, 0) + 1

        if warning_type not in self.warning_msgs:
            self.warning_msgs[warning_type] = []
        if message:
            self.warning_msgs[warning_type].append(message)


@dataclass
class ModelParseDiagnostics:
    """Diagnostics for a single model parse operation."""

    file_id: str
    relpath: str
    parse_status: ParseStatus
    parse_error_msg: Optional[str] = None
    elements_loaded: int = 0
    elements_skipped: int = 0
    parse_time_ms: int = 0
    file_size_bytes_source: int = 0
    file_size_bytes_ir: int = 0
    warning_count: int = 0
    warnings_by_type: Dict[str, int] = field(default_factory=dict)
    warning_msgs: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def skip_ratio(self) -> float:
        """Ratio of skipped elements to total elements."""
        denom = max(1, self.elements_loaded + self.elements_skipped)
        return self.elements_skipped / denom

    @property
    def warnings_per_element(self) -> float:
        """Average warnings per loaded element."""
        denom = max(1, self.elements_loaded)
        return self.warning_count / denom

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["skip_ratio"] = self.skip_ratio
        result["warnings_per_element"] = self.warnings_per_element
        return result


@dataclass
class ParseFailure:
    """Information about a failed parse attempt."""

    relpath: str
    ir_id: Optional[str]
    error_class: str
    message: str
    parser: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ParseBatchResult:
    """Result container for batch parsing operations."""

    parser_language: str
    totals: Dict[str, int]
    irs: List[IR] = field(default_factory=list)
    diagnostics: Dict[str, ModelParseDiagnostics] = field(default_factory=dict)
    failures: List[ParseFailure] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "parser_language": self.parser_language,
            "totals": dict(self.totals),
            "irs": [ir.to_dict() for ir in self.irs],
            "diagnostics": {k: v.to_dict() for k, v in self.diagnostics.items()},
            "failures": [f.to_dict() for f in self.failures],
        }
