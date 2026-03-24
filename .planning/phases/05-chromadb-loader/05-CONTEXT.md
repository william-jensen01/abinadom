# Phase 5: ChromaDB Loader - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `extractors/phase6_chromadb_loader.py` — transform Phase 5 validated output bundles (TalkMetadata + TalkParagraphs + TalkCitations + TalkFootnotes + ValidationReport) into ChromaDB `documents/metadatas/ids` format for 4 collections, insert in dependency order with batch chunking, and generate a post-insertion verification report. No new extraction capabilities. No changes to Phases 1–5.

</domain>

<decisions>
## Implementation Decisions

### Document Text (What to Embed)

- **D-01:** `conference_talks` — embed `f"{title}\n\n{talk_preview}"` when `talk_preview` is present; fall back to `title` alone when absent. Rationale: talk_preview was fetched from Church API specifically to enrich talk-level semantic search; title-only gives poor signal for short/evocative titles.
- **D-02:** `conference_talk_paragraphs` — embed `paragraph.text` (clean text, HTML stripped). Specified in PIPELINE_SPEC.md.
- **D-03:** `conference_talk_citations` — embed `citation.context_window` text. Specified in PIPELINE_SPEC.md.
- **D-04:** `conference_talk_footnotes` — embed `footnote.context_window` text. Specified in PIPELINE_SPEC.md.

### Metadata Field Selection

- **D-05:** Include all non-None fields from each dataclass as metadata. No manual curation — include everything present. Downstream filtering (MCP server, Milestone 2) can use any field without requiring a pipeline change. Planner determines exact per-collection field lists by reading the model dataclasses.
- **D-06:** Flatten any nested structures (lists → pipe-joined strings or JSON strings). ChromaDB metadata values must be scalars.

### Annotation Paragraph Handling

- **D-07:** Annotation paragraphs (`source_type="annotation"`) are excluded from `conference_talk_paragraphs` — not embedded.
- **D-08:** Annotation text is folded into `conference_talks` metadata as `annotations` field — pipe-joined string of all annotation texts for that talk. If no annotations, field is omitted (non-None rule).
- **D-09:** Citations extracted from annotation paragraphs are included in `conference_talk_citations` normally — their `paragraph_id` remains valid even though the parent paragraph is not embedded.

### Invalid Talk Handling

- **D-10:** If `validation_report.is_valid is False`, skip all 4 collection inserts for that talk. Log the `talk_id` and `errors` list at WARNING level. Continue processing remaining talks. Consistent with fail-safe hybrid used across the pipeline.
- **D-11:** Skipped talks are included in the post-insertion verification summary (count of skipped + list of talk_ids).

### ChromaDB Client Setup

- **D-12:** Use `chromadb.PersistentClient(path=CHROMADB_PATH)` where `CHROMADB_PATH` is defined in `config/pipeline_config.py` alongside other pipeline constants.
- **D-13:** Tests inject a temporary directory (e.g., `tmp_path` pytest fixture) or use `chromadb.EphemeralClient()` — no hardcoded test paths.

### Claude's Discretion

- Embedding function choice (ChromaDB default `all-MiniLM-L6-v2` is reasonable unless there's a reason to override)
- Verification report format (markdown or structured text to stdout/log)
- Batch size default value (pipeline spec suggests 5000 records; tune as needed)
- Exact retry logic for failed ChromaDB batches

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ChromaDB Loader Requirements
- `.planning/REQUIREMENTS.md` §ChromaDB Loader (LOAD) — LOAD-01 through LOAD-06 acceptance criteria

### Pipeline Architecture
- `docs/PIPELINE_SPEC.md` §Phase 6 — Full Phase 6 spec: data preparation, annotation handling, insertion strategy, verification requirements, error handling

### Phase 5 Output (Loader input)
- `models/validation_report.py` — ValidationReport dataclass (is_valid, errors, warnings, stats)
- `models/talk_metadata.py` — TalkMetadata dataclass (Phase 1 output)
- `models/paragraph_data.py` — ParagraphData + TalkParagraphs dataclasses (Phase 2 output)
- `models/citation_data.py` — CitationData + TalkCitations dataclasses (Phase 3 output)
- `models/footnote_data.py` — FootnoteData + TalkFootnotes dataclasses (Phase 4 output)

### Configuration
- `config/pipeline_config.py` — CHROMADB_PATH and other pipeline constants live here

### Existing Phase Patterns
- `extractors/phase5_validation.py` — Reference for extractor module structure and logging conventions
- `extractors/pipeline.py` — process_talk_pipeline() orchestrates Phases 2–4; Phase 6 integrates at the buffer-flush level

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config/pipeline_config.py` — Add CHROMADB_PATH constant here (consistent with other pipeline constants)
- `extractors/pipeline.py` — Shows how phases compose; Phase 6 sits outside this function, called when buffer flushes
- `models/*.py` — All five dataclasses are the direct input to Phase 6; planner must read all of them for field lists

### Established Patterns
- `logger = logging.getLogger(__name__)` — logging standard across all extractors
- No `logging.basicConfig` in extractor modules
- Typed dataclasses with `@dataclass` — Phase 6 module follows same pattern
- Pure functions where possible; side effects (ChromaDB writes) isolated to insertion layer
- `encoding='utf-8'` on all file I/O

### Integration Points
- `extractors/phase6_chromadb_loader.py` — new file to create; follows Phase 1–5 naming convention
- `config/pipeline_config.py` — add `CHROMADB_PATH` constant
- Buffer/flush logic lives in the orchestrator (Phase 6, Milestone 1) — Phase 6 loader receives a list of validated bundles, not a streaming loop

### No existing ChromaDB code
No `chromadb` imports exist yet in the codebase. Phase 6 is the first consumer.

</code_context>

<specifics>
## Specific Ideas

- talk_preview fallback is intentional: ~4,006 of 7,659 talks have previews from the Church API cache. Older talks may lack them. Embedding quality for those talks will be lower but not broken.
- Annotation handling is a three-way split: exclude from paragraphs, fold text into talk metadata, keep citations in citations collection. The paragraph_id on annotation-sourced citations remains valid (it points to a real paragraph even though that paragraph isn't embedded).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-chromadb-loader*
*Context gathered: 2026-03-24*
