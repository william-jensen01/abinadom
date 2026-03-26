# -*- coding: utf-8 -*-
"""
Unit tests for Phase 6 orchestrator: scripts/run_pipeline.py

All tests mock external dependencies (DB, ChromaDB, extractors) using
unittest.mock.patch so no real database or ChromaDB is needed.
"""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.run_pipeline as run_pipeline
from scripts.run_pipeline import _get_all_gc_talk_ids, _record_failure


# =============================================================================
# Fixtures / helpers
# =============================================================================


def _make_pipeline_result(talk_id=1, success=True):
    """Build a mock TalkPipelineResult."""
    result = MagicMock()
    result.talk_id = talk_id
    result.success = success
    result.metadata = MagicMock()
    result.paragraphs = MagicMock()
    result.citations = MagicMock()
    result.footnotes = MagicMock()
    result.errors = [] if success else ["extraction failed"]
    return result


def _make_validation(is_valid=True):
    """Build a mock ValidationReport."""
    v = MagicMock()
    v.is_valid = is_valid
    v.errors = [] if is_valid else ["validation error"]
    return v


def _make_chroma_collection(existing_ids=None):
    """Build a mock ChromaDB collection."""
    col = MagicMock()
    # .get() returns dict with 'ids' key
    col.get.return_value = {"ids": existing_ids if existing_ids is not None else []}
    return col


# =============================================================================
# Test: _get_all_gc_talk_ids
# =============================================================================


def test_get_all_gc_talk_ids():
    """_get_all_gc_talk_ids queries core_db with INNER JOIN conference_talk and returns int list."""
    mock_db = MagicMock()
    mock_db.select.return_value = [{"ID": 1}, {"ID": 2}]

    with patch.object(run_pipeline, "core_db", mock_db):
        result = _get_all_gc_talk_ids()

    # Assert the SQL contains INNER JOIN conference_talk
    call_args = mock_db.select.call_args
    sql = call_args[0][0]
    assert "INNER JOIN conference_talk" in sql, f"Expected INNER JOIN conference_talk in SQL: {sql}"

    # Assert the result is a list of ints
    assert result == [1, 2]


# =============================================================================
# Test: full loop calls all phases
# =============================================================================


def test_full_loop_calls_all_phases():
    """main() calls process_talk_pipeline and validate_talk for each talk, then load_talk_bundles."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])  # no cached talks
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_pipeline_result = _make_pipeline_result(talk_id=1)
    mock_validation = _make_validation(is_valid=True)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", return_value=mock_pipeline_result) as mock_pipeline,
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation) as mock_validate,
        patch.object(run_pipeline, "load_talk_bundles", return_value={}) as mock_load,
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    # process_talk_pipeline called twice (for talk_id 1 and 2)
    assert mock_pipeline.call_count == 2
    # validate_talk called twice
    assert mock_validate.call_count == 2
    # load_talk_bundles called at least once (final flush)
    assert mock_load.call_count >= 1


# =============================================================================
# Test: resume skips already-processed talks
# =============================================================================


def test_resume_skips_processed():
    """When ChromaDB has talk_1, skip it; process talk_2."""
    # talk_1 is already in ChromaDB, talk_2 is not
    def get_side_effect(ids):
        if ids == ["talk_1"]:
            return {"ids": ["talk_1"]}
        return {"ids": []}

    mock_chroma_col = MagicMock()
    mock_chroma_col.get.side_effect = get_side_effect
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_pipeline_result = _make_pipeline_result(talk_id=2)
    mock_validation = _make_validation(is_valid=True)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", return_value=mock_pipeline_result) as mock_pipeline,
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    # Only called once (for talk_id=2, not talk_id=1)
    assert mock_pipeline.call_count == 1
    call_talk_id = mock_pipeline.call_args[0][2]  # positional arg index 2
    assert call_talk_id == 2


# =============================================================================
# Test: _record_failure writes JSON
# =============================================================================


def test_record_failure_writes_json(tmp_path):
    """_record_failure appends to list and writes JSON file to disk."""
    failed_talks = []
    fake_path = tmp_path / "failed_talks.json"

    with patch.object(run_pipeline, "FAILED_TALKS_PATH", fake_path):
        _record_failure(123, "some error", failed_talks)

    # Check the in-memory list was updated
    assert len(failed_talks) == 1
    assert failed_talks[0] == {"talk_id": 123, "error": "some error"}

    # Check the file was written
    assert fake_path.exists()
    with open(fake_path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0] == {"talk_id": 123, "error": "some error"}


# =============================================================================
# Test: exception in process_talk_pipeline logs failure
# =============================================================================


def test_failed_talk_logged_on_exception():
    """When process_talk_pipeline raises, _record_failure is called with the talk_id."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[42]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=RuntimeError("boom")),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}),
        patch.object(run_pipeline, "_record_failure") as mock_record,
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    # _record_failure should have been called once with talk_id=42
    assert mock_record.call_count == 1
    args = mock_record.call_args[0]
    assert args[0] == 42  # talk_id
    assert "boom" in args[1]  # error message


# =============================================================================
# Test: validation failure skips talk and records it
# =============================================================================


