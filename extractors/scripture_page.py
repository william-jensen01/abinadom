"""Parse Church API scripture pages (`type/content` JSON) into plain rows (SPEC-v2 §2, §4.2, §8).

Pure functions: no database, no network. scripts/build_scriptures.py stores what they return.

The page kind comes from the URI (docs/scriptures/AUDIT.md Q3). Chapter-like kinds (CHAPTER_KINDS) yield
header texts, verses and footnotes; `jst_appendix` pages yield footnotes only (their passages are parsed by
extractors/scripture_jst.py and are never verses); TOC pages yield a title only.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag

from config.scripture_books import BOOK_CROSSWALK

VOLUMES = ("ot", "nt", "bofm", "dc-testament", "pgp")
TOC_VOLUMES = VOLUMES + ("jst",)
CHAPTER_KINDS = ("chapter", "section", "front_matter", "declaration", "facsimile")  # pages that get a chapter row

# a JST verse named in a footnote's text: "JST Gen. 8:13 …", "JST 1 Cor. 14:2 …", "JST Gen. 8:23–24 …"
JST_TEXT_REF = re.compile(r"JST\s+((?:\d\s+)?[A-Z][A-Za-z]*\.?)\s+(\d+):(\d+)(?:\s*[–—-]\s*(\d+))?(?!\d)")
# core.db BookID of each Bible book, by cite abbreviation and by URI segment (the JST covers the OT and NT)
JST_BOOK_BY_CITE = {cite: core for (vol, _), (cite, core) in BOOK_CROSSWALK.items() if vol in ("ot", "nt")}
JST_BOOK_BY_SEGMENT = {seg: core for (vol, seg), (_, core) in BOOK_CROSSWALK.items() if vol in ("ot", "nt")}


def soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup or "", "html.parser")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def plain_text(node) -> str:
    """Clean text: no verse number, pilcrow, page break or footnote marker; italics and other markup flattened."""
    def walk(parent):
        for child in parent.children:
            if type(child) is NavigableString:
                yield str(child)
            elif isinstance(child, Tag):
                classes = set(child.get("class") or ())
                if classes & {"verse-number", "para-mark", "page-break"} or (child.name == "sup" and "marker" in classes):
                    continue
                if child.name == "br":
                    yield " "
                    continue
                yield from walk(child)
                if classes & {"line", "question", "answer"}:   # pieces that sit side by side with no space between
                    yield " "
    return collapse("".join(walk(node)))


# ---------------------------------------------------------------------------
# URIs
# ---------------------------------------------------------------------------

def segments(uri: str) -> List[str]:
    """['bofm', 'alma', '32'] for '/scriptures/bofm/alma/32'."""
    parts = [p for p in uri.split("/") if p]
    return parts[1:] if parts[:1] == ["scriptures"] else parts


def classify(uri: str) -> str:
    """Page kind from the URI, in the rule order of AUDIT.md Q3."""
    segs = segments(uri)
    if len(segs) <= 1:
        return "volume_toc"
    if segs[-1] == "_contents":
        return "book_toc"
    if segs[0] == "jst":
        return "jst_appendix"
    if segs[1] == "od":
        return "declaration"
    if segs[-1].startswith("fac-"):
        return "facsimile"
    if not segs[-1].isdigit():
        return "front_matter"
    return "section" if segs[0] == "dc-testament" else "chapter"


def book_uri(uri: str) -> Optional[str]:
    """The book a page belongs to: `/scriptures/ot/gen/1` and `…/gen/_contents` -> `/scriptures/ot/gen`;
    `/scriptures/pgp/abr/fac-1` -> `/scriptures/pgp/abr/fac` (the Facsimiles are a book of their own).
    None for volume-level pages and the JST appendix."""
    segs = segments(uri)
    if len(segs) != 3 or segs[0] == "jst":
        return None
    base = f"/scriptures/{segs[0]}/{segs[1]}"
    if segs[2] == "_contents" or segs[2].isdigit():
        return base
    m = re.fullmatch(r"([a-z]+)-\d+", segs[2])
    return f"{base}/{m.group(1)}" if m else None


def jst_book(uri: str) -> Optional[int]:
    """core.db BookID of a JST appendix URI: `/scriptures/jst/jst-gen/9` -> 101 (Genesis)."""
    segs = segments(uri or "")
    return JST_BOOK_BY_SEGMENT.get(segs[1].removeprefix("jst-")) if len(segs) > 1 and segs[0] == "jst" else None


def link_uri(href: str) -> Optional[str]:
    """'/study/scriptures/ot/gen/1?lang=eng' -> '/scriptures/ot/gen/1'; None outside /scriptures/."""
    path = urlsplit(href or "").path.removeprefix("/study")
    return path.rstrip("/") if path.startswith("/scriptures/") else None


# ---------------------------------------------------------------------------
# tables of contents
# ---------------------------------------------------------------------------

def toc_links(data: dict) -> List[str]:
    """Page URIs a TOC body links to, in order, without duplicates, within the six TOC volumes."""
    out = []
    for uri in re.findall(r'href="/study(/scriptures/[^"?#]+)', (data.get("content") or {}).get("body") or ""):
        uri = uri.rstrip("/")
        if segments(uri)[0] in TOC_VOLUMES and uri not in out:
            out.append(uri)
    return out


def toc_groups(data: dict) -> dict:
    """uri -> titles of the TOC groups (`<li><h2>`) holding its link, innermost first: for `pgp/abr/fac-1`,
    ["Facsimiles", "Abraham"]. They name the books."""
    groups = {}
    for a in soup((data.get("content") or {}).get("body")).find_all("a", href=True):
        h2s = [h for h in (li.find("h2", recursive=False) for li in a.find_parents("li")) if h]
        groups.setdefault(link_uri(a["href"]), [collapse((h.find("p", class_="title") or h).get_text()) for h in h2s])
    return groups


def contents_links(data: dict) -> List[str]:
    """The pages a book's `_contents` page lists, in order."""
    out = []
    for a in soup((data.get("content") or {}).get("body")).find_all("a", href=True):
        uri = link_uri(a["href"])
        if uri and not uri.endswith("/_contents") and uri not in out:
            out.append(uri)
    return out


