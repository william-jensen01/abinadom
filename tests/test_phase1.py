"""
Unit tests for Phase 1: Talk Metadata Extraction

Tests cover:
- Schema validation
- Validators
- TalkMetadata dataclass
- Database queries and transformations
- ChromaDB format conversion
- SQLite schema validation (QUAL-06)
- Phase 1 edge cases via in-memory SQLite (QUAL-05)
"""

import unittest
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config.schemas import (
    TALK_METADATA_SCHEMA,
    validate_schema,
    get_required_fields,
    get_optional_fields,
    get_default_value,
)
from utils.validators import (
    validate_year,
    validate_month,
    validate_date_iso,
    validate_speaker_name,
    validate_positive_int,
    sanitize_speaker_name,
    determine_conference_month,
)
from models.talk_metadata import TalkMetadata, create_talk_metadata_from_db_row
from extractors.phase1_talk_metadata import (
    transform_db_row_to_metadata,
    prepare_for_chromadb,
)


class TestSchema(unittest.TestCase):
    """Test schema configuration."""

    def test_schema_has_required_fields(self):
        """Schema should have all essential fields."""
        required = get_required_fields(TALK_METADATA_SCHEMA)
        self.assertIn("talk_id", required)
        self.assertIn("title", required)
        self.assertIn("speaker_name", required)
        self.assertIn("conference_year", required)

    def test_schema_has_optional_fields(self):
        """Schema should define optional fields."""
        optional = get_optional_fields(TALK_METADATA_SCHEMA)
        self.assertIn("session_id", optional)
        self.assertIn("url", optional)
        self.assertIn("audio_url", optional)

    def test_validate_schema_valid_data(self):
        """Valid data should pass schema validation."""
        data = {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual General Conference",
            "talk_date": "2023-04-01",
            "extraction_timestamp": datetime.now().isoformat(),
            "extraction_version": "1.0.0",
        }

        is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
        self.assertTrue(is_valid, f"Expected valid, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_validate_schema_missing_required(self):
        """Missing required fields should fail validation."""
        data = {
            "talk_id": 1,
            "title": "Test Talk",
            # Missing speaker_name, conference_year, etc.
        }

        is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)

    def test_validate_schema_wrong_type(self):
        """Wrong data types should fail validation."""
        data = {
            "talk_id": "not_an_int",  # Should be int
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual",
            "talk_date": "2023-04-01",
            "extraction_timestamp": datetime.now().isoformat(),
            "extraction_version": "1.0.0",
        }

        is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
        self.assertFalse(is_valid)
        self.assertTrue(any("talk_id" in err for err in errors))


class TestValidators(unittest.TestCase):
    """Test validation functions."""

    def test_validate_year_valid(self):
        """Valid years should pass."""
        self.assertTrue(validate_year(2023))
        self.assertTrue(validate_year(1942))
        self.assertTrue(validate_year(2024))

    def test_validate_year_invalid(self):
        """Invalid years should fail."""
        self.assertFalse(validate_year(1941))  # Too early
        self.assertFalse(validate_year(3000))  # Too far in future
        self.assertFalse(validate_year("2023"))  # Wrong type

    def test_validate_month_valid(self):
        """Valid conference months should pass."""
        self.assertTrue(validate_month("April"))
        self.assertTrue(validate_month("October"))

    def test_validate_month_invalid(self):
        """Invalid months should fail."""
        self.assertFalse(validate_month("January"))
        self.assertFalse(validate_month("april"))  # Case sensitive
        self.assertFalse(validate_month(4))  # Wrong type

    def test_validate_date_iso_valid(self):
        """Valid ISO dates should pass."""
        self.assertTrue(validate_date_iso("2023-04-01"))
        self.assertTrue(validate_date_iso("1942-10-15"))

    def test_validate_date_iso_invalid(self):
        """Invalid date formats should fail."""
        self.assertFalse(validate_date_iso("04/01/2023"))
        self.assertFalse(validate_date_iso("2023-13-01"))  # Invalid month
        self.assertFalse(validate_date_iso("not-a-date"))

    def test_validate_speaker_name_valid(self):
        """Valid speaker names should pass."""
        self.assertTrue(validate_speaker_name("John Doe"))
        self.assertTrue(validate_speaker_name("María García"))
        self.assertTrue(validate_speaker_name("X"))  # Single letter

    def test_validate_speaker_name_invalid(self):
        """Invalid speaker names should fail."""
        self.assertFalse(validate_speaker_name(""))
        self.assertFalse(validate_speaker_name("   "))  # Only whitespace
        self.assertFalse(validate_speaker_name(123))  # Wrong type

    def test_validate_positive_int(self):
        """Test positive integer validation."""
        self.assertTrue(validate_positive_int(1))
        self.assertTrue(validate_positive_int(1000))
        self.assertFalse(validate_positive_int(0))
        self.assertFalse(validate_positive_int(-1))
        self.assertFalse(validate_positive_int("1"))

    def test_sanitize_speaker_name(self):
        """Test speaker name formatting."""
        self.assertEqual(sanitize_speaker_name("John", "Doe"), "John Doe")
        self.assertEqual(sanitize_speaker_name("", "Doe"), "Doe")
        self.assertEqual(sanitize_speaker_name("John", ""), "John")
        self.assertEqual(sanitize_speaker_name("", ""), "Unknown Speaker")

    def test_determine_conference_month(self):
        """Test conference month determination."""
        self.assertEqual(determine_conference_month("A"), "April")
        self.assertEqual(determine_conference_month("S"), "October")
        self.assertEqual(determine_conference_month("X"), "October")  # Default


