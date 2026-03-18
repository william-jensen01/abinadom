"""
Footnote data structures for Phase 4 extraction.

Provides type-safe representation of footnote data with validation.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class FootnoteData:
    """Represents a single footnote extracted from a talk paragraph."""

    # Identity
    footnote_id: int        # talk_id * 100000 + paragraph_number * 100 + footnote_index (1-based)
    talk_id: int
    paragraph_id: int       # talk_id * 10000 + paragraph_number
    paragraph_number: int   # 1-indexed

    # Raw extraction
    footnote_number: int    # Superscript number (* → sequential fallback)
    footnote_text_raw: str  # Full footnote text (embedded as ChromaDB document)

    # Position in paragraph clean text
    char_position: int      # Where marker appears (-1 if not found)

    # Context
    context_before: str = ""
    context_after: str = ""
    context_window: str = ""   # context_before + footnote_text_raw + context_after

    # Metadata
    parse_success: bool = True
    extraction_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate required fields."""
        if self.footnote_id <= 0:
            raise ValueError(f"Invalid footnote_id: {self.footnote_id}")
        if self.paragraph_number < 1:
            raise ValueError(f"Invalid paragraph_number: {self.paragraph_number}")
        if self.footnote_number < 1:
            raise ValueError(f"Invalid footnote_number: {self.footnote_number}")
        if not self.footnote_text_raw:
            raise ValueError("footnote_text_raw must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_chromadb_format(self) -> tuple[str, Dict[str, Any], str]:
        """
        Convert to ChromaDB format.

        Returns:
            Tuple of (document, metadata, id)
                - document: context_window (or footnote_text_raw if context unavailable)
                - metadata: All metadata fields except context_window
                - id: Unique identifier (fn_{footnote_id})
        """
        document = self.context_window or self.footnote_text_raw
        metadata = self.to_dict()
        metadata.pop("context_window", None)
        doc_id = f"fn_{self.footnote_id}"
        return document, metadata, doc_id

    def __repr__(self) -> str:
        return (
            f"FootnoteData(id={self.footnote_id}, "
            f"talk_id={self.talk_id}, "
            f"fn_num={self.footnote_number}, "
            f"char_pos={self.char_position})"
        )


@dataclass
class TalkFootnotes:
    """Container for all footnotes from a single talk."""

    talk_id: int
    footnotes: List[FootnoteData]
    total_footnotes: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.total_footnotes != len(self.footnotes):
            raise ValueError(
                f"Total footnotes ({self.total_footnotes}) does not match "
                f"actual footnote count ({len(self.footnotes)})"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "talk_id": self.talk_id,
            "footnotes": [f.to_dict() for f in self.footnotes],
            "total_footnotes": self.total_footnotes,
            "extraction_success": self.extraction_success,
            "extraction_errors": self.extraction_errors,
        }

    def __repr__(self) -> str:
        return (
            f"TalkFootnotes(talk_id={self.talk_id}, "
            f"footnotes={self.total_footnotes}, "
            f"success={self.extraction_success})"
        )
