"""
Centralized processing parameters for the extraction pipeline.

All phases import constants from here. DB paths and file paths are NOT
included -- they stay passed-in or per-script.

Logging Level Conventions:
  DEBUG   -- verbose parsing detail, per-item tracing
  INFO    -- progress milestones, phase start/completion, record counts
  WARNING -- skipped items, fallbacks, suspicious-but-not-blocking events
  ERROR   -- failures that halt or corrupt output
"""

# --- HTML Parsing ---
PARAGRAPH_HTML_PARSER = "html5lib"
CITATION_HTML_PARSER = "html.parser"
FOOTNOTE_HTML_PARSER = "html.parser"

# --- Paragraph Extraction (Phase 2) ---
MIN_PARAGRAPH_LENGTH = 10
NORMALIZE_WHITESPACE = True
STRIP_FOOTNOTE_MARKERS = False
DECODE_ENTITIES = True
MIN_PARAGRAPHS_WARNING = 3
MAX_PARAGRAPHS_WARNING = 150
MIN_WORD_COUNT_INFO = 5
MAX_WORD_COUNT_WARNING = 400
MAX_WORD_COUNT_CRITICAL = 800

# --- Citation Extraction (Phase 3) ---
CONTEXT_BEFORE_CHARS = 100
CONTEXT_AFTER_CHARS = 100
CONTEXT_WINDOW_MODE = "word"
POSITION_MATCH_CASE_SENSITIVE = False
MAX_CITATIONS_PER_PARAGRAPH_WARNING = 20
CITATION_BATCH_SIZE = 100
SQLITE_MAX_PARAMS = 999
MAX_VERSE_RANGE = 200

# --- Footnote Extraction (Phase 4) ---
MAX_FOOTNOTES_PER_PARAGRAPH_WARNING = 20
# Footnotes share CONTEXT_BEFORE_CHARS, CONTEXT_AFTER_CHARS, CONTEXT_WINDOW_MODE

# --- Weaviate Loader (Phase 6) ---
WEAVIATE_BATCH_SIZE = 50
WEAVIATE_COLLECTION_NAMES = {
    "talks": "ConferenceTalks",
    "paragraphs": "ConferenceTalkParagraphs",
    "citations": "ConferenceTalkCitations",
    "footnotes": "ConferenceTalkFootnotes",
}

# --- ChromaDB backward-compatibility (verify_chromadb_pipeline.py) ---
# Production now uses Weaviate (Phase 24). These names are kept for operators
# who still run ChromaDB instances and use verify_chromadb_pipeline.py.
CHROMADB_COLLECTION_NAMES = {
    "talks": "conference_talks",
    "paragraphs": "conference_talk_paragraphs",
    "citations": "conference_talk_citations",
    "footnotes": "conference_talk_footnotes",
}
