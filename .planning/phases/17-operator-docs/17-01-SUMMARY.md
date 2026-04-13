---
phase: 17-operator-docs
plan: "01"
subsystem: docs
tags: [documentation, oauth, connection-guide, mcp]
dependency_graph:
  requires: []
  provides: [docs/CONNECTION.md]
  affects: []
tech_stack:
  added: []
  patterns: [RFC 9728 Protected Resource Metadata, RFC 8414 Authorization Server Metadata, MCP JSON-RPC 2.0]
key_files:
  created:
    - docs/CONNECTION.md
  modified: []
decisions:
  - "D-08: Connection guide covers three clients — Claude.ai (OAuth 2.0), Claude Desktop (Remote MCP), generic HTTP clients"
  - "D-09: Written for technical user — minimal explanation, steps and commands only"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-04-13"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 17 Plan 01: Connection Guide Summary

**One-liner:** MCP connection guide covering OAuth 2.0 for Claude.ai, remote MCP for Claude Desktop, and M2M token flow for curl/HTTP clients.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write docs/CONNECTION.md | b1fef7d | docs/CONNECTION.md |

## What Was Built

Created `docs/CONNECTION.md` — a technical connection guide for three MCP client types:

- **Claude.ai (OAuth 2.0):** 5-step walkthrough using RFC 9728 auto-discovery; Claude.ai handles the full OAuth 2.1 flow automatically once the URL is entered.
- **Claude Desktop (Remote MCP):** JSON config snippet for `mcpServers` key; OAuth handshake happens automatically on restart.
- **Other Clients (curl, HTTP):** Auth0 M2M client credentials token acquisition, then MCP JSON-RPC 2.0 session flow (initialize → list tools → call tool) with concrete `curl` examples including `Authorization: Bearer` and `Mcp-Session-Id` headers.

Also includes:
- Discovery Endpoints table (4 endpoints: `/health`, two `/.well-known/oauth-protected-resource` paths, `/.well-known/oauth-authorization-server`)
- Troubleshooting section (401, 404 on well-known, connection refused, OAuth redirect failure)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all sections contain concrete steps, commands, and examples. No placeholder text.

## Threat Flags

None — documentation only; no code changes, no new endpoints, no credentials committed. Placeholder domains (`yourdomain.com`) used throughout.

## Self-Check: PASSED

- [x] `docs/CONNECTION.md` exists
- [x] Commit `b1fef7d` exists in git log
- [x] All acceptance criteria verified (grep counts passed)
- [x] No TODO/TBD in file
