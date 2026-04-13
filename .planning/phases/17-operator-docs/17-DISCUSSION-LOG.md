# Phase 17: Operator Docs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 17-operator-docs
**Areas discussed:** Doc structure & location, Self-deploy audience, Key management guide format, Connection guide scope

---

## Doc Structure & Location

| Option | Description | Selected |
|--------|-------------|----------|
| docs/ files + infra/SETUP.md stays | New files in docs/: CONNECTION.md, DEPLOY.md, KEY-MANAGEMENT.md. Existing infra/SETUP.md unchanged. | ✓ |
| Root-level README.md | Single README covering all guides | |
| Extend infra/SETUP.md | Expand infra/SETUP.md to include all content | |

**User's choice:** docs/ files + infra/SETUP.md stays  
**Follow-up — Entry point:** Root README.md chosen (concise project description + links to all 3 guides + infra/SETUP.md)

---

## Self-Deploy Audience

| Option | Description | Selected |
|--------|-------------|----------|
| Linux server operator | Assumes Docker installed, starts from "clone the repo" | ✓ |
| Complete newcomer | Walks through Docker install + server setup basics | |
| You decide | Claude picks balance from infra/SETUP.md tone | |

**User's choice:** Linux server operator

**Follow-up — Caddy/Tunnel step:**

| Option | Description | Selected |
|--------|-------------|----------|
| Link to infra/SETUP.md | DEPLOY.md links out; no duplication | ✓ |
| Inline a summary | Condensed version in DEPLOY.md | |
| Copy verbatim | Full infra/SETUP.md content pasted in | |

**User's choice:** Link to infra/SETUP.md

---

## Key Management Guide Format

| Option | Description | Selected |
|--------|-------------|----------|
| Step-by-step walkthrough | Narrative: issue → verify → revoke → confirm | |
| Reference page | Flat list of commands with flags and examples | ✓ |
| Both | Walkthrough + command reference appendix | |

**User's choice:** Reference page

**Follow-up — Usage log inspection:**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — include it | Section showing how to query auth.db | ✓ |
| No — CRUD only | Only create/revoke/list commands | |

**User's choice:** Yes — include usage log inspection

---

## Connection Guide Scope

**Clients to cover:** Claude.ai (OAuth 2.0), Claude Desktop (bearer token), Other clients (all three selected)

**Audience:**

| Option | Description | Selected |
|--------|-------------|----------|
| Knows Claude, not MCP internals | Explains bearer tokens, where to paste | |
| Technical user | Assumes HTTP API knowledge; minimal explanation | ✓ |
| Complete beginner | Explains what MCP is first | |

**User's choice:** Technical user

---
