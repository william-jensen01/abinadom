"""Book resolver (SPEC-v2 §13): free-text book input -> a `book` row of scripture.db.

Built from the API TOC (the `book` table: name, URI segment, cite abbreviation) plus the `core_book_id` crosswalk
in `config/scripture_books.py`, not from core.db. Accepts full names, URI abbreviations, cite abbreviations,
word/digit ordinals ("First Nephi" / "1 Nephi" / "1 Ne."), "D&C", and the old v1 aliases. Matching ignores case,
periods, dashes and spaces. A leading "JST" ("JST Genesis", "JST Gen.") resolves the same book with `jst=True`:
the caller then reads the JST in its own numbering.
"""
import re
from dataclasses import dataclass, replace
from typing import Iterable, Optional

from config.scripture_books import BOOK_CROSSWALK, display_book_name

_ORDINALS = {
    "first": "1", "1st": "1", "i": "1",
    "second": "2", "2nd": "2", "ii": "2",
    "third": "3", "3rd": "3", "iii": "3",
    "fourth": "4", "4th": "4", "iv": "4",
}

_JST_PREFIX = re.compile(
    r"^(?:jst|joseph smith translation(?: of(?: the)?)?|inspired version(?: of(?: the)?)?)\s+(?=\S)")

# Old v1 aliases, by book URI. Added on top of what the TOC row provides.
_EXTRA_ALIASES = {
    "/scriptures/dc-testament/dc": ["D&C", "DC", "D & C", "Doctrine and Covenants", "Doctrine & Covenants",
                                    "Section", "Sections"],
    "/scriptures/dc-testament/od": ["OD", "Official Declaration", "Official Declarations"],
    "/scriptures/ot/ps": ["Psalm", "Psalms", "Ps", "Pslm"],
    "/scriptures/ot/song": ["Song of Solomon", "Song of Songs", "Songs of Solomon", "Canticles", "SoS"],
    "/scriptures/ot/eccl": ["Ecclesiastes", "Eccles"],
    "/scriptures/nt/rev": ["Revelation of John", "Revelations", "Apocalypse"],
    "/scriptures/nt/john": ["Jn"],
    "/scriptures/nt/1-jn": ["1 John", "1 Jn"],
    "/scriptures/nt/2-jn": ["2 John", "2 Jn"],
    "/scriptures/nt/3-jn": ["3 John", "3 Jn"],
    "/scriptures/nt/philip": ["Phil", "Php"],
    "/scriptures/bofm/w-of-m": ["Words of Mormon", "WofM", "W of M"],
    "/scriptures/bofm/hel": ["Helaman"],
    "/scriptures/bofm/morm": ["Mormon"],
    "/scriptures/bofm/moro": ["Moroni"],
    "/scriptures/pgp/js-m": ["Joseph Smith Matthew", "JSM", "JS-M"],
    "/scriptures/pgp/js-h": ["Joseph Smith History", "JSH", "JS-H"],
    "/scriptures/pgp/a-of-f": ["Articles of Faith", "AoF", "A of F"],
    "/scriptures/pgp/abr/fac": ["Facsimile", "Facsimiles", "Fac"],
}


def _key(text: str) -> str:
    """Lowercase, no periods, dashes as spaces, a leading ordinal word as its digit, then no spaces at all."""
    t = re.sub(r"[—–\-]", " ", text.lower().replace(".", " ").replace(",", " "))
    words = t.split()
    if len(words) > 1 and words[0] in _ORDINALS:
        words[0] = _ORDINALS[words[0]]
    return "".join(words)


@dataclass(frozen=True)
class ResolvedBook:
    book_id: int
    uri: str
    name: str                # the Church's name ("Sections" for the D&C)
    display_name: str        # "Doctrine and Covenants"
    cite_abbr: str           # "1 Ne.", "D&C"
    core_book_id: Optional[int]
    num_chapters: Optional[int]
    jst: bool = False        # the input named the JST ("JST Genesis")


class BookResolver:
    def __init__(self, books: Iterable[ResolvedBook]):
        self._books = list(books)
        self._by_alias: dict[str, ResolvedBook] = {}
        self._by_id = {b.book_id: b for b in self._books}
        self._by_core = {b.core_book_id: b for b in self._books if b.core_book_id is not None}
        for b in self._books:
            for alias in self._aliases(b):
                self._by_alias.setdefault(_key(alias), b)

    @classmethod
    def from_rows(cls, rows: Iterable[dict]) -> "BookResolver":
        """`rows`: `book` rows (book_id, uri, name, abbr, cite_abbr, core_book_id, num_chapters).
        The crosswalk fills a missing cite_abbr or core_book_id."""
        books = []
        for r in rows:
            parts = r["uri"].split("/")            # "", "scriptures", volume, path...
            cite, core = BOOK_CROSSWALK.get((parts[2], "/".join(parts[3:])), (None, None))
            books.append(ResolvedBook(
                book_id=r["book_id"], uri=r["uri"], name=r["name"],
                display_name=display_book_name(r["uri"], r["name"]),
                cite_abbr=r.get("cite_abbr") or cite or r["name"],
                core_book_id=r.get("core_book_id") if r.get("core_book_id") is not None else core,
                num_chapters=r.get("num_chapters"),
            ))
        return cls(books)

    @staticmethod
    def _aliases(b: ResolvedBook) -> list[str]:
        slug = b.uri.rsplit("/", 1)[-1]
        out = [b.name, b.display_name, b.cite_abbr, slug, *_EXTRA_ALIASES.get(b.uri, [])]
        if b.uri.endswith("/abr/fac"):
            out = [a for a in out if a != "abr"]
        return out

    @property
    def books(self) -> list[ResolvedBook]:
        return list(self._books)

    def by_id(self, book_id: int) -> Optional[ResolvedBook]:
        return self._by_id.get(book_id)

    def by_core_id(self, core_book_id: int) -> Optional[ResolvedBook]:
        return self._by_core.get(core_book_id)

    def resolve(self, text: str) -> Optional[ResolvedBook]:
        """The book a user wrote, or None. "JST Genesis" gives Genesis with jst=True."""
        if not text or not text.strip():
            return None
        t = re.sub(r"\s+", " ", text.replace(".", " ").strip().lower())
        jst = False
        m = _JST_PREFIX.match(t)
        if m:
            jst, t = True, t[m.end():]
        book = self._by_alias.get(_key(t))
        if book is None:
            return None
        return replace(book, jst=True) if jst else book