class TestTalkMetadata(unittest.TestCase):
    """Test TalkMetadata dataclass."""

    def get_valid_metadata_dict(self) -> Dict[str, Any]:
        """Get valid metadata dictionary for testing."""
        return {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual General Conference",
            "talk_date": "2023-04-01",
        }

    def test_create_talk_metadata_valid(self):
        """Should create TalkMetadata with valid data."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)

        self.assertEqual(metadata.talk_id, 1)
        self.assertEqual(metadata.title, "Test Talk")
        self.assertEqual(metadata.speaker_name, "John Doe")
        self.assertEqual(metadata.conference_year, 2023)

    def test_create_talk_metadata_with_optionals(self):
        """Should handle optional fields correctly."""
        data = self.get_valid_metadata_dict()
        data.update(
            {
                "session_id": 10,
                "session_description": "Saturday Morning Session",
                "url": "/general-conference/2023/04/test-talk",
            }
        )

        metadata = create_talk_metadata_from_db_row(data)

        self.assertEqual(metadata.session_id, 10)
        self.assertEqual(metadata.session_description, "Saturday Morning Session")
        self.assertEqual(metadata.url, "/general-conference/2023/04/test-talk")

    def test_talk_metadata_validation_invalid_talk_id(self):
        """Should raise ValueError for invalid talk_id."""
        data = self.get_valid_metadata_dict()
        data["talk_id"] = -1  # Invalid

        with self.assertRaises(ValueError):
            create_talk_metadata_from_db_row(data)

    def test_talk_metadata_validation_invalid_year(self):
        """Should raise ValueError for invalid year."""
        data = self.get_valid_metadata_dict()
        data["conference_year"] = 1900  # Too early

        with self.assertRaises(ValueError):
            create_talk_metadata_from_db_row(data)

    def test_talk_metadata_validation_invalid_month(self):
        """Should raise ValueError for invalid month."""
        data = self.get_valid_metadata_dict()
        data["conference_month"] = "January"  # Invalid

        with self.assertRaises(ValueError):
            create_talk_metadata_from_db_row(data)

    def test_talk_metadata_to_dict(self):
        """Should convert to dictionary correctly."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)
        result = metadata.to_dict()

        self.assertIsInstance(result, dict)
        self.assertEqual(result["talk_id"], 1)
        self.assertEqual(result["title"], "Test Talk")

    def test_talk_metadata_to_db_record(self):
        """Should convert to DB record format correctly."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)
        document, meta, doc_id = metadata.to_db_record()

        # Check document
        self.assertIsInstance(document, str)
        self.assertIn("Test Talk", document)
        self.assertIn("John Doe", document)

        # Check metadata
        self.assertIsInstance(meta, dict)
        self.assertEqual(meta["talk_id"], 1)

        # Check ID
        self.assertEqual(doc_id, "talk_1")

    def test_talk_metadata_validate_against_schema(self):
        """Should validate against schema correctly."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)
        is_valid, errors = metadata.validate_against_schema()

        self.assertTrue(is_valid, f"Expected valid, got errors: {errors}")

    def test_talk_metadata_repr(self):
        """Should have readable string representation."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)
        repr_str = repr(metadata)

        self.assertIn("TalkMetadata", repr_str)
        self.assertIn("talk_id=1", repr_str)


class TestExtraction(unittest.TestCase):
    """Test extraction functions."""

    def get_sample_db_row(self) -> Dict[str, Any]:
        """Get sample database row for testing."""
        return {
            "talk_id": 1,
            "title": "Test Talk",
            "talk_date": "2023-04-01",
            "corpus": "E",
            "url": "/test",
            "uri_l": "/literal",
            "uri_gc": "/gc",
            "data_aid": "aid123",
            "speaker_id": 100,
            "speaker_role_id": 5,
            "audio_url": None,
            "video_low_url": None,
            "video_med_url": None,
            "video_high_url": None,
            "speaker_given_names": "John",
            "speaker_last_names": "Doe",
            "speaker_abbr": "JD",
            "conference_id": 50,
            "conference_description": "2023 Annual General Conference",
            "conference_year": 2023,
            "conference_annual": "A",
            "session_id": 10,
            "session_description": "Saturday Morning Session",
            "session_abbr": "Saturday Morning",
            "session_date": "2023-04-01",
            "session_sequence": 1,
            "talk_sequence": 1,
            "start_page_num": 10,
            "end_page_num": 15,
        }

    def test_transform_db_row(self):
        """Should transform database row correctly."""
        row = self.get_sample_db_row()
        result = transform_db_row_to_metadata(row)

        self.assertEqual(result["talk_id"], 1)
        self.assertEqual(result["title"], "Test Talk")
        self.assertEqual(result["speaker_name"], "John Doe")
        self.assertEqual(result["conference_month"], "April")

    def test_transform_db_row_with_nulls(self):
        """Should handle NULL values correctly."""
        row = self.get_sample_db_row()
        row["session_id"] = None
        row["url"] = None

        result = transform_db_row_to_metadata(row)

        self.assertIsNone(result["session_id"])
        self.assertIsNone(result["url"])

    def test_prepare_for_chromadb(self):
        """Should prepare data for ChromaDB correctly."""
        # Create sample metadata
        data = {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual General Conference",
            "talk_date": "2023-04-01",
        }
        metadata_list = [create_talk_metadata_from_db_row(data)]

        # Prepare for ChromaDB
        documents, metadatas, ids = prepare_for_chromadb(metadata_list)

        # Check structure
        self.assertEqual(len(documents), 1)
        self.assertEqual(len(metadatas), 1)
        self.assertEqual(len(ids), 1)

        # Check content
        self.assertIsInstance(documents[0], str)
        self.assertIsInstance(metadatas[0], dict)
        self.assertEqual(ids[0], "talk_1")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_title(self):
        """Should handle empty title."""
        data = {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "",  # Empty
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual",
            "talk_date": "2023-04-01",
        }

        with self.assertRaises(ValueError):
            create_talk_metadata_from_db_row(data)

    def test_missing_speaker_name(self):
        """Should handle missing speaker name gracefully."""
        row = {
            "talk_id": 1,
            "title": "Test",
            "talk_date": "2023-04-01",
            "corpus": "E",
            "speaker_id": 100,
            "speaker_given_names": None,
            "speaker_last_names": None,
            "conference_id": 50,
            "conference_description": "2023 Annual",
            "conference_year": 2023,
            "conference_annual": "A",
        }

        result = transform_db_row_to_metadata(row)
        self.assertEqual(result["speaker_name"], "Unknown Speaker")


class TestTalkMetadataDDL(unittest.TestCase):
    """Validate talk_metadata table DDL in core.52.db."""

    @classmethod
    def setUpClass(cls):
        try:
            from db import CORE_DB_PATH
            cls.db_path = CORE_DB_PATH
            cls.db_available = True
        except Exception:
            cls.db_available = False

    def test_talk_metadata_table_exists(self):
        """talk_metadata table should exist in core.52.db after DDL runs."""
        if not self.db_available:
            self.skipTest("Database not available")
        conn = sqlite3.connect(self.db_path)
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='talk_metadata'"
            ).fetchone()
            self.assertIsNotNone(result, "talk_metadata table does not exist in core.52.db")
        finally:
            conn.close()

    def test_talk_metadata_has_expected_columns(self):
        """talk_metadata should have 7 columns: talk_id, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid."""
        if not self.db_available:
            self.skipTest("Database not available")
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("PRAGMA table_info(talk_metadata)").fetchall()
            col_names = [row[1] for row in rows]
            self.assertEqual(len(col_names), 7, f"Expected 7 columns, got {len(col_names)}: {col_names}")
            expected = ["talk_id", "speaker_role_id", "uri_l", "uri_gc", "kicker", "talk_preview", "data_aid"]
            self.assertEqual(col_names, expected, f"Column mismatch: {col_names}")
        finally:
            conn.close()

    def test_talk_metadata_has_indexes(self):
        """talk_metadata should have indexes on data_aid and uri_gc."""
        if not self.db_available:
            self.skipTest("Database not available")
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='talk_metadata'"
            ).fetchall()
            index_names = [row[0] for row in rows]
            self.assertIn("idx_talk_metadata_data_aid", index_names,
                          f"idx_talk_metadata_data_aid not found in {index_names}")
            self.assertIn("idx_talk_metadata_uri_gc", index_names,
                          f"idx_talk_metadata_uri_gc not found in {index_names}")
        finally:
            conn.close()


class TestBackfillTargets(unittest.TestCase):
    """Validate backfill scripts use upsert helper and avoid direct table writes."""

    @classmethod
    def setUpClass(cls):
        cls.migration_dir = Path(__file__).parent.parent / "db" / "one-off-migration"
        cls.backfill_scripts = [
            "backfill_talk_metadata.py",
            "backfill_talk_kicker.py",
            "backfill_talk_uri.py",
            "backfill_talk_metadata_role_extraction.py",
            "backfill_talk_preview.py",
        ]

    def test_backfill_scripts_use_upsert_helper(self):
        """All 5 backfill scripts should import upsert_talk_metadata."""
        for script in self.backfill_scripts:
            content = (self.migration_dir / script).read_text(encoding="utf-8")
            self.assertIn("upsert_talk_metadata", content,
                          f"{script} does not import upsert_talk_metadata")

    def test_no_direct_writes_to_talks_table(self):
        """Backfill scripts (except Title in backfill_talk_metadata) should not UPDATE talk SET."""
        for script in self.backfill_scripts:
            content = (self.migration_dir / script).read_text(encoding="utf-8")
            if script == "backfill_talk_metadata.py":
                self.assertIn("UPDATE talk SET", content,
                              f"{script} should contain the allowed Title update")
                self.assertIn("UPDATE talk SET Title", content,
                              f"{script} UPDATE talk SET should only target Title")
            else:
                self.assertNotIn("UPDATE talk SET", content,
                                 f"{script} contains direct UPDATE talk SET")


class TestEnrichedFields(unittest.TestCase):
    """Tests for enriched field coverage in Phase 1."""

    def _base_data(self) -> Dict[str, Any]:
        return {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual General Conference",
            "talk_date": "2023-04-01",
        }

    def test_talk_metadata_has_kicker_field(self):
        """TalkMetadata dataclass should have kicker: Optional[str]."""
        data = self._base_data()
        data["kicker"] = "A test kicker"
        metadata = create_talk_metadata_from_db_row(data)
        self.assertEqual(metadata.kicker, "A test kicker")

    def test_talk_metadata_has_talk_preview_field(self):
        """TalkMetadata dataclass should have talk_preview: Optional[str]."""
        data = self._base_data()
        data["talk_preview"] = "Preview text"
        metadata = create_talk_metadata_from_db_row(data)
        self.assertEqual(metadata.talk_preview, "Preview text")

    def test_kicker_in_document_summary(self):
        """Document summary should include kicker when present."""
        data = self._base_data()
        data["kicker"] = "Inspiring subtitle"
        metadata = create_talk_metadata_from_db_row(data)
        summary = metadata._create_document_summary()
        self.assertIn("Kicker: Inspiring subtitle", summary)

    def test_talk_preview_in_document_summary(self):
        """Document summary should include talk_preview when present."""
        data = self._base_data()
        data["talk_preview"] = "A brief preview of the talk."
        metadata = create_talk_metadata_from_db_row(data)
        summary = metadata._create_document_summary()
        self.assertIn("Preview: A brief preview of the talk.", summary)

    def test_enriched_fields_optional(self):
        """kicker and talk_preview should default to None."""
        data = self._base_data()
        metadata = create_talk_metadata_from_db_row(data)
        self.assertIsNone(metadata.kicker)
        self.assertIsNone(metadata.talk_preview)

    def test_query_has_left_join(self):
        """Phase 1 query should LEFT JOIN talk_metadata."""
        from extractors.phase1_talk_metadata import build_talk_metadata_query
        query, _ = build_talk_metadata_query()
        self.assertIn("LEFT JOIN talk_metadata", query)

    def test_transform_db_row_includes_enriched_fields(self):
        """transform_db_row_to_metadata should map kicker and talk_preview."""
        row = {
            "talk_id": 1, "title": "Test", "talk_date": "2023-04-01",
            "corpus": "E", "speaker_id": 100, "speaker_role_id": 5,
            "speaker_given_names": "John", "speaker_last_names": "Doe",
            "conference_id": 50, "conference_description": "2023 Annual",
            "conference_year": 2023, "conference_annual": "A",
            "kicker": "Test kicker", "talk_preview": "Test preview",
        }
        result = transform_db_row_to_metadata(row)
        self.assertEqual(result["kicker"], "Test kicker")
        self.assertEqual(result["talk_preview"], "Test preview")


class TestTopicTablesUnchanged(unittest.TestCase):
    """Topic table smoke tests -- verify backfills did not alter topic data."""

    @classmethod
    def setUpClass(cls):
        """Load DB counts once for the class."""
        try:
            from db import Database, CORE_DB_PATH
            db = Database(CORE_DB_PATH)
            cls.conference_topic_count = db.scalar("SELECT COUNT(*) FROM conference_topic")
            cls.talk_topic_count = db.scalar("SELECT COUNT(*) FROM talk_topic")
            cls.db_available = True
        except Exception:
            cls.db_available = False

    def test_conference_topic_count_unchanged(self):
        """conference_topic row count should not change after backfills."""
        if not self.db_available:
            self.skipTest("Database not available")
        self.assertEqual(self.conference_topic_count, 333,
                         f"Expected 333, got {self.conference_topic_count}")

    def test_talk_topic_count_unchanged(self):
        """talk_topic row count should not change after backfills."""
        if not self.db_available:
            self.skipTest("Database not available")
        self.assertEqual(self.talk_topic_count, 16162,
                         f"Expected 16162, got {self.talk_topic_count}")


class TestTopicsField(unittest.TestCase):
    """Tests for topics field on TalkMetadata (Phase 8)."""

    def _base_data(self) -> Dict[str, Any]:
        return {
            "talk_id": 1,
            "speaker_id": 100,
            "conference_id": 50,
            "title": "Test Talk",
            "speaker_name": "John Doe",
            "conference_year": 2023,
            "conference_month": "April",
            "conference_description": "2023 Annual General Conference",
            "talk_date": "2023-04-01",
        }

    def test_topics_field_with_values(self):
        """TalkMetadata should store topics as List[str]."""
        data = self._base_data()
        data["topics"] = ["Atonement", "Faith", "Prayer"]
        metadata = create_talk_metadata_from_db_row(data)
        self.assertEqual(metadata.topics, ["Atonement", "Faith", "Prayer"])

    def test_topics_field_defaults_empty(self):
        """TalkMetadata topics should default to [] when not provided."""
        data = self._base_data()
        metadata = create_talk_metadata_from_db_row(data)
        self.assertEqual(metadata.topics, [])

    def test_topics_in_document_summary(self):
        """Document summary should include 'Topics: ...' when topics present."""
        data = self._base_data()
        data["topics"] = ["Atonement", "Faith"]
        metadata = create_talk_metadata_from_db_row(data)
        summary = metadata._create_document_summary()
        self.assertIn("Topics: Atonement, Faith", summary)

    def test_topics_not_in_summary_when_empty(self):
        """Document summary should NOT include 'Topics:' when topics is empty."""
        data = self._base_data()
        metadata = create_talk_metadata_from_db_row(data)
        summary = metadata._create_document_summary()
        self.assertNotIn("Topics:", summary)

    def test_transform_splits_topics_str(self):
        """transform_db_row_to_metadata should split pipe-delimited topics_str."""
        row = {
            "talk_id": 1, "title": "Test", "talk_date": "2023-04-01",
            "corpus": "E", "speaker_id": 100,
            "speaker_given_names": "John", "speaker_last_names": "Doe",
            "conference_id": 50, "conference_description": "2023 Annual",
            "conference_year": 2023, "conference_annual": "A",
            "topics_str": "Atonement|Faith|Prayer",
        }
        result = transform_db_row_to_metadata(row)
        self.assertEqual(result["topics"], ["Atonement", "Faith", "Prayer"])

    def test_transform_null_topics_str(self):
        """transform_db_row_to_metadata with no topics_str produces []."""
        row = {
            "talk_id": 1, "title": "Test", "talk_date": "2023-04-01",
            "corpus": "E", "speaker_id": 100,
            "speaker_given_names": "John", "speaker_last_names": "Doe",
            "conference_id": 50, "conference_description": "2023 Annual",
            "conference_year": 2023, "conference_annual": "A",
        }
        result = transform_db_row_to_metadata(row)
        self.assertEqual(result["topics"], [])

    def test_query_has_group_concat_subquery(self):
        """Phase 1 query should contain GROUP_CONCAT subquery for topics."""
        from extractors.phase1_talk_metadata import build_talk_metadata_query
        query, _ = build_talk_metadata_query()
        self.assertIn("GROUP_CONCAT", query)
        self.assertIn("topics_str", query)
        self.assertIn("talk_topic", query)
        self.assertIn("conference_topic", query)

    def test_schema_includes_topics(self):
        """TALK_METADATA_SCHEMA should have a topics entry."""
        self.assertIn("topics", TALK_METADATA_SCHEMA)
        self.assertEqual(TALK_METADATA_SCHEMA["topics"]["type"], list)
        self.assertFalse(TALK_METADATA_SCHEMA["topics"]["required"])

    def test_schema_validates_with_topics(self):
        """Schema validation should pass for data including topics."""
        data = self._base_data()
        data["topics"] = ["Atonement"]
        data["extraction_timestamp"] = datetime.now().isoformat()
        data["extraction_version"] = "1.0.0"
        is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
        self.assertTrue(is_valid, f"Expected valid, got errors: {errors}")

    def test_topics_flow_through_in_memory_db(self):
        """Topics from talk_topic + conference_topic should appear in extracted metadata."""
        conn = _build_in_memory_db(
            talk_rows=[(1, 'G', 'http://example.com', 'Test Talk', '2020-04-05', 1, None, None, None, None, None)],
            speaker_rows=[(1, 'John', 'Doe', 'JD', '', 'Doe, John')],
            conference_rows=[(1, 'April 2020', 'A20', 2020, 1, '2020-04-01')],
            session_rows=[(1, 'Saturday Morning', 'SM', '2020-04-04', 1, 1)],
            conf_talk_rows=[(1, 1, 1, 5, 1)],
        )
        # Insert topic data into the tables created by _build_in_memory_db
        conn.execute("INSERT INTO conference_topic VALUES (1, 'Atonement')")
        conn.execute("INSERT INTO conference_topic VALUES (2, 'Faith')")
        conn.execute("INSERT INTO talk_topic VALUES (1, 1)")
        conn.execute("INSERT INTO talk_topic VALUES (1, 2)")
        conn.commit()

        db = InMemoryDatabase(conn)
        from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
        result = fetch_talk_by_id(db, 1)
        self.assertIsNotNone(result)
        metadata = extract_talk_metadata(result)
        self.assertEqual(sorted(metadata.topics), ["Atonement", "Faith"])
        conn.close()


def _build_in_memory_db(
    talk_rows: List[Tuple],
    speaker_rows: List[Tuple],
    conference_rows: List[Tuple],
    session_rows: List[Tuple],
    conf_talk_rows: List[Tuple],
    talk_metadata_rows: Optional[List[Tuple]] = None,
) -> sqlite3.Connection:
    """
    Build minimal in-memory SQLite core DB for Phase 1 testing.

    Column order matches DDL so INSERT positional values are unambiguous.
    talk: (ID, Corpus, URL, Title, Date, SpeakerID, Kicker, AudioUrl, VideoLowUrl, VideoMedUrl, VideoHighUrl)
    speaker: (ID, GivenNames, LastNames, Abbr, Info, NameSort)
    conference: (ID, Description, Abbr, Year, Annual, IssueDate)
    conf_session: (ID, Description, Abbr, Date, Sequence, ConferenceID)
    conference_talk: (TalkID, SessionID, StartPageNum, EndPageNum, Sequence)
    talk_metadata: (talk_id, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid)
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE talk (
        ID INT PRIMARY KEY, Corpus TEXT, URL TEXT, Title TEXT, Date TEXT,
        SpeakerID INT, Kicker TEXT, AudioUrl TEXT, VideoLowUrl TEXT,
        VideoMedUrl TEXT, VideoHighUrl TEXT
    )""")
    conn.execute("""CREATE TABLE speaker (
        ID INT PRIMARY KEY, GivenNames TEXT, LastNames TEXT, Abbr TEXT, Info TEXT, NameSort TEXT
    )""")
    conn.execute("""CREATE TABLE conference (
        ID INT PRIMARY KEY, Description TEXT, Abbr TEXT, Year INT, Annual INT, IssueDate TEXT
    )""")
    conn.execute("""CREATE TABLE conf_session (
        ID INT PRIMARY KEY, Description TEXT, Abbr TEXT, Date TEXT, Sequence INT, ConferenceID INT
    )""")
    conn.execute("""CREATE TABLE conference_talk (
        TalkID INT, SessionID INT, StartPageNum INT, EndPageNum INT, Sequence INT
    )""")
    conn.execute("""CREATE TABLE talk_metadata (
        talk_id INT PRIMARY KEY, speaker_role_id INT, uri_l TEXT, uri_gc TEXT,
        kicker TEXT, talk_preview TEXT, data_aid TEXT
    )""")
    conn.execute("""CREATE TABLE conference_topic (
        id INT PRIMARY KEY, name TEXT
    )""")
    conn.execute("""CREATE TABLE talk_topic (
        talk_id INT, topic_id INT
    )""")
    for r in talk_rows:
        conn.execute("INSERT INTO talk VALUES (?,?,?,?,?,?,?,?,?,?,?)", r)
    for r in speaker_rows:
        conn.execute("INSERT INTO speaker VALUES (?,?,?,?,?,?)", r)
    for r in conference_rows:
        conn.execute("INSERT INTO conference VALUES (?,?,?,?,?,?)", r)
    for r in session_rows:
        conn.execute("INSERT INTO conf_session VALUES (?,?,?,?,?,?)", r)
    for r in conf_talk_rows:
        conn.execute("INSERT INTO conference_talk VALUES (?,?,?,?,?)", r)
    for r in (talk_metadata_rows or []):
        conn.execute("INSERT INTO talk_metadata VALUES (?,?,?,?,?,?,?)", r)
    conn.commit()
    return conn


class InMemoryDatabase:
    """Minimal Database-like wrapper for in-memory SQLite testing."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def select(self, query: str, params: tuple = ()) -> List[Dict]:
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def select_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        rows = self.select(query, params)
        return rows[0] if rows else None


