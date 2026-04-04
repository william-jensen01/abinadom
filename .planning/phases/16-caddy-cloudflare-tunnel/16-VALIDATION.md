---
phase: 16
slug: caddy-cloudflare-tunnel
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | none — default pytest discovery |
| **Quick run command** | `pipenv run py -m pytest tests/ -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/ -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -v` + manual `curl https://mcp.yourdomain.com/health` after infra stack is up
- **Before `/gsd:verify-work`:** Full suite must be green + live curl check passes
- **Max feedback latency:** 15 seconds (automated), manual curl after stack up

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | DEPLOY-03 | manual | — | N/A | ⬜ pending |
| 16-01-02 | 01 | 1 | DEPLOY-04 | manual | — | N/A | ⬜ pending |
| 16-02-01 | 02 | 1 | DEPLOY-03 | regression | `pipenv run py -m pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*None — existing infrastructure covers all phase requirements. No new test stubs needed; DEPLOY-03 and DEPLOY-04 require live Cloudflare environment and cannot be automated.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Caddy terminates TLS, proxies to MCP server | DEPLOY-03 | Requires live Cloudflare account, registered domain, running Docker stack | `curl -f https://mcp.yourdomain.com/health` → HTTP 200 with `{"status": "healthy"}` |
| cloudflared exposes stable public URL | DEPLOY-04 | Requires live Cloudflare tunnel token, internet connectivity | `curl -f https://mcp.yourdomain.com/health` from external network; verify host IP not in response headers |
| Stack restart restores public URL | DEPLOY-04 | Requires full stack teardown/restart | `docker compose -f infra/docker-compose.yml down && docker compose -f infra/docker-compose.yml up -d`; re-run curl |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
