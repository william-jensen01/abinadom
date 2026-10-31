"""
Integration tests: Full pipeline end-to-end (metadata through validation) over 5 real talks.

Validates phase-to-phase data contracts at every boundary. Tests skip
gracefully when DB files are not present.
"""
import os
import sys
import pytest
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from db import Database, CORE_DB_PATH, CONTENT_DB_PATH
from extractors.pipeline import process_talk_pipeline, TalkPipelineResult
from extractors.validation import validate_talk

# Skip the entire module when DB files are not present
DB_AVAILABLE = os.path.exists(CORE_DB_PATH) and os.path.exists(CONTENT_DB_PATH)
pytestmark = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="DB files not present (core.52.db / content.52.db)",
)

# =============================================================================
# Hardcoded talk IDs (D-02 — researched from actual DB)
# =============================================================================

INTEGRATION_TALK_IDS = [
    1,      # 1942 earliest era, Corpus='E', URL=None — old era + no URL
    8827,   # 2025, 78 citations, Corpus='G' — recent era + citation-rich
    3679,   # 1982, Welfare Session, Corpus='G' — unusual session type
    258,    # 1946, 72 citations, Corpus='E' — citation-heavy early era
    8726,   # 2024, 75 citations, Corpus='G' — recent + high citation count
]


# =============================================================================
# Module-scoped fixtures (run once for entire test session)
# =============================================================================


@pytest.fixture(scope="module")
def core_db():
    return Database(CORE_DB_PATH)


@pytest.fixture(scope="module")
def content_db():
    return Database(CONTENT_DB_PATH)


@pytest.fixture(scope="module")
def book_cache(core_db):
    from extractors.citations import fetch_all_books
    return fetch_all_books(core_db)


@pytest.fixture(scope="module")
def pipeline_config():
    from config.schemas import PARAGRAPH_CONFIG
    return PARAGRAPH_CONFIG


# =============================================================================
# Test 1: Full pipeline runs without errors for each talk
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_pipeline_end_to_end(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Pipeline completes successfully for each integration talk (D-01, D-04)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    assert result.success, f"Pipeline failed for talk {talk_id}: {result.errors}"


# =============================================================================
# Test 2: Talk metadata boundary — metadata has required fields
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_talk_metadata_boundary(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Talk metadata output has required metadata fields with correct types (D-03)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    meta = result.metadata
    assert meta is not None, f"No metadata for talk {talk_id}"
    assert isinstance(meta.talk_id, int)
    assert meta.talk_id == talk_id
    assert isinstance(meta.speaker_name, str) and len(meta.speaker_name) > 0
    assert isinstance(meta.conference_year, int) and meta.conference_year >= 1942
    assert isinstance(meta.title, str) and len(meta.title) > 0


# =============================================================================
# Test 3: Paragraphs boundary — paragraphs non-empty with required fields
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_paragraphs_boundary(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Paragraph extraction output has non-empty paragraphs with required fields (D-03)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    paras = result.paragraphs
    assert paras.extraction_success
    assert len(paras.paragraphs) > 0, f"No paragraphs for talk {talk_id}"
    for p in paras.paragraphs:
        assert isinstance(p.paragraph_id, int)
        assert p.talk_id == talk_id
        assert isinstance(p.text, str) and len(p.text) > 0
        assert isinstance(p.paragraph_number, int) and p.paragraph_number >= 1


# =============================================================================
# Test 4: Citations boundary — citations extracted with required fields
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_citations_boundary(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Citation extraction output has citations with required fields when present (D-03)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    cites = result.citations
    assert cites.extraction_success
    # Not all talks have citations, but our selected talks do (talk 1 might not)
    if cites.total_citations > 0:
        for c in cites.citations:
            assert isinstance(c.citation_id, int)
            assert isinstance(c.paragraph_id, int)
            assert isinstance(c.book, str)


# =============================================================================
# Test 5: Footnotes boundary — footnotes extracted with required fields
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_footnotes_boundary(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Footnote extraction output has footnotes with required fields when present (D-03)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    fns = result.footnotes
    assert fns.extraction_success
    if fns.total_footnotes > 0:
        for f in fns.footnotes:
            assert isinstance(f.footnote_id, int)
            assert isinstance(f.paragraph_id, int)


# =============================================================================
# Test 6: Validation passes
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_validation(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Validation gate passes for all integration talks (D-01, D-04)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    report = validate_talk(
        result.metadata, result.paragraphs, result.citations, result.footnotes,
        db=core_db
    )
    assert report.is_valid, f"Validation failed for talk {talk_id}: {report.errors}"


# =============================================================================
# Test 7: Cross-phase data contract — paragraph_ids referenced by
#          citations/footnotes exist in the paragraph list (D-03)
# =============================================================================


@pytest.mark.parametrize("talk_id", INTEGRATION_TALK_IDS)
def test_cross_phase_paragraph_ids(talk_id, core_db, content_db, book_cache, pipeline_config):
    """Every citation and footnote paragraph_id resolves to an existing paragraph (D-03)."""
    result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, pipeline_config)
    para_ids = {p.paragraph_id for p in result.paragraphs.paragraphs}
    for c in result.citations.citations:
        assert c.paragraph_id in para_ids, (
            f"Citation {c.citation_id} refs missing paragraph {c.paragraph_id}"
        )
    for f in result.footnotes.footnotes:
        assert f.paragraph_id in para_ids, (
            f"Footnote {f.footnote_id} refs missing paragraph {f.paragraph_id}"
        )
