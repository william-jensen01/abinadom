"""Book resolver (SPEC-v2 §13): free-text book input -> a `book` row of scripture.db.

Built from the API TOC (the `book` table: name, URI segment, cite abbreviation, core_book_id), not from core.db.
Accepts full names, URI segments, cite abbreviations, word/digit ordinals ("First Nephi" / "1 Nephi" / "1 Ne."),
"D&C" / "Doctrine and Covenants", and the old v1 aliases. Matching ignores case, periods, dashes and spaces.
A leading "JST" ("JST Genesis", "JST Gen.") names the same book read in JST numbering.
"""
import re
from typing import Iterable, Optional

from config.scripture_books import display_book_name

_ORDINALS = {"first": "1", "1st": "1", "i": "1", "second": "2", "2nd": "2", "ii": "2",
             "third": "3", "3rd": "3", "iii": "3", "fourth": "4", "4th": "4", "iv": "4"}

_JST_PREFIX = re.compile(
    r"^(?:jst|joseph smith translation(?: of(?: the)?)?|inspired version(?: of(?: the)?)?)\s+(?=\S)")

# Old v1 aliases, by book URI, on top of the row's name, display name, cite abbreviation and URI segment.
_EXTRA_ALIASES = {
    "/scriptures/dc-testament/dc": ["D&C", "DC", "D & C", "Doctrine & Covenants", "Section"],
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
    """Lowercase, no periods or commas, dashes as spaces, a leading ordinal word as its digit, then no spaces."""
    words = re.sub(r"[—–\-]", " ", text.lower().replace(".", " ").replace(",", " ")).split()
    if len(words) > 1 and words[0] in _ORDINALS:
        words[0] = _ORDINALS[words[0]]
    return "".join(words)


class BookResolver:
    def __init__(self, rows: Iterable[dict]):
        """`rows`: `book` rows (book_id, uri, name, cite_abbr, core_book_id, num_chapters), in TOC order.
        Each gets a `display_name` ("Doctrine and Covenants" for the Church's "Sections")."""
        self.by_id: dict[int, dict] = {}
        self._by_alias: dict[str, dict] = {}
        for r in rows:
            b = dict(r, display_name=display_book_name(r["uri"], r["name"]))
            self.by_id[b["book_id"]] = b
            for alias in (b["name"], b["display_name"], b["cite_abbr"], b["uri"].rsplit("/", 1)[-1],
                          *_EXTRA_ALIASES.get(b["uri"], [])):
                if alias:
                    self._by_alias.setdefault(_key(alias), b)

    def resolve(self, text: str) -> Optional[tuple[dict, bool]]:
        """(book row, jst) for what a user wrote, or None. "JST Genesis" gives Genesis with jst=True."""
        t = re.sub(r"\s+", " ", (text or "").replace(".", " ").strip().lower())
        m = _JST_PREFIX.match(t)
        book = self._by_alias.get(_key(t[m.end():] if m else t)) if t else None
        return (book, bool(m)) if book else None
