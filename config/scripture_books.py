"""Static crosswalk from Church API books to their cite abbreviation and core.db `book.ID`.

Keyed by (volume segment, book path) as in `/scriptures/<volume>/<book path>`; the Facsimiles are the book
`abr/fac`. Values are (cite_abbr, core_book_id), both taken from core.db's `book` table (`CiteAbbr`, `ID`).
`book.abbr` is not copied from core.db (whose `Abbr` for D&C is "sec"): it is the URI's book segment with
hyphens as spaces ("1-ne" -> "1 ne", "abr/fac" -> "fac"), see `book_abbr`.
A book missing here still builds, with cite_abbr = its name and core_book_id NULL.
"""

VOLUME_ABBR = {"ot": "OT", "nt": "NT", "bofm": "B of M", "dc-testament": "D&C", "pgp": "P of GP"}

BOOK_CROSSWALK = {
    ("ot", "gen"): ("Gen.", 101), ("ot", "ex"): ("Ex.", 102), ("ot", "lev"): ("Lev.", 103),
    ("ot", "num"): ("Num.", 104), ("ot", "deut"): ("Deut.", 105), ("ot", "josh"): ("Josh.", 106),
    ("ot", "judg"): ("Judg.", 107), ("ot", "ruth"): ("Ruth", 108), ("ot", "1-sam"): ("1 Sam.", 109),
    ("ot", "2-sam"): ("2 Sam.", 110), ("ot", "1-kgs"): ("1 Kgs.", 111), ("ot", "2-kgs"): ("2 Kgs.", 112),
    ("ot", "1-chr"): ("1 Chr.", 113), ("ot", "2-chr"): ("2 Chr.", 114), ("ot", "ezra"): ("Ezra", 115),
    ("ot", "neh"): ("Neh.", 116), ("ot", "esth"): ("Esth.", 117), ("ot", "job"): ("Job", 118),
    ("ot", "ps"): ("Ps.", 119), ("ot", "prov"): ("Prov.", 120), ("ot", "eccl"): ("Eccl.", 121),
    ("ot", "song"): ("Song", 122), ("ot", "isa"): ("Isa.", 123), ("ot", "jer"): ("Jer.", 124),
    ("ot", "lam"): ("Lam.", 125), ("ot", "ezek"): ("Ezek.", 126), ("ot", "dan"): ("Dan.", 127),
    ("ot", "hosea"): ("Hosea", 128), ("ot", "joel"): ("Joel", 129), ("ot", "amos"): ("Amos", 130),
    ("ot", "obad"): ("Obad.", 131), ("ot", "jonah"): ("Jonah", 132), ("ot", "micah"): ("Micah", 133),
    ("ot", "nahum"): ("Nahum", 134), ("ot", "hab"): ("Hab.", 135), ("ot", "zeph"): ("Zeph.", 136),
    ("ot", "hag"): ("Hag.", 137), ("ot", "zech"): ("Zech.", 138), ("ot", "mal"): ("Mal.", 139),
    ("nt", "matt"): ("Matt.", 140), ("nt", "mark"): ("Mark", 141), ("nt", "luke"): ("Luke", 142),
    ("nt", "john"): ("John", 143), ("nt", "acts"): ("Acts", 144), ("nt", "rom"): ("Rom.", 145),
    ("nt", "1-cor"): ("1 Cor.", 146), ("nt", "2-cor"): ("2 Cor.", 147), ("nt", "gal"): ("Gal.", 148),
    ("nt", "eph"): ("Eph.", 149), ("nt", "philip"): ("Philip.", 150), ("nt", "col"): ("Col.", 151),
    ("nt", "1-thes"): ("1 Thes.", 152), ("nt", "2-thes"): ("2 Thes.", 153), ("nt", "1-tim"): ("1 Tim.", 154),
    ("nt", "2-tim"): ("2 Tim.", 155), ("nt", "titus"): ("Titus", 156), ("nt", "philem"): ("Philem.", 157),
    ("nt", "heb"): ("Heb.", 158), ("nt", "james"): ("James", 159), ("nt", "1-pet"): ("1 Pet.", 160),
    ("nt", "2-pet"): ("2 Pet.", 161), ("nt", "1-jn"): ("1 Jn.", 162), ("nt", "2-jn"): ("2 Jn.", 163),
    ("nt", "3-jn"): ("3 Jn.", 164), ("nt", "jude"): ("Jude", 165), ("nt", "rev"): ("Rev.", 166),
    ("bofm", "1-ne"): ("1 Ne.", 205), ("bofm", "2-ne"): ("2 Ne.", 206), ("bofm", "jacob"): ("Jacob", 207),
    ("bofm", "enos"): ("Enos", 208), ("bofm", "jarom"): ("Jarom", 209), ("bofm", "omni"): ("Omni", 210),
    ("bofm", "w-of-m"): ("W of M", 211), ("bofm", "mosiah"): ("Mosiah", 212), ("bofm", "alma"): ("Alma", 213),
    ("bofm", "hel"): ("Hel.", 214), ("bofm", "3-ne"): ("3 Ne.", 215), ("bofm", "4-ne"): ("4 Ne.", 216),
    ("bofm", "morm"): ("Morm.", 217), ("bofm", "ether"): ("Ether", 218), ("bofm", "moro"): ("Moro.", 219),
    ("dc-testament", "dc"): ("D&C", 302), ("dc-testament", "od"): ("O.D.", 303),
    ("pgp", "moses"): ("Moses", 401), ("pgp", "abr"): ("Abr.", 402), ("pgp", "abr/fac"): ("Fac.", 403),
    ("pgp", "js-m"): ("JS—M", 404), ("pgp", "js-h"): ("JS—H", 405), ("pgp", "a-of-f"): ("A of F", 406),
}

# a sub-book's name when the volume TOC gives it no group of its own (its parent's group would misname it)
SUB_BOOK_NAMES = {("pgp", "abr/fac"): "Facsimiles"}


def book_abbr(book_path: str) -> str:
    """"1-ne" -> "1 ne", "abr/fac" -> "fac"."""
    return book_path.rsplit("/", 1)[-1].replace("-", " ")


# core.db BookID -> (volume segment, book path, cite_abbr). Names a JST row's book even when the store has no row for it.
CORE_BOOKS = {core_id: (vol, path, cite) for (vol, path), (cite, core_id) in BOOK_CROSSWALK.items()}


def display_book_name(uri: str, name: str) -> str:
    """The Church names the D&C's book "Sections"; people (and embeddings) want "Doctrine and Covenants"."""
    return "Doctrine and Covenants" if uri == "/scriptures/dc-testament/dc" else name