# ---------------------------------------------------------------------------
# footnotes
# ---------------------------------------------------------------------------

@dataclass
class Ref:
    """One footnote_ref row (seq is its position in Footnote.refs). `book_uri` and `jst_book` (core.db BookID
    of a 'jst' ref's JST verse) are resolved to IDs by the build."""
    category: str
    ref_type: str                  # scripture-ref (an <a href>) | jst-note (a jst span's text)
    href: Optional[str]
    label: str
    target_uri: Optional[str] = None
    book_uri: Optional[str] = None
    chapter: Optional[int] = None
    verse_start: Optional[int] = None
    verse_end: Optional[int] = None
    help: Optional[str] = None     # "tg/hope": a study-help page (not fetched)
    jst_book: Optional[int] = None


def resolve_href(href: str) -> List[Ref]:
    """The targets of a fully qualified Church href, one per `id=` range. Never reads the link label.

    `/study/scriptures/nt/john/20?lang=eng&id=p29#p29` -> nt/john/20, verses 29..29; `id=p18%2Cp20-p21` gives
    two targets. A path outside the six volumes (`tg/…`, `bd/…`) is a study help.
    """
    parts = urlsplit(href or "")
    uri = link_uri(href)
    segs = segments(uri) if uri else []
    if not segs:
        return [Ref("", "scripture-ref", href, "")]
    base = Ref("", "scripture-ref", href, "", target_uri="/scriptures/" + "/".join(segs))
    if segs[0] not in TOC_VOLUMES:
        base.help = "/".join(segs)
        return [base]
    if len(segs) >= 3:
        base.book_uri = f"/scriptures/{segs[0]}/{segs[1]}"
        base.chapter = int(segs[2]) if segs[2].isdigit() else None
    ranges = []
    for token in (parse_qs(parts.query).get("id") or [""])[0].split(","):
        if m := re.fullmatch(r"p(\d+)(?:-p(\d+))?", token.strip()):
            ranges.append((int(m.group(1)), int(m.group(2) or m.group(1))))
    if not ranges or base.chapter is None:
        return [base]
    return [Ref(**{**base.__dict__, "verse_start": a, "verse_end": b}) for a, b in ranges]


@dataclass
class Footnote:
    note_key: str
    marker: str
    letter: Optional[str]
    context: str
    text: str
    text_html: str
    pid: Optional[str]
    refs: List[Ref] = field(default_factory=list)


def jst_text_refs(text: str) -> List[Ref]:
    """One 'jst-note' ref per JST verse of the first "JST <book> <chapter>:<verse>[–<verse>]" in a jst span's text
    (its target is parsed from the text: the one exception to "never parse the label"). [] when it names none."""
    m = JST_TEXT_REF.search(text)
    if not m or int(m.group(4) or m.group(3)) < int(m.group(3)):
        return []
    cite = m.group(1)
    book = JST_BOOK_BY_CITE.get(cite) or JST_BOOK_BY_CITE.get(cite + ".")
    return [Ref("jst", "jst-note", None, text, chapter=int(m.group(2)), verse_start=v, verse_end=v, jst_book=book)
            for v in range(int(m.group(3)), int(m.group(4) or m.group(3)) + 1)]


