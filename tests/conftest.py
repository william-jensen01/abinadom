"""
Shared pytest fixtures for Phase 21 loader integration tests.

Port-check fixtures (D-08): session-scoped, auto-skip when Docker is down.
TalkBundle fixture (D-09): deterministic minimal bundle (talk_id=9999) shared by all 3 loader tests.
"""
import socket
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from loaders.shared_transforms import TalkBundle


# ---------------------------------------------------------------------------
# Port-check helpers (D-08)
# ---------------------------------------------------------------------------

def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def chromadb_available():
    """Skip test module if ChromaDB is not reachable at localhost:8000."""
    if not _is_port_open("localhost", 8000):
        pytest.skip("ChromaDB not reachable at localhost:8000 — start Docker Compose")


@pytest.fixture(scope="session")
def weaviate_available():
    """Skip test module if Weaviate is not reachable at localhost:8080."""
    if not _is_port_open("localhost", 8080):
        pytest.skip("Weaviate not reachable at localhost:8080 — start Docker Compose")


@pytest.fixture(scope="session")
def qdrant_available():
    """Skip test module if Qdrant is not reachable at localhost:6333."""
    if not _is_port_open("localhost", 6333):
        pytest.skip("Qdrant not reachable at localhost:6333 — start Docker Compose")


@pytest.fixture(scope="session")
def ollama_available():
    """Skip test if Ollama is not reachable at localhost:11434."""
    if not _is_port_open("localhost", 11434):
        pytest.skip("Ollama not reachable at localhost:11434")


# ---------------------------------------------------------------------------
# Factory functions (adapted from test_phase6.py, talk_id=9999)
# ---------------------------------------------------------------------------

def make_talk_metadata(**kwargs) -> TalkMetadata:
    defaults = dict(
        talk_id=9999,
        speaker_id=1,
        conference_id=1,
        title="Test Loader Talk",
        speaker_name="Elder Test",
        conference_year=2024,
        conference_month="April",
        conference_description="April 2024 General Conference",
        talk_date="2024-04-07",
        talk_preview="This is the preview text for loader tests.",
        corpus="E",
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_version="1.0.0",
    )
    defaults.update(kwargs)
    return TalkMetadata(**defaults)


def make_paragraph(paragraph_id=1, paragraph_number=1, text="Loader test paragraph text.", source_type="p", **kwargs) -> ParagraphData:
    defaults = dict(
        paragraph_id=paragraph_id,
        talk_id=9999,
        paragraph_number=paragraph_number,
        text=text,
        text_raw=None,
        word_count=4,
        source_type=source_type,
    )
    defaults.update(kwargs)
    return ParagraphData(**defaults)


def make_talk_paragraphs(paragraphs: list[ParagraphData]) -> TalkParagraphs:
    return TalkParagraphs(
        talk_id=9999,
        paragraphs=paragraphs,
        total_paragraphs=len(paragraphs),
        total_words=sum(p.word_count for p in paragraphs),
        extraction_success=True,
    )


def make_citation(citation_id=1, paragraph_id=99990001, paragraph_number=1, **kwargs) -> CitationData:
    defaults = dict(
        citation_id=citation_id,
        talk_id=9999,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        citation_text_raw="John 3:16",
        char_position=5,
        char_end_position=12,
        scripture_ref="John 3:16",
        book="John",
        book_abbr="John",
        book_id=43,
        chapter=3,
        verses="16",
        verse_start=16,
        verse_end=16,
        verse_list=[16],
        context_window="For God so loved the world John 3:16 that he gave",
    )
    defaults.update(kwargs)
    return CitationData(**defaults)


def make_talk_citations(citations: list[CitationData]) -> TalkCitations:
    return TalkCitations(
        talk_id=9999,
        citations=citations,
        total_citations=len(citations),
        extraction_success=True,
    )


def make_footnote(footnote_id=99990100, paragraph_id=99990001, paragraph_number=1, **kwargs) -> FootnoteData:
    defaults = dict(
        footnote_id=footnote_id,
        talk_id=9999,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        footnote_number=1,
        footnote_text_raw="See John 3:16",
        char_position=10,
        context_window="surrounding loader test text See John 3:16 end",
    )
    defaults.update(kwargs)
    return FootnoteData(**defaults)


def make_talk_footnotes(footnotes: list[FootnoteData]) -> TalkFootnotes:
    return TalkFootnotes(
        talk_id=9999,
        footnotes=footnotes,
        total_footnotes=len(footnotes),
        extraction_success=True,
    )


# ---------------------------------------------------------------------------
# Shared TalkBundle fixture (D-09)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def talk_bundle() -> TalkBundle:
    """
    Minimal deterministic TalkBundle for all loader round-trip tests.

    Contains: 1 talk (talk_id=9999), 2 paragraphs, 1 citation, 1 footnote.
    is_valid=True so no records are skipped.
    """
    metadata = make_talk_metadata()
    paragraphs = make_talk_paragraphs([
        make_paragraph(paragraph_id=99990001, paragraph_number=1, text="First loader test paragraph."),
        make_paragraph(paragraph_id=99990002, paragraph_number=2, text="Second loader test paragraph."),
    ])
    citations = make_talk_citations([make_citation()])
    footnotes = make_talk_footnotes([make_footnote()])
    validation_report = ValidationReport(
        talk_id=9999,
        is_valid=True,
        errors=[],
        warnings=[],
        stats={},
    )
    return metadata, paragraphs, citations, footnotes, validation_report
