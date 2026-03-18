## Noise Audit

**ChromaDB metadata serves two purposes:** filtering queries and enriching results. If a field does neither, it's noise.

### TalkMetadata

| Field | Verdict | Reasoning |
|-------|---------|-----------|
| `talk_id` | **Keep** | Primary key, cross-collection joins |
| `speaker_id` | **Noise** | Numeric ID — `speaker_name` is the queryable version |
| `conference_id` | **Noise** | Numeric ID — `conference_year` + `conference_month` covers it |
| `title` | **Keep** | Searchable, result display |
| `speaker_name` | **Keep** | Filter by speaker |
| `conference_year` | **Keep** | Filter by year |
| `conference_month` | **Keep** | Filter by April/October |
| `conference_description` | **Keep** | Human-readable, result display |
| `talk_date` | **Keep** | Date filtering/sorting |
| `session_id` | **Noise** | Numeric — `session_description` covers it |
| `session_description` | **Keep** | Filter by session type |
| `session_abbr` | **Noise** | Redundant with `session_description` |
| `session_date` | **Noise** | Redundant with `talk_date` |
| `session_sequence` | **Noise** | Ordering within session — marginal |
| `talk_sequence` | **Noise** | Same |
| `url` | **Keep** | Link back to source |
| `uri_l`, `uri_gc` | **Noise** | Internal church URIs |
| `data_aid` | **Noise** | Internal identifier |
| `audio_url` | **Borderline** | Could link to audio from results |
| `video_low/med/high_url` | **Noise** | Three quality levels is excessive; at most keep one |
| `corpus` | **Noise** | Always "E" |
| `speaker_role_id` | **Noise** | Numeric, meaningless without lookup |
| `start_page_num`, `end_page_num` | **Noise** | Print edition pages |
| `extraction_timestamp` | **Noise** | Pipeline internal |
| `extraction_version` | **Noise** | Pipeline internal |

### ParagraphData

| Field | Verdict | Reasoning |
|-------|---------|-----------|
| `paragraph_id` | **Keep** | Primary key |
| `talk_id` | **Keep** | Foreign key |
| `paragraph_number` | **Keep** | Position in talk, ordering |
| `text` | **Keep** | The document being embedded |
| `text_raw` | **Noise** | Debug HTML — large, not searchable |
| `word_count` | **Borderline** | Could filter by length, but when would you? |
| `list_header` | **Noise** | Structural detail, not queryable |
| `list_item_index` | **Noise** | Same |
| `position_in_item` | **Noise** | Same |
| `has_scripture_citation` | **Keep** | Filter: "paragraphs with scripture references" |
| `has_footnote` | **Keep** | Filter: "paragraphs with footnotes" |
| `citation_count` | **Noise** | `has_scripture_citation` covers the boolean case; exact count is rarely useful as a filter |
| `footnote_count` | **Noise** | Same reasoning |
| `extraction_warnings` | **Noise** | Pipeline internal |

### CitationData

| Field | Verdict | Reasoning |
|-------|---------|-----------|
| `citation_id` | **Keep** | Primary key |
| `talk_id` | **Keep** | Foreign key |
| `paragraph_id` | **Keep** | Foreign key |
| `paragraph_number` | **Keep** | Ordering |
| `citation_text_raw` | **Keep** | Display text, result enrichment |
| `char_position` | **Noise** | Position within paragraph — not a search dimension |
| `char_end_position` | **Noise** | Same |
| `scripture_ref` | **Keep** | Normalized reference for display/filter |
| `book` | **Keep** | Filter by book |
| `book_abbr` | **Noise** | Redundant with `book` |
| `book_id` | **Noise** | Numeric, redundant with `book` |
| `chapter` | **Keep** | Filter by chapter |
| `verses` | **Keep** | Raw verse string for display |
| `verse_start` | **Keep** | Range filtering |
| `verse_end` | **Keep** | Range filtering |
| `verse_list` / `verse_list_str` | **Noise** | Expanded list doesn't help filtering; `verse_start`/`verse_end` covers range |
| `is_jst` | **Keep** | Meaningful filter |
| `citation_location` | **Keep** | Inline vs footnote filter |
| `parse_success` | **Noise** | Pipeline internal |
| `parse_source` | **Noise** | Pipeline internal |
| `parse_pattern` | **Noise** | Pipeline internal |
| `parse_confidence` | **Noise** | Pipeline internal |
| `context_before` | **Noise** | Redundant — `context_window` is the document |
| `context_after` | **Noise** | Same |
| `context_window` | **Keep** | The document being embedded |
| `extraction_warnings` | **Noise** | Pipeline internal |

### FootnoteData

| Field | Verdict | Reasoning |
|-------|---------|-----------|
| `footnote_id` | **Keep** | Primary key |
| `talk_id` | **Keep** | Foreign key |
| `paragraph_id` | **Keep** | Foreign key |
| `paragraph_number` | **Keep** | Ordering |
| `footnote_number` | **Keep** | Display, ordering within paragraph |
| `footnote_text_raw` | **Keep** | Content, result display |
| `char_position` | **Noise** | Position within paragraph |
| `context_before` | **Noise** | Redundant with context_window |
| `context_after` | **Noise** | Same |
| `context_window` | **Keep** | The document being embedded |
| `parse_success` | **Noise** | Pipeline internal |
| `extraction_warnings` | **Noise** | Pipeline internal |

---

## Summary

About **half** of the metadata fields across all models are noise for ChromaDB. The biggest categories:

1. **Pipeline internals** — parse_*, extraction_*, timestamps, versions
2. **Redundant IDs** — numeric IDs where human-readable names exist
3. **Positional data** — char_position, char_end_position
4. **Redundant text** — context_before/after (document is context_window), text_raw, book_abbr

**On `word_count`**: I'd call it borderline. "Find short paragraphs about X" isn't a real use case. Semantic search returns relevant results regardless of length. But it's a single int — cheap to keep. Your call.

**On `citation_count`/`footnote_count`**: The boolean flags already answer "does this paragraph have citations/footnotes?" The exact count as a filter predicate ("paragraphs with exactly 5 citations") is not a real query.

Should Phase 5 validation include flagging which fields should be stripped before ChromaDB insertion? Or should that be Phase 6's concern when it calls `to_chromadb_format()`?