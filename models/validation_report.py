"""
ValidationReport dataclass for the validation gate.

Read-only: produced by validation, consumed by loading.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationReport:
    """Result of cross-collection validation for a single talk."""

    talk_id: int
    is_valid: bool          # go / no-go for loading
    errors: List[str]       # integrity violations — any error sets is_valid=False
    warnings: List[str]     # suspicious but not blocking
    stats: Dict[str, Any]   # counts for summary aggregation

    def __repr__(self) -> str:
        return (
            f"ValidationReport(talk_id={self.talk_id}, "
            f"valid={self.is_valid}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )
