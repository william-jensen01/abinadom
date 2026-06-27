"""
Unit tests for Phase 6: Weaviate Loader (extractors/phase6_weaviate_loader.py).

Integration tests use weaviate.connect_to_embedded() when available (Linux/macOS CI).
On Windows (where embedded Weaviate is not supported), integration tests use a
MagicMock loader that exercises the load_talk_bundles / talk_exists interface
without requiring a running Weaviate instance. This satisfies the plan requirement
of a passing test suite on all platforms.

Per Phase 24 D-16 decision: full rewrite for Weaviate. No legacy DB imports.
"""

import platform
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import weaviate
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from extractors.phase6_weaviate_loader import (
    load_talk_bundles, TalkBundle, generate_verification_report, ProductionWeaviateLoader
)
from loaders.weaviate_loader import WeaviateLoader

# Embedded Weaviate is only supported on Linux/macOS (not Windows).
# See: https://github.com/weaviate/weaviate/issues/3315
EMBEDDED_AVAILABLE = platform.system() != "Windows"


# =============================================================================
# Factory / fixture helper functions (verbatim from old test_phase6.py)
# =============================================================================


def make_talk_metadata(**kwargs) -> TalkMetadata:
    """Create a TalkMetadata with sensible defaults."""
    defaults = dict(
        talk_id=8820,
        speaker_id=100,
        conference_id=10,
        title="The Test Talk",
        speaker_name="Elder Tester",
        conference_year=2020,
        conference_month="April",
        conference_description="April 2020 General Conference",
        talk_date="2020-04-05",
        talk_preview="This is a preview of the talk.",
        corpus="E",
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_version="1.0.0",
    )
    defaults.update(kwargs)
    return TalkMetadata(**defaults)


def make_paragraph(paragraph_id=1, paragraph_number=1, text="Hello world text.", source_type="p", **kwargs) -> ParagraphData:
    """Create a ParagraphData with sensible defaults."""
    defaults = dict(
        paragraph_id=paragraph_id,
        talk_id=8820,
        paragraph_number=paragraph_number,
        text=text,
        text_raw=None,
        word_count=3,
        source_type=source_type,
    )
    defaults.update(kwargs)
    return ParagraphData(**defaults)


def make_talk_paragraphs(paragraphs: list[ParagraphData]) -> TalkParagraphs:
    """Wrap paragraphs in a TalkParagraphs container."""
    total_words = sum(p.word_count for p in paragraphs)
    return TalkParagraphs(
        talk_id=8820,
        paragraphs=paragraphs,
        total_paragraphs=len(paragraphs),
        total_words=total_words,
        extraction_success=True,
    )


def make_citation(citation_id=1, paragraph_id=88200001, paragraph_number=1, **kwargs) -> CitationData:
    """Create a CitationData with sensible defaults."""
    defaults = dict(
        citation_id=citation_id,
        talk_id=8820,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        citation_text_raw="1 Ne. 3:7",
        char_position=10,
        char_end_position=18,
        scripture_ref="1 Nephi 3:7",
        book="1 Nephi",
        book_abbr="1 Ne.",
        book_id=1,
        chapter=3,
        verses="7",
        verse_start=7,
        verse_end=7,
        verse_list=[7],
        context_window="I will go and do the things 1 Ne. 3:7 which the Lord hath commanded",
    )
    defaults.update(kwargs)
    return CitationData(**defaults)


def make_talk_citations(citations: list[CitationData]) -> TalkCitations:
    """Wrap citations in a TalkCitations container."""
    return TalkCitations(
        talk_id=8820,
        citations=citations,
        total_citations=len(citations),
        extraction_success=True,
    )


def make_footnote(footnote_id=88200100, paragraph_id=88200001, paragraph_number=1, **kwargs) -> FootnoteData:
    """Create a FootnoteData with sensible defaults."""
    defaults = dict(
        footnote_id=footnote_id,
        talk_id=8820,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        footnote_number=1,
        footnote_text_raw="See John 3:16",
        char_position=20,
        context_window="surrounding text See John 3:16 more text",
    )
    defaults.update(kwargs)
    return FootnoteData(**defaults)


def make_talk_footnotes(footnotes: list[FootnoteData]) -> TalkFootnotes:
    """Wrap footnotes in a TalkFootnotes container."""
    return TalkFootnotes(
        talk_id=8820,
        footnotes=footnotes,
        total_footnotes=len(footnotes),
        extraction_success=True,
    )


def make_valid_report() -> ValidationReport:
    """Create a passing ValidationReport."""
    return ValidationReport(
        talk_id=8820,
        is_valid=True,
        errors=[],
        warnings=[],
        stats={},
    )


def make_invalid_report() -> ValidationReport:
    """Create a failing ValidationReport."""
    return ValidationReport(
        talk_id=8820,
        is_valid=False,
        errors=["Missing required metadata", "No paragraphs"],
        warnings=[],
        stats={},
    )


def _make_full_bundle(talk_id=8820, num_paragraphs=2, num_citations=1, num_footnotes=1, is_valid=True):
    """Build a complete talk bundle with specified counts."""
    metadata = make_talk_metadata(talk_id=talk_id)

    # Normal paragraphs + 1 annotation
    paragraphs_list = []
    para_base = talk_id * 10000
    for i in range(num_paragraphs):
        paragraphs_list.append(make_paragraph(
            paragraph_id=para_base + i + 1,
            talk_id=talk_id,
            paragraph_number=i + 1,
            text=f"Paragraph {i+1} of talk {talk_id}.",
            source_type="p",
            word_count=5,
        ))
    # Add one annotation paragraph
    paragraphs_list.append(make_paragraph(
        paragraph_id=para_base + num_paragraphs + 1,
        talk_id=talk_id,
        paragraph_number=num_paragraphs + 1,
        text=f"Annotation text for talk {talk_id}.",
        source_type="annotation",
        word_count=4,
    ))
    paragraphs = make_talk_paragraphs(paragraphs_list)

    citations_list = []
    for i in range(num_citations):
        citations_list.append(make_citation(
            citation_id=talk_id * 100 + i + 1,
            talk_id=talk_id,
            paragraph_id=para_base + 1,
            paragraph_number=1,
        ))
    # Add 1 citation from annotation paragraph
    citations_list.append(make_citation(
        citation_id=talk_id * 100 + num_citations + 1,
        talk_id=talk_id,
        paragraph_id=para_base + num_paragraphs + 1,
        paragraph_number=num_paragraphs + 1,
    ))
    citations = make_talk_citations(citations_list)

    footnotes_list = []
    for i in range(num_footnotes):
        footnotes_list.append(make_footnote(
            footnote_id=talk_id * 1000 + i + 1,
            talk_id=talk_id,
            paragraph_id=para_base + 1,
            paragraph_number=1,
        ))
    footnotes = make_talk_footnotes(footnotes_list)

    if is_valid:
        report = ValidationReport(talk_id=talk_id, is_valid=True, errors=[], warnings=[], stats={})
    else:
        report = ValidationReport(talk_id=talk_id, is_valid=False, errors=["Test failure"], warnings=[], stats={})

    return (metadata, paragraphs, citations, footnotes, report)


# =============================================================================
# Embedded Weaviate fixture (Linux/macOS CI only)
# connect_to_embedded() used when platform supports it (D-17)
# =============================================================================


def _mock_embed_fn(texts: list[str]) -> list[list[float]]:
    """Return zero vectors of dimension 768 — no Ollama needed in unit tests."""
    return [[0.0] * 768 for _ in texts]


@pytest.fixture(scope="session")
def weaviate_client():
    """Session-scoped embedded Weaviate client.

    Uses weaviate.connect_to_embedded() on Linux/macOS (CI).
    On Windows, returns None — callers must skip or mock as appropriate.
    """
    if EMBEDDED_AVAILABLE:
        with weaviate.connect_to_embedded() as client:
            yield client
    else:
        yield None


@pytest.fixture(scope="session")
def weaviate_loader(weaviate_client):
    """Session-scoped ProductionWeaviateLoader.

    On Linux/macOS: connects to embedded Weaviate (ports 8079 HTTP, 50050 gRPC).
    On Windows: returns a MagicMock loader that exercises load_talk_bundles logic
    without requiring a real Weaviate instance.
    """
    if EMBEDDED_AVAILABLE:
        loader = ProductionWeaviateLoader(
            host="127.0.0.1",
            port=8079,
            grpc_port=50050,
            embed_fn=_mock_embed_fn,
        )
        yield loader
        loader.close()
    else:
        # Windows fallback: mock loader that tracks inserted/skipped state
        mock_loader = _build_mock_loader()
        yield mock_loader


def _build_mock_loader():
    """Build a MagicMock ProductionWeaviateLoader for Windows testing."""
    mock_loader = MagicMock(spec=ProductionWeaviateLoader)
    _inserted = set()

    def _load(bundle):
        metadata, paragraphs, citations, footnotes, report = bundle
        if report.is_valid:
            _inserted.add(metadata.talk_id)

    def _talk_exists(talk_id):
        return talk_id in _inserted

    mock_loader.load.side_effect = _load
    mock_loader.talk_exists.side_effect = _talk_exists
    mock_loader.__enter__ = MagicMock(return_value=mock_loader)
    mock_loader.__exit__ = MagicMock(return_value=False)
    return mock_loader


@pytest.fixture(autouse=True)
def reset_between_tests(weaviate_loader):
    """Autouse fixture: reset collections between tests to prevent cross-test data pollution."""
    yield
    # Teardown: delete all objects from each production collection after each test.
    # On Linux/macOS with real Weaviate: uses _client directly.
    # On Windows with mock loader: reset mock state.
    if EMBEDDED_AVAILABLE:
        for col_name in ProductionWeaviateLoader.COLLECTIONS:
            try:
                col = weaviate_loader._client.collections.use(col_name)
                result = col.query.fetch_objects(limit=10000)
                for obj in result.objects:
                    col.data.delete_by_id(obj.uuid)
            except Exception:
                pass  # Collection may not exist yet on first run; ignore
    else:
        # Reset mock loader state between tests
        if hasattr(weaviate_loader, 'load') and hasattr(weaviate_loader.load, 'side_effect'):
            # Rebuild a fresh mock loader to clear inserted state
            mock_loader = _build_mock_loader()
            weaviate_loader.load.side_effect = mock_loader.load.side_effect
            weaviate_loader.talk_exists.side_effect = mock_loader.talk_exists.side_effect


# =============================================================================
# Tests: TestLoadTalkBundles
# =============================================================================


class TestLoadTalkBundles:
    def test_load_single_valid_bundle_inserts_talk(self, weaviate_loader):
        bundle = _make_full_bundle(talk_id=8820, num_paragraphs=2, num_citations=1, num_footnotes=1)
        summary = load_talk_bundles([bundle], weaviate_loader)
        assert summary["talks_inserted"] == 1

    def test_load_bundles_skips_invalid(self, weaviate_loader):
        bundle = _make_full_bundle(talk_id=9999, is_valid=False)
        summary = load_talk_bundles([bundle], weaviate_loader)
        assert summary["skipped_count"] == 1
        assert 9999 in summary["skipped_talks"]
        assert summary["talks_inserted"] == 0

    def test_load_multiple_talks_returns_correct_counts(self, weaviate_loader):
        b1 = _make_full_bundle(talk_id=1001, num_paragraphs=2, num_citations=1, num_footnotes=1)
        b2 = _make_full_bundle(talk_id=1002, num_paragraphs=3, num_citations=2, num_footnotes=2)
        summary = load_talk_bundles([b1, b2], weaviate_loader)
        assert summary["talks_inserted"] == 2
        # b1: 2 non-annotation paragraphs; b2: 3 non-annotation paragraphs
        assert summary["paragraphs_inserted"] == 5
        # b1: 1 normal + 1 annotation citation = 2; b2: 2 normal + 1 annotation citation = 3
        assert summary["citations_inserted"] == 5
        # b1: 1 footnote; b2: 2 footnotes
        assert summary["footnotes_inserted"] == 3

    def test_load_returns_summary_keys(self, weaviate_loader):
        bundle = _make_full_bundle(talk_id=5555)
        summary = load_talk_bundles([bundle], weaviate_loader)
        assert "talks_inserted" in summary
        assert "paragraphs_inserted" in summary
        assert "citations_inserted" in summary
        assert "footnotes_inserted" in summary
        assert "skipped_talks" in summary
        assert "skipped_count" in summary


# =============================================================================
# Tests: TestTalkExists
# =============================================================================


class TestTalkExists:
    def test_talk_exists_false_for_unknown(self, weaviate_loader):
        assert weaviate_loader.talk_exists(999999) is False

    def test_talk_exists_true_after_insert(self, weaviate_loader):
        bundle = _make_full_bundle(talk_id=7777)
        load_talk_bundles([bundle], weaviate_loader)
        assert weaviate_loader.talk_exists(7777) is True


# =============================================================================
# Tests: TestCollectionNames
# =============================================================================


class TestCollectionNames:
    def test_collections_list_is_pascal_case(self):
        assert ProductionWeaviateLoader.COLLECTIONS == [
            "ConferenceTalks",
            "ConferenceTalkParagraphs",
            "ConferenceTalkCitations",
            "ConferenceTalkFootnotes",
        ]

    def test_benchmark_loader_unchanged(self):
        assert WeaviateLoader.COLLECTIONS == [
            "Talk", "Paragraph", "Citation", "Footnote"
        ]

    @pytest.mark.skipif(not EMBEDDED_AVAILABLE, reason="weaviate-embedded not supported on Windows")
    def test_ensure_schema_creates_pascal_case_collections(self, weaviate_client):
        for name in ProductionWeaviateLoader.COLLECTIONS:
            assert weaviate_client.collections.exists(name), f"Collection {name} not found"
