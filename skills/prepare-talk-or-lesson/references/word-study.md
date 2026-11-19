# A word study for a talk or lesson

Use this when the user's message turns on one word (grace, meek, endure, remember) and seeing how the scriptures
use that word would give them something to say. Do it with them, a step at a time, and keep it to what serves the
talk: a word study is a source for one point, not the talk itself.

## Finding the word in the scriptures

1. `search(query="<the word>", collection="scripture_verses", alpha=0.0)` finds verses containing it. Narrow with
   `volume` ("Book of Mormon", "New Testament") or `book` when the user wants one book's usage. Up to 20 rows a page (`limit`),
   `offset` for more.
2. Keyword search matches whole words, with no stemming: "endure" misses "endureth", "endured" and "enduring", and
   "meek" misses "meekness". Search the forms the KJV uses, one at a time, and say which forms you searched.
3. `total` is the number of verses that pass the filters (the whole volume, or the whole scriptures), not the number
   containing the word. Do not report it as a count of uses; describe what the pages you read show instead.

## Reading what the uses show

- Pick a handful of verses with the user and read each with `get_verse`, with the verses around it, before saying
  what the word means there.
- Footnotes on the word sometimes give the Hebrew or Greek sense, an alternate reading, or another verse that uses
  the word; bring those up, quoting the footnote as returned. If no footnote speaks to it, do not supply an original
  language meaning from memory as if the scriptures' notes gave it; if you add one from your own knowledge, say so.
- Look for what the uses have in common and where they differ: who uses the word, about what, what it is paired or
  contrasted with. Ask the user what they notice before you summarise.

## How speakers have used it

`search` on `paragraphs` with the word and a short phrase of the idea (at the default alpha) finds conference passages
that dwell on it; `group_by_talk=true` spreads them across talks. Quote them as returned, with speaker, title, month
and year, and read the talk with `get_talk` before saying how the speaker used the word.

## Bringing it back to the talk

End with one or two sentences the user could build on, in their words: ask what in the study struck them and how it
bears on their message. Do not write the point for them until their notes for it exist.