def parse_footnote(key: str, fn: dict) -> Footnote:
    """One `content.footnotes` entry. Refs come from the `<a href>`s of its `<span data-note-category>` segments.

    A 'jst' ref is made only from a `jst` segment, and only for a JST verse it names, one ref per verse:
    from its link into the JST appendix (`/scriptures/jst/…?id=p4-p6`), or else from its text ("JST Gen. 8:13 …",
    ref_type 'jst-note'). A segment that names no JST verse ("JST entitles this book …") gets no 'jst' ref. Any
    other link in a `jst` segment is a 'cross-ref'; a JST link in another segment keeps that segment's category.
    """
    html = fn.get("text") or ""
    doc = soup(html)
    m = re.fullmatch(r"note\d+_([a-z]+)", key)
    note = Footnote(key, fn.get("marker") or "", m and m.group(1), collapse(fn.get("context")), plain_text(doc),
                    html, fn.get("pid"))
    for span in doc.find_all("span", attrs={"data-note-category": True}):
        category = span["data-note-category"]
        anchors = span.find_all("a", href=True)
        if category == "jst" and not any("/scriptures/jst/" in a["href"] for a in anchors):
            note.refs += jst_text_refs(plain_text(span))
        for a in anchors:
            is_jst = "/scriptures/jst/" in a["href"]
            cat = "cross-ref" if category == "jst" and not is_jst else category
            for r in resolve_href(a["href"]):
                r.category, r.label = cat, plain_text(a)
                if cat == "jst":
                    r.jst_book = jst_book(r.target_uri)
                    if r.verse_start is not None:  # one ref per JST verse
                        note.refs += [Ref(**{**r.__dict__, "verse_start": v, "verse_end": v})
                                      for v in range(r.verse_start, r.verse_end + 1)]
                        continue
                note.refs.append(r)
    return note


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

@dataclass
class Verse:
    verse: int
    aid: str
    html_id: str
    text: str
    text_html: str


@dataclass
class Page:
    uri: str
    kind: str
    title: Optional[str]
    number: Optional[int] = None
    summary: Optional[str] = None
    intro: Optional[str] = None
    summary_html: Optional[str] = None
    intro_html: Optional[str] = None
    verses: List[Verse] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    note_markers: List[str] = field(default_factory=list)   # every study-note-ref in the body ("note2_a")


def _verse(p) -> Verse:
    html_id = p.get("id") or ""
    vn = p.find(class_="verse-number")
    number = html_id[1:] if re.fullmatch(r"p\d+", html_id) else collapse(vn.get_text() if vn else "")
    if not number.isdigit():
        raise ValueError(f"verse paragraph without a number: id={html_id!r}")
    return Verse(int(number), str(p.get("data-aid") or ""), html_id, plain_text(p), p.decode_contents())


def parse_page(uri: str, data: dict) -> Page:
    """Parse one raw page (the decoded `type/content` JSON)."""
    kind = classify(uri)
    content = data.get("content") or {}
    page = Page(uri, kind, collapse((data.get("meta") or {}).get("title")) or None)
    if kind in ("volume_toc", "book_toc"):
        return page
    body = soup(content.get("body"))
    page.footnotes = [parse_footnote(k, v) for k, v in (content.get("footnotes") or {}).items()]
    page.note_markers = [a["href"].lstrip("#") for a in body.select("a.study-note-ref[href]")]
    if kind == "jst_appendix":
        return page
    m = re.search(r"(\d+)$", uri)
    page.number = int(m.group(1)) if m and kind != "front_matter" else None
    page.verses = [_verse(p) for p in body.select("p.verse")]
    intro, summary = body.select_one("p.study-intro"), body.select_one("p.study-summary")
    if intro:
        page.intro, page.intro_html = plain_text(intro), intro.decode_contents()
    if summary:
        page.summary, page.summary_html = plain_text(summary), summary.decode_contents()
    elif page.verses and intro:  # summary fallback (AUDIT.md Q3): study-intro, then usx-cd paragraphs, else none
        page.summary, page.summary_html = page.intro, page.intro_html
    elif page.verses and (cds := body.select("p.usx-cd")):
        page.summary = collapse(" ".join(plain_text(p) for p in cds))
        page.summary_html = "\n".join(p.decode_contents() for p in cds)
    return page