class TestSchemaValidation(unittest.TestCase):
    """Tests for SQLite schema validation (QUAL-06)."""

    def test_schema_validation_passes_correct_schema(self):
        """validate_schema accepts a DB with all expected tables and columns."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE talk (ID INT PRIMARY KEY, Corpus TEXT, URL TEXT, Title TEXT, Date TEXT, SpeakerID INT)")
        conn.execute("CREATE TABLE speaker (ID INT PRIMARY KEY, GivenNames TEXT, LastNames TEXT)")
        conn.execute("CREATE TABLE conference (ID INT PRIMARY KEY, Description TEXT, Year INT, Annual INT)")
        conn.execute("CREATE TABLE conf_session (ID INT PRIMARY KEY, Description TEXT, ConferenceID INT)")
        conn.execute("CREATE TABLE conference_talk (TalkID INT, SessionID INT, Sequence INT)")
        conn.execute("CREATE TABLE citation (ID INT PRIMARY KEY, TalkID INT, BookID INT, Chapter INT, Verses TEXT)")
        conn.execute("CREATE TABLE book (ID INT PRIMARY KEY, Abbr TEXT, FullName TEXT)")
        conn.execute("CREATE TABLE talk_metadata (talk_id INT PRIMARY KEY, speaker_role_id INT, uri_l TEXT, uri_gc TEXT, kicker TEXT, talk_preview TEXT, data_aid TEXT)")
        from db import validate_schema, EXPECTED_CORE_TABLES
        # Should not raise
        validate_schema(conn, EXPECTED_CORE_TABLES, "test_core")
        conn.close()

    def test_schema_validation_missing_table(self):
        """validate_schema raises SchemaError when a required table is missing."""
        conn = sqlite3.connect(":memory:")
        # Only create 'talk' — missing all others
        conn.execute("CREATE TABLE talk (ID INT PRIMARY KEY, Corpus TEXT, URL TEXT, Title TEXT, Date TEXT, SpeakerID INT)")
        from db import validate_schema, SchemaError, EXPECTED_CORE_TABLES
        with self.assertRaises(SchemaError) as ctx:
            validate_schema(conn, EXPECTED_CORE_TABLES, "test_core")
        self.assertIn("not found", str(ctx.exception))
        conn.close()

    def test_schema_validation_missing_column(self):
        """validate_schema raises SchemaError when a required column is missing."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE talk (ID INT PRIMARY KEY, Corpus TEXT)")  # Missing URL, Title, Date, SpeakerID
        conn.execute("CREATE TABLE speaker (ID INT PRIMARY KEY, GivenNames TEXT, LastNames TEXT)")
        conn.execute("CREATE TABLE conference (ID INT PRIMARY KEY, Description TEXT, Year INT, Annual INT)")
        conn.execute("CREATE TABLE conf_session (ID INT PRIMARY KEY, Description TEXT, ConferenceID INT)")
        conn.execute("CREATE TABLE conference_talk (TalkID INT, SessionID INT, Sequence INT)")
        conn.execute("CREATE TABLE citation (ID INT PRIMARY KEY, TalkID INT, BookID INT, Chapter INT, Verses TEXT)")
        conn.execute("CREATE TABLE book (ID INT PRIMARY KEY, Abbr TEXT, FullName TEXT)")
        conn.execute("CREATE TABLE talk_metadata (talk_id INT PRIMARY KEY, speaker_role_id INT, uri_l TEXT, uri_gc TEXT, kicker TEXT, talk_preview TEXT, data_aid TEXT)")
        from db import validate_schema, SchemaError, EXPECTED_CORE_TABLES
        with self.assertRaises(SchemaError) as ctx:
            validate_schema(conn, EXPECTED_CORE_TABLES, "test_core")
        self.assertIn("missing columns", str(ctx.exception))
        conn.close()

    def test_schema_validation_content_db(self):
        """validate_schema accepts a content DB with correct talkbody table."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE talkbody (TalkID INT PRIMARY KEY, Text TEXT, TextRaw TEXT)")
        from db import validate_schema, EXPECTED_CONTENT_TABLES
        validate_schema(conn, EXPECTED_CONTENT_TABLES, "test_content")
        conn.close()


class TestPhase1EdgeCases(unittest.TestCase):
    """Tests for Phase 1 edge cases using in-memory SQLite fixtures (QUAL-05)."""

    def test_edge_missing_speaker(self):
        """Phase 1 handles a talk whose SpeakerID has no matching speaker row."""
        conn = _build_in_memory_db(
            talk_rows=[(1, 'G', 'http://example.com', 'Test Talk', '2020-04-05', 999, None, None, None, None, None)],
            speaker_rows=[],  # No speaker with ID 999
            conference_rows=[(1, 'April 2020', 'A20', 2020, 1, '2020-04-01')],
            session_rows=[(1, 'Saturday Morning', 'SM', '2020-04-04', 1, 1)],
            conf_talk_rows=[(1, 1, 1, 5, 1)],
        )
        db = InMemoryDatabase(conn)
        from extractors.phase1_talk_metadata import fetch_talk_by_id
        # INNER JOIN on speaker means no match returns None — that's valid graceful handling
        result = fetch_talk_by_id(db, 1)
        # Should return a row if LEFT JOIN, or None if INNER JOIN — either way: no crash
        if result is not None:
            from extractors.phase1_talk_metadata import extract_talk_metadata
            metadata = extract_talk_metadata(result)
            self.assertEqual(metadata.talk_id, 1)
        # No exception raised is the key requirement
        conn.close()

    def test_edge_unusual_session_type(self):
        """Phase 1 handles talks from welfare/sustaining sessions."""
        conn = _build_in_memory_db(
            talk_rows=[(1, 'G', 'http://example.com', 'Welfare Report', '1982-04-03', 1, None, None, None, None, None)],
            speaker_rows=[(1, 'Thomas', 'Monson', 'TSM', '', 'Monson, Thomas')],
            conference_rows=[(1, 'April 1982', 'A82', 1982, 1, '1982-04-01')],
            session_rows=[(1, 'Welfare Session', 'WS', '1982-04-03', 1, 1)],
            conf_talk_rows=[(1, 1, 1, 5, 1)],
        )
        db = InMemoryDatabase(conn)
        from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
        result = fetch_talk_by_id(db, 1)
        self.assertIsNotNone(result, "Expected a row for welfare session talk")
        metadata = extract_talk_metadata(result)
        self.assertEqual(metadata.talk_id, 1)
        self.assertEqual(metadata.title, 'Welfare Report')
        conn.close()

    def test_edge_no_url_talk(self):
        """Phase 1 handles talks with NULL URL (Ensign-era corpus)."""
        conn = _build_in_memory_db(
            talk_rows=[(1, 'E', None, 'Faith and Works', '1946-04-06', 1, None, None, None, None, None)],
            speaker_rows=[(1, 'David', 'McKay', 'DOM', '', 'McKay, David')],
            conference_rows=[(1, 'April 1946', 'A46', 1946, 1, '1946-04-01')],
            session_rows=[(1, 'Saturday Morning', 'SM', '1946-04-06', 1, 1)],
            conf_talk_rows=[(1, 1, 1, 5, 1)],
        )
        db = InMemoryDatabase(conn)
        from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
        result = fetch_talk_by_id(db, 1)
        self.assertIsNotNone(result, "Expected a row for no-URL talk")
        metadata = extract_talk_metadata(result)
        self.assertEqual(metadata.talk_id, 1)
        self.assertIsNone(metadata.url)
        conn.close()


def run_tests():
    """Run all tests."""
    unittest.main(argv=[""], verbosity=2, exit=False)


if __name__ == "__main__":
    run_tests()
