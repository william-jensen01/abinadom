---
phase: 20
slug: benchmark-infrastructure-framework
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed in virtualenv) |
| **Config file** | none — default pytest discovery |
| **Quick run command** | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py tests/test_phase6.py -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/test_shared_transforms.py tests/test_metrics.py tests/test_phase6.py -q`
- **Before `/gsd-verify-work`:** Full suite must be green + Docker Compose health checks pass
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | BENCH-01 | — | N/A | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x -q` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | BENCH-01 | — | N/A | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x -q` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | BENCH-01 | — | N/A | unit | `pipenv run py -m pytest tests/test_shared_transforms.py -x -q` | ❌ W0 | ⬜ pending |
| 20-01-04 | 01 | 1 | BENCH-01 | — | No regression in production loader | unit | `pipenv run py -m pytest tests/test_phase6.py -x -q` | ✅ | ⬜ pending |
| 20-02-01 | 02 | 1 | BENCH-05 | — | N/A | unit | `pipenv run py -m pytest tests/test_metrics.py -x -q` | ❌ W0 | ⬜ pending |
| 20-02-02 | 02 | 1 | BENCH-05 | — | N/A | unit | `pipenv run py -m pytest tests/test_metrics.py -x -q` | ❌ W0 | ⬜ pending |
| 20-03-01 | 03 | 1 | BENCH-06 | — | N/A | unit | `pipenv run py -m pytest tests/test_metrics.py -x -q` | ❌ W0 | ⬜ pending |
| 20-04-01 | 04 | 2 | EVAL-01 | T-exposed-ports | Ports bound to localhost only | manual | `docker compose -f infra/docker-compose.vector-dbs.yml up -d && curl http://localhost:8000/api/v1/heartbeat` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_shared_transforms.py` — stubs for BENCH-01 (flatten_metadata, rich_metadata, prepare_talk_bundle)
- [ ] `tests/test_metrics.py` — stubs for BENCH-05 (dataclasses, recall_at_k) and BENCH-06 (CANONICAL_QUERIES structure)

*Existing infrastructure covers pytest — no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose starts all 3 DBs with passing health checks | EVAL-01 | Requires running Docker daemon; not runnable in unit test context | Run `docker compose -f infra/docker-compose.vector-dbs.yml up -d`; then `curl http://localhost:8000/api/v1/heartbeat` (200), `curl http://localhost:8080/v1/.well-known/ready` (200), `curl http://localhost:6333/healthz` (200) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
