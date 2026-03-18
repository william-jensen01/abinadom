# URI Variant Generator

A Python script that generates multiple URI variants from talk URLs for robust content retrieval. Creates literal and normalized General Conference URI versions.

## Overview

This script:

1. **Adds three new columns** to the `talk` table: `URI_L`, `URI_GC`, `URI_Success`
2. **Processes all talk URLs** from the `URL` column
3. **Generates URI variants**:
   - **URI_L**: Literal URI with minimal processing
   - **URI_GC**: General Conference variant with normalized dates
4. **Prepares tracking column**: `URI_Success` (populated later by validation)

## Requirements

- Python 3.6+
- SQLite database with `talk` table containing `URL` column

## Usage

### Basic Usage

```bash
python generate_uri_variants.py <core_db_path>
```

### Example

```bash
python generate_uri_variants.py core.52.db
```

## URI Column Definitions

### URI_L (Literal URI)
**Purpose:** Direct copy of URL path with minimal processing

**Processing:**
1. Strip protocol and domain
2. Remove `/study` prefix if present
3. Remove `?lang=eng` query parameter
4. Keep ALL path segments (including session paths)

**Examples:**
```
URL: https://www.lds.org/study/ensign/2019/05/priesthood-session/33clark?lang=eng
URI_L: /ensign/2019/05/priesthood-session/33clark

URL: http://lds.org/ensign/2011/11/teaching-after-the-manner-of-the-spirit?lang=eng
URI_L: /ensign/2011/11/teaching-after-the-manner-of-the-spirit
```

### URI_GC (General Conference Normalized)
**Purpose:** General Conference variant with normalized dates and extracted identifiers

**Processing:**
1. Replace topic with `general-conference`
2. Normalize month to nearest GC (04 or 10)
3. Adjust year for January (year - 1)
4. Extract identifier (last path segment, remove session paths)

**Month Normalization Rules:**
```
01 → 10 (year - 1)
02-06 → 04
07-12 → 10
```

**Examples:**
```
URL: https://www.lds.org/study/ensign/2019/05/priesthood-session/33clark?lang=eng
URI_GC: /general-conference/2019/04/33clark

URL: http://lds.org/ensign/1973/07/the-family-influence?lang=eng
URI_GC: /general-conference/1973/04/the-family-influence

URL: http://lds.org/ensign/1974/01/the-example-of-christ?lang=eng
URI_GC: /general-conference/1973/10/the-example-of-christ
```

### URI_Success (Validation Status)
**Purpose:** Track which URI variant successfully retrieves content

**Values:**
- `NULL` - Not yet validated
- `URI_L` - Literal URI worked
- `URI_GC` - General Conference URI worked
- `BOTH` - Both URIs worked
- `NONE` - Neither URI worked

**Note:** This column is created empty and populated by a separate validation script.

## URL Pattern Support

The script handles all historical URL formats:

### Period 1: Current (2023/04 - ongoing)
```
https://www.churchofjesuschrist.org/study/general-conference/2023/04/17eyring?lang=eng
URI_L: /general-conference/2023/04/17eyring
URI_GC: /general-conference/2023/04/17eyring
```

### Period 2: Ensign/Liahona with Identifier (2019/11 - 2022/11)
```
https://www.churchofjesuschrist.org/study/liahona/2021/11/17giuffra?lang=eng
URI_L: /liahona/2021/11/17giuffra
URI_GC: /general-conference/2021/10/17giuffra
```

### Period 3: Ensign with Session + Identifier (2019/05)
```
https://www.lds.org/study/ensign/2019/05/priesthood-session/33clark?lang=eng
URI_L: /ensign/2019/05/priesthood-session/33clark
URI_GC: /general-conference/2019/04/33clark
```

### Period 4: Ensign with Session + Title (2013/11 - 2018/11)
```
https://www.lds.org/ensign/2015/05/general-womens-session/defenders-of-the-family-proclamation?lang=eng
URI_L: /ensign/2015/05/general-womens-session/defenders-of-the-family-proclamation
URI_GC: /general-conference/2015/04/defenders-of-the-family-proclamation
```

### Period 5: Old Ensign (1971/06 - 2013/05)
```
http://lds.org/ensign/2007/11/the-power-to-change?lang=eng
URI_L: /ensign/2007/11/the-power-to-change
URI_GC: /general-conference/2007/10/the-power-to-change
```

