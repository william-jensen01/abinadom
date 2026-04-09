# Deferred Items — Phase 16.2 Plan 02

## Out-of-scope pre-existing issues

### test_phase1.py::TestTalkMetadataDDL::test_talk_metadata_has_expected_columns

**Symptom:** Fails in worktree with `AssertionError: 0 != 7 — Expected 7 columns, got 0: []`

**Root cause:** The worktree does not have the SQLite database file (it is git-ignored and not present in worktrees). The test relies on the real database existing at the path configured in `.env`. On the main project directory the test passes.

**Impact:** Not caused by Plan 02 changes. Server.py and tests/test_server.py do not touch SQLite pipeline databases.

**Resolution:** Not needed for this plan. Database file must be present in the environment for this test to pass. Pre-existing constraint in worktree execution.