def test_validation_failure_skips_talk():
    """When validate_talk returns is_valid=False, talk is not added to bundles."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_pipeline_result = _make_pipeline_result(talk_id=7)
    mock_validation = _make_validation(is_valid=False)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[7]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", return_value=mock_pipeline_result),
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}) as mock_load,
        patch.object(run_pipeline, "_record_failure") as mock_record,
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    # _record_failure must have been called (validation failure logged)
    assert mock_record.call_count == 1
    assert mock_record.call_args[0][0] == 7

    # load_talk_bundles should NOT be called (pending_bundles stays empty, no final flush needed)
    # OR if called, bundles list must be empty
    if mock_load.call_count > 0:
        # If called (final flush path), the bundles arg should be empty
        bundles_arg = mock_load.call_args[0][0]
        assert len(bundles_arg) == 0


# =============================================================================
# Test: final summary is printed
# =============================================================================


def test_final_summary_printed(capsys):
    """After the loop, main() prints a summary with all counters."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_pipeline_result = _make_pipeline_result(talk_id=1)
    mock_validation = _make_validation(is_valid=True)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", return_value=mock_pipeline_result),
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    captured = capsys.readouterr()
    output = captured.out

    assert "Run complete" in output
    assert "Processed:" in output
    assert "Skipped" in output
    assert "Failed:" in output


# =============================================================================
# Test: skip mode default (3 talks, 2 already cached)
# =============================================================================


def test_skip_mode_default():
    """Default mode (no --force): talks already in ChromaDB are skipped; only unprocessed talk is processed."""
    def get_side_effect(ids):
        if ids == ["talk_1"]:
            return {"ids": ["talk_1"]}
        if ids == ["talk_2"]:
            return {"ids": []}
        if ids == ["talk_3"]:
            return {"ids": ["talk_3"]}
        return {"ids": []}

    mock_chroma_col = MagicMock()
    mock_chroma_col.get.side_effect = get_side_effect
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_pipeline_result = _make_pipeline_result(talk_id=2)
    mock_validation = _make_validation(is_valid=True)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2, 3]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", return_value=mock_pipeline_result) as mock_pipeline,
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py"]
        run_pipeline.main()

    # Only talk_id=2 (not in ChromaDB) should be processed; talk_1 and talk_3 skipped
    assert mock_pipeline.call_count == 1
    call_talk_id = mock_pipeline.call_args[0][2]
    assert call_talk_id == 2


# =============================================================================
# Test: --force flag bypasses ChromaDB skip check entirely
# =============================================================================


def test_force_flag_reprocesses():
    """--force flag causes all talks to be reprocessed; ChromaDB .get() is NOT called."""
    mock_chroma_col = MagicMock()
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_validation = _make_validation(is_valid=True)

    def pipeline_side_effect(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
        return _make_pipeline_result(talk_id=talk_id)

    with (
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=pipeline_side_effect) as mock_pipeline,
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", return_value={}),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py", "--force"]
        run_pipeline.main()

    # Both talks processed (force bypasses skip)
    assert mock_pipeline.call_count == 2
    # ChromaDB .get() should NOT be called (skip check entirely bypassed in force mode)
    assert mock_chroma_col.get.call_count == 0


# =============================================================================
# Test: buffer flush at CHROMADB_BATCH_SIZE boundary
# =============================================================================


def test_buffer_flush_at_batch_size():
    """With CHROMADB_BATCH_SIZE=2 and 3 talks, load_talk_bundles called twice: once at boundary, once final."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_validation = _make_validation(is_valid=True)

    # Track bundle snapshot sizes at each flush call (before pending_bundles.clear())
    flush_sizes = []

    def pipeline_side_effect(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
        return _make_pipeline_result(talk_id=talk_id)

    def load_bundles_side_effect(bundles, *args, **kwargs):
        # Capture the size before clear() is called
        flush_sizes.append(len(bundles))
        return {}

    with (
        patch.object(run_pipeline, "CHROMADB_BATCH_SIZE", 2),
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2, 3]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=pipeline_side_effect),
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", side_effect=load_bundles_side_effect),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py", "--force"]
        run_pipeline.main()

    # First flush at boundary (2 talks), second flush for remaining (1 talk)
    assert len(flush_sizes) == 2, f"Expected 2 flushes, got {len(flush_sizes)}: {flush_sizes}"
    assert flush_sizes[0] == 2, f"First flush should have 2 bundles, got {flush_sizes[0]}"
    assert flush_sizes[1] == 1, f"Final flush should have 1 bundle, got {flush_sizes[1]}"


# =============================================================================
# Test: final flush only when total < CHROMADB_BATCH_SIZE
# =============================================================================


def test_final_flush_on_remaining():
    """With CHROMADB_BATCH_SIZE=100 and 2 talks, load_talk_bundles called once (final flush only)."""
    mock_chroma_col = _make_chroma_collection(existing_ids=[])
    mock_chroma_client = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_chroma_col

    mock_validation = _make_validation(is_valid=True)

    flush_sizes = []

    def pipeline_side_effect(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
        return _make_pipeline_result(talk_id=talk_id)

    def load_bundles_side_effect(bundles, *args, **kwargs):
        flush_sizes.append(len(bundles))
        return {}

    with (
        patch.object(run_pipeline, "CHROMADB_BATCH_SIZE", 100),
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=[1, 2]),
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_chromadb_client", return_value=mock_chroma_client),
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=pipeline_side_effect),
        patch.object(run_pipeline, "validate_talk", return_value=mock_validation),
        patch.object(run_pipeline, "load_talk_bundles", side_effect=load_bundles_side_effect),
        patch.object(run_pipeline, "_record_failure"),
    ):
        sys.argv = ["run_pipeline.py", "--force"]
        run_pipeline.main()

    # Only final flush, never hit batch boundary
    assert len(flush_sizes) == 1, f"Expected 1 flush, got {len(flush_sizes)}: {flush_sizes}"
    assert flush_sizes[0] == 2, f"Final flush should have 2 bundles, got {flush_sizes[0]}"
