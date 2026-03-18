# Scripture Citation Index - SQL Queries

This document contains key SQL queries for navigating and accessing scripture data from the SQLite databases (`core.db` and `content.db`).

## Database Files

-   `core.db` - Contains book metadata, scripture text, citations, and navigation data
-   `content.db` - Contains talk/discourse body text

## URL Patterns Observed

The site uses hash-based URLs with **hexadecimal encoding** for book IDs:

### Pattern Structure

-   **Book view**: `#{bookID_hex}::`
-   **Chapter view**: `#{bookID_hex}{chapter_decimal}::`
-   **Citation Index for Book**: `#{scriptureBookID_hex}{scriptureChapter_hex}::c{citationBookID_hex}`
-   **Citation Index for Chapter**: `#{scriptureBookID_hex}{scriptureChapter_hex}::c{citationBookID_hex}{citationChapter_decimal}`
-   **Citation Index for Verse**: `#{scriptureBookID_hex}{scriptureChapter_hex}::c{citationBookID_hex}{citationChapter_decimal}{verse_decimal}`
-   **Talk View**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:c{citationBookID_hex}{citationChapter_decimal}{verse_decimal}`
-   **Talk View with Conference Library (Specific Session)**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:g{sessionID_hex}`
-   **Talk View with Conference Library (All Sessions)**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:g`
-   **Talk View with Content Library Navigation**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:n`
-   **Talk View with Speakers Index**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:p`
-   **Talk View with Search Interface**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:s`
-   **Talk View with Journal of Discourses**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:j`
-   **Talk View with Topical Index**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:i1`
-   **Talk View with Scriptural Teachings Index**: `#{scriptureBookID_hex}{scriptureChapter_hex}:t{talkID_hex}${textPosition_decimal}:t`

**Deeper Navigation Patterns (Right Panel):**

-   **Speakers by Letter**: `:pL{letter}` (e.g., `:pLD` for speakers with last name starting with D)
-   **Specific Speaker**: `:p{speakerID_hex}` (e.g., `:p630` for speaker ID 1584)
-   **Journal of Discourses Volume**: `:j{volume_number}` (e.g., `:j01` for Vol. 1, `:j26` for Vol. 26)
-   **Journal of Discourses Discourse**: `#db1:t{discourseID_hex}:j{volume_number}` (e.g., `#db1:t2711:j01`)
-   **Topical Index Letter**: `:i{code}` (e.g., `:i3` for topics starting with A)
-   **Topical Index Topic**: `:i{topicID}` (e.g., `:i6a` for topic "Aaron")
-   **Scriptural Teachings Page**: `#db1:t{talkID_hex}{page_number}:t` (e.g., `#db1:t41eb7:t` for page 7)

**In-Document Navigation:**

-   **Scripture Links in Talk Text**: `#{scriptureReference}:t{talkID_hex}${textPosition_decimal}:c{citationReference}` (updates left panel)
-   **Footnote Links**: In-page anchors like `#note1`, `#note2`, etc. (scroll within talk, no URL change)

### Examples - Scripture Reading

-   Homepage: `/`
-   Genesis (ID 101 = 0x65): `#065::`
-   Genesis Chapter 1: `#06501::`
-   Exodus (ID 102 = 0x66): `#066::`
-   Matthew (ID 140 = 0x8C): `#08C::`
-   Matthew Chapter 5: `#08C05::`
-   Mark (ID 141 = 0x8D): `#08D::`
-   1 Nephi (ID 205 = 0xCD): `#0CD::`
-   1 Nephi Chapter 3: `#0CD03::`
-   Moses (ID 401 = 0x191): `#191::`

### Examples - Citation Index

-   Moroni Ch 10 showing Moroni book citations: `#0db0a::c0db` (Moroni ID 219 = 0xDB, Ch 10 = 0x0A)
-   Moroni Ch 10 showing Moroni Ch 7 citations: `#0db0a::c0db07`
-   Moroni Ch 10 showing Moroni 7:47 citations: `#0db0a::c0db0747`
-   Genesis Ch 1 showing Genesis 1:1 citations: `#06501::c06501` (Genesis ID 101 = 0x65)

### Examples - Talk View

-   "Cheering Each Other On" (Talk ID 8816 = 0x2270) at text position 145145, showing Moroni 7:47 citation:
    `#0db0a:t2270$145145:c0db0747`
    -   Left panel: Moroni Chapter 10
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Citation index for Moroni 7:47

### Examples - Conference Library View (Specific Session)

-   Same talk viewing 2025 October Saturday Morning session:
    `#0d4128b0:t2270$145145:g8c3`
    -   Session ID in database: 1086
    -   URL value: 1086 + 1157 = 2243 = 0x8C3 (hex encoding with base offset)
    -   Left panel: Mosiah Chapter 18 verses 8-10
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Conference library showing October 2025 talks grouped by session

### Examples - Conference Library View (All Sessions)

-   "Cheering Each Other On" with full General Conference library:
    `#db1:t2270$145145:g`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: General Conference library showing all sessions from 1942 to present
        -   List of conferences: 2025-October, 2025-April, 2024-October, etc.

### Examples - Content Library View

