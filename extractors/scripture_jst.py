"""The JST (Joseph Smith Translation): core.db's J/F rows and the Church's JST appendix pages (SPEC-v2 §5).

- `read_core_jst`: every core.db `Flag IN ('J','F')` row, read only through `db.Database`. The build stores them in
  `jst_verse` in JST numbering, text decoded and otherwise unchanged.
- `parse_appendix`: the passages of a JST appendix page (`/scriptures/jst/jst-gen/9`), one `<section>` each with a
  heading "JST, Genesis 9:4–6. Compare <a>Genesis 8:20–22</a>". The build stores them in `jst_passage`, with the
  heading's links (the KJV range after "Compare", plus "similar changes …" and "see also" links) in
  `jst_passage_ref`. Appendix verses are never `verse` rows, and passages never `footnote_ref` rows.

The `jst` footnotes on KJV verses are parsed with the other footnotes (extractors/scripture_page.py).
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from db import CORE_DB_PATH, Database
from extractors.scripture_page import Ref, collapse, plain_text, resolve_href, soup


def read_core_jst(core_db_path: Optional[str] = None) -> Tuple[List[dict], int]:
    """(every core.db J/F row as {ID, BookID, Chapter, Verse, Flag, Text} ordered by ID, core.db's own count)."""
    path = core_db_path or CORE_DB_PATH
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise FileNotFoundError(f"PREREQUISITE: {path} is missing or empty; build it first "
                                f"(`pipenv run python scripts/build.py --version 55`)")
    db = Database(path, timeout=120)
    try:
        rows = db.select("SELECT ID, BookID, Chapter, Verse, Flag, Text FROM scripture "
                         "WHERE Flag IN ('J','F') ORDER BY ID")
        return rows, db.scalar("SELECT COUNT(*) FROM scripture WHERE Flag IN ('J','F')")
    finally:
        db.close()


def parse_verse_spec(spec: str) -> Optional[List[Tuple[int, int, int, int]]]:
    """"9:4–6" -> [(9,4,9,6)]; "4:1, 5–6, 8–9" -> [(4,1,4,1),(4,5,4,6),(4,8,4,9)]; "1:1–8:18" -> [(1,1,8,18)].

    (chapter, verse, chapter_end, verse_end) in JST numbering. A bare number after a comma continues the chapter.
    None when a token does not parse or a range runs backwards.
    """
    out, chapter = [], None
    for token in collapse(spec).rstrip(".").split(","):
        m = re.fullmatch(r"(?:(\d+):)?(\d+)(?:\s*[–—-]\s*(?:(\d+):)?(\d+))?", token.strip())
        if not m or (m.group(1) is None and chapter is None) or (m.group(3) and not m.group(1)):
            return None
        chapter = int(m.group(1) or chapter)
        end_chapter = int(m.group(3) or chapter)
        out.append((chapter, int(m.group(2)), end_chapter, int(m.group(4) or m.group(2))))
        chapter = end_chapter
    return out if out and all((c1, v1) <= (c2, v2) for c1, v1, c2, v2 in out) else None


@dataclass
class Passage:
    section_id: Optional[str]
    anchor_aid: Optional[str]
    title: str                            # "JST, Genesis 9:4–6."
    verse_spec: Optional[str]             # "9:4–6"
    ranges: Optional[list]                # parse_verse_spec(verse_spec)
    intro: Optional[str]
    paragraphs: List[int]                 # verse numbers of the <p class="verse"> printed under the heading
    refs: List[Tuple[str, Ref, Optional[int]]] = field(default_factory=list)  # (rel, target, chapter_end)


def heading_refs(h2) -> List[Tuple[str, Ref, Optional[int]]]:
    """The links of a heading, one per range. Links after "Compare" are the KJV range (rel 'compare'); after
    "similar change(s)" they are 'similar', after "see also" 'see-also'. A `span=1:1-6:13` href crosses chapters."""
    out, rel = [], "compare"
    for node in h2.descendants:
        if isinstance(node, str):
            if node.parent.name != "a":
                low = node.lower()
                rel = ("similar" if "similar change" in low else "see-also" if "see also" in low
                       else "compare" if "compare" in low else rel)
            continue
        if node.name != "a" or not node.get("href"):
            continue
        span = re.fullmatch(r"(\d+):(\d+)-(\d+):(\d+)", (parse_qs(urlsplit(node["href"]).query).get("span") or [""])[0])
        targets = resolve_href(node["href"])
        for r in targets:
            r.label = plain_text(node)
            if span:
                c1, v1, c2, v2 = map(int, span.groups())
                r.chapter, r.verse_start, r.verse_end = c1, v1, v2
            out.append((rel, r, int(span.group(3)) if span else None))
    return out


def parse_appendix(uri: str, data: dict) -> List[Passage]:
    """The passages of one appendix page, in page order: each `<h2>` whose `<strong>` starts "JST,"."""
    passages = []
    for h2 in soup((data.get("content") or {}).get("body")).find_all("h2"):
        title = plain_text(h2.find("strong")) if h2.find("strong") else ""
        if not title.startswith("JST,"):
            continue
        section = h2.find_parent("section")
        m = re.search(r"\d+:\d+", title)
        spec = title[m.start():].rstrip(". ").strip() if m else None
        intro = section.select_one("p.study-intro") if section else None
        paragraphs = [int(p["id"][1:]) for p in (section.select("p.verse") if section else [])
                      if re.fullmatch(r"p\d+", p.get("id") or "")]
        passages.append(Passage(section.get("id") if section else None, h2.get("data-aid"), title, spec,
                                parse_verse_spec(spec) if spec else None, plain_text(intro) if intro else None,
                                paragraphs, heading_refs(h2)))
    return passages
