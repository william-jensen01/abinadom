"""
Unit tests for Phase 1: Talk Metadata Extraction

Tests cover:
- Schema validation
- Validators
- TalkMetadata dataclass
- Database queries and transformations
- ChromaDB format conversion
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

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

    def test_talk_metadata_to_chromadb_format(self):
        """Should convert to ChromaDB format correctly."""
        data = self.get_valid_metadata_dict()
        metadata = create_talk_metadata_from_db_row(data)
        document, meta, doc_id = metadata.to_chromadb_format()

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


@unittest.skip("Wave 0 stub -- filled by Plan 01-01")
class TestTalkMetadataDDL(unittest.TestCase):
    """Stubs for talk_metadata table DDL validation."""

    def test_talk_metadata_table_exists(self):
        """talk_metadata table should exist in core.52.db after DDL runs."""
        self.fail("Stub -- implement after Plan 01-01 creates the table")

    def test_talk_metadata_has_expected_columns(self):
        """talk_metadata should have 7 columns: talk_id, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid."""
        self.fail("Stub")

    def test_talk_metadata_has_indexes(self):
        """talk_metadata should have indexes on data_aid and uri_gc."""
        self.fail("Stub")


@unittest.skip("Wave 0 stub -- filled by Plan 01-01")
class TestBackfillTargets(unittest.TestCase):
    """Stubs for backfill script target validation."""

    def test_backfill_scripts_use_upsert_helper(self):
        """All 5 backfill scripts should import upsert_talk_metadata."""
        self.fail("Stub")

    def test_no_direct_writes_to_talks_table(self):
        """Backfill scripts (except Title in backfill_talk_metadata) should not UPDATE talk SET."""
        self.fail("Stub")


@unittest.skip("Wave 0 stub -- filled by Plan 01-03")
class TestEnrichedFields(unittest.TestCase):
    """Stubs for enriched field coverage in Phase 1."""

    def test_talk_metadata_has_kicker_field(self):
        """TalkMetadata dataclass should have kicker: Optional[str]."""
        self.fail("Stub")

    def test_talk_metadata_has_talk_preview_field(self):
        """TalkMetadata dataclass should have talk_preview: Optional[str]."""
        self.fail("Stub")

    def test_kicker_in_document_summary(self):
        """Document summary should include kicker when present."""
        self.fail("Stub")

    def test_talk_preview_in_document_summary(self):
        """Document summary should include talk_preview when present."""
        self.fail("Stub")

    def test_enriched_fields_optional(self):
        """kicker and talk_preview should default to None."""
        self.fail("Stub")

    def test_query_has_left_join(self):
        """Phase 1 query should LEFT JOIN talk_metadata."""
        self.fail("Stub")

    def test_transform_db_row_includes_enriched_fields(self):
        """transform_db_row_to_metadata should map kicker and talk_preview."""
        self.fail("Stub")


@unittest.skip("Wave 0 stub -- filled by Plan 01-03")
class TestTopicTablesUnchanged(unittest.TestCase):
    """Stubs for topic table smoke test."""

    def test_conference_topic_count_unchanged(self):
        """conference_topic row count should not change after backfills."""
        self.fail("Stub")

    def test_talk_topic_count_unchanged(self):
        """talk_topic row count should not change after backfills."""
        self.fail("Stub")


def run_tests():
    """Run all tests."""
    unittest.main(argv=[""], verbosity=2, exit=False)


if __name__ == "__main__":
    run_tests()