## Console Output

```
================================================================================
URI Variant Generator
================================================================================
Database: core.52.db
================================================================================

Step 1: Adding URI columns to talk table...
  Added column: URI_L
  Added column: URI_GC
  Added column: URI_Success

Step 2: Loading talks from database...
Found 7659 talks with URLs

Step 3: Generating URI variants...
--------------------------------------------------------------------------------
Progress: 500/7659 talks processed
Progress: 1000/7659 talks processed
...
⚠️  TalkID 1234: Failed to generate URIs from URL: http://invalid-url
--------------------------------------------------------------------------------

================================================================================
Summary:
  Total talks processed: 7659
  URI_L generated: 7658
  URI_GC generated: 7658
  Failed to generate: 1
  Success rate: 99.9%
================================================================================

✓ URI columns created and populated successfully!

Note: URI_Success column created but left empty (populate with validation script)
================================================================================
```

## Database Schema

After running the script, the `talk` table will have these additional columns:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| URI_L | TEXT | Literal URI from URL | `/ensign/2019/05/priesthood-session/33clark` |
| URI_GC | TEXT | General Conference normalized URI | `/general-conference/2019/04/33clark` |
| URI_Success | TEXT | Validation status (NULL initially) | `URI_GC` or `URI_L` or `BOTH` or `NONE` |

## Use Cases

### 1. Robust Content Retrieval
Try multiple URI variants when fetching talk content:
```python
# Try URI_GC first (most common)
response = fetch(f"{API_BASE}{uri_gc}")
if response.ok:
    update(uri_success='URI_GC')
else:
    # Fallback to URI_L
    response = fetch(f"{API_BASE}{uri_l}")
    if response.ok:
        update(uri_success='URI_L')
```

### 2. Data Quality Analysis
Identify talks with missing or invalid URLs:
```sql
SELECT ID, Title, URL 
FROM talk 
WHERE URL IS NOT NULL 
  AND (URI_L IS NULL OR URI_GC IS NULL);
```

### 3. Month Distribution
Analyze original publication months:
```sql
SELECT 
  SUBSTR(URI_L, INSTR(URI_L, '/', INSTR(URI_L, '/', 2) + 1) + 1, 2) as month,
  COUNT(*) as count
FROM talk
WHERE URI_L IS NOT NULL
GROUP BY month
ORDER BY month;
```

### 4. Validate Normalization
Check talks where January was normalized to previous October:
```sql
SELECT ID, Title, URI_L, URI_GC
FROM talk
WHERE URI_L LIKE '%/01/%'
  AND URI_GC LIKE '%/10/%';
```

## Integration Workflow

Recommended workflow:

```bash
# Step 1: Generate URI variants
python generate_uri_variants.py core.52.db

# Step 2: Validate URIs (separate script)
python validate_uris.py core.52.db

# Step 3: Analyze results
sqlite3 core.52.db "SELECT URI_Success, COUNT(*) FROM talk GROUP BY URI_Success;"
```

## Error Handling

The script handles:
- **Missing URLs**: Skipped (NULL values for URI columns)
- **Malformed URLs**: Logged and skipped
- **Invalid date formats**: Logged and skipped
- **Existing columns**: Updates values instead of failing

## Performance

- **Fast execution**: Pure Python string processing
- **No API calls**: Works offline
- **Typical speed**: ~2000 talks per second
- **7600+ talks**: Completes in under 5 seconds

## Troubleshooting

### Column already exists error
**Solution:** Script handles this automatically by updating existing values

### Failed to generate URIs
**Cause:** Invalid URL format or missing components
**Solution:** Review logged warnings and check source URLs

### Incorrect month normalization
**Cause:** Edge case not covered
**Solution:** Review normalization logic for specific month

## Notes

- **Read-only source**: Never modifies original `URL` column
- **Safe to re-run**: Updates existing columns if present
- **Idempotent**: Can run multiple times safely
- **URI_Success starts NULL**: Requires separate validation script

## Month Normalization Examples

```
January (01):
  2020/01 → 2019/10 (year decrements)

February-June (02-06):
  2020/02 → 2020/04
  2020/05 → 2020/04
  2020/06 → 2020/04

July-December (07-12):
  2020/07 → 2020/04
  2020/09 → 2020/10
  2020/11 → 2020/10
  2020/12 → 2020/10
```

## License

This script is provided as-is for educational and research purposes.
