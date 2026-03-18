# Coding Conventions

**Analysis Date:** 2026-03-18

## Naming Patterns

**Files:**
- Lowercase with underscores: `phase1_talk_metadata.py`, `html_parsing_utils.py`
- Phase files follow pattern: `phase{N}_{description}.py`
- Test files mirror source: `test_phase{N}.py`, `test_html_parsing_utils.py`
- Models and configs in subdirectories: `models/talk_metadata.py`, `config/schemas.py`

**Functions:**
- Lowercase with underscores (snake_case): `fetch_all_talks()`, `extract_talk_metadata()`, `transform_db_row_to_metadata()`
- Private/internal functions prefixed with underscore: `_find_position_anchor()`, `_snap_to_word_boundaries()`, `_parse_punct_class()`
- Verbs used consistently: `fetch_*` for database retrieval, `extract_*` for data transformation, `validate_*` for validation

**Variables:**
- Lowercase with underscores: `talk_id`, `speaker_name`, `metadata_list`, `row`
- Boolean prefixed with `is_` or `has_`: `is_valid`, `has_session`
- Private class members prefixed with underscore: `self._soup`, `self._text_raw`, `self._parser`

**Types:**
- Dataclasses with PascalCase: `TalkMetadata`, `ParagraphData`, `CitationData`, `FootnoteData`
- Exception classes: Inherit from standard exceptions (`ValueError`, `KeyError`, `TypeError`)
- Type hints throughout: `Dict[str, Any]`, `List[TalkMetadata]`, `Optional[int]`

**Constants:**
- Uppercase with underscores: `ELEMENT_PLACEHOLDER = "\x00"`, `PARAGRAPH_CONFIG`, `TALK_METADATA_SCHEMA`

## Code Style

**Formatting:**
- Python 3.6+ syntax with type hints on all functions
- No external formatter enforced (Prettier/Black not in Pipfile)
- Indentation: 4 spaces
- Line length: No strict limit observed, but generally reasonable (~80-100 chars)
- Blank lines: Two blank lines between top-level definitions, one between methods

**Linting:**
- No `.eslintrc`, `.flake8`, or `.pylintrc` files present
- No pre-commit hooks configured
- Code quality relies on manual review and test coverage

**Code Organization:**
- Modules organized into functional sections with clear comment dividers:
  ```
  # =============================================================================
  # SECTION NAME
  # =============================================================================
  ```
- Clear layering in extractor modules:
  - Database Layer (data access)
  - Extraction Layer (transformation)
  - Validation Layer (quality checks)
  - Orchestration (high-level pipelines)

## Import Organization

**Order:**
1. Standard library imports (`sys`, `logging`, `re`, `copy`, `from pathlib`, `from typing`, `from datetime`)
2. Third-party imports (`requests`, `beautifulsoup4`, `pytest`)
3. Local imports (`from db import`, `from models import`, `from extractors import`, `from config import`)

**Path Aliases:**
- `sys.path.append(str(Path(__file__).parent.parent))` used to enable imports from parent directory
- No formal alias system; relative imports from project root

**Examples from codebase:**
```python
# Standard library first
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Third-party
from bs4 import BeautifulSoup, NavigableString, Tag

# Local
from db import core_db, Database
from models.talk_metadata import TalkMetadata, create_talk_metadata_from_db_row
from utils.validators import sanitize_speaker_name, determine_conference_month
```

## Error Handling

**Patterns:**
- Specific exception catching for known errors: `except (KeyError, ValueError, TypeError) as e:`
- Generic `except Exception as e:` for unknown errors with logging and re-raise
- Errors logged with context before re-raising:
  ```python
  except Exception as e:
      logger.error(f"Database query failed for talk ID {talk_id}: {e}")
      raise
  ```
- Graceful degradation in extractors: errors collected and logged without stopping pipeline
- Early returns for validation failures with descriptive errors

**Error Propagation:**
- Database layer: Re-raises with `raise` (preserves traceback)
- Extraction layer: Catches, logs, and collects errors for batch processing
- Validation layer: Returns tuple of `(is_valid, error_list)` or raises `ValueError`
- Main entry points: Try-except with `sys.exit(1)` on failure

**Example from `phase1_talk_metadata.py`:**
```python
for idx, row in enumerate(rows, 1):
    try:
        metadata = extract_talk_metadata(row)
        metadata_list.append(metadata)
    except Exception as e:
        talk_id = row.get("talk_id", "unknown")
        logger.warning(f"Skipping talk ID {talk_id} due to error: {e}")
        errors.append({"talk_id": talk_id, "error": str(e), "row": row})
```

## Logging

**Framework:** Python's standard `logging` module

**Setup Pattern:**
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
```

**Patterns:**
- Logger created per module using `__name__`
- Info level for major steps: `logger.info(f"Fetching {len(rows)} talks from database")`
- Warning level for skipped items: `logger.warning(f"Talk ID {talk_id} not found")`
- Error level for exceptions: `logger.error(f"Database query failed: {e}")`
- Debug level for detailed diagnostic info: `logger.debug(f"Row data: {row}")`
- Log messages include context (IDs, counts, reasons)

## Comments

**When to Comment:**
- Module-level docstrings describe purpose and architecture (always present)
- Function docstrings with Args, Returns, Raises (always present)
- Complex algorithms: explain the "why" not the "what"
- Section dividers for logical groupings with visual separators (80-char lines)
- Inline comments for non-obvious logic (rare, code should be self-explanatory)

**JSDoc/TSDoc:**
- Docstrings follow Google-style format in Python:
  ```python
  def extract_talk_metadata(row: Dict[str, Any]) -> TalkMetadata:
      """
      Extract TalkMetadata from database row.

      Args:
          row: Raw database row

      Returns:
          TalkMetadata instance

      Raises:
          ValueError: If required fields are missing or invalid
      """
  ```

## Function Design

**Size:**
- Small focused functions (20-50 lines typical)
- Complex operations broken into layer-specific functions
- Main pipeline orchestrators call smaller transformation functions

**Parameters:**
- Explicit parameters preferred; avoid `**kwargs`
- Optional parameters have `Optional[]` type hints
- Default values for optional parameters: `limit: Optional[int] = None`
- Config dictionaries passed explicitly (not global state)

**Return Values:**
- Functions return data, not None on error (exceptions raised instead)
- Tuple returns for multi-part results: `Tuple[List[str], List[Dict], List[str]]`
- Validation functions return `Tuple[bool, List[str]]` (is_valid, errors)
- Extraction returns typed objects (`TalkMetadata`, `ParagraphData`, `CitationData`)

## Module Design

**Exports:**
- All public functions and classes exported naturally (no `__all__` defined)
- Private functions prefixed with `_` for internal use
- Classes defined at module level, not nested

**Barrel Files:**
- No barrel files (index.py) used
- `__init__.py` present but mostly empty (only in `config/` and `models/` directories)
- Direct imports from modules preferred: `from extractors.phase1_talk_metadata import extract_talks_for_chromadb`

**Dataclass Usage:**
- Heavy use of `@dataclass` for type-safe data structures
- Fields with type hints and optional defaults
- Methods for serialization: `to_dict()`, `to_chromadb_format()`
- Validation methods: `validate_against_schema()`

---

*Convention analysis: 2026-03-18*
