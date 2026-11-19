---
name: study-scripture-passage
description: Walk a user through studying a scripture passage step by step with this server's tools, checking in between steps - the chapter around it, the verses with their footnotes and the Joseph Smith Translation, the cross references, then the General Conference talks that cite it and one talk read in context. Use when the user asks to study, read closely or dig into a chapter, a range of verses or a single verse ("Help me study Alma 32:21-43"). For other questions about talks, speakers or quotes use gospel-research.
---

# Study a scripture passage

A guided study, one step at a time: the user reads and reacts, you bring the next layer. The ground rules of
gospel-research hold throughout: scripture text comes from `get_verse`, never from memory; quotation marks go only
around returned text; keep apart what the verse says, what a speaker taught about it, and your own reading.

## Before the first step

- **Settle the passage.** Get book, chapter and verses. If the user only remembers wording, find the verse with
  `search(query="...", collection="scripture_verses", alpha=0.0)`; for a topic ("the chapter about the seed"),
  `collection="scripture_chapters"`. Confirm the reference before going on.
- **Ask what they are after** if it is not plain: their own study, a lesson, one question about the passage. It
  sets how deep each step goes and which steps to skip.
- **Say the plan in one line** ("we'll look at the chapter, read the verses with their footnotes, follow the cross
  references, then see which talks use it"), so the user can steer before you start.

Book names: `get_chapter_overview`, `get_verse`, `find_cross_references` and `get_citing_talks` take abbreviations
("1 Ne.", "D&C"; a D&C `chapter` is the section number). One call covers one chapter, so a passage that crosses a chapter break takes a call per chapter.

## The steps

End every step the same way: two to four sentences on what it showed, then a question with concrete choices (a
verse to slow down on, the next step, or stop). Wait for the answer. Never run the whole flow in one turn.

### 1. The chapter

`get_chapter_overview(book, chapter)`. Tell the user where the passage sits: the chapter's summary and intro, its
length, and what the passage answers or turns on. `top_cross_references` lists the scriptures the chapter's
footnotes point to most often (at most ten, no JST and no study helps): name the two or three that stand out as
threads to follow later, without saying what they say until you have read them.

For a single verse, skip this call: `get_verse` returns the `chapter_summary`, which is enough orientation.

### 2. The verses

`get_verse(book, chapter, verse_start, verse_end)`, a few verses at a time: a sense unit of roughly three to eight
verses, split where the chapter summary's sentences split. Alma 32:21–43 is several calls, not one.

- Give the verses' text as returned, with their references, then ask the user what they notice before you explain.
- Footnotes come by default. Do not read them all out. Bring up the ones that change the reading: a note on the Hebrew
  or Greek, an alternate reading, an explanation of a word or custom, or a cross reference the user is likely to know.
  Pass `include_footnotes=false` for a quick reread of verses already covered.
- **JST**: for a Bible passage, pass `include_jst=true`. The Book of Mormon, D&C and Pearl of Great Price have no
  JST. When a verse comes back with JST text, put the two wordings side by side and point to what the JST adds or
  changes. Long JST passages, Genesis 1–6 and JST-heavy chapters have their own handling: see
  [references/jst.md](references/jst.md).
- To see which verses of the passage talks lean on most, add `include_citing_talks=true`: with more than one verse,
  `citing_talks_by_verse` gives a count per verse. It is a good guide to where to slow down, and it sets up step 5.

### 3. Cross references

Pick one to three key verses with the user, then `find_cross_references(book, chapter, verse)` for each.

- `outgoing` holds the scripture links of that verse's footnotes, already seen in step 2. The new information is
  `incoming`: the other verses whose footnotes point here. A footnote marked `whole_chapter` names the whole
  chapter, not this verse, so it is a looser tie; put verse-specific links first.
- Read a target with `get_verse` (with `include_footnotes=false` to keep it short) before saying anything about it;
  then say how it bears on the passage: the same image, a fulfilment, an answer to a question the passage raises.
- It is one hop. Go further only when the user wants to follow a thread: call it again on the target verse.

### 4. Study helps

Footnotes also name Topical Guide and Bible Dictionary entries: refs whose target is the entry's name, such as
"tg/hope" (a Bible Dictionary entry starts "bd/"). This server has no Topical Guide or Bible Dictionary text, so this step is short today:
list the entries the passage's footnotes name, as topics the user can look up, and do not summarise an entry from
memory as if the server had returned it. If the user wants a topic followed through the talks, search `paragraphs` for
it.

### 5. Talks that cite it

`get_citing_talks(book, chapter, verse_start, verse_end)` lists them, newest first, with `total` for the whole
count. Tell the user the total before listing any, and offer a direction: the newest, the earliest, or the ones
citing a particular verse.

- `order="oldest"` for the earliest uses; `next_offset` for the next page; `conference_only=true` to keep only the
  talks you can open with `get_talk`. The others (titles and dates only) cannot be read here: say so rather than
  describing them.
- A row's `cites` shows what the talk cites. A talk citing one verse of the passage is a better source for that
  verse than one citing the whole chapter in passing. A row with `via` was found only through a JST passage or a Book of
  Moses verse linked to the passage, not the passage itself: say so when you use it.
- Rows carry no speaker; the speaker comes from `get_talk`'s header. Do not name a speaker for a talk you have not
  opened.
- The counts follow formal citations only. A talk can quote or allude to a verse without citing it; to find those,
  search `paragraphs` for the verse's key phrase and read the snippets.

### 6. A talk in context

Choose one talk with the user among those with `get_talk_available` true (a recent one, an early one, or one that
cites exactly their verse).

1. `get_talk_citations(talk_id)` gives the talk's scriptures in order; the rows for the passage carry
   `context_window`, the words around the citation, and show what other verses the speaker set beside it.
2. `get_talk(talk_id)` gives the full text; find the passage by its context window and read the paragraphs around
   it, not only the citing sentence.
3. Tell the user how the speaker uses the verse (as proof, as an image, to answer a question, applied to a new
   situation), quoting the talk with speaker, title, month and year. Then compare it with what the verse said in
   step 2, and note where the talk goes beyond the text.

To see the words around the citation across several talks at once, with speakers, `find_by_scripture` gives one row per
citation with `speaker_name` and `context_window`. Pass the book's full name ("Alma", "1 Nephi"; abbreviations
miss), expect at most `limit` rows in no set order, and for the Doctrine and Covenants use the route above: it may
find nothing there.

## When to change the plan

- **A single verse:** skip step 1, read it with the verses on either side, spend the time on cross references and
  talks.
- **A whole chapter:** step 1, then read it in sections by the summary's divisions; use `citing_talks_by_verse` from
  a whole-chapter `get_verse(..., include_citing_talks=true)` to pick the verses for steps 3 and 5.
- **A JST-heavy passage:** see [references/jst.md](references/jst.md); the JST comparison becomes the centre of
  step 2.
- **The user asks for the talks first:** go to step 5, then come back to the text; a talk is easier to weigh once
  the verse has been read.
- **The user wants to stop or switch:** stop; offer a two-line summary of what you covered, with references.
