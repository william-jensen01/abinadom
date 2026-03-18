## Phase 4 Bug Summary — Footnote Text Extraction

---

### Bug 1: Whitespace Destroyed Between Inline Elements

**File:** `extractors/phase4_footnote_extraction.py` — `_extract_footnote_text()`

**Symptom:**

```
Input:  Joseph B. Wirthlin, "The Great Commandment," <cite>Ensign</cite> or <cite>Liahona</cite>
Output: Joseph B. Wirthlin, "The Great Commandment,"EnsignorLiahona
```

Spaces between `<cite>` tags and surrounding text nodes were silently dropped.

**Root Cause:**
`BeautifulSoup`'s `get_text(strip=True)` strips each individual text node before joining them with no separator. The spaces around `or` are plain text nodes — `" or "` — and `strip=True` discards their leading/trailing whitespace. Since there's no separator, elements concatenate directly.

**Fix:**

```python
# Before
return fn_span.get_text(strip=True)

# After
return fn_span.get_text().strip()
```

`get_text()` without `strip=True` concatenates all text nodes as-is, preserving internal whitespace. The outer `.strip()` only removes leading/trailing whitespace from the final result.

---

### Bug 2: Extra Leading Spaces on Citations from `sx()` Anchors

**File:** `extractors/phase4_footnote_extraction.py` — new `_render_footnote_span()`

**Symptom:**

```
Input:  <a onclick="sx(this, 139288)">&nbsp;</a><a onclick="gs(139288)">Luke 19:1–4</a>
Output: " Luke 19:1–4"  (leading non-breaking space)
```

Every scripture citation inside a footnote had a spurious leading space.

**Root Cause:**
The LDS website uses a two-anchor pattern inside each `<span class="citation">`:

1. `<a onclick="sx(...)">` — a JavaScript hook containing only `&nbsp;` (U+00A0). This is purely a UI toggle and contains no display text.
2. `<a onclick="gs(...)">` — the actual scripture reference text.

`get_text()` collected both anchors' content, so `&nbsp;` appeared before every citation.

**Fix:**
In `_render_footnote_span()`, before extracting text, remove all `sx()` anchors from a deep copy of the span:

```python
for a in span.find_all("a"):
    if "sx(" in a.get("onclick", ""):
        a.decompose()
```

Then normalize any remaining `&nbsp;` (`\u00a0`) to regular spaces and collapse runs of multiple spaces.

---

### Bug 3: Missing Punctuation from CSS `ccontainer` Pseudo-Elements

**File:** `extractors/phase4_footnote_extraction.py` — `_ccontainer_punctuation()`, `_parse_punct_class()`

**Symptom:**

```
Input:  <span class="ccontainer rsemi">...<a onclick="gs(...)">Luke 19:1–4</a>...</span> see also
Output: "Luke 19:1–4 see also"   (missing semicolon)
Expected: "Luke 19:1–4; see also"
```

Punctuation that the browser renders via CSS `::after`/`::before` pseudo-elements on `ccontainer` spans was entirely absent from extracted text.

**Root Cause:**
The site uses CSS classes on `<span class="ccontainer rsemi">` (and similar) to inject punctuation visually — none of it exists in the HTML text content. `get_text()` has no knowledge of CSS, so it silently omits this punctuation entirely.

**Initial Fix (static map — later replaced):**
Added `_PUNCT_CHARS` dict mapping known class name suffixes to characters, and `_ccontainer_punctuation()` to inject `NavigableString` nodes into a deep copy of the span before text extraction. This worked but required hardcoding compound names like `parencomma` and `brackdotrdquo` as explicit entries, which would require manual updates for every new variation encountered.

**Final Fix (dynamic parsing):**
Replaced the static map with a parser based on the structural pattern in the class names:

- Every class name is a **concatenation of `{l|r}{token}` segments**
- `l` = prefix (insert before citation), `r` = suffix (insert after citation)
- Direction is **sticky**: tokens without an explicit `l`/`r` inherit the most recently seen direction (default `r`)
- Only atomic tokens need to be defined: `semi`, `dot`, `comma`, `paren`, `brack`, `dquo`, `squo`
- Greedy longest-match prevents ambiguity (e.g., `dquo` matched before `d`)

This correctly parses any compound without new entries:

| Class            | Parse trace                                | Result       |
| ---------------- | ------------------------------------------ | ------------ |
| `rsemi`          | `r`+`semi`                                 | suffix `;`   |
| `rparencomma`    | `r`+`paren`, `comma`(sticky `r`)           | suffix `),`  |
| `rbrackdotrdquo` | `r`+`brack`, `dot`(sticky `r`), `r`+`dquo` | suffix `]."` |
| `lparen`         | `l`+`paren`                                | prefix `(`   |

**Key function:**

```python
def _parse_punct_class(cls: str) -> Tuple[str, str]:
    direction = "r"
    while i < n:
        # Try explicit direction + token
        if cls[i] in ("l", "r"):
            for token in _TOKENS_BY_LENGTH:  # greedy longest-match
                if cls[i+1:i+1+len(token)] == token:
                    direction = cls[i]; emit char; advance; break
        # Fallback: bare token with sticky direction
        else:
            for token in _TOKENS_BY_LENGTH:
                if cls[i:i+len(token)] == token:
                    emit char with current direction; advance; break
```

---

### Tests Added

15 new tests in `TestFootnoteTextRendering` covering:

- Whitespace preserved between `<cite>` elements
- `&nbsp;` normalized, multiple spaces collapsed
- `sx()` anchor removal leaves no leading space
- `_ccontainer_punctuation` unit tests for each known class pattern
- `_parse_punct_class` behaviour via compound cases (`rparencomma`, `rbrackdotrdquo`)
- Two real-world HTML examples end-to-end