-   "Cheering Each Other On" with Content Library navigation menu:
    `#db1:t2270$145145:n`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Content Library with navigation options:
        -   General Conference (1942 to present)
        -   Journal of Discourses (Discourses from the 1800's)
        -   Topical Index (to the Journal of Discourses)
        -   Scriptural Teachings of the Prophet Joseph Smith
        -   Bottom navigation: Citation Index | Library | Speakers | Search

### Examples - Speakers Index View

-   "Cheering Each Other On" with Speakers alphabetical index:
    `#db1:t2270$145145:p`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Alphabetical index of all speakers (A-Z)
        -   Clicking a letter shows all speakers whose last name starts with that letter

### Examples - Search Interface View

-   "Cheering Each Other On" with search interface:
    `#db1:t2270$145145:s`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Search interface with filters:
        -   Search input field
        -   Speaker dropdown (all speakers available)
        -   Year range selectors (1830-2025)
        -   Content source checkboxes: General Conference, Journal of Discourses, Scriptural Teachings
        -   Sort by relevance option
        -   Tabs: Talks | Scriptures

### Examples - Journal of Discourses View

-   "Cheering Each Other On" with Journal of Discourses volumes:
    `#db1:t2270$145145:j`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: List of Journal of Discourses volumes (Vol. 1 through Vol. 26)
        -   Each volume is clickable to view its contents

### Examples - Topical Index View

-   "Cheering Each Other On" with Topical Index:
    `#db1:t2270$145145:i1`
    -   Left panel: Alma Chapter 1
    -   Middle panel: Talk text at character position 145145
    -   Right panel: Alphabetical index for Journal of Discourses topics (0-9, A-Z)
        -   Each letter is clickable to view topics starting with that letter

### Examples - Scripture References in Talk Text

-   Clicking "Mosiah 18:8-10" link within talk text:
    `#0d4128b0:t2270$145145:c0db0747`

    -   Updates left panel to display Mosiah 18:8-10
    -   Middle panel remains on talk at position 145145
    -   Right panel shows citation index for Moroni 7:47

-   Clicking "Matthew 7:12" link within talk text:
    `#0d4128b0:t2270$145145:c08c0712`
    -   Updates left panel to display Matthew 7:12
    -   Middle panel remains on talk
    -   Right panel shows citation index for Matthew 7:12

**Note**: The left panel scripture reference encoding for verse ranges appears to use a complex hexadecimal scheme (e.g., `0d4128b0` represents Mosiah 18:8-10), but the exact encoding formula requires further investigation.

### URL Conversion Formula

```sql
-- Convert Book ID to hex for URL
SELECT printf('#%03X::', ID) as BookURL FROM book WHERE ID = 101;
-- Result: #065::

-- Convert Chapter to URL
SELECT printf('#%03X%02d::', BookID, Chapter) as ChapterURL
FROM scripture WHERE BookID = 101 AND Chapter = 1 LIMIT 1;
-- Result: #06501::

-- Convert Citation Index URL (for a specific verse)
SELECT printf('#%03X%02X::c%03X%02d%02d',
  101, 1,        -- Scripture being read: Genesis Ch 1
  101, 1, 1      -- Citation index: Genesis 1:1
) as CitationURL;
-- Result: #06501::c06501

-- Convert Talk View URL
SELECT printf('#%03X%02X:t%X$%d:c%03X%02d%02d',
  219, 10,       -- Scripture being read: Moroni Ch 10
  8816,          -- Talk ID (hex format)
  145145,        -- Text position in talk
  219, 7, 47     -- Citation: Moroni 7:47
) as TalkURL;
-- Result: #0db0a:t2270$145145:c0db0747

-- Convert Conference Library View URL (with Session)
-- IMPORTANT: Session ID in URL = (Database SessionID + 1157) in hex
SELECT printf('#%03X%02X:t%X$%d:g%x',
  210, 18,       -- Scripture being read: Mosiah Ch 18 (approximate, actual encoding TBD)
  8816,          -- Talk ID (hex format)
  145145,        -- Text position in talk
  1086 + 1157    -- Session ID: Database ID 1086 + offset 1157 = 2243 = 0x8C3
) as ConferenceLibraryURL;
-- Result: #0d212:t2270$145145:g8c3
```

## Database Structure

### Key Tables

-   **book**: Book metadata (ID, abbreviations, names, chapter counts, citation counts)
-   **scripture**: Verse text (BookID, Chapter, Verse, Flag, Text)
-   **next_chapter**: Chapter navigation (BookChapter, NextBookChapter, PrevBookChapter)
-   **citation**: Scripture citations in talks (TalkID, BookID, Chapter, Verses, MinVerse, MaxVerse)
-   **conference_talk**: Conference talk metadata (TalkID, SessionID, StartPageNum, EndPageNum)
-   **speaker**: Speaker information (ID, GivenNames, LastNames, Abbr, Info)
-   **talk**: Talk metadata (ID, Corpus, URL, Title, Date, SpeakerID, AudioUrl, VideoUrl)
-   **talkbody**: Talk full text (TalkID, Text) - stored in `content.52.db`

### Key Concepts

-   **Book IDs**:
    -   Testaments: 1=OT, 2=NT, 3=BM, 4=DC, 5=PGP
    -   Books: 101=Genesis, 140=Matthew, 205=1 Nephi, 219=Moroni, etc.
-   **Chapter IDs**: `bookID * 1000 + chapterNumber` (e.g., Genesis Ch 1 = 101001)
-   **Scripture Flags**:
    -   `S` = Standard text (KJV)
    -   `F` = JST footnoted version
    -   `J` = JST only
    -   `H` = Section header
-   **Citation Tracking**:
    -   Citations link TalkID to scripture references (BookID, Chapter, MinVerse, MaxVerse)
    -   Verses field contains the citation text (e.g., "47" or "47-48")
    -   Speaker table links to TalkID to get speaker names
-   **Talk View URLs**:
    -   Talk IDs are encoded in hexadecimal in URLs (e.g., Talk ID 8816 = 0x2270)
    -   Text positions indicate character offset in the talk body text
    -   Format: `t{talkID_hex}${textPosition_decimal}`
-   **Conference Library View**:
    -   Session IDs are encoded in hexadecimal (e.g., Session 2243 = 0x8C3 for 2025-O)
    -   Format: `:g{sessionID_hex}` shows specific conference session talks
    -   Format: `:g` (without session ID) shows all General Conference sessions from 1942 to present
    -   Right panel displays conference sessions in chronological order
-   **Content Library View**:
    -   Format: `:n` replaces citation index/conference library in right panel
    -   Shows general content navigation menu with options for:
        -   General Conference (1942 to present) - links to `:g`
        -   Journal of Discourses (Discourses from the 1800's) - links to `:j`
        -   Topical Index (to the Journal of Discourses) - links to `:i1`
        -   Scriptural Teachings of the Prophet Joseph Smith
    -   Bottom navigation includes: Citation Index, Library, Speakers, Search
-   **Speakers Index View**:
    -   Format: `:p` shows alphabetical index of all speakers
    -   Right panel displays A-Z letters for browsing speakers by last name
    -   Clicking a letter shows all speakers whose last name starts with that letter
-   **Search Interface View**:
    -   Format: `:s` shows search interface with advanced filters
    -   Search options include:
        -   Text search input field
        -   Speaker filter (dropdown with all speakers)
        -   Year range selector (1830-2025)
        -   Content source checkboxes (General Conference, Journal of Discourses, Scriptural Teachings)
        -   Sort by relevance toggle
        -   Search mode tabs (Talks | Scriptures)
-   **Journal of Discourses View**:
    -   Format: `:j` shows volumes of Journal of Discourses
    -   Right panel displays Vol. 1 through Vol. 26
    -   Each volume is clickable to view discourses within
-   **Topical Index View**:
    -   Format: `:i1` shows alphabetical topical index for Journal of Discourses
    -   Right panel displays 0-9 and A-Z index
    -   Clicking a letter/number shows topics starting with that character
-   **Dynamic Scripture Links**:
    -   Scripture references within talk text are clickable links
    -   Clicking updates left panel to show the referenced scripture
    -   URL pattern updates left panel reference while maintaining talk and right panel state
-   **Footnotes**:
    -   Footnotes use standard HTML anchor links (`#note1`, `#note2`, etc.)
    -   Scroll to footnote section at bottom of talk without changing main URL

## Navigation Queries

### 1. Get all top-level scripture categories

```sql
SELECT ID, Abbr, FullName, CitationCount
FROM book
WHERE ParentBookID IS NULL OR ParentBookID = 0
ORDER BY ID;
```

**Sample URLs from this query:**

-   Old Testament (ID 1): No direct URL - navigate via first book like Genesis `#065::`
-   New Testament (ID 2): No direct URL - navigate via first book like Matthew `#08C::`
-   Book of Mormon (ID 3): No direct URL - navigate via first book like 1 Nephi `#0CD::`

### 2. Get all books under a specific testament

```sql
-- Old Testament (ParentBookID = 1)
SELECT ID, Abbr, CiteAbbr, FullName, NumChapters, CitationCount
FROM book
WHERE ParentBookID = 1
ORDER BY ID;

-- Use ParentBookID: 1=OT, 2=NT, 3=BM, 4=DC, 5=PGP
```

**Sample URLs from this query (Old Testament books):**

-   Genesis (ID 101 = 0x65): `#065::`
-   Exodus (ID 102 = 0x66): `#066::`
-   Leviticus (ID 103 = 0x67): `#067::`

### 3. Get book details by abbreviation

```sql
SELECT ID, Abbr, FullName, NumChapters, URLPath, ParentBookID
FROM book
WHERE Abbr = 'gen';
```

**Sample URL from this query:**

-   Genesis (result of query, ID 101): `#065::`

### 4. Get book navigation breadcrumb

```sql
SELECT b1.ID as BookID, b1.FullName as BookName,
       b2.ID as ParentID, b2.FullName as ParentName
FROM book b1
LEFT JOIN book b2 ON b1.ParentBookID = b2.ID
WHERE b1.ID = 101;  -- Genesis
```

**Sample URL from this query:**

-   Genesis (BookID 101, ParentID 1): `#065::`

### 5. Get sequential position of books

```sql
SELECT ROW_NUMBER() OVER (ORDER BY ID) as Position,
       ID, Abbr, FullName, ParentBookID
FROM book
WHERE ParentBookID >= 1 AND ParentBookID <= 5
ORDER BY ID;
```

**Sample URLs from this query:**

-   Position 1 - Genesis (ID 101): `#065::`
-   Position 40 - Matthew (ID 140): `#08C::`
-   Position 66 - 1 Nephi (ID 205): `#0CD::`

## Chapter Queries

### 6. Get chapter list for a specific book

```sql
SELECT DISTINCT Chapter,
       COUNT(*) as VerseCount
FROM scripture
WHERE BookID = 101  -- Genesis
  AND (Flag IS NULL OR Flag = 'S')
GROUP BY Chapter
ORDER BY Chapter;
```

**Sample URLs from this query (Genesis chapters):**

-   Chapter 1: `#06501::`
-   Chapter 2: `#06502::`
-   Chapter 50: `#06550::`

### 7. Navigate to next/previous chapter

```sql
SELECT BookChapter, NextBookChapter, PrevBookChapter
FROM next_chapter
WHERE BookChapter = 101001;  -- Genesis Chapter 1
```

**Sample URLs from this query (Genesis Chapter 1 navigation):**

-   Current chapter (101001): `#06501::`
-   Next chapter (101002): `#06502::`
-   Previous chapter: None (first chapter in Bible)

## Verse Queries

### 8. Get all verses for a specific chapter (KJV)

```sql
SELECT Verse, Text
FROM scripture
WHERE BookID = 101
  AND Chapter = 1
  AND Flag = 'S'  -- S = Standard (KJV)
ORDER BY Verse;
```

**Sample URL for this query:**

-   Genesis Chapter 1 (contains verses 1-31): `#06501::`

### 9. Get all verses for a specific chapter (JST)

```sql
SELECT Verse, Text
FROM scripture
WHERE BookID = 101
  AND Chapter = 1
  AND Flag IN ('F', 'J')  -- F = JST footnoted, J = JST only
ORDER BY Verse;
```

**Sample URL for this query:**

-   Genesis Chapter 1 JST (contains JST variants): `#06501::`

### 10. Get a specific verse

```sql
SELECT ID, BookID, Chapter, Verse, Flag, Text
FROM scripture
WHERE BookID = 101
  AND Chapter = 1
  AND Verse = 1
  AND Flag = 'S';
```

**Sample URL for this query:**

-   Genesis 1:1 (displayed within chapter view): `#06501::`

## Citation Queries

### 11. Get citation counts for all books in a testament

```sql
SELECT b.Abbr, b.FullName, b.CitationCount
FROM book b
WHERE b.ParentBookID = 3  -- Book of Mormon
ORDER BY b.ID;
```

**Sample URLs from this query (Book of Mormon books):**

-   1 Nephi (ID 205 = 0xCD): `#0CD::`
-   2 Nephi (ID 206 = 0xCE): `#0CE::`
-   Alma (ID 212 = 0xD4): `#0D4::`

### 12. Get all citations for a specific verse

```sql
SELECT c.ID, c.TalkID, c.BookID, c.Chapter, c.Verses,
       s.GivenNames, s.LastNames
FROM citation c
JOIN speaker s ON c.TalkID = s.ID
WHERE c.BookID = 219    -- Moroni
  AND c.Chapter = 7
  AND c.MinVerse <= 47
  AND c.MaxVerse >= 47
ORDER BY c.ID DESC
LIMIT 10;
```

**Sample URL for this query:**

-   Citation index for Moroni 7:47: `#0db0a::c0db0747` (view from any chapter)

### 13. Get citation count by verse for a chapter

```sql
SELECT MinVerse as Verse, COUNT(*) as CitationCount
FROM citation
WHERE BookID = 219  -- Moroni
  AND Chapter = 7
GROUP BY MinVerse
ORDER BY MinVerse;
```

**Sample URLs from this query:**

-   Moroni 7:12 (23 citations): `#0db07::c0db0712`
-   Moroni 7:47 (85 citations): `#0db07::c0db0747`
-   Moroni 7:48 (84 citations): `#0db07::c0db0748`

### 14. Get talk details for citations

```sql
SELECT c.BookID, c.Chapter, c.Verses,
       s.GivenNames || ' ' || s.LastNames as Speaker,
       ct.StartPageNum, ct.SessionID
FROM citation c
JOIN speaker s ON c.TalkID = s.ID
JOIN conference_talk ct ON c.TalkID = ct.TalkID
WHERE c.BookID = 219
  AND c.Chapter = 7
  AND c.MinVerse = 47
LIMIT 5;
```

**Sample URL for this query:**

-   Moroni 7:47 citations: `#0db07::c0db0747`

## Talk Queries

### 15. Get talk details by ID

```sql
SELECT t.ID, t.Title, t.Date, t.Corpus,
       s.GivenNames, s.LastNames
FROM talk t
LEFT JOIN speaker s ON t.SpeakerID = s.ID
WHERE t.ID = 8816;  -- "Cheering Each Other On"
```

**Sample URL for this query:**

-   Talk 8816 viewing Moroni 7:47: `#0db0a:t2270$145145:c0db0747` (Talk ID 8816 = 0x2270)

### 16. Get talk text with citation

```sql
SELECT t.ID, t.Title,
       tb.Text as TalkBody,
       SUBSTR(tb.Text, 145145, 100) as TextAtPosition
FROM talk t
JOIN talkbody tb ON t.ID = tb.TalkID
WHERE t.ID = 8816;
```

**Sample URL for this query:**

-   Position 145145 in talk 8816: `#0db0a:t2270$145145:c0db0747`

### 17. Find talks by speaker

```sql
SELECT t.ID, t.Title, t.Date,
       s.GivenNames, s.LastNames
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
WHERE s.LastNames = 'Dennis'
  AND s.GivenNames LIKE '%Anette%'
ORDER BY t.Date DESC;
```

**Sample URLs from this query:**

-   Talk 8816 (2025): `#0db0a:t2270$0:c0db0747`
-   Other talks by J. Anette Dennis (with their respective hex IDs)

### 18. Get all citations within a specific talk

```sql
SELECT c.BookID, c.Chapter, c.Verses, c.MinVerse, c.MaxVerse,
       b.FullName
FROM citation c
JOIN book b ON c.BookID = b.ID
WHERE c.TalkID = 8816
ORDER BY c.BookID, c.Chapter, c.MinVerse;
```

**Sample URL for first citation:**

-   First citation in talk 8816: `#0db0a:t2270$0:c{bookID_hex}{chapter}{verse}`

## Conference Session Queries

### 19. Get all talks in a conference session

```sql
SELECT t.ID, t.Title, t.Date,
       s.GivenNames, s.LastNames,
       ct.SessionID, ct.StartPageNum
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
JOIN conference_talk ct ON t.ID = ct.TalkID
WHERE ct.SessionID = 2243  -- 2025 October conference
ORDER BY ct.StartPageNum;
```

**Sample URL for this query:**

-   Conference library for 2025-O session: `#0d4128b0:t2270$145145:g8c3` (Session ID 2243 = 0x8C3)

### 20. Get conference session details from talk ID

```sql
SELECT ct.SessionID, t.Date, t.Corpus
FROM conference_talk ct
JOIN talk t ON ct.TalkID = t.ID
WHERE ct.TalkID = 8816;
```

**Sample URL from this query:**

-   Show session library for talk 8816's conference: `#0d4128b0:t2270$145145:g8c3`

## Examples

### Genesis Chapter 1, Verse 1 (KJV)

```sql
SELECT Text
FROM scripture
WHERE BookID = 101 AND Chapter = 1 AND Verse = 1 AND Flag = 'S';
-- Result: "In the beginning God created the heaven and the earth."
```

**URL:** `#06501::` (verse displayed in chapter view)

### Get all Book of Mormon books with citation counts

```sql
SELECT ID, Abbr, FullName, NumChapters, CitationCount
FROM book
WHERE ParentBookID = 3
ORDER BY ID;
```

**Sample URLs from results:**

-   1 Nephi (ID 205): `#0CD::`
-   Mosiah (ID 210): `#0D2::`
-   Moroni (ID 218): `#0DA::`

### Calculate Chapter ID from Book and Chapter

```sql
-- Genesis (BookID=101) Chapter 1
-- ChapterID = 101 * 1000 + 1 = 101001
SELECT 101 * 1000 + 1 as ChapterID;
```

**URL for Genesis Chapter 1:** `#06501::`

---

Last Updated: 2025-11-27

## Deeper Navigation Patterns

### Conference Library Session Navigation

**Pattern**: Starting from `:g` (all conferences view), clicking a specific conference session updates the URL to include the session ID in hexadecimal.

**Example URL Progression:**

1. General Conference library (all sessions): `#db1:t2270$145145:g`
2. Click "2025-October" → `#db1:t2270$145145:g8c3` (Session ID 2243 = 0x8C3)
3. Click a specific talk → `#db1:t2270:g8c3` (text position removed, shows talk from beginning)

**What displays:**

-   Right panel shows all talks in the 2025-October conference, organized by session time:
    -   Saturday Morning
    -   Saturday Afternoon
    -   Saturday Evening
    -   Sunday Morning
    -   Sunday Afternoon
-   Each talk is listed with speaker name and title
-   Clicking a talk navigates to that talk while keeping the conference library visible

**SQL Query to Find Session ID:**

```sql
-- Find Session ID for a specific conference
SELECT DISTINCT ct.SessionID,
       printf('g%x', ct.SessionID) as URLSuffix,
       t.Date,
       COUNT(*) as TalkCount
FROM conference_talk ct
JOIN talk t ON ct.TalkID = t.ID
WHERE t.Date LIKE '2025-10%'  -- October 2025
GROUP BY ct.SessionID;
-- Result: SessionID=2243, URLSuffix=g8c3
```

**SQL Query to List All Talks in a Session:**

```sql
-- Get all talks in the 2025-October conference session
SELECT t.ID,
       printf('t%x', t.ID) as TalkURLCode,
       t.Title,
       s.GivenNames || ' ' || s.LastNames as Speaker,
       ct.StartPageNum,
       ct.SessionID
FROM conference_talk ct
JOIN talk t ON ct.TalkID = t.ID
JOIN speaker s ON t.SpeakerID = s.ID
WHERE ct.SessionID = 2243  -- 2025-October (0x8C3)
ORDER BY ct.StartPageNum;
-- Use TalkURLCode in format: #db1:t{TalkURLCode}:g8c3
```

### Speakers Index Navigation

**Pattern**: `:p` displays an alphabetical index (A-Z) of all speakers.

**URL Patterns:**

1. Main speakers index: `#db1:t2270$145145:p`
2. Speakers by letter: `#db1:t2270$145145:pL{letter}` (e.g., `:pLD` for letter D)
3. Specific speaker: `#db1:t2270$145145:p{speakerID_hex}` (e.g., `:p630` for speaker ID 1584)

**Example URL Progression:**

1. Speakers alphabetical index: `#db1:t2270$145145:p`
2. Click "D" → `#db1:t2270$145145:pLD`
3. Click "Dennis, J. Anette" → `#db1:t2270$145145:p630` (Speaker ID 1584 = 0x630)

**What displays:**

-   `:p` - Right panel shows clickable letters A through Z
-   `:pL{letter}` - Right panel shows all speakers whose last name starts with that letter
-   `:p{speakerID_hex}` - Right panel shows all talks by that specific speaker

**SQL Query to Find Speaker ID:**

```sql
-- Find Speaker ID by name
SELECT ID,
       printf('p%x', ID) as URLSuffix,
       GivenNames,
       LastNames
FROM speaker
WHERE LastNames = 'Dennis'
  AND GivenNames LIKE '%Anette%';
-- Result: ID=1584, URLSuffix=p630
```

**SQL Query to List All Talks by a Speaker:**

```sql
-- Get all talks by a specific speaker
SELECT t.ID,
       printf('t%x', t.ID) as TalkURLCode,
       t.Title,
       t.Date,
       s.GivenNames || ' ' || s.LastNames as Speaker
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
WHERE s.ID = 1584  -- J. Anette Dennis
ORDER BY t.Date DESC;
-- Use TalkURLCode in format: #db1:t{TalkURLCode}:p630
```

### Journal of Discourses Navigation

**Pattern**: `:j` displays volumes of Journal of Discourses.

**URL Patterns:**

1. Main volumes index: `#db1:t2270$145145:j`
2. Specific volume: `#db1:t2270$145145:j{volume_number}` (e.g., `:j01` for Volume 1, `:j26` for Volume 26)
3. Specific discourse within volume: `#db1:t{discourseID_hex}:j{volume_number}` (e.g., `#db1:t2711:j01`)

**Example URL Progression:**

1. Journal of Discourses volumes list: `#db1:t2270$145145:j`
2. Click "Vol. 1" → `#db1:t2270$145145:j01`
3. Click first discourse (Brigham Young - Salvation) → `#db1:t2711:j01` (Discourse ID 10001 = 0x2711)

**What displays:**

-   `:j` - Right panel shows Vol. 1 through Vol. 26 clickable links
-   `:j{volume}` - Right panel shows all discourses in that volume with speaker and title
-   `t{discourseID}:j{volume}` - Middle panel shows the discourse text, right panel maintains volume navigation

**SQL Query to Find Journal of Discourses Volumes:**

```sql
-- Get all Journal of Discourses volumes
-- Note: Volume information may be stored in talk metadata or separate table
-- This query retrieves talks from the Journal of Discourses corpus
SELECT DISTINCT t.ID,
       printf('t%x', t.ID) as TalkURLCode,
       t.Title,
       s.GivenNames || ' ' || s.LastNames as Speaker
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
WHERE t.Corpus = 'Journal of Discourses'
ORDER BY t.ID
LIMIT 20;
-- Use TalkURLCode in format: #db1:t{TalkURLCode}:j01
```

**SQL Query to List Discourses in Volume 1:**

```sql
-- Get all discourses in Journal of Discourses Volume 1
-- Volume information may be encoded in a separate field or table
-- This query shows the pattern for accessing discourse metadata
SELECT t.ID,
       printf('t%x', t.ID) as TalkURLCode,
       t.Title,
       t.Date,
       s.GivenNames || ' ' || s.LastNames as Speaker
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
WHERE t.Corpus = 'Journal of Discourses'
  AND t.ID >= 10001  -- First discourse in Vol. 1
  AND t.ID < 10100   -- Approximate range for Vol. 1
ORDER BY t.ID;
-- Example: Discourse ID 10001 = 0x2711 → URL: #db1:t2711:j01
```

### Topical Index Navigation

**Pattern**: `:i1` displays the alphabetical topical index for Journal of Discourses.

**URL Patterns:**

1. Main topical index: `#db1:t2270$145145:i1` (shows 0-9, A-Z index)
2. Topics by letter: Pattern appears to be `:i{code}` (e.g., `:i3` for letter A)
3. Specific topic: Pattern appears to be `:i{topicID_hex}` (e.g., `:i6a` for "Aaron")

**Example URL Progression:**

1. Topical index main page: `#db1:t2270$145145:i1`
2. Click "A" → `#db1:t2270$145145:i3`
3. Click "Aaron" topic → `#db1:t2270$145145:i6a`

**What displays:**

-   `:i1` - Right panel shows 0-9 and A-Z clickable index
-   `:i3` - Right panel shows all topics starting with letter A
-   `:i{topicID}` - Right panel shows Journal of Discourses references for that topic

**Note**: The exact encoding scheme for `:i{code}` patterns requires further investigation. The codes `:i1` (main index), `:i3` (letter A), and `:i6a` (topic "Aaron") suggest a numeric system, but the full pattern is not yet clear.

**SQL Query Pattern:**

```sql
-- Note: The topical index may be stored in a separate table
-- or as metadata in the database. This query pattern is speculative
-- and would need to be verified against the actual schema.
SELECT * FROM topical_index
WHERE Letter = 'A'
ORDER BY Topic;
-- Would map to URL suffix: :i3 for letter A topics
```

### Scriptural Teachings Navigation

**Pattern**: `:t` displays the "Scriptural Teachings of the Prophet Joseph Smith" page index.

**URL Patterns:**

1. Main page index: `#db1:t2270$145145:t` (shows all sections and page numbers)
2. Specific page: `#db1:t{talkID_hex}{page_number}:t` (e.g., `#db1:t41eb1:t` for page 1)

**Example URL Progression:**

1. Scriptural Teachings page index: `#db1:t2270$145145:t`
2. Click "1" (page 1) → `#db1:t41eb1:t` (Talk ID 16875 = 0x41EB for Scriptural Teachings)
3. Click "7" (page 7) → `#db1:t41eb7:t`

**What displays:**

-   `:t` - Right panel shows organized index of Scriptural Teachings:
    -   Title and Introduction (pages 1-4)
    -   Section One: 1830-1834 (pages 7-43)
    -   Section Two: 1834-1837 (pages 47-113)
    -   Section Three: 1838-1839 (pages 117-151)
    -   Section Four: 1839-1842 (pages 155-233)
    -   Section Five: 1842-1843 (pages 237-281)
    -   Section Six: 1843-1844 (pages 285-395)
-   `t{talkID}{page}:t` - Left panel shows the page content, right panel maintains the page index navigation

**SQL Query to Find Scriptural Teachings Talk ID:**

```sql
-- Find the Talk ID for Scriptural Teachings of the Prophet Joseph Smith
SELECT ID,
       printf('t%x', ID) as TalkURLCode,
       Title,
       Corpus
FROM talk
WHERE Title LIKE '%Scriptural Teachings%Prophet Joseph Smith%'
   OR Title LIKE '%Teachings of the Prophet Joseph Smith%';
-- Result: ID=16875, URLSuffix=t41eb
-- Page URLs: t41eb1 (page 1), t41eb7 (page 7), etc.
```

**URL Pattern Formula:**

```sql
-- Generate URL for specific page of Scriptural Teachings
-- TalkID = 16875 (0x41EB)
-- Page number is appended in decimal
SELECT printf('#db1:t%x%d:t', 16875, 1) as Page1URL;
-- Result: #db1:t41eb1:t

SELECT printf('#db1:t%x%d:t', 16875, 7) as Page7URL;
-- Result: #db1:t41eb7:t

SELECT printf('#db1:t%x%d:t', 16875, 395) as Page395URL;
-- Result: #db1:t41eb395:t
```

## Additional Notes

### Print Functionality

-   Print links trigger browser print dialog via `javascript:void(0);`
-   No URL pattern associated with printing
-   Prints the current talk content from the middle panel

### Unresolved Patterns

-   **Verse Range Encoding**: The exact hexadecimal encoding for verse ranges (e.g., `0d4128b0` for Mosiah 18:8-10) requires additional investigation. It appears to use a different scheme than the simple book/chapter/verse encoding used elsewhere.
-   **Watch/Listen Links**: These link to external churchofjesuschrist.org resources for video/audio playback, not part of the internal URL scheme.

---

## Journal of Discourses Topical Index (Priority 1 Research - COMPLETE)

### Overview

The Journal of Discourses Topical Index provides hierarchical navigation to topics discussed in the 19th-century Journal of Discourses. The system uses three interconnected tables to organize topics, citations, and cross-references.

### Database Tables

#### Table: `jdtopic`

Hierarchical topic structure with 46,191 total entries.

**Schema:**

-   `ID` (INT, PRIMARY KEY) - Unique topic identifier
-   `ParentID` (INT) - Parent topic ID for hierarchical organization
-   `TopicText` (TEXT) - The topic name or heading
-   `TargetID` (INT) - References either jdcite.ID or jdalso.ID depending on TargetType
-   `TargetType` (TEXT) - Type of topic entry: 'X' (heading), 'C' (citation), 'A' (cross-reference)

**TargetType Values:**

-   **'X'** (11,035 entries): Category headers and groupings with no direct content
-   **'C'** (35,041 entries): Topics with citations, TargetID points to jdcite.ID
-   **'A'** (115 entries): "See also" cross-references, TargetID points to jdalso.ID

**Hierarchy Structure:**

-   Root: ID 1 (Journal of Discourses Topical Index)
-   Top-level sections: IDs 2-27 (0-9, A-Z)
    -   ID 2: "0–9"
    -   ID 3: "A"
    -   ID 4: "B"
    -   ID 5: "C"
    -   ... through ID 27: "Z"
-   Content topics start at ID 100+

#### Table: `jdcite`

Citation records linking topics to specific Journal of Discourses locations (54,780 total entries).

**Schema:**

-   `ID` (INT, PRIMARY KEY) - Unique citation identifier
-   `JdtopicID` (INT) - References jdtopic.ID
-   `SpeakerID` (INT) - References speaker.ID
-   `Pages` (TEXT) - Page range citation (e.g., "60", "332–333")
-   `TargetVolume` (INT) - Journal of Discourses volume number
-   `TargetPage` (INT) - Starting page number in volume
-   `TargetDiscourse` (INT) - Discourse number within volume

#### Table: `jdalso`

Cross-reference records for "see also" navigation (479 total entries).

**Schema:**

-   `ID` (INT, PRIMARY KEY) - Unique cross-reference identifier
-   `AlsoText` (TEXT) - Display text (e.g., "see also Abortion", "see Birth control")
-   `JdtopicID` (INT) - Source topic ID (references jdtopic.ID)
-   `TargetJdtopicID` (INT) - Target topic ID (references jdtopic.ID)

### URL Patterns

#### Basic Topical Index Navigation

-   **Main topical index**: `:i1` - Shows 0-9, A-Z alphabetical navigation
-   **Letter sections**: `:i{sectionID}` - Shows topics starting with specific letter
    -   `:i2` - Topics starting with 0-9 (section ID 2)
    -   `:i3` - Topics starting with A (section ID 3)
    -   `:i4` - Topics starting with B (section ID 4)
    -   etc.
-   **Specific topic**: `:i{topicID}` - Shows topic details and citations
    -   Example: `:i107` - Topic "Aaronic Priesthood" (ID 107)
    -   Example: `:i263` - Topic "Defense" (ID 263)

#### Topical Index with Talk View

-   **Format**: `#{scripture}:t{talkID_hex}${textPosition}:i{topicID}`
-   **Example**: `#db1:t2719$60a:i3`
    -   Left panel: Alma Chapter 1
    -   Middle panel: JD Discourse ID 10009 (0x2719), page 60, column a
    -   Right panel: Topics starting with "A" (section ID 3)

#### Clicking a Topic Citation

-   **Format**: `#{scripture}:t{talkID_hex}${textPosition}:i{topicID}`
-   **Example**: Clicking "Abrahamic Promise" from `:i3` navigates to:
    -   `#db1:t2719$60a:i3`
    -   TalkID 10009 (hex 0x2719) = JD Discourse 9, Volume 1, Page 60, column a

### SQL Queries

#### 1. Get Topical Index Root and Top-Level Sections

```sql
-- Get the root index and alphabetical sections
SELECT ID, ParentID, TopicText, TargetType
FROM jdtopic
WHERE ParentID IN (0, 1)
ORDER BY ID;
```

**Results map to URLs:**

-   ID 1 (root) → `:i1` (main alphabetical index)
-   ID 2 (0-9) → `:i2`
-   ID 3 (A) → `:i3`
-   ID 4 (B) → `:i4`
-   etc.

#### 2. Get All Topics in a Specific Letter Section

```sql
-- Get all topics starting with "A" (ParentID = 3)
SELECT ID, TopicText, TargetID, TargetType
FROM jdtopic
WHERE ParentID = 3
ORDER BY ID;
```

**Sample results:**

-   ID 106: "Aaron" (Type X - heading with no citations)
-   ID 107: "Aaronic Priesthood" (Type X - has subtopics)
-   ID 111: "Abrahamic Promise" (Type C - has citations, TargetID = 314)

**URLs:**

-   `:i3` shows this list
-   `:i111` navigates to "Abrahamic Promise" with citations

#### 3. Get Topic with Citation Details

```sql
-- Get topic "Abrahamic Promise" with its citation
SELECT
    t.ID as TopicID,
    t.TopicText,
    t.TargetType,
    c.ID as CitationID,
    c.TargetVolume,
    c.TargetPage,
    c.TargetDiscourse,
    c.Pages,
    s.GivenNames,
    s.LastNames
FROM jdtopic t
LEFT JOIN jdcite c ON t.TargetID = c.ID AND t.TargetType = 'C'
LEFT JOIN speaker s ON c.SpeakerID = s.ID
WHERE t.ID = 111;
```

**Result:**

-   TopicID: 111
-   TopicText: "Abrahamic Promise"
-   TargetVolume: 1 (Journal of Discourses Vol. 1)
-   TargetPage: 60
-   TargetDiscourse: 9
-   Speaker: "Orson Pratt"

**URL generated:** `#db1:t2719$60a:i3`

-   Talk ID 10009 (JD Discourse 9) = 0x2719
-   Text position $60a = page 60, column a

#### 4. Get Topic with "See Also" Cross-References

```sql
-- Get topic "Abortion" with cross-references
SELECT
    t.ID as TopicID,
    t.TopicText,
    a.AlsoText,
    a.TargetJdtopicID,
    target.TopicText as TargetTopicText
FROM jdtopic t
LEFT JOIN jdalso a ON t.ID = a.JdtopicID
LEFT JOIN jdtopic target ON a.TargetJdtopicID = target.ID
WHERE t.ID = 109;
```

**Results:**

-   Topic 109: "Abortion"
-   Cross-references:
    -   "see also Birth control" → Topic 263
    -   "see also Infanticide" → Topic 1130
    -   "see also Murder" → Topic 1524

**URLs:**

-   `:i109` shows "Abortion" with "see also" links
-   Clicking "see also Birth control" navigates to `:i263`

#### 5. Get All Citations for a Topic

```sql
-- Get all Journal of Discourses citations for "Aaronic Priesthood"
SELECT
    c.ID as CitationID,
    c.Pages,
    c.TargetVolume,
    c.TargetPage,
    c.TargetDiscourse,
    s.GivenNames || ' ' || s.LastNames as Speaker,
    t.ID as TalkID,
    printf('t%x', t.ID) as TalkHexID,
    printf('#db1:t%x$%da:i%d', t.ID, c.TargetPage, jdt.ID) as GeneratedURL
FROM jdtopic jdt
JOIN jdcite c ON jdt.TargetID = c.ID AND jdt.TargetType = 'C'
JOIN speaker s ON c.SpeakerID = s.ID
JOIN talk t ON t.ID = (10000 + c.TargetDiscourse)
WHERE jdt.ParentID = 107  -- Get subtopics under "Aaronic Priesthood"
ORDER BY c.TargetVolume, c.TargetPage
LIMIT 10;
```

**Sample URLs generated:**

-   Citation to JD Vol. 1, Discourse 9, Page 60 → `#db1:t2719$60a:i107`
-   Citation to JD Vol. 4, Discourse 50, Page 209 → `#db1:t274a$209a:i107`

#### 6. Generate URL for Any Topic Citation

```sql
-- Universal URL generator for topical index citations
SELECT
    jdt.ID as TopicID,
    jdt.TopicText,
    c.TargetVolume,
    c.TargetPage,
    c.TargetDiscourse,
    s.LastNames as Speaker,
    -- Calculate Talk ID (JD discourses start at 10001)
    (10000 + c.TargetDiscourse) as TalkID,
    -- Generate complete URL
    printf('#db1:t%x$%da:i%d',
        (10000 + c.TargetDiscourse),  -- Talk ID in hex
        c.TargetPage,                  -- Page number
        jdt.ID                         -- Topic ID
    ) as TopicalIndexURL
FROM jdtopic jdt
JOIN jdcite c ON jdt.TargetID = c.ID
JOIN speaker s ON c.SpeakerID = s.ID
WHERE jdt.ID = 111;  -- "Abrahamic Promise"
```

**Result:**

-   TopicID: 111
-   TopicText: "Abrahamic Promise"
-   TalkID: 10009 (hex 2719)
-   URL: `#db1:t2719$60a:i111`

#### 7. Find Topics by Keyword

```sql
-- Search for topics containing "priesthood"
SELECT ID, TopicText, ParentID, TargetType,
       printf(':i%d', ID) as URLSuffix
FROM jdtopic
WHERE TopicText LIKE '%priesthood%'
  AND ParentID > 1  -- Exclude root and letter headers
ORDER BY TopicText;
```

**Sample results:**

-   ID 107: "Aaronic Priesthood" → `:i107`
-   ID 1508: "Melchizedek Priesthood" → `:i1508`
-   ID 1736: "Priesthood" → `:i1736`

#### 8. Get Hierarchical Topic Structure

```sql
-- Get topic with its full hierarchy path
WITH RECURSIVE topic_path AS (
    -- Base case: start with a specific topic
    SELECT ID, ParentID, TopicText, 0 as Level
    FROM jdtopic
    WHERE ID = 10020  -- "Angels seen by obedient members of"

    UNION ALL

    -- Recursive case: get parent topics
    SELECT t.ID, t.ParentID, t.TopicText, tp.Level + 1
    FROM jdtopic t
    JOIN topic_path tp ON t.ID = tp.ParentID
    WHERE t.ParentID IS NOT NULL
)
SELECT ID, TopicText, Level
FROM topic_path
ORDER BY Level DESC;
```

**Sample result:**

-   Level 0: "Journal of Discourses Topical Index" (ID 1)
-   Level 1: "A" (ID 3)
-   Level 2: "Aaronic Priesthood" (ID 107)
-   Level 3: "Angels seen by obedient members of" (ID 10020)

#### 9. Count Citations by Topic Type

```sql
-- Statistics on topic organization
SELECT
    TargetType,
    COUNT(*) as Count,
    CASE TargetType
        WHEN 'X' THEN 'Category Headers'
        WHEN 'C' THEN 'Topics with Citations'
        WHEN 'A' THEN 'Cross-References'
    END as Description
FROM jdtopic
GROUP BY TargetType
ORDER BY Count DESC;
```

**Results:**

-   Type C: 35,041 topics with citations
-   Type X: 11,035 category headers
-   Type A: 115 "see also" cross-references
-   **Total**: 46,191 entries

#### 10. Find Most Referenced Topics

```sql
-- Topics with the most citation entries
SELECT
    jdt.ID,
    jdt.TopicText,
    COUNT(DISTINCT c.ID) as CitationCount,
    printf(':i%d', jdt.ID) as URLSuffix
FROM jdtopic jdt
LEFT JOIN jdcite c ON jdt.TargetID = c.ID AND jdt.TargetType = 'C'
WHERE jdt.TargetType = 'C'
GROUP BY jdt.ID, jdt.TopicText
ORDER BY CitationCount DESC
LIMIT 20;
```

### URL Pattern Formula

#### For Topic List View

```sql
-- Navigate to topics starting with letter "A"
SELECT printf('#db1::i%d', ID) as URL
FROM jdtopic
WHERE TopicText = 'A' AND ParentID = 1;
-- Result: #db1::i3
```

#### For Specific Topic with Citation

```sql
-- Navigate to a specific topic and show its first citation
SELECT printf('#db1:t%x$%da:i%d',
    (10000 + c.TargetDiscourse),  -- JD discourse Talk ID
    c.TargetPage,                  -- Page number
    t.ID                           -- Topic ID
) as URL
FROM jdtopic t
JOIN jdcite c ON t.TargetID = c.ID
WHERE t.ID = 111  -- "Abrahamic Promise"
LIMIT 1;
-- Result: #db1:t2719$60a:i111
```

### Navigation Examples

#### Example 1: Browse Topics by Letter

1. Start: `#db1::i1` (Main index)
2. Click "A": `#db1::i3` (Shows all "A" topics)
3. Click "Aaronic Priesthood": `#db1::i107` (Shows subtopics)
4. Click a subtopic citation: `#db1:t{talkID}${page}a:i{subtopicID}`

#### Example 2: Follow Cross-References

1. View topic: `#db1::i109` ("Abortion")
2. See "see also Birth control"
3. Click link: `#db1::i263` ("Birth control" topic)

#### Example 3: View Topic Citation

1. From topic list: `#db1::i3` ("A" topics)
2. Click "Abrahamic Promise"
3. View citation: `#db1:t2719$60a:i111`
    - Middle panel: JD Vol. 1, Discourse 9, Page 60, Orson Pratt
    - Right panel: "Abrahamic Promise" topic details

### Key Insights

1. **Direct ID Mapping**: The `:i{topicID}` pattern uses the actual jdtopic.ID value directly
2. **Hierarchical Structure**: Topics are organized in a tree with root → letters → topics → subtopics
3. **Three Entry Types**:
    - Headers (X) organize the index
    - Citations (C) link to actual discourse content
    - Cross-references (A) connect related topics
4. **Talk ID Calculation**: For JD discourses, Talk ID = 10000 + DiscourseNumber
5. **Text Position Format**: `$60a` = page 60, column a (left column)

### Integration with Other Tables

```sql
-- Complete topic citation with talk and speaker details
SELECT
    jdt.ID as TopicID,
    jdt.TopicText,
    c.TargetVolume as Volume,
    c.TargetPage as Page,
    c.Pages as PageRange,
    c.TargetDiscourse as DiscourseNum,
    t.ID as TalkID,
    t.Title as DiscourseTitle,
    s.GivenNames || ' ' || s.LastNames as Speaker,
    printf('#db1:t%x$%da:i%d', t.ID, c.TargetPage, jdt.ID) as URL
FROM jdtopic jdt
JOIN jdcite c ON jdt.TargetID = c.ID AND jdt.TargetType = 'C'
JOIN speaker s ON c.SpeakerID = s.ID
JOIN talk t ON t.ID = (10000 + c.TargetDiscourse)
WHERE jdt.ID = 111;
```

This comprehensive topical index system enables:

-   Hierarchical topic browsing
-   Direct navigation to discourse citations
-   Cross-reference discovery
-   Programmatic URL generation for any topic or citation

---

## Conference Sessions (`conf_session` and `conference` tables)

### Table Schemas

#### `conf_session` Table

```sql
-- Schema: ID, Description, Abbr, Date, Sequence, ConferenceID
--
-- Individual conference sessions (e.g., "Saturday Morning Session", "Sunday Afternoon Session")
-- Links to parent conference via ConferenceID
-- Sequence determines the order of sessions within a conference
```

#### `conference` Table

```sql
-- Schema: ID, Description, Abbr, Year, Annual, IssueDate
--
-- Conference metadata (year and type)
-- Annual values: 'A' = April General Conference, 'S' = October (Semi-Annual) General Conference
```

### URL Encoding Formula

**CRITICAL**: Session IDs in URLs use a base offset of **+1157**

```
URL hex value = (Database SessionID + 1157) converted to hexadecimal
```

**Example:**

-   Database Session ID: 1086 (Saturday Morning, October 2025)
-   URL Calculation: 1086 + 1157 = 2243 = 0x8C3
-   URL Pattern: `:g8c3`

### SQL Queries

#### Get All Sessions for a Specific Conference

```sql
-- Get all sessions for October 2025 conference
SELECT
    cs.ID as SessionID,
    cs.ID + 1157 as URLValue,
    printf('0x%X', cs.ID + 1157) as URLHex,
    cs.Description,
    cs.Abbr,
    cs.Date,
    cs.Sequence,
    c.Year,
    c.Annual,
    c.Description as ConferenceName
FROM conf_session cs
JOIN conference c ON cs.ConferenceID = c.ID
WHERE c.Year = 2025 AND c.Annual = 'S'
ORDER BY cs.Sequence;

-- Results:
-- SessionID | URLValue | URLHex | Description
-- 1086      | 2243     | 0x8C3  | Saturday Morning Session, 4 Oct 2025
-- 1087      | 2244     | 0x8C4  | Saturday Afternoon Session, 4 Oct 2025
-- 1088      | 2245     | 0x8C5  | Saturday Evening Session, 4 Oct 2025
-- 1089      | 2246     | 0x8C6  | Sunday Morning Session, 5 Oct 2025
-- 1090      | 2247     | 0x8C7  | Sunday Afternoon Session, 5 Oct 2025
```

#### Get All Conferences

```sql
-- Get recent conferences with their IDs
SELECT
    ID,
    printf('0x%X', ID) as HexID,
    Description,
    Abbr,
    Year,
    Annual,
    IssueDate
FROM conference
ORDER BY Year DESC, Annual DESC
LIMIT 10;

-- Results:
-- ID  | HexID | Description                          | Year | Annual
-- 168 | 0xA8  | 2025 Semi-Annual General Conference  | 2025 | S
-- 167 | 0xA7  | 2025 Annual General Conference       | 2025 | A
-- 165 | 0xA5  | 2024 Semi-Annual General Conference  | 2024 | S
-- 164 | 0xA4  | 2024 Annual General Conference       | 2024 | A
```

#### Get Talks for a Specific Session

```sql
-- Get all talks from Sunday Afternoon Session, October 2025 (Session ID 1090)
SELECT
    ct.TalkID,
    printf('0x%X', ct.TalkID) as TalkHex,
    t.Title,
    s.GivenNames || ' ' || s.LastNames as Speaker,
    ct.Sequence as TalkSequence,
    cs.Description as SessionDesc,
    cs.ID as SessionID,
    printf('g%x', cs.ID + 1157) as URLPattern
FROM conference_talk ct
JOIN talk t ON ct.TalkID = t.ID
JOIN speaker s ON t.SpeakerID = s.ID
JOIN conf_session cs ON ct.SessionID = cs.ID
WHERE ct.SessionID = 1090
ORDER BY ct.Sequence;

-- Results:
-- TalkID | TalkHex | Title                           | Speaker           | URLPattern
-- 8827   | 0x227B  | They Are Their Own Judges       | David A. Bednar   | g8c7
-- 8828   | 0x227C  | The Name by Which Ye Are Called | Arnaud Cuvelier   | g8c7
-- 8829   | 0x227D  | Forsake Not Your Own Mercy      | Jeffrey R. Holland| g8c7
```

#### Comprehensive Session Listing with Talk Counts

```sql
-- Get session details with talk counts for recent conferences
SELECT
    cs.ID as SessionID,
    printf('g%x', cs.ID + 1157) as URLPattern,
    c.Year,
    c.Annual,
    cs.Sequence,
    cs.Abbr as SessionAbbr,
    cs.Description,
    COUNT(ct.TalkID) as TalkCount
FROM conf_session cs
JOIN conference c ON cs.ConferenceID = c.ID
LEFT JOIN conference_talk ct ON cs.ID = ct.SessionID
WHERE c.Year >= 2024
GROUP BY cs.ID
ORDER BY c.Year DESC, c.Annual DESC, cs.Sequence;
```

### URL Construction Examples

#### Generate Session Library URL

```sql
-- Generate URL to view a talk with conference session library in right panel
-- Formula: #{scriptureRef}:t{talkID_hex}${textPos}:g{(sessionID+1157)_hex}

SELECT printf('#db1:t%x$%d:g%x',
    8827,          -- Talk ID (David A. Bednar's talk)
    0,             -- Text position (start of talk)
    1090 + 1157    -- Session ID 1090 + offset 1157 = 2247 = 0x8C7
) as URL;
-- Result: #db1:t227b$0:g8c7
```

#### Find Session ID from Year and Session Type

```sql
-- Find Saturday Morning session for October 2024
SELECT
    cs.ID as DatabaseSessionID,
    cs.ID + 1157 as URLValue,
    printf('g%x', cs.ID + 1157) as URLPattern,
    cs.Description
FROM conf_session cs
JOIN conference c ON cs.ConferenceID = c.ID
WHERE c.Year = 2024
  AND c.Annual = 'S'
  AND cs.Abbr = 'Saturday Morning';

-- Result:
-- DatabaseSessionID | URLValue | URLPattern | Description
-- 1071              | 2228     | g8b4       | Saturday Morning Session, 5 Oct 2024
```

#### Generate URLs for All Talks in a Session

```sql
-- Generate complete URLs for all talks in October 2025 Saturday Morning session
SELECT
    t.Title,
    s.LastNames as Speaker,
    printf('#db1:t%x$0:g%x',
        ct.TalkID,
        cs.ID + 1157
    ) as URL,
    printf('Session: %s, Talk %d of %d',
        cs.Abbr,
        ct.Sequence,
        (SELECT COUNT(*) FROM conference_talk WHERE SessionID = cs.ID)
    ) as Info
FROM conference_talk ct
JOIN talk t ON ct.TalkID = t.ID
JOIN speaker s ON t.SpeakerID = s.ID
JOIN conf_session cs ON ct.SessionID = cs.ID
WHERE cs.ID = 1086  -- Saturday Morning, Oct 2025
ORDER BY ct.Sequence;
```

### Key Insights

1. **Session ID Offset**: URLs always use `SessionID + 1157` encoded in hexadecimal
2. **Conference Types**:
    - `Annual = 'A'` → April General Conference
    - `Annual = 'S'` → October Semi-Annual (labeled as "October" in modern times)
3. **Session Sequence**: The `Sequence` field orders sessions within a conference (1, 2, 3, etc.)
4. **Date Range**: Sessions span from 1942 to present (IDs 1 to 1090+ as of 2025)
5. **URL Patterns**:
    - `:g` → Show all General Conference sessions (conference library)
    - `:g{sessionID_hex}` → Show specific conference session with talks grouped by session

### Integration Examples

#### Link Talk to Its Session

```sql
-- Find which session a talk belongs to and generate session library URL
SELECT
    t.ID as TalkID,
    t.Title,
    s.LastNames as Speaker,
    cs.Description as Session,
    c.Year,
    c.Annual,
    printf('#db1:t%x$0:g%x',
        t.ID,
        cs.ID + 1157
    ) as SessionLibraryURL
FROM talk t
JOIN speaker s ON t.SpeakerID = s.ID
JOIN conference_talk ct ON t.ID = ct.TalkID
JOIN conf_session cs ON ct.SessionID = cs.ID
JOIN conference c ON cs.ConferenceID = c.ID
WHERE t.ID = 8827;  -- "They Are Their Own Judges"

-- Result shows the talk with its session and properly encoded URL
```

#### Find All October 2025 Sessions

```sql
-- Get all sessions for a conference with properly formatted URLs
SELECT
    cs.Sequence,
    cs.Abbr,
    cs.Description,
    cs.Date,
    COUNT(ct.TalkID) as NumTalks,
    printf(':g%x', cs.ID + 1157) as URLSuffix
FROM conf_session cs
JOIN conference c ON cs.ConferenceID = c.ID
LEFT JOIN conference_talk ct ON cs.ID = ct.SessionID
WHERE c.Year = 2025 AND c.Annual = 'S'
GROUP BY cs.ID
ORDER BY cs.Sequence;

-- Result provides complete session overview with URL suffixes:
-- Sequence | Abbr             | URLSuffix | NumTalks
-- 1        | Saturday Morning | :g8c3     | 5
-- 2        | Saturday Afternoon| :g8c4    | 5
-- etc.
```

### Session URL Pattern Summary

**Pattern**: `#{scriptureRef}:t{talkID_hex}${textPos}:g{sessionURL_hex}`

Where:

-   `scriptureRef` = Scripture reference being displayed in left panel
-   `talkID_hex` = Talk ID in hexadecimal
-   `textPos` = Character offset in talk text (decimal)
-   `sessionURL_hex` = **(SessionID + 1157)** in hexadecimal

**Complete Example**:

-   Database Session ID: 1086
-   URL Calculation: 1086 + 1157 = 2243 → hex(2243) = 8C3
-   Full URL: `#db1:t227b$0:g8c3`
    -   Left: Alma 1
    -   Middle: Talk 8827 (0x227B) at position 0
    -   Right: October 2025 Saturday Morning session (0x8C3)

---

Last Updated: 2025-11-27 (Priority 2 Complete: Conference Sessions Documented)
