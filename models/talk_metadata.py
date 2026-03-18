"""
TalkMetadata dataclass for Phase 1 extraction.

Provides type-safe representation of talk metadata with validation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config.schemas import TALK_METADATA_SCHEMA, validate_schema
from utils.validators import (
    validate_year,
    validate_month,
    validate_date_iso,
    validate_speaker_name,
    validate_positive_int,
)


@dataclass
class TalkMetadata:
    """
    Talk metadata extracted from database.

    Represents all metadata for a single General Conference talk,
    ready for ChromaDB insertion.
    """

    # Primary identifiers
    talk_id: int
    speaker_id: int
    conference_id: int

    # Core metadata
    title: str
    speaker_name: str

    # Conference information
    conference_year: int
    conference_month: str  # 'April' or 'October'
    conference_description: str

    # Talk date
    talk_date: str  # ISO format YYYY-MM-DD

    # Session information (optional)
    session_id: Optional[int] = None
    session_description: Optional[str] = None
    session_abbr: Optional[str] = None
    session_date: Optional[str] = None
    session_sequence: Optional[int] = None
    talk_sequence: Optional[int] = None

    # URLs and identifiers
    url: Optional[str] = None
    uri_l: Optional[str] = None
    uri_gc: Optional[str] = None
    data_aid: Optional[str] = None

    # Media URLs
    audio_url: Optional[str] = None
    video_low_url: Optional[str] = None
    video_med_url: Optional[str] = None
    video_high_url: Optional[str] = None

    # Additional metadata
    corpus: str = "E"
    speaker_role_id: Optional[int] = None
    start_page_num: Optional[int] = None
    end_page_num: Optional[int] = None

    # Extraction metadata
    extraction_timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    extraction_version: str = "1.0.0"

    def __post_init__(self):
        """Validate fields after initialization."""
        # Validate required fields
        if not validate_positive_int(self.talk_id):
            raise ValueError(f"Invalid talk_id: {self.talk_id}")

        if not validate_positive_int(self.speaker_id):
            raise ValueError(f"Invalid speaker_id: {self.speaker_id}")

        if not validate_positive_int(self.conference_id):
            raise ValueError(f"Invalid conference_id: {self.conference_id}")

        if not validate_speaker_name(self.title):
            raise ValueError(f"Invalid title: {self.title}")

        if not validate_speaker_name(self.speaker_name):
            raise ValueError(f"Invalid speaker_name: {self.speaker_name}")

        if not validate_year(self.conference_year):
            raise ValueError(f"Invalid conference_year: {self.conference_year}")

        if not validate_month(self.conference_month):
            raise ValueError(f"Invalid conference_month: {self.conference_month}")

        if not validate_date_iso(self.talk_date):
            raise ValueError(f"Invalid talk_date: {self.talk_date}")

        # Validate optional session fields if provided
        if self.session_id is not None and not validate_positive_int(self.session_id):
            raise ValueError(f"Invalid session_id: {self.session_id}")

        if self.session_sequence is not None and not isinstance(
            self.session_sequence, int
        ):
            raise ValueError(f"Invalid session_sequence: {self.session_sequence}")

        if self.talk_sequence is not None and not isinstance(self.talk_sequence, int):
            raise ValueError(f"Invalid talk_sequence: {self.talk_sequence}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return asdict(self)

    def to_chromadb_format(self) -> tuple[str, Dict[str, Any], str]:
        """
        Convert to ChromaDB format.

        Returns:
            Tuple of (document, metadata, id)
                - document: Text to embed (summary of talk)
                - metadata: All metadata fields
                - id: Unique identifier (talk_{talk_id})
        """
        # Create document text for embedding
        # This is a summary that captures key searchable information
        document = self._create_document_summary()

        # Create metadata dict (all fields except those in document)
        metadata = self.to_dict()

        # Create unique ID
        doc_id = f"talk_{self.talk_id}"

        return document, metadata, doc_id

    def _create_document_summary(self) -> str:
        """
        Create document summary for embedding.

        This summary includes key information that makes talks searchable:
        - Title
        - Speaker
        - Conference
        - Session

        Returns:
            Summary text
        """
        parts = [
            f"Title: {self.title}",
            f"Speaker: {self.speaker_name}",
            f"Conference: {self.conference_description}",
        ]

        if self.session_description:
            parts.append(f"Session: {self.session_description}")

        if self.talk_date:
            parts.append(f"Date: {self.talk_date}")

        return "\n".join(parts)

    def validate_against_schema(self) -> tuple[bool, list[str]]:
        """
        Validate against schema definition.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        data = self.to_dict()
        return validate_schema(data, TALK_METADATA_SCHEMA)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TalkMetadata(talk_id={self.talk_id}, "
            f"title='{self.title[:50]}...', "
            f"speaker='{self.speaker_name}', "
            f"conference='{self.conference_year} {self.conference_month}')"
        )


def create_talk_metadata_from_db_row(row: Dict[str, Any]) -> TalkMetadata:
    """
    Create TalkMetadata from database query result.

    Args:
        row: Dictionary from database query with all required fields

    Returns:
        TalkMetadata instance

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # This factory function handles the mapping from database column names
    # to TalkMetadata fields, with appropriate type conversions and defaults
    return TalkMetadata(
        # Required fields
        talk_id=int(row["talk_id"]),
        speaker_id=int(row["speaker_id"]),
        conference_id=int(row["conference_id"]),
        title=str(row["title"]),
        speaker_name=str(row["speaker_name"]),
        conference_year=int(row["conference_year"]),
        conference_month=str(row["conference_month"]),
        conference_description=str(row["conference_description"]),
        talk_date=str(row["talk_date"]),
        # Optional session fields
        session_id=row.get("session_id"),
        session_description=row.get("session_description"),
        session_abbr=row.get("session_abbr"),
        session_date=row.get("session_date"),
        session_sequence=row.get("session_sequence"),
        talk_sequence=row.get("talk_sequence"),
        # Optional URL and identifier fields
        url=row.get("url"),
        uri_l=row.get("uri_l"),
        uri_gc=row.get("uri_gc"),
        data_aid=row.get("data_aid"),
        # Optional media URLs
        audio_url=row.get("audio_url"),
        video_low_url=row.get("video_low_url"),
        video_med_url=row.get("video_med_url"),
        video_high_url=row.get("video_high_url"),
        # Optional additional metadata
        corpus=row.get("corpus", "E"),
        speaker_role_id=row.get("speaker_role_id"),
        start_page_num=row.get("start_page_num"),
        end_page_num=row.get("end_page_num"),
        # Extraction metadata (auto-populated)
        extraction_timestamp=datetime.now().isoformat(),
        extraction_version="1.0.0",
    )
