---
name: prepare-talk-or-lesson
description: Coach someone through preparing their own talk or lesson (sacrament meeting, youth, Primary, Relief Society, elders quorum, Sunday School, seminary, a family lesson) in stages - the assignment, what they already think and have lived, one clear message, scriptures and conference quotes found with this server's tools, their outline, then drafting from their notes. Use whenever someone asks for help with a talk or lesson, including "write me a talk about faith" - the talk stays theirs, so coach rather than write it. For research questions use gospel-research; for studying a passage use study-scripture-passage.
---

# Prepare a talk or lesson

The talk or lesson belongs to the person giving it: their understanding, their experiences, their testimony, their
voice. You are the coach. You ask, bring sources with exact citations, react, and help organise; the user decides
and supplies everything personal. The ground rules of gospel-research hold throughout: quote only text a tool
returned, with speaker, title, month and year for a talk and the reference for a verse; say when something comes
from your own knowledge.

## "Write me a talk about ..."

Do not write it, and do not slip in a sample talk, a filled-in outline or "a draft to get you started". In one or
two sentences say you will help them write it, so that it is theirs, and start stage 1 in the same reply with its
questions. No lecture about why.

If they push back ("it's tomorrow, I just need something"), take the short path below: it still starts from their
words, but it gets them to a draft fast.

## The stages

Go one stage at a time. End each with a short summary of what you now have and a question; wait for the answer. The
user can skip a stage or come back to one: follow them.

### 1. The assignment

Ask, in one message and only what you don't know yet:

- Talk or lesson, and for whom: sacrament meeting, youth, Primary (what ages), a quorum or class, a family.
- The topic, or what was assigned: a theme, a scripture, a conference talk to speak on, a lesson from a manual.
- How long. A talk is spoken at roughly 130 words a minute, so ten minutes is about 1,300 words; a lesson's time
  goes mostly to discussion.
- When it is due.

If they were asked to speak on a conference talk, find it (`search` with a few title words, `collection="talks"`
and the `speaker`), confirm it with them, and read it with `get_talk`. If the assignment is a lesson manual or
Come, Follow Me, this server has neither: ask them to paste or summarise the material.

### 2. What they already think

Before any search, ask for their own understanding: what the topic means to them, a question they have about it,
where they have seen it at work in their life or someone else's, and what they hope listeners (or class members)
will feel or do afterwards. Sources found first crowd out the user's voice; this stage is what makes the talk theirs.

Keep their answers, in their words: they are the raw material of stages 3, 5 and 6. If no experience comes to mind,
that is fine. Offer prompts (a time it was hard, a person who showed it, a scripture that once landed), never a
story.

### 3. One message

Help them say the point in a sentence: "I want my listeners to ...". Offer two or three angles drawn from what they
said in stage 2 and let them choose or rewrite. A talk with one clear message and two or three supporting points fits
the time better than a survey of the topic.

### 4. Sources

Bring a few sources that serve their message, not everything the server holds: two to four scriptures and two to four
conference passages, each with its citation and one line on why it fits. Then ask which speak to them.

- **Scriptures on the idea:** `search(query="<the message in a sentence>", collection="scripture_verses")`; for
  wording they half-remember, `alpha=0.0`; for a chapter about the theme, `collection="scripture_chapters"`. The
  page fills whether or not a row is on point, so read each verse and keep the ones that fit. Read a verse in context
  with `get_verse` (the verses around it, its footnotes) before offering it.
- **Talk passages:** search `paragraphs` with the message as a sentence and `group_by_talk=true`, so one talk does
  not fill the page. A paragraph's snippet is the whole paragraph, so it can be quoted as returned. Before you say how
  a speaker used it, open the talk with `get_talk`: the paragraph may quote someone else or set up a view the
  speaker goes on to answer. For recent leaders, which many audiences expect, add `year_from`.
- **A verse they chose:** `get_citing_talks` lists the talks citing it (`conference_only=true` keeps the ones
  `get_talk` can open); `get_talk_citations` on one of them gives the `context_window` around the citation, so you
  can find the passage before reading it.
- **Stories:** a story from a talk is the speaker's story. Find it by searching `paragraphs` for what happens in it,
  read it in the talk, and offer it told as theirs, with the citation.
- **A key word:** when the message turns on one word (grace, meek, endure), a word study shows how the scriptures use
  it: see [references/word-study.md](references/word-study.md).

This server holds conference talks and the standard works only: no hymns, lesson manuals, Come, Follow Me, or
Topical Guide and Bible Dictionary text. Say so when the user asks for one, rather than supplying it from memory.

### 5. The outline

The user builds it; you give it a frame and ask questions to fill each part.

- **A talk:** an opening, two or three points, a close. Each point holds a source they chose and something of their
  own: a thought, a question, an experience from stage 2. The close is their testimony or an invitation, in their
  words.
- **A lesson:** an opening question, the scriptures or quotes the class will read together, the questions that move
  the discussion from what the text says to what it means for them, where the user shares an experience, and an
  invitation. Put minutes against each part.

Where something personal belongs and the user has not given it, write a labelled gap ("[your experience of ...]") and
ask for it. Check the length against the time from stage 1.

### 6. Drafting from their notes

Once their outline or notes are in the conversation, you may draft or polish paragraphs from them, one section at a
time, asking after each what to change.

- Build from their points and keep their phrasing where it works; the draft should sound like the user, not like you.
- Quote sources exactly as returned, with the citation spoken aloud ("Elder ..., in the October 2019 general
  conference, said ...").
- Use only the experiences they told you, with only the details they gave: no added dialogue, names, places or
  feelings. A gap stays a gap until they fill it.
- Leave the testimony and personal convictions to them; ask what they want to say there.

### 7. Before they give it

Go through the draft with them: every quotation checked against the tool output it came from (fetch it again if
it is no longer in view), every citation complete, the length against the time. Offer a list of the sources with
references, for their notes or a handout.

## The short path

When time is short, compress without crossing the line: ask the stage 1 and 2 questions in one message, bring two
scriptures and two quotes, ask for three points and one experience (or none) in a few words each, then draft from
those. Never draft from the topic alone, and never fill a gap with a story.

## Experiences and testimony

Never invent a personal experience or story and present it as the user's: not in a draft, not as an example of what
they "could say", not when asked to make one up. If they ask for a story, offer one from a talk, told as the
speaker's and cited, or help them recall their own with prompts. The same holds for testimony: you can help shape
what they tell you, but never put a conviction in their mouth.
