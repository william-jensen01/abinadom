---
status: partial
phase: 05-chromadb-loader
source: [05-VERIFICATION.md]
started: 2026-03-25T23:58:00Z
updated: 2026-03-25T23:58:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. PersistentClient path wiring

Call `get_chromadb_client()` (no path argument) and use the returned client to run `load_talk_bundles` with a small set of real bundles.
expected: A `data/chromadb/` directory is created in the project root containing ChromaDB segment files and all 4 collection subdirectories.
result: [pending]

### 2. Ollama embedding function connectivity

Call `get_embedding_function()` with Ollama running and `nomic-embed-text` pulled, then embed a document.
expected: Returns a float vector; no connection errors.
result: [pending]

### 3. Verification report readability in production

Inspect printed verification report from a production run (call `generate_verification_report` against a real PersistentClient after loading data).
expected: Human-readable output shows counts, document previews, FK check results, and pass/fail.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
