# Phase 10: Tools & Normalization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 10 — Tools & Normalization

---

## Area 1: Search Result Shape

**Q: What fields should appear in each search result?**
Options: Snippet + key metadata / Snippet only / Snippet + talk_id only
**Selected:** Snippet + key metadata (snippet, speaker_name, title, conference_year, conference_month, talk_id)

**Q: How should relevance/distance scores be handled?**
Options: Omit scores / Human-readable tier / Include raw score
User requested trade-off analysis before deciding.
- Raw score: useful for weak-match signal, but ChromaDB distance is hard to interpret in absolute terms; Claude may over-anchor on number
- Human-readable tier: qualitative (high/medium/low) but requires per-collection threshold calibration
- Omit: clean output, rely on semantic judgment — add filtering later if needed
**Selected:** Omit scores

**Q: Should paragraph search results include speaker/title/year via a secondary talk lookup?**
User raised design oversight: paragraph records don't store speaker_name, title, conference_year, conference_month.
User proposed addressing this via a gap phase before Phase 10 rather than a secondary lookup at query time.
**Selected:** Fix via gap phase (paragraph metadata enrichment). Agreed result shape: snippet + speaker_name + title + conference_year + conference_month + talk_id.

**Q: Should talk_id be included?**
User challenged: could speaker/title/conference metadata filters identify a talk without an ID.
Analysis: metadata filters have ambiguity risk (multiple talks per speaker per conference). Disambiguation flow: search(collection="talks") returns candidates with talk_ids → user picks → get_talk(talk_id). talk_id makes this deterministic.
**Selected:** Yes — include talk_id

---

## Area 2: Speaker Normalization

**Q: How should the server resolve informal speaker names?**
Options: ChromaDB query at startup / Hardcoded lookup dict / Runtime ChromaDB query
User proposal: offload to Claude — LLMs know canonical names, no server-side normalization needed.
Discussion: Claude handles well-known GAs correctly. Risk: ChromaDB exact-match filter fails if Claude's name varies from DB string (e.g., missing middle initial). Mitigation: case-insensitive contains match.
**Selected:** Claude resolves canonical name + server does case-insensitive contains match. No lookup tables.

---

## Area 3: get_talk Format

**Q: How should get_talk structure returned talk content?**
Options: Header + body / Paragraphs only / Structured JSON-style
**Selected:** Header + body — speaker, title, conference month/year, session — followed by paragraphs joined in narrative order.

---

## Area 4: Default Collection

**Q: When collection is omitted from search, what's the default?**
User raised: should there be separate tools per collection rather than one tool with a parameter?
Analysis: separate tools multiply token overhead from descriptions — conflicts with "minimal token overhead" requirement. Single tool with optional collection parameter keeps descriptions tight; Claude selects collection based on query intent.
**Selected:** Single search tool, default collection = paragraphs. Claude passes collection="talks" for discovery queries.

---

## Deferred

- Gap phase for paragraph metadata enrichment flagged as required before Phase 10 execution. User initiated — noted in CONTEXT.md deferred section with suggestion to use `/gsd:insert-phase`.
