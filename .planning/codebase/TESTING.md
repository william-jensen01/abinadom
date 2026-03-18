# Testing Patterns

**Analysis Date:** 2026-03-18

## Test Framework

**Runner:**
- `pytest` (defined in Pipfile dev-packages)
- Config: No `pytest.ini`, `setup.cfg`, or `pyproject.toml` config file present
- Virtual environment: `pipenv` (see Pipfile)

**Assertion Library:**
- `pytest` assertions (simple `assert` statements)
- Custom validation via test methods (no special assertion library)
- `unittest.TestCase` assertions in some test files (e.g., `test_phase1.py`)

**Run Commands:**
```bash
pipenv run py -m pytest tests/                    # Run all tests
pipenv run py -m pytest tests/test_phase1.py -v   # Run with verbose output
pipenv run py -m pytest --co                       # Collect tests (dry run)
pipenv run py tests/test_phase1.py                 # Direct test runner
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory at project root
- Pattern: Mirror extractor/module names
- Actual structure:
  ```
  tests/
  ├── test_html_parsing_utils.py
  ├── test_phase1.py
  ├── test_phase2.py
  ├── test_phase3.py
  ├── test_phase4.py
  ├── test_phase5.py
  └── __init__.py
  ```

**Naming:**
- Test files: `test_{module_name}.py`
- Test classes: `Test{Feature}` (e.g., `TestSchema`, `TestValidators`, `TestTalkMetadata`)
- Test methods: `test_{specific_behavior}` (e.g., `test_schema_has_required_fields`, `test_validate_year_invalid`)

**Import Pattern:**
```python
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

import pytest
from bs4 import BeautifulSoup
from extractors.phase1_talk_metadata import (
    transform_db_row_to_metadata,
    prepare_for_chromadb,
)
```

## Test Structure

**Suite Organization:**

**Using pytest (Phase 2+):**
```python
class TestHTMLParsing:
    """Test HTML parsing functionality."""

    def test_parse_simple_html(self):
        """Test parsing simple HTML."""
        html = "<p>Hello world</p>"
        soup = parse_html(html)
        assert soup is not None
        assert soup.find("p") is not None
```

**Using unittest (Phase 1):**
```python
class TestSchema(unittest.TestCase):
    """Test schema configuration."""

    def test_schema_has_required_fields(self):
        """Schema should have all essential fields."""
        required = get_required_fields(TALK_METADATA_SCHEMA)
        self.assertIn("talk_id", required)
        self.assertIn("title", required)
```

**Patterns:**

**Setup:**
- Helper methods for common test data: `get_valid_metadata_dict()`, `get_sample_db_row()`
- No explicit `setUp()` method (data created per-test)
- Fixtures created inline within test methods

**Teardown:**
- No explicit `tearDown()` or cleanup (no stateful resources)
- No database or file cleanup needed (tests use sample data)

**Assertion:**
- pytest: `assert condition`, `assert actual == expected`
- unittest: `self.assertEqual()`, `self.assertIn()`, `self.assertTrue()`, `self.assertRaises()`
- Error assertions: `with self.assertRaises(ValueError):`

## Mocking

**Framework:**
- No `unittest.mock` or `pytest-mock` observed in test files
- Pure functional tests without mocking (real schemas, validators tested directly)
- Database tests use actual `content_db` instance (not mocked)
- HTML parsing tests use BeautifulSoup with sample HTML strings

**Patterns:**
- HTML mocking via string literals:
  ```python
  html = '<span class="citation" id="1">D&C 1:1</span> some text'
  soup = BeautifulSoup(html, "html.parser")
  span = soup.find("span", class_="citation")
  assert _find_position_anchor(span) is span
  ```
- Database row mocking via dictionaries:
  ```python
  def get_sample_db_row(self) -> Dict[str, Any]:
      return {
          "talk_id": 1,
          "title": "Test Talk",
          "talk_date": "2023-04-01",
          # ... other fields
      }
  ```

**What to Mock:**
- Nothing currently mocked (tests are integration-focused)
- Database calls use actual `core_db` and `content_db` instances
- File I/O tested with actual files

**What NOT to Mock:**
- Validators: tested directly with real data
- Schemas: tested with real configuration
- BeautifulSoup: used directly with test HTML
- Database: real database queries in fixture data

## Fixtures and Factories

**Test Data:**
```python
def get_valid_metadata_dict(self) -> Dict[str, Any]:
    """Get valid metadata dictionary for testing."""
    return {
        "talk_id": 1,
        "speaker_id": 100,
        "conference_id": 50,
        "title": "Test Talk",
        "speaker_name": "John Doe",
        "conference_year": 2023,
        "conference_month": "April",
        "conference_description": "2023 Annual General Conference",
        "talk_date": "2023-04-01",
    }
```

**Factory Pattern:**
- `create_talk_metadata_from_db_row(data)` factory function from models
- Used in tests to construct valid objects: `metadata = create_talk_metadata_from_db_row(data)`
- Factories include validation, making them good for happy-path tests

**Location:**
- Test helper methods on test class: `self.get_valid_metadata_dict()`
- Sample data defined inline in test methods for clarity
- No separate fixtures file (kept in test classes)

## Coverage

**Requirements:**
- No coverage threshold enforced
- No coverage config file present
- Tests written for all major functions but coverage not tracked

**View Coverage:**
```bash
# If pytest-cov installed:
pipenv install pytest-cov
pipenv run py -m pytest --cov=extractors --cov=models tests/
```

## Test Types

**Unit Tests:**
- **Scope:** Individual functions and classes in isolation
- **Approach:** Test one behavior per test method
- **Examples:** `test_validate_year_valid()`, `test_sanitize_speaker_name()`, `test_parse_html_empty()`
- **Location:** `tests/test_phase*.py`

**Integration Tests:**
- **Scope:** Functions working together (extraction pipeline layers)
- **Approach:** Full pipeline from input to output
- **Examples:** `test_transform_db_row()` + `test_prepare_for_chromadb()` in sequence
- **Location:** Same test files (marked by scope, not separate)

**E2E Tests:**
- **Framework:** Not used
- **Coverage:** End-to-end tested via example scripts in `examples/` directory
- **Manual verification:** Integration verified through actual pipeline runs

## Common Patterns

**Async Testing:**
- Not applicable (no async code in codebase)

**Error Testing:**
```python
def test_talk_metadata_validation_invalid_talk_id(self):
    """Should raise ValueError for invalid talk_id."""
    data = self.get_valid_metadata_dict()
    data["talk_id"] = -1  # Invalid

    with self.assertRaises(ValueError):
        create_talk_metadata_from_db_row(data)
```

**Edge Case Testing:**
```python
class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_title(self):
        """Should handle empty title."""
        data = {
            # ... required fields
            "title": "",  # Empty
        }
        with self.assertRaises(ValueError):
            create_talk_metadata_from_db_row(data)

    def test_missing_speaker_name(self):
        """Should handle missing speaker name gracefully."""
        row = {
            # ... fields
            "speaker_given_names": None,
            "speaker_last_names": None,
        }
        result = transform_db_row_to_metadata(row)
        self.assertEqual(result["speaker_name"], "Unknown Speaker")
```

**Parameterized Testing:**
- Not used; individual test methods for each case
- Alternative: Could use `@pytest.mark.parametrize` (not currently employed)

**HTML Parsing Tests:**
```python
class TestHTMLParsing:
    """Test HTML parsing functionality."""

    def test_parse_simple_html(self):
        html = "<p>Hello world</p>"
        soup = parse_html(html)
        assert soup is not None
        assert soup.find("p") is not None

    def test_parse_empty_html(self):
        soup = parse_html("")
        assert soup is None

    def test_parse_malformed_html(self):
        html = "<p>Unclosed tag"
        soup = parse_html(html)
        assert soup is not None
```

**Validation Tests:**
```python
def test_validate_schema_valid_data(self):
    """Valid data should pass schema validation."""
    data = {
        "talk_id": 1,
        # ... all required fields
    }
    is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
    self.assertTrue(is_valid, f"Expected valid, got errors: {errors}")
    self.assertEqual(len(errors), 0)

def test_validate_schema_missing_required(self):
    """Missing required fields should fail validation."""
    data = {
        "talk_id": 1,
        "title": "Test Talk",
        # Missing speaker_name, conference_year, etc.
    }
    is_valid, errors = validate_schema(data, TALK_METADATA_SCHEMA)
    self.assertFalse(is_valid)
    self.assertGreater(len(errors), 0)
```

## Test Execution Examples

**Run all tests:**
```bash
pipenv run py -m pytest tests/
```

**Run specific test file:**
```bash
pipenv run py -m pytest tests/test_phase1.py -v
```

**Run specific test class:**
```bash
pipenv run py -m pytest tests/test_phase1.py::TestSchema -v
```

**Run specific test method:**
```bash
pipenv run py -m pytest tests/test_phase1.py::TestSchema::test_schema_has_required_fields -v
```

**Run with output capture disabled (see print statements):**
```bash
pipenv run py -m pytest tests/ -s
```

---

*Testing analysis: 2026-03-18*
