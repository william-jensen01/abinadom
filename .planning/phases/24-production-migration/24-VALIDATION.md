---
phase: 24
slug: production-migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-11
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (pipenv) |
| **Config file** | none — existing pytest.ini or pyproject.toml |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase6.py tests/test_phase6_orchestrator.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest -x -q` |
| **Estimated runtime** | ~30 seconds (weaviate-embedded adds ~5s first run) |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/ -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | MIGR-01 | — | N/A | import | `pipenv run py -c "from extractors.phase6_weaviate_loader import load_talk_bundles, TalkBundle"` | ✅ | ⬜ pending |
| 24-01-02 | 01 | 1 | MIGR-01 | — | N/A | unit | `pipenv run py -m pytest tests/test_phase6.py -x -q` | ✅ | ⬜ pending |
| 24-02-01 | 02 | 1 | MIGR-01 | — | N/A | import | `pipenv run py scripts/run_pipeline.py --help` | ✅ | ⬜ pending |
| 24-02-02 | 02 | 1 | MIGR-01 | — | N/A | grep | `grep -i chromadb scripts/run_pipeline.py` (expect no match) | ✅ | ⬜ pending |
| 24-03-01 | 03 | 1 | MIGR-02 | — | N/A | import | `grep -i chromadb server.py` (expect no match) | ✅ | ⬜ pending |
| 24-03-02 | 03 | 1 | MIGR-02 | — | N/A | import | `pipenv run py -c "from config.pipeline_config import WEAVIATE_COLLECTION_NAMES"` | ✅ | ⬜ pending |
| 24-04-01 | 04 | 2 | MIGR-03 | — | N/A | compose | `docker compose config` (expect weaviate service present) | ✅ | ⬜ pending |
| 24-05-01 | 05 | 2 | MIGR-01 | — | N/A | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py -x -q` | ✅ | ⬜ pending |
| 24-06-01 | 06 | 3 | MIGR-04 | — | N/A | manual | Full pipeline run (human-gated) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase6.py` — rewritten for Weaviate (D-16); `weaviate.connect_to_embedded()` fixture
- [ ] `tests/test_phase6_orchestrator.py` — minimal patch only (D-20); replace 9 `get_chromadb_client` patches with WeaviateLoader mocks

*Both files currently raise ModuleNotFoundError — fixing import errors is Wave 0 for this phase.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full pipeline run completes for 5,838 talks | MIGR-04 | Runtime hours; external Weaviate instance required | `pipenv run py scripts/run_pipeline.py`; check Weaviate Paragraph count ≥ 5,838; `failed_talks.json` empty/absent |
| MCP search + get_talk return correct results | MIGR-04 | Requires live server + Weaviate; subjective result quality | 3 representative queries via Claude Desktop; check non-empty results, no Weaviate connection errors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
