"""Parse one Church API scripture page (the `type/content` JSON) into plain rows (SPEC-v2 §2, §4.2, §8).

Pure functions: nothing here touches a database or the network. `scripts/build_scriptures.py`
feeds every `raw_latest` page through `parse_page` / `parse_toc` and stores the results.

The page kind comes from the URI, because the TOC's `data-content-type` does not separate the document
kinds (docs/scriptures/AUDIT.md Q3). `parse_page` dispatches on it:

    volume_toc / book_toc   title only (TOC bodies are read by `parse_toc` and `parse_book_contents`)
    jst_appendix            title and footnotes only. Appendix passages are not verses; extracting the
                            passages and their "Compare" links is left to the JST item (scripture_jst.py)
    chapter, section, declaration, facsimile, front_matter
                            header texts, verses, footnotes, and the body's footnote markers
"""
import html as _html
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag

VOLUMES = ("ot", "nt", "bofm", "dc-testament", "pgp")
JST_VOLUME = "jst"
TOC_VOLUMES = VOLUMES + (JST_VOLUME,)

KIND_VOLUME_TOC = "volume_toc"
KIND_BOOK_TOC = "book_toc"
KIND_JST_APPENDIX = "jst_appendix"
KIND_DECLARATION = "declaration"
KIND_FACSIMILE = "facsimile"
KIND_FRONT_MATTER = "front_matter"
KIND_SECTION = "section"
KIND_CHAPTER = "chapter"

# Kinds that get a `chapter` row (AUDIT.md Q3). jst_appendix, book_toc and volume_toc get a `page` row only.
CHAPTER_KINDS = (KIND_CHAPTER, KIND_SECTION, KIND_DECLARATION, KIND_FACSIMILE, KIND_FRONT_MATTER)

# Inline elements that are not part of the verse text.
_SKIP_CLASSES = {"verse-number", "para-mark", "page-break"}
# Inline pieces that sit side by side with no whitespace between them in the HTML.
_SPACED_CLASSES = {"line", "question", "answer"}


# ---------------------------------------------------------------------------
# URIs
# ---------------------------------------------------------------------------

def uri_segments(uri: str) -> List[str]:
    """['bofm', 'alma', '32'] for '/scriptures/bofm/alma/32'."""
    parts = [p for p in uri.split("/") if p]
    return parts[1:] if parts and parts[0] == "scriptures" else parts


def classify_page(uri: str) -> str:
    """Page kind from the URI (rule order from AUDIT.md Q3)."""
    segs = uri_segments(uri)
    if len(segs) <= 1:
        return KIND_VOLUME_TOC
    if segs[-1] == "_contents":
        return KIND_BOOK_TOC
    if segs[0] == JST_VOLUME:
        return KIND_JST_APPENDIX
    if "od" in segs[1:-1] or (len(segs) >= 2 and segs[1] == "od"):
        return KIND_DECLARATION
    if segs[-1].startswith("fac-"):
        return KIND_FACSIMILE
    last = segs[-1]
    if last == "title-page" or not last.isdigit():
        return KIND_FRONT_MATTER
    if segs[0] == "dc-testament":
        return KIND_SECTION
    return KIND_CHAPTER


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup or "", "html.parser")


def _classes(tag: Tag) -> List[str]:
    c = tag.get("class") or []
    return c.split() if isinstance(c, str) else list(c)


