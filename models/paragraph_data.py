"""
Paragraph data structures for Phase 2 extraction.

Provides type-safe representation of paragraph data with validation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class ParagraphData:
    """Represents a single paragraph extracted from a talk."""

    # Identity
    paragraph_id: int  # From database or generated: talk_id * 10000 + paragraph_number
    talk_id: int  # Parent talk reference
    paragraph_number: int  # 1-indexed position in talk

    # Content
    text: str  # Clean text (HTML stripped)
    text_raw: Optional[str]  # Original HTML (for debugging/reprocessing)

    # Metrics
    word_count: int

    # List context
    list_header: Optional[str] = None
    list_item_index: Optional[int] = None
    position_in_item: Optional[int] = None

    # Downstream flags (populated in later phases, default False)
    has_scripture_citation: bool = False
    has_footnote: bool = False
    citation_count: int = 0
    footnote_count: int = 0

    # Extraction metadata
    extraction_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate required fields."""
        if not self.text or not self.text.strip():
            raise ValueError(f"Paragraph {self.paragraph_id} has empty text")
        if self.paragraph_number < 1:
            raise ValueError(f"Invalid paragraph_number: {self.paragraph_number}")
        if self.word_count < 0:
            raise ValueError("Word count cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ChromaDB metadata."""
        result = asdict(self)
        return result

    def to_chromadb_format(self) -> tuple[str, Dict[str, Any], str]:
        """
        Convert to ChromaDB format.

        Returns:
            Tuple of (document, metadata, id)
                - document: Text to embed (paragraph text)
                - metadata: All metadata fields
                - id: Unique identifier (para_{paragraph_id})
        """
        # Document is the paragraph text itself
        document = self.text

        # Metadata includes all fields except text (which is in document)
        metadata = self.to_dict()
        # Remove text from metadata since it's in document
        metadata.pop("text", None)

        # Create unique ID
        doc_id = f"para_{self.paragraph_id}"

        return document, metadata, doc_id

    def __repr__(self) -> str:
        """String representation."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return (
            f"ParagraphData(id={self.paragraph_id}, "
            f"talk_id={self.talk_id}, "
            f"num={self.paragraph_number}, "
            f"text='{text_preview}')"
        )


@dataclass
class TalkParagraphs:
    """Container for all paragraphs from a single talk."""

    talk_id: int
    paragraphs: List[ParagraphData]
    total_paragraphs: int
    total_words: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate container data."""
        if self.total_paragraphs != len(self.paragraphs):
            raise ValueError(
                f"Total paragraphs ({self.total_paragraphs}) does not match "
                f"actual paragraph count ({len(self.paragraphs)})"
            )

        # Verify total counts match sum of individual paragraphs
        actual_words = sum(p.word_count for p in self.paragraphs)

        if self.total_words != actual_words:
            raise ValueError(
                f"Total words ({self.total_words}) does not match "
                f"sum of paragraph words ({actual_words})"
            )

    def get_paragraph(self, paragraph_number: int) -> Optional[ParagraphData]:
        """Get paragraph by number (1-indexed)."""
        for para in self.paragraphs:
            if para.paragraph_number == paragraph_number:
                return para
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "talk_id": self.talk_id,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "total_paragraphs": self.total_paragraphs,
            "total_words": self.total_words,
            "extraction_success": self.extraction_success,
            "extraction_errors": self.extraction_errors,
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TalkParagraphs(talk_id={self.talk_id}, "
            f"paragraphs={self.total_paragraphs}, "
            f"words={self.total_words}, "
            f"success={self.extraction_success})"
        )


@dataclass
class ValidationResult:
    """Result of paragraph validation."""

    is_valid: bool
    errors: List[str]  # Critical issues
    warnings: List[str]  # Non-critical issues
    stats: Dict[str, Any]  # Extraction statistics

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ValidationResult(valid={self.is_valid}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )
