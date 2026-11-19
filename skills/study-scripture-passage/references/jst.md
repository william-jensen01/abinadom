# The Joseph Smith Translation in a passage study

Read this when the passage is in the Bible and the JST matters to it: `include_jst=true` brought back JST text, the
user asked about the JST, or the passage is in Genesis 1–6.

## What `include_jst=true` returns

Each verse the Church links to the JST gets a `jst` list of entries, each a `reference` and its `text`. Two kinds
arrive in the same list:

- **A JST footnote's verse**: one entry per JST verse the footnote names, with that verse's full text.
- **An appendix passage**: one entry for a whole JST passage from the appendix that the Church compares with this
  verse, its verses joined into one text under the passage's reference ("JST Gen. 14:25–40").

An appendix passage's text appears in full only on the first verse of the response it covers. The later verses it
covers carry a one-line pointer ("See ... under ...") instead. So:

- Do not tell the user that a later verse has no JST, or a different one: it shares the passage shown above it.
- If you read the chapter in several calls, the passage's full text comes back again on the first covered verse of
  each call. Show it once.

## Comparing the wordings

Put the KJV verse and its JST text side by side and say what the JST adds, removes or rewords. Short changes
(a word, a clause) go verse by verse inside step 2. A long passage that rewrites or adds whole verses deserves its
own pass:

1. Read the KJV verses it compares with: `get_verse(book="Genesis", chapter=14, verse_start=18, verse_end=20,
   include_jst=true)`.
2. Read the JST passage in its own numbering: `get_verse(book="JST Genesis", chapter=14, verse_start=25,
   verse_end=40)`. The JST numbers its chapters and verses its own way, so JST Gen. 14:25 is not KJV Gen. 14:25;
   cite JST verses by their JST reference. These rows carry the text only: no footnotes, and an empty chapter
   summary.
3. Walk through the JST passage a few verses at a time, as in step 2, marking what has no counterpart in the KJV.

`numbering="jst"` does the same as a "JST ..." book name. JST numbering covers the Old and New Testaments only.
`get_chapter_overview` and `find_cross_references` take standard chapters and verses only: run them on the KJV verses.

## Genesis 1–6 and the Book of Moses

The JST of the opening chapters of Genesis is published as the Book of Moses. On Genesis 1:1–6:13,
`include_jst=true` brings the whole appendix passage JST Gen. 1:1–8:18, hundreds of verses, in full on the first
verse it covers (after any JST footnote verse), with pointers on the rest. Do not show that block. Many footnotes on
those verses point into the Book of Moses: take those references from the footnotes and read them with
`get_verse(book="Moses", ...)` as the JST reading of the verse. Pass `include_jst=true` on these chapters only when
you want a JST footnote's own verse, and then use that entry, not the passage.

The talks step does not follow that passage; it goes through the Moses footnotes instead: on those verses `get_citing_talks` also lists talks that cite the linked Moses
verse. A talk found only that way has `via` naming the Moses verse: tell the user it cites Moses, not Genesis.

## Talks citing the JST

`get_citing_talks` on a KJV verse already includes talks that cite the JST verses its footnotes name or a JST
passage compared with it. A talk found only through a compared passage (or a Moses verse) has `via` naming it; one
found through a footnote's JST verse has none, but its `cites` show the JST reference. To list only the talks
citing the JST text itself, pass the JST reference: `get_citing_talks(book="JST Genesis", chapter=14, verse_start=25,
verse_end=40)`.
