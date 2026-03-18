"""
Unified extraction pipeline.

Orchestrates Phase 2 → Phase 3 → Phase 4 for a single talk, sharing a
single HTML parse per paragraph across all three phases via ParagraphHTMLContext.

Usage:
    result = process_talk_pipeline(
        content_db=content_db_instance,
        core_db=core_db_instance,
        talk_id=12345,
        book_cache=book_cache,
        config=PARAGRAPH_CONFIG,
    )
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(str(Path(__file__).parent.parent))

from db import Database, Row
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import TalkCitations
from models.footnote_data import TalkFootnotes
from extractors.html_parsing_utils import ParagraphHTMLContext
from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
from extractors.phase2_paragraph_extraction import process_talk_paragraphs
from extractors.phase3_citation_extraction import process_talk_citations
from extractors.phase4_footnote_extraction import process_talk_footnotes

logger = logging.getLogger(__name__)


# =============================================================================
# Result container
# =============================================================================


@dataclass
class TalkPipelineResult:
    """Aggregated output from all four extraction phases for a single talk."""

    talk_id: int
    metadata: Optional[TalkMetadata]
    paragraphs: TalkParagraphs
    citations: TalkCitations
    footnotes: TalkFootnotes
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return (
            self.metadata is not None
            and self.paragraphs.extraction_success
            and self.citations.extraction_success
            and self.footnotes.extraction_success
            and not self.errors
        )


# =============================================================================
# Orchestrator
# =============================================================================


def process_talk_pipeline(
    content_db: Database,
    core_db: Database,
    talk_id: int,
    book_cache: Dict[int, Row],
    config: Dict[str, Any],
) -> TalkPipelineResult:
    """
    Run the full extraction pipeline for a single talk.

    Steps:
      1. Phase 1 — extract talk metadata from core DB
      2. Phase 2 — extract paragraphs from HTML
      3. Build ParagraphHTMLContext per paragraph (one lazy parse each)
      4. Phase 3 — extract citations using shared contexts
      5. Phase 4 — extract footnotes using shared contexts

    Paragraph citation/footnote count fields are back-filled in-place by
    Phases 3 and 4 (they already mutate ParagraphData directly).

    Returns a TalkPipelineResult with all outputs and merged diagnostics.
    """
    all_warnings: List[str] = []
    all_errors: List[str] = []

    # --- Phase 1 ---
    logger.debug(f"Pipeline: Phase 1 for talk {talk_id}")
    talk_metadata: Optional[TalkMetadata] = None
    try:
        row = fetch_talk_by_id(core_db, talk_id)
        if row is None:
            all_errors.append(f"Phase 1: talk {talk_id} not found in core DB")
        else:
            talk_metadata = extract_talk_metadata(row)
    except Exception as e:
        logger.error(f"Pipeline: Phase 1 failed for talk {talk_id}: {e}", exc_info=True)
        all_errors.append(f"Phase 1 failed: {e}")

    # --- Phase 2 ---
    logger.debug(f"Pipeline: Phase 2 for talk {talk_id}")
    talk_paragraphs, phase2_warnings = process_talk_paragraphs(
        content_db, talk_id, config
    )
    all_warnings.extend(phase2_warnings)

    if talk_paragraphs is None:
        all_errors.extend(phase2_warnings)
        empty_cites = TalkCitations(
            talk_id=talk_id,
            citations=[],
            total_citations=0,
            extraction_success=False,
            extraction_errors=phase2_warnings,
        )
        empty_fns = TalkFootnotes(
            talk_id=talk_id,
            footnotes=[],
            total_footnotes=0,
            extraction_success=False,
            extraction_errors=phase2_warnings,
        )
        empty_paras = TalkParagraphs(
            talk_id=talk_id,
            paragraphs=[],
            total_paragraphs=0,
            total_words=0,
            extraction_success=False,
            extraction_errors=phase2_warnings,
        )
        return TalkPipelineResult(
            talk_id=talk_id,
            metadata=talk_metadata,
            paragraphs=empty_paras,
            citations=empty_cites,
            footnotes=empty_fns,
            errors=all_errors,
        )

    if not talk_paragraphs.extraction_success:
        all_errors.extend(talk_paragraphs.extraction_errors)

    paragraphs: List[ParagraphData] = talk_paragraphs.paragraphs

    # --- Build shared contexts ---
    parser = config.get("html_parser", "html.parser")
    contexts: Dict[int, ParagraphHTMLContext] = {
        para.paragraph_id: ParagraphHTMLContext(para.text_raw, parser)
        for para in paragraphs
        if para.text_raw
    }
    logger.debug(f"Pipeline: built {len(contexts)} HTML contexts for talk {talk_id}")

    # --- Phase 3 ---
    logger.debug(f"Pipeline: Phase 3 for talk {talk_id}")
    try:
        talk_citations, cite_warnings = process_talk_citations(
            core_db_instance=core_db,
            talk_id=talk_id,
            paragraphs=paragraphs,
            book_cache=book_cache,
            config=config,
            contexts=contexts,
        )
        all_warnings.extend(cite_warnings)
    except Exception as e:
        logger.error(f"Pipeline: Phase 3 failed for talk {talk_id}: {e}", exc_info=True)
        all_errors.append(f"Phase 3 failed: {e}")
        talk_citations = TalkCitations(
            talk_id=talk_id,
            citations=[],
            total_citations=0,
            extraction_success=False,
            extraction_errors=[str(e)],
        )

    # --- Phase 4 ---
    logger.debug(f"Pipeline: Phase 4 for talk {talk_id}")
    try:
        talk_footnotes, fn_warnings = process_talk_footnotes(
            talk_id=talk_id,
            paragraphs=paragraphs,
            config=config,
            contexts=contexts,
        )
        all_warnings.extend(fn_warnings)
    except Exception as e:
        logger.error(f"Pipeline: Phase 4 failed for talk {talk_id}: {e}", exc_info=True)
        all_errors.append(f"Phase 4 failed: {e}")
        talk_footnotes = TalkFootnotes(
            talk_id=talk_id,
            footnotes=[],
            total_footnotes=0,
            extraction_success=False,
            extraction_errors=[str(e)],
        )

    return TalkPipelineResult(
        talk_id=talk_id,
        metadata=talk_metadata,
        paragraphs=talk_paragraphs,
        citations=talk_citations,
        footnotes=talk_footnotes,
        warnings=all_warnings,
        errors=all_errors,
    )
