# Phase 2: Code Quality - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-20
**Phase:** 02-code-quality
**Areas discussed:** Config centralization scope, Root script disposition, Cache manager decision, Logging convention

---

## Config Centralization Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Processing params only | Parser choice, batch sizes, context windows, regex patterns. DB/file paths stay as-is. | ✓ |
| Processing + file paths | Also centralize DB path, talk_previews.json, other file paths. | |
| Everything configurable | Processing params, file paths, logging config, API endpoints. | |

**User's choice:** Processing params only
**Notes:** Narrow, focused module. DB paths stay passed-in or per-script.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level constants | `CONTEXT_WINDOW_SIZE = 150`, etc. Simple importable constants. | ✓ |
| Dataclass or NamedTuple | Structured config object with type checking. | |
| Dict with sections | `CONFIG = {"parsing": {...}}` — grouped but no type safety. | |

**User's choice:** Module-level constants

---

| Option | Description | Selected |
|--------|-------------|----------|
| Replace in-place | Import constant and use directly. Single source of truth. | ✓ |
| Leave defaults + comment | Keep local defaults as fallback with comment. | |

**User's choice:** Replace in-place

---

## Root Script Disposition

| Option | Description | Selected |
|--------|-------------|----------|
| UPDATE.py still active | | ✓ |
| process_all.py still active | | ✓ |
| process_topics.py still active | | ✓ |
| run_phase2_tests.py still active | | |

**User's choice:** UPDATE.py, process_all.py, process_topics.py are active. run_phase2_tests.py is not.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Move to scripts/ | Move all 3 active scripts with docstrings. | ✓ |
| Stay at root with docstrings | Document in place. | |
| Move process_all.py only | Partial move. | |

**User's choice:** Move all 3 active scripts to scripts/

---

| Option | Description | Selected |
|--------|-------------|----------|
| Delete run_phase2_tests.py | Superseded by pytest. | ✓ |
| Archive with comment | Rename with archiving note. | |

**User's choice:** Delete

---

## Cache Manager Decision

| Option | Description | Selected |
|--------|-------------|----------|
| cache_manager_CLAUDE.py | Modern CachedSession API. Recommended. | ✓ |
| cache_manager_OLD.py | Older style with URL encoding fixes. | |
| Merge best of both | Keep modern API, fold in URL encoding fixes. | |

**User's choice:** cache_manager_CLAUDE.py is canonical

---

| Option | Description | Selected |
|--------|-------------|----------|
| Delete the other | Remove dead code. | ✓ |
| Archive with comment | Rename with note. | |

**User's choice:** Delete cache_manager_OLD.py

---

## Logging Convention

| Option | Description | Selected |
|--------|-------------|----------|
| Per-module getLogger only | `logger = logging.getLogger(__name__)` everywhere. No basicConfig in modules. | ✓ |
| Shared setup function | config/logging_config.py with setup_logging(). | |
| Keep Phase 1 pattern | logging.basicConfig in each module. | |

**User's choice:** Per-module getLogger only. Caller configures root logger.

---

| Option | Description | Selected |
|--------|-------------|----------|
| INFO/WARNING/ERROR for milestones/skips/failures | Matches Phase 3 patterns. | ✓ |
| DEBUG for all parsing, INFO for milestones only | Quieter defaults. | |
| You decide | Claude picks. | |

**User's choice:** INFO for progress, WARNING for skips, ERROR for failures; DEBUG for verbose parsing detail.

---

## Claude's Discretion

- Exact module docstring wording for moved scripts
- Edge cases in citation refactor not covered by REFACTOR_CITATION_PARSING.md
- Whether to add `__all__` to pipeline_config.py

## Deferred Ideas

None raised during discussion.
