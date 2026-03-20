"""
Phase 1: Talk Metadata Extraction

Extracts talk-level metadata from SQLite database and prepares it for ChromaDB insertion.

This module implements a layered architecture:
- Database Layer: SQL queries and raw data retrieval
- Extraction Layer: Data transformation and structuring
- Validation Layer: Data quality assurance

All functions are pure (no side effects) and composable.
"""

import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, Database
from models.talk_metadata import TalkMetadata, create_talk_metadata_from_db_row
from utils.validators import sanitize_speaker_name, determine_conference_month

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# DATABASE LAYER - Pure SQL queries
# =============================================================================


def build_talk_metadata_query(
    talk_id: Optional[int] = None,
    conference_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> Tuple[str, List[Any]]:
    """
    Build SQL query for talk metadata with all joins.

    This query joins:
    - talk table (core metadata)
    - speaker table (speaker information)
    - conference_talk table (session linking)
    - conf_session table (session details)
    - conference table (conference details)

    Args:
        talk_id: Optional filter for specific talk ID
        conference_id: Optional filter for specific conference
        limit: Optional limit on number of results

    Returns:
        Tuple of (query_string, parameters)
    """
    query = """
        SELECT
            -- Talk core fields
            t.ID as talk_id,
            t.Title as title,
            t.Date as talk_date,
            t.Corpus as corpus,
            t.URL as url,
            COALESCE(tm.uri_l, t.URI_L) as uri_l,
            COALESCE(tm.uri_gc, t.URI_GC) as uri_gc,
            COALESCE(tm.data_aid, t.data_aid) as data_aid,
            t.SpeakerID as speaker_id,
            COALESCE(tm.speaker_role_id, t.speaker_role_id) as speaker_role_id,
            tm.kicker,
            tm.talk_preview,
            t.AudioUrl as audio_url,
            t.VideoLowUrl as video_low_url,
            t.VideoMedUrl as video_med_url,
            t.VideoHighUrl as video_high_url,

            -- Speaker fields
            s.GivenNames as speaker_given_names,
            s.LastNames as speaker_last_names,
            s.Abbr as speaker_abbr,

            -- Conference fields
            c.ID as conference_id,
            c.Description as conference_description,
            c.Year as conference_year,
            c.Annual as conference_annual,

            -- Session fields (optional - may be NULL)
            cs.ID as session_id,
            cs.Description as session_description,
            cs.Abbr as session_abbr,
            cs.Date as session_date,
            cs.Sequence as session_sequence,

            -- Talk-Session linking (optional)
            ct.Sequence as talk_sequence,
            ct.StartPageNum as start_page_num,
            ct.EndPageNum as end_page_num

        FROM talk t

        -- Required joins
        INNER JOIN speaker s ON t.SpeakerID = s.ID
        INNER JOIN conference_talk ct ON t.ID = ct.TalkID
        INNER JOIN conf_session cs ON ct.SessionID = cs.ID
        INNER JOIN conference c ON cs.ConferenceID = c.ID

        LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id

        WHERE 1=1
    """

    params = []

    # Add filters
    if talk_id is not None:
        query += " AND t.ID = ?"
        params.append(talk_id)

    if conference_id is not None:
        query += " AND c.ID = ?"
        params.append(conference_id)

    # Order by conference year (newest first) and talk sequence
    query += " ORDER BY c.Year DESC, cs.Sequence ASC, ct.Sequence ASC"

    # Add limit
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    return query, params


def fetch_all_talks(db: Database, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch all talks from database.

    Args:
        db: Database instance
        limit: Optional limit on results

    Returns:
        List of raw database rows as dictionaries
    """
    query, params = build_talk_metadata_query(limit=limit)
    logger.info(f"Fetching talks from database (limit={limit or 'none'})")

    try:
        rows = db.select(query, params)
        logger.info(f"Fetched {len(rows)} talks from database")
        return rows
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        raise


def fetch_talk_by_id(db: Database, talk_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch single talk by ID.

    Args:
        db: Database instance
        talk_id: Talk ID to fetch

    Returns:
        Database row as dictionary, or None if not found
    """
    query, params = build_talk_metadata_query(talk_id=talk_id)
    logger.info(f"Fetching talk ID {talk_id}")

    try:
        row = db.select_one(query, params)
        if row:
            logger.info(f"Found talk ID {talk_id}")
        else:
            logger.warning(f"Talk ID {talk_id} not found")
        return row
    except Exception as e:
        logger.error(f"Database query failed for talk ID {talk_id}: {e}")
        raise


def fetch_talks_by_conference(
    db: Database, conference_id: int, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch all talks from a specific conference.

    Args:
        db: Database instance
        conference_id: Conference ID
        limit: Optional limit on results

    Returns:
        List of database rows as dictionaries
    """
    query, params = build_talk_metadata_query(conference_id=conference_id, limit=limit)
    logger.info(f"Fetching talks for conference ID {conference_id}")

    try:
        rows = db.select(query, params)
        logger.info(f"Fetched {len(rows)} talks for conference ID {conference_id}")
        return rows
    except Exception as e:
        logger.error(f"Database query failed for conference ID {conference_id}: {e}")
        raise


# =============================================================================
# EXTRACTION LAYER - Data transformation
# =============================================================================


def transform_db_row_to_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform database row into metadata dictionary.

    This function handles:
    - Field renaming from database columns to schema fields
    - Type conversions
    - NULL handling
    - Computed fields (e.g., speaker_name, conference_month)

    Args:
        row: Raw database row

    Returns:
        Transformed metadata dictionary ready for TalkMetadata
    """
    # Compute speaker full name
    speaker_name = sanitize_speaker_name(
        row.get("speaker_given_names"), row.get("speaker_last_names")
    )

    # Determine conference month from annual flag
    conference_month = determine_conference_month(row.get("conference_annual", "S"))

    # Build transformed dictionary
    metadata = {
        # Required fields
        "talk_id": row["talk_id"],
        "speaker_id": row["speaker_id"],
        "conference_id": row["conference_id"],
        "title": row["title"],
        "speaker_name": speaker_name,
        "conference_year": row["conference_year"],
        "conference_month": conference_month,
        "conference_description": row["conference_description"],
        "talk_date": row["talk_date"],
        # Optional session fields
        "session_id": row.get("session_id"),
        "session_description": row.get("session_description"),
        "session_abbr": row.get("session_abbr"),
        "session_date": row.get("session_date"),
        "session_sequence": row.get("session_sequence"),
        "talk_sequence": row.get("talk_sequence"),
        # Optional URL and identifier fields
        "url": row.get("url"),
        "uri_l": row.get("uri_l"),
        "uri_gc": row.get("uri_gc"),
        "data_aid": row.get("data_aid"),
        # Optional media URLs
        "audio_url": row.get("audio_url"),
        "video_low_url": row.get("video_low_url"),
        "video_med_url": row.get("video_med_url"),
        "video_high_url": row.get("video_high_url"),
        # Optional additional metadata
        "corpus": row.get("corpus", "E"),
        "speaker_role_id": row.get("speaker_role_id"),
        # Enriched fields from talk_metadata
        "kicker": row.get("kicker"),
        "talk_preview": row.get("talk_preview"),
        "start_page_num": row.get("start_page_num"),
        "end_page_num": row.get("end_page_num"),
    }

    return metadata


def extract_talk_metadata(row: Dict[str, Any]) -> TalkMetadata:
    """
    Extract TalkMetadata from database row.

    Args:
        row: Raw database row

    Returns:
        TalkMetadata instance

    Raises:
        ValueError: If required fields are missing or invalid
    """
    try:
        # Transform database row
        metadata_dict = transform_db_row_to_metadata(row)

        # Create TalkMetadata instance (includes validation)
        metadata = create_talk_metadata_from_db_row(metadata_dict)

        logger.debug(f"Extracted metadata for talk ID {metadata.talk_id}")
        return metadata

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Failed to extract metadata from row: {e}")
        logger.debug(f"Row data: {row}")
        raise


def extract_all_talk_metadata(
    db: Database, limit: Optional[int] = None
) -> List[TalkMetadata]:
    """
    Extract metadata for all talks.

    Args:
        db: Database instance
        limit: Optional limit on number of talks

    Returns:
        List of TalkMetadata instances
    """
    logger.info(f"Starting extraction of all talk metadata (limit={limit or 'none'})")

    # Fetch raw data
    rows = fetch_all_talks(db, limit=limit)

    # Transform to TalkMetadata
    metadata_list = []
    errors = []

    for idx, row in enumerate(rows, 1):
        try:
            metadata = extract_talk_metadata(row)
            metadata_list.append(metadata)

            if idx % 100 == 0:
                logger.info(f"Processed {idx}/{len(rows)} talks")

        except Exception as e:
            talk_id = row.get("talk_id", "unknown")
            logger.warning(f"Skipping talk ID {talk_id} due to error: {e}")
            errors.append({"talk_id": talk_id, "error": str(e), "row": row})

    logger.info(
        f"Extraction complete: {len(metadata_list)} successful, "
        f"{len(errors)} errors"
    )

    if errors:
        logger.warning(f"Encountered {len(errors)} errors during extraction")
        # Log first few errors for debugging
        for error in errors[:5]:
            logger.debug(f"Error detail: {error}")

    return metadata_list


# =============================================================================
# CHROMADB PREPARATION - Format conversion
# =============================================================================


def prepare_for_chromadb(
    metadata_list: List[TalkMetadata],
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Prepare talk metadata for ChromaDB insertion.

    Converts list of TalkMetadata into the three parallel lists required
    by ChromaDB's add() method.

    Args:
        metadata_list: List of TalkMetadata instances

    Returns:
        Tuple of (documents, metadatas, ids)
            - documents: List of text summaries to embed
            - metadatas: List of metadata dictionaries
            - ids: List of unique identifiers
    """
    logger.info(f"Preparing {len(metadata_list)} talks for ChromaDB")

    documents = []
    metadatas = []
    ids = []

    for metadata in metadata_list:
        doc, meta, doc_id = metadata.to_chromadb_format()
        documents.append(doc)
        metadatas.append(meta)
        ids.append(doc_id)

    logger.info(f"Prepared {len(documents)} documents for ChromaDB")

    return documents, metadatas, ids


# =============================================================================
# VALIDATION LAYER - Data quality checks
# =============================================================================


def validate_extraction_results(
    metadata_list: List[TalkMetadata],
) -> Tuple[bool, List[str]]:
    """
    Validate extraction results against schema.

    Args:
        metadata_list: List of TalkMetadata instances

    Returns:
        Tuple of (all_valid, error_messages)
    """
    logger.info(f"Validating {len(metadata_list)} talk metadata instances")

    all_errors = []

    for metadata in metadata_list:
        is_valid, errors = metadata.validate_against_schema()
        if not is_valid:
            all_errors.extend(
                [f"Talk ID {metadata.talk_id}: {error}" for error in errors]
            )

    is_all_valid = len(all_errors) == 0

    if is_all_valid:
        logger.info("All metadata instances passed validation")
    else:
        logger.warning(f"Found {len(all_errors)} validation errors")
        for error in all_errors[:10]:  # Log first 10 errors
            logger.debug(f"Validation error: {error}")

    return is_all_valid, all_errors


# =============================================================================
# HIGH-LEVEL PIPELINE - Complete extraction workflow
# =============================================================================


def extract_talks_for_chromadb(
    limit: Optional[int] = None, validate: bool = True
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Complete extraction pipeline from database to ChromaDB format.

    This is the main entry point for Phase 1 extraction. It:
    1. Fetches data from database
    2. Transforms into TalkMetadata
    3. Validates (optional)
    4. Converts to ChromaDB format

    Args:
        limit: Optional limit on number of talks to extract
        validate: Whether to run validation checks (default True)

    Returns:
        Tuple of (documents, metadatas, ids) ready for ChromaDB

    Raises:
        ValueError: If validation fails and validate=True
    """
    logger.info(
        f"Starting Phase 1 extraction pipeline "
        f"(limit={limit or 'none'}, validate={validate})"
    )

    start_time = datetime.now()

    # Step 1: Extract metadata
    metadata_list = extract_all_talk_metadata(core_db, limit=limit)

    # Step 2: Validate (optional)
    if validate:
        is_valid, errors = validate_extraction_results(metadata_list)
        if not is_valid:
            logger.error(f"Validation failed with {len(errors)} errors")
            raise ValueError(f"Validation failed: {errors[:5]}")  # Show first 5 errors

    # Step 3: Prepare for ChromaDB
    documents, metadatas, ids = prepare_for_chromadb(metadata_list)

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"Phase 1 extraction complete: {len(documents)} talks in {elapsed:.2f}s"
    )

    return documents, metadatas, ids


def get_extraction_stats(metadata_list: List[TalkMetadata]) -> Dict[str, Any]:
    """
    Generate statistics about extracted metadata.

    Args:
        metadata_list: List of TalkMetadata instances

    Returns:
        Dictionary of statistics
    """
    if not metadata_list:
        return {
            "total_talks": 0,
            "conferences": [],
            "speakers": [],
            "year_range": (None, None),
        }

    stats = {
        "total_talks": len(metadata_list),
        "conferences": len(set(m.conference_id for m in metadata_list)),
        "speakers": len(set(m.speaker_id for m in metadata_list)),
        "year_range": (
            min(m.conference_year for m in metadata_list),
            max(m.conference_year for m in metadata_list),
        ),
        "with_session": sum(1 for m in metadata_list if m.session_id is not None),
        "with_url": sum(1 for m in metadata_list if m.url is not None),
        "with_audio": sum(1 for m in metadata_list if m.audio_url is not None),
        "with_video": sum(1 for m in metadata_list if m.video_high_url is not None),
    }

    return stats


# =============================================================================
# MAIN - Example usage and CLI interface
# =============================================================================


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 1: Extract talk metadata from database"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of talks to extract (default: all)",
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip validation checks"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Print statistics only (no extraction)"
    )

    args = parser.parse_args()

    try:
        if args.stats:
            # Just show stats
            metadata_list = extract_all_talk_metadata(core_db, limit=args.limit)
            stats = get_extraction_stats(metadata_list)
            print("\n=== Extraction Statistics ===")
            for key, value in stats.items():
                print(f"{key}: {value}")
        else:
            # Full extraction
            documents, metadatas, ids = extract_talks_for_chromadb(
                limit=args.limit, validate=not args.no_validate
            )

            print(f"\n=== Extraction Complete ===")
            print(f"Total talks: {len(documents)}")
            print(f"Sample document (first talk):")
            print(f"  ID: {ids[0]}")
            print(f"  Document: {documents[0][:200]}...")
            print(f"  Metadata keys: {list(metadatas[0].keys())}")

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