def _has_class(tag: Tag, name: str) -> bool:
    return name in _classes(tag)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _walk_text(node, out: List[str]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            if type(child).__name__ in ("Comment", "Doctype", "ProcessingInstruction"):
                continue
            out.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        classes = set(_classes(child))
        if classes & _SKIP_CLASSES or (child.name == "sup" and "marker" in classes):
            continue
        if child.name == "br":
            out.append(" ")
            continue
        _walk_text(child, out)
        if classes & _SPACED_CLASSES:
            out.append(" ")


def plain_text(node) -> str:
    """Clean text of a node: no verse number, pilcrow, page break or footnote marker; italics flattened."""
    out: List[str] = []
    _walk_text(node, out)
    return _collapse("".join(out))


def _inner_html(tag: Tag) -> str:
    return tag.decode_contents()


# ---------------------------------------------------------------------------
# hrefs -> targets
# ---------------------------------------------------------------------------

_ID_RANGE = re.compile(r"^p(\d+)(?:-p(\d+))?$")


@dataclass
class Target:
    target_uri: Optional[str] = None
    book_uri: Optional[str] = None          # "/scriptures/bofm/alma", resolved to book_id by the build
    chapter: Optional[int] = None
    verse_ranges: List[Tuple[Optional[int], Optional[int]]] = field(default_factory=lambda: [(None, None)])
    help: Optional[str] = None              # "tg/hope" (study-help page, not fetched)
    volume: Optional[str] = None


def resolve_href(href: str) -> Target:
    """Resolve a fully qualified Church href. Never reads the link label.

    `/study/scriptures/nt/john/20?lang=eng&id=p29#p29` -> nt/john/20, verses 29..29.
    `id=p18%2Cp20-p21` gives two ranges (18..18 and 20..21). A `tg/…`, `bd/…` or other non-volume
    path is a study help: `help` holds the path.
    """
    href = _html.unescape(href or "")
    parts = urlsplit(href)
    path = parts.path
    if path.startswith("/study"):
        path = path[len("/study"):]
    if not path.startswith("/scriptures/"):
        return Target()
    segs = [s for s in path.split("/") if s][1:]
    if not segs:
        return Target()
    volume = segs[0]
    if volume not in TOC_VOLUMES:
        return Target(target_uri="/scriptures/" + "/".join(segs), help="/".join(segs), volume=volume)

    target = Target(target_uri="/scriptures/" + "/".join(segs), volume=volume)
    if len(segs) >= 3:
        target.book_uri = f"/scriptures/{segs[0]}/{segs[1]}"
        if segs[2].isdigit():
            target.chapter = int(segs[2])
    ids = (parse_qs(parts.query).get("id") or [""])[0]
    ranges: List[Tuple[Optional[int], Optional[int]]] = []
    for token in ids.split(","):
        m = _ID_RANGE.match(token.strip())
        if m:
            start = int(m.group(1))
            ranges.append((start, int(m.group(2)) if m.group(2) else start))
    if ranges and target.chapter is not None:
        target.verse_ranges = ranges
    return target


# ---------------------------------------------------------------------------
# footnotes
# ---------------------------------------------------------------------------

@dataclass
class ParsedRef:
    seq: int
    category: str
    ref_type: str
    href: Optional[str]
    label: str
    target: Target = field(default_factory=Target)
    verse_start: Optional[int] = None
    verse_end: Optional[int] = None


@dataclass
class ParsedFootnote:
    note_key: str
    marker: str
    letter: Optional[str]
    context: str
    text: str
    text_html: str
    pid: Optional[str]
    refs: List[ParsedRef] = field(default_factory=list)


_NOTE_KEY = re.compile(r"^note\d+_([a-z]+)$")
# "JST Gen. 8:13", "JST 1 Cor. 14:2", "JST Matt. 5:24": a JST book, chapter and verse named in a span's text.
# Only used to decide whether an hrefless `jst` span gets a ref row; the JST item parses the target itself.
_NAMES_JST_VERSE = re.compile(r"JST\s+(?:\d\s+)?[A-Z][A-Za-z.]*\s+\d+:\d+")


def names_jst_verse(text: str) -> bool:
    """True when the text names a JST chapter and verse (not "JST entitles this book …", not "JS—M 1:4")."""
    return bool(_NAMES_JST_VERSE.search(text or ""))


def parse_footnote(key: str, fn: dict) -> ParsedFootnote:
    """One `content.footnotes` entry.

    Refs come from the `<a href>`s inside the `<span data-note-category>` segments of `text`
    (they are the same links as `referenceUris`, in the same order, but carry the category).

    A 'jst' ref is made only from a `jst` segment, and only for a JST verse it names:
      - a link into the JST appendix (`/scriptures/jst/…`) is the target: one 'jst' ref per verse of
        its `id=` range (`p4-p6` gives verses 4, 5 and 6);
      - otherwise, when the segment's text names a JST verse ("JST Gen. 8:13 …"), one hrefless 'jst' ref
        with ref_type 'jst-note' holds the text; the JST item parses and resolves it;
      - a segment that names no JST verse ("JST entitles this book …", "JS—M 1:4 adds …") gets no 'jst' ref.
    Any other link inside a `jst` segment is an ordinary inline ref, stored as 'cross-ref'. Links into
    `/scriptures/jst/` inside other segments (e.g. `cross-ref`) keep their segment's category.
    """
    text_html = fn.get("text") or ""
    soup = _soup(text_html)
    m = _NOTE_KEY.match(key)
    note = ParsedFootnote(
        note_key=key,
        marker=fn.get("marker") or "",
        letter=m.group(1) if m else None,
        context=_collapse(fn.get("context") or ""),
        text=plain_text(soup),
        text_html=text_html,
        pid=fn.get("pid"),
    )
    seq = 0
    for span in soup.find_all("span", attrs={"data-note-category": True}):
        category = span["data-note-category"]
        anchors = [a for a in span.find_all("a", href=True)]
        if category == "jst" and not any("/scriptures/jst/" in _html.unescape(a["href"]) for a in anchors):
            span_text = plain_text(span)
            if names_jst_verse(span_text):
                note.refs.append(ParsedRef(seq, "jst", "jst-note", None, span_text))
                seq += 1
        for a in anchors:
            href = _html.unescape(a["href"])
            cat = category
            if category == "jst" and "/scriptures/jst/" not in href:
                cat = "cross-ref"
            target = resolve_href(href)
            label = plain_text(a)
            for start, end in target.verse_ranges:
                if cat == "jst" and start is not None and end is not None and end > start:
                    # one 'jst' ref per JST verse
                    for v in range(start, end + 1):
                        note.refs.append(ParsedRef(seq, cat, "scripture-ref", href, label, target, v, v))
                        seq += 1
                    continue
                note.refs.append(ParsedRef(seq, cat, "scripture-ref", href, label, target, start, end))
                seq += 1
    return note


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

@dataclass
class ParsedVerse:
    verse: int
    aid: str
    html_id: str
    text: str
    text_html: str


@dataclass
class ParsedPage:
    uri: str
    kind: str
    title: Optional[str]
    number: Optional[int] = None
    summary: Optional[str] = None
    intro: Optional[str] = None
    summary_html: Optional[str] = None
    intro_html: Optional[str] = None
    verses: List[ParsedVerse] = field(default_factory=list)
    footnotes: List[ParsedFootnote] = field(default_factory=list)
    body_note_keys: List[str] = field(default_factory=list)   # every study-note-ref href in the body ("note2_a")
    verse_paragraphs: int = 0                                  # <p> carrying the `verse` class, counted independently


def _page_title(uri: str, data: dict) -> Optional[str]:
    title = ((data.get("meta") or {}).get("title") or "").strip()
    return _collapse(_html.unescape(title)) or None


def _header_para(soup: BeautifulSoup, cls: str) -> Optional[Tag]:
    for p in soup.find_all("p"):
        if _has_class(p, cls):
            return p
    return None


def _parse_verses(soup: BeautifulSoup) -> List[ParsedVerse]:
    verses = []
    for p in soup.find_all("p"):
        if not _has_class(p, "verse"):
            continue
        html_id = p.get("id") or ""
        m = re.match(r"^p(\d+)$", html_id)
        if m:
            number = int(m.group(1))
        else:
            vn = p.find("span", class_="verse-number")
            digits = re.search(r"\d+", vn.get_text()) if vn else None
            if not digits:
                raise ValueError(f"verse paragraph without a number: id={html_id!r}")
            number = int(digits.group(0))
        verses.append(ParsedVerse(
            verse=number,
            aid=str(p.get("data-aid") or ""),
            html_id=html_id,
            text=plain_text(p),
            text_html=_inner_html(p),
        ))
    return verses


def _parse_content_page(uri: str, kind: str, data: dict) -> ParsedPage:
    content = data.get("content") or {}
    body = content.get("body") or ""
    soup = _soup(body)
    page = ParsedPage(uri=uri, kind=kind, title=_page_title(uri, data))

    segs = uri_segments(uri)
    m = re.search(r"(\d+)$", segs[-1])
    if kind != KIND_FRONT_MATTER and kind != KIND_JST_APPENDIX and m:
        page.number = int(m.group(1))

    page.footnotes = [parse_footnote(k, v) for k, v in (content.get("footnotes") or {}).items()]
    page.body_note_keys = [
        a["href"].lstrip("#") for a in soup.find_all("a") if _has_class(a, "study-note-ref") and a.get("href")
    ]

    if kind == KIND_JST_APPENDIX:
        return page

    page.verses = _parse_verses(soup)
    page.verse_paragraphs = len(page.verses)

    intro_p = _header_para(soup, "study-intro")
    summary_p = _header_para(soup, "study-summary")
    if intro_p is not None:
        page.intro, page.intro_html = plain_text(intro_p), _inner_html(intro_p)
    if summary_p is not None:
        page.summary, page.summary_html = plain_text(summary_p), _inner_html(summary_p)
    elif page.verses:
        # summary fallback (AUDIT.md Q3): study-intro, then the usx-cd paragraphs, else none
        if intro_p is not None:
            page.summary, page.summary_html = page.intro, page.intro_html
        else:
            cds = [p for p in soup.find_all("p") if _has_class(p, "usx-cd")]
            if cds:
                page.summary = _collapse(" ".join(plain_text(p) for p in cds))
                page.summary_html = "\n".join(_inner_html(p) for p in cds)
    return page


def parse_page(uri: str, data: dict) -> ParsedPage:
    """Parse one raw page (the decoded `type/content` JSON). Dispatches on the page kind."""
    kind = classify_page(uri)
    if kind in (KIND_VOLUME_TOC, KIND_BOOK_TOC):
        return ParsedPage(uri=uri, kind=kind, title=_page_title(uri, data))
    return _parse_content_page(uri, kind, data)


# ---------------------------------------------------------------------------
# tables of contents
# ---------------------------------------------------------------------------

@dataclass
class TocBook:
    uri: str                # "/scriptures/bofm/alma"
    name: str
    volume: str


@dataclass
class TocItem:
    uri: str
    title: str
    book_uri: Optional[str]   # the book (or sub-book) group this link sits in


@dataclass
class Toc:
    title: Optional[str]
    books: List[TocBook] = field(default_factory=list)
    items: List[TocItem] = field(default_factory=list)


def _link_uri(href: str) -> Optional[str]:
    path = urlsplit(_html.unescape(href)).path
    if path.startswith("/study"):
        path = path[len("/study"):]
    if not path.startswith("/scriptures/"):
        return None
    return path.rstrip("/")


def _group_book_uri(links: List[str]) -> Optional[str]:
    """The book a group of links belongs to, or None when they are volume-level pages.

    `/scriptures/ot/gen/1` and `/scriptures/ot/gen/_contents` -> `/scriptures/ot/gen`.
    `/scriptures/pgp/abr/fac-1` -> `/scriptures/pgp/abr/fac` (the Facsimiles group, a book of its own).
    """
    for uri in links:
        segs = uri_segments(uri)
        if len(segs) != 3 or segs[0] == JST_VOLUME:
            continue
        base = f"/scriptures/{segs[0]}/{segs[1]}"
        last = segs[2]
        if last == "_contents" or last.isdigit():
            return base
        m = re.match(r"^([a-z]+)-\d+$", last)
        if m:
            return f"{base}/{m.group(1)}"
    return None


def _base_book_uri(links: List[str]) -> Optional[str]:
    for uri in links:
        segs = uri_segments(uri)
        if len(segs) == 3 and segs[0] != JST_VOLUME:
            return f"/scriptures/{segs[0]}/{segs[1]}"
    return None


def parse_toc(data: dict, volume: Optional[str] = None) -> Toc:
    """A volume TOC: its books (groups with a numbered-page list) and every linked page, in order.

    `volume` is the volume segment of the TOC page's URI ("bofm", "jst"); the build passes it. Without it
    the response's own `uri` field is used.
    """
    body = (data.get("content") or {}).get("body") or ""
    soup = _soup(body.replace('\\"', '"'))
    toc = Toc(title=_page_title("", data))
    root = soup.find("ul")
    seen = set()
    if root is None:
        return toc

    def walk(ul: Tag, book_uri: Optional[str], volume: Optional[str]) -> None:
        for li in ul.find_all("li", recursive=False):
            a = li.find("a", recursive=False)
            if a is not None and a.get("href"):
                uri = _link_uri(a["href"])
                if uri and uri_segments(uri)[0] in TOC_VOLUMES and uri not in seen:
                    seen.add(uri)
                    title_p = a.find("p", class_="title")
                    toc.items.append(TocItem(uri, _collapse((title_p or a).get_text()), book_uri))
                continue
            sub = li.find("ul", recursive=False)
            if sub is None:
                continue
            direct = [_link_uri(x["href"]) for child in sub.find_all("li", recursive=False)
                      for x in child.find_all("a", recursive=False)]
            group_book = _group_book_uri([u for u in direct if u])
            if group_book is None and book_uri is None:
                # a group holding only sub-groups (e.g. Abraham with just its Facsimiles): the book is the
                # base of the nested links
                nested = [_link_uri(x["href"]) for x in sub.find_all("a")]
                group_book = _base_book_uri([u for u in nested if u])
            current = book_uri
            if group_book is not None and volume != JST_VOLUME:
                current = group_book
            if current == group_book and group_book is not None and group_book not in {b.uri for b in toc.books}:
                h2 = li.find("h2", recursive=False)
                title_p = h2.find("p", class_="title") if h2 else None
                name = _collapse((title_p or h2).get_text()) if (title_p or h2) else group_book.rsplit("/", 1)[-1]
                toc.books.append(TocBook(group_book, name, uri_segments(group_book)[0]))
            walk(sub, current, volume)

    volume_segment = volume
    meta_uri = (data.get("uri") or "")
    if volume_segment is None and meta_uri:
        volume_segment = (uri_segments(meta_uri) or [None])[0]
    walk(root, None, volume_segment)
    return toc


def contents_link_book(link: str, contents_book_uri: str) -> str:
    """The book a link on a book's `_contents` page counts toward.

    Usually the `_contents` page's own book. Abraham's `_contents` also lists the facsimiles
    (`/scriptures/pgp/abr/fac-1`), which are a book of their own (`/scriptures/pgp/abr/fac`, as in the
    volume TOC's "Facsimiles" group), so a `fac-N` link counts toward `<book>/fac`.
    """
    segs = uri_segments(link)
    if len(segs) == 3 and re.match(r"^fac-\d+$", segs[2]):
        return f"/scriptures/{segs[0]}/{segs[1]}/fac"
    return contents_book_uri


def parse_book_contents(data: dict) -> List[str]:
    """The page URIs a book's `_contents` page links to, in order (its chapters, sections or documents)."""
    body = (data.get("content") or {}).get("body") or ""
    soup = _soup(body)
    out: List[str] = []
    for a in soup.find_all("a", href=True):
        uri = _link_uri(a["href"])
        if uri and uri_segments(uri) and uri_segments(uri)[-1] != "_contents" and uri not in out:
            out.append(uri)
    return out
