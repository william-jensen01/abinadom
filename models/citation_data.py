"""
Citation data structures for Phase 3 extraction.

Provides type-safe representation of scripture citation data with validation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class CitationData:
    """Represents a single scripture citation extracted from a talk paragraph."""

    # Identity
    citation_id: int          # From core.52.db citation.ID (= HTML span id)
    talk_id: int
    paragraph_id: int         # talk_id * 10000 + paragraph_number
    paragraph_number: int     # 1-indexed

    # Raw extraction
    citation_text_raw: str    # Display text from HTML (e.g., "D&C 84:32-44")

    # Position in paragraph clean text
    char_position: int        # Start offset (-1 if not found)
    char_end_position: int    # End offset (-1 if not found)

    # Parsed fields (primary source: DB lookup)
    scripture_ref: str        # Normalized: "Doctrine and Covenants 84:32-44"
    book: str                 # FullName from book table
    book_abbr: str            # CiteAbbr from book table
    book_id: Optional[int]
    chapter: Optional[int]
    verses: str               # Raw from DB: "32-44", "3,5,7"
    verse_start: Optional[int]   # MinVerse
    verse_end: Optional[int]     # MaxVerse
    verse_list: List[int]        # Expanded: [32,33,...,44]

    # Classification
    is_jst: bool = False
    citation_location: str = "inline"  # "inline" or "footnote"

    # Parse metadata
    parse_success: bool = False
    parse_source: str = ""       # "db_lookup" or "regex_fallback"
    parse_pattern: str = ""
    parse_confidence: float = 0.0  # 1.0 for DB, 0.5-0.9 for regex

    # Context
    context_before: str = ""
    context_after: str = ""
    context_window: str = ""

    extraction_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate required fields."""
        if self.citation_id < 0:
            raise ValueError(f"Invalid citation_id: {self.citation_id}")
        if self.paragraph_number < 1:
            raise ValueError(f"Invalid paragraph_number: {self.paragraph_number}")
        if self.citation_location not in ("inline", "footnote"):
            raise ValueError(f"Invalid citation_location: {self.citation_location}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        return result

    def to_chromadb_format(self) -> tuple[str, Dict[str, Any], str]:
        """
        Convert to ChromaDB format.

        Returns:
            Tuple of (document, metadata, id)
                - document: context_window (text surrounding the citation)
                - metadata: All metadata fields
                - id: Unique identifier (cite_{citation_id}_{paragraph_id})
        """
        document = self.context_window or self.citation_text_raw
        metadata = self.to_dict()
        # Remove large text fields from metadata
        metadata.pop("context_window", None)
        metadata.pop("verse_list", None)
        # Store verse_list as a comma-separated string for ChromaDB compatibility
        metadata["verse_list_str"] = ",".join(str(v) for v in self.verse_list)
        doc_id = f"cite_{self.citation_id}_{self.paragraph_id}"
        return document, metadata, doc_id

    def __repr__(self) -> str:
        return (
            f"CitationData(id={self.citation_id}, "
            f"talk_id={self.talk_id}, "
            f"ref='{self.scripture_ref}', "
            f"loc={self.citation_location})"
        )


@dataclass
class TalkCitations:
    """Container for all citations from a single talk."""

    talk_id: int
    citations: List[CitationData]
    total_citations: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.total_citations != len(self.citations):
            raise ValueError(
                f"Total citations ({self.total_citations}) does not match "
                f"actual citation count ({len(self.citations)})"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "talk_id": self.talk_id,
            "citations": [c.to_dict() for c in self.citations],
            "total_citations": self.total_citations,
            "extraction_success": self.extraction_success,
            "extraction_errors": self.extraction_errors,
        }

    def __repr__(self) -> str:
        return (
            f"TalkCitations(talk_id={self.talk_id}, "
            f"citations={self.total_citations}, "
            f"success={self.extraction_success})"
        )
