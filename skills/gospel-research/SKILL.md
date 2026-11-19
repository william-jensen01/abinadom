---
name: gospel-research
description: How to research General Conference talks and the standard works with this server's tools. Use for any question about what a speaker taught or said, whether a quote is genuine, how a teaching was presented across speakers and decades, studying one talk or one speaker, or what a scripture says. For studying a scripture passage step by step use study-scripture-passage; for preparing a talk or lesson use prepare-talk-or-lesson.
---

# Gospel research

The server holds the General Conference talks since 1942 and the standard works (verses, chapter summaries,
footnotes, the JST). Every answer about what a talk or a scripture says starts from a tool call.

## Ground rules

- **Database before memory.** Call a tool before saying what a talk or verse says. If you then add something from
  your own knowledge, say so in so many words ("from my general knowledge, not the database").
- **Quote only returned text.** Quotation marks go around text a tool returned in this conversation, nothing else.
  Give speaker, title, and month and year with every quote from a talk.
- **Read before you characterise.** A paragraph snippet is one paragraph. Before you state what a talk argues, or
  that a speaker held a view, read the talk with `get_talk`.
- **A result is not a match.** `search` with a query and any alpha above 0 fills the page (up to `limit`) whenever
  enough objects pass the filters, relevant or not, and its `total` is how many objects pass the filters, not how
  many match the query. Decide relevance by reading the snippets.
- **Report gaps.** An empty or off-topic result is a finding: say what you searched and that it found nothing,
  rather than filling the gap from memory.
- **Three voices.** Keep apart what the scripture says, what a speaker taught, and your own synthesis; make clear
  which one each statement is.

## Which role

- **Research assistant**, when the user wants something found (a quote, a talk, who said what): search widely,
  report sources exactly, keep commentary short.
- **Discussion partner**, when the user is thinking through an idea or doctrine: bring talks and verses that bear on
  it, show where speakers agree, differ or shift emphasis over time, and ask what the user makes of it.
- **Study guide**, when the user wants to understand one talk or teaching: retrieve it, walk through it in order,
  point to the key passages, and check in before going deeper.

Conversations move between roles; follow the user. For a step-by-step study of a scripture passage, switch to the
study-scripture-passage skill; for helping someone prepare their own talk or lesson, to prepare-talk-or-lesson.

## Choosing a tool

| You need | Use | Not |
|---|---|---|
| Wording or an idea inside talks | `search` on `paragraphs` | `collection="talks"`: a talk is indexed by its title, preview and topics, never its text, and before about 1971 by its title alone |
| Every talk by a speaker, or how many | `search(query="", speaker="...", collection="talks", sort_by="date_asc")`: `total` is the exact count, `offset` pages | `corpus_stats`, which has no filters |
| Who cited a verse, with the sentence around the citation | `find_by_scripture` | |
| Every talk citing a verse, with a count | `get_citing_talks` | `find_by_scripture`, which stops at `limit` hits |
| The scriptures one talk uses, in order | `get_talk_citations` | |
| A talk's full text | `get_talk` | |
| A verse's text, footnotes, JST | `get_verse` | quoting a verse from memory |
| What a chapter is about | `get_chapter_overview` | |
| Verses linked to a verse by footnotes | `find_cross_references` | |
| Talks per year or per season, corpus sizes | `corpus_stats` | |

Traps that the descriptions do not spell out:

- `find_by_scripture` compares the book with the stored full name, so an abbreviation such as "1 Ne." misses the
  citations stored as "1 Nephi". It returns
  one row per citation, so a talk citing the verse twice shows twice, in no particular order, with no `total` and
  no paging. It reads only conference talks. Its rows carry `speaker_name` and `context_window`; `get_citing_talks`
  rows carry neither, so pair them: `get_citing_talks` for the complete list, then `get_talk` (whose header names the
  speaker) for the ones that matter. `get_citing_talks` also lists talks outside General Conference; `get_talk` opens
  only rows with `get_talk_available` true, so say so rather than describing the others.
- `corpus_stats` on the talk collections fetches Weaviate's default 100 groups before sorting by count and cutting to `limit` (20 by
  default). `group_by="conference_year"` gives the 20 busiest years unless you pass `limit=100`, then sort the years
  yourself. `group_by="speaker_name"` has more speakers than that, so the list is incomplete: never read a speaker's
  absence from it as zero talks.
- `speaker` is a substring filter: a surname such as "Smith" matches many speakers. Check `speaker_name` on the rows
  before attributing anything, and before reporting a browse `total` as one person's count.
- `sort_by` works only with an empty query; with a query it is ignored. `group_by_talk` needs a query, works only on
  `paragraphs`, and ranks by meaning alone (alpha does not apply), so it suits themes, not exact words or names.
- With the default hybrid search, `relevance` ranks hits within one call and cannot be compared between calls. With
  `alpha=1.0` it is a vector certainty, which can be compared across calls with the same query.
- If `search_mode` says the embedding service is unavailable, results are keyword-only: tell the user, and expect
  weaker results for ideas phrased differently from the talks.

## Checking a quote

When the user asks whether a speaker said something:

1. Search for the words on `paragraphs` with `alpha=0.0` and `query_properties=["text"]`, without a speaker filter
   first: the attribution may be wrong. Keyword search returns paragraphs sharing any of the words, so a hit proves
   nothing until its snippet contains the wording. If the full sentence finds nothing close, retry with its five to
   eight most distinctive words, then with a near paraphrase at the default alpha.
2. When a paragraph has the wording, read it in the talk with `get_talk`: the speaker may be quoting someone else
   (an earlier leader, a hymn, a scripture). Report who the words belong to.
3. Report speaker, title, month and year, and the passage as the talk gives it, noting any difference from the
   wording the user brought.
4. If nothing matches, say exactly that: the wording was not found in General Conference talks since 1942. Never call
   the quote fake or misattributed; it may come from a book, a devotional, an earlier talk, or another wording.

## A question across speakers and decades

1. Search `paragraphs` one decade at a time (`year_from` / `year_to`), so recent talks do not crowd out the early
   ones. Each window returns a full page regardless, so judge it by reading the snippets; to compare how strongly
   windows speak to the idea, use `alpha=1.0` and compare certainties. To say how many talks each window holds, sum
   the years from `corpus_stats(collection="talks", group_by="conference_year", limit=100)`.
2. Use `group_by_talk=true` within a window to see the idea across several talks rather than one talk's paragraphs.
3. Read the strongest talk in each window with `get_talk` before saying what it teaches.
4. Present a timeline, with the speaker and the month and year by every point; then say what stayed, what changed,
   and what the evidence cannot show. A change in vocabulary is not by itself a change in teaching.
5. Do not filter on topics for the early decades: talks before about 1971 have none.
6. To keep a speaker's view apart from scripture, take the verses the talk relies on from `get_talk_citations`, read
   them with `get_verse`, and say where the talk goes beyond the text.

## Studying one talk or one speaker

- **One talk.** `get_talk`; outline it in your own words (opening, main movements, close) with a short quote at each
  turn. Then `get_talk_citations` for the scriptures it stands on, in order; read the one or two that carry the
  argument with `get_verse`. Ask the user where to go deeper.
- **One speaker.** Browse their talks oldest first (the table above) and confirm `speaker_name` on every row. For a
  theme, search `paragraphs` with `speaker` and a query, with `group_by_talk=true`. A speaker's favourite scriptures
  come from `get_talk_citations` on talks you have read, not from memory. Say which talks you read and how many
  you did not.
