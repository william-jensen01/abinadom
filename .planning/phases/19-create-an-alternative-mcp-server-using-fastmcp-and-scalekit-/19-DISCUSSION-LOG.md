# Phase 19: FastMCP + ScaleKit MCP Server — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 19-create-an-alternative-mcp-server-using-fastmcp-and-scalekit
**Areas discussed:** ScaleKit auth provider approach, ScaleKit setup, Scope enforcement, scalekit-sdk-python removal, D-06 well-known endpoints update, Auth test strategy

---

## ScaleKit Auth Provider Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Custom ScalekitTokenVerifier | Write TokenVerifier subclass wrapping scalekit-sdk-python SDK (original research approach) | |
| FastMCP built-in ScalekitProvider | Use `fastmcp.server.auth.providers.scalekit.ScalekitProvider` directly — no custom class, no SDK | ✓ |

**User's choice:** FastMCP has a built-in ScalekitProvider — no custom TokenVerifier class needed, no scalekit-sdk-python.

**Notes:** Discovery during session — FastMCP 3.2.4 ships `ScalekitProvider` as a first-class built-in provider alongside Auth0, Azure, Clerk, GitHub, Google, etc. It uses JWKS/JWT internally via `JWTVerifier` and handles `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` natively. The entire `auth/scalekit_verifier.py` file proposed in the research is unnecessary.

---

## ScaleKit Resource Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Resource already created | SCALEKIT_RESOURCE_ID is ready | |
| Will create before execution | Set up MCP Server in ScaleKit Dashboard before running Phase 19 | |
| Defer to operator via env var | Document as required env var without assuming it exists yet | ✓ |

**User's choice:** Document SCALEKIT_RESOURCE_ID as a required env var — operator sets it after creating the MCP Server resource in ScaleKit Dashboard.

---

## Scope Enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| No required scopes | Any valid ScaleKit JWT accepted | ✓ |
| Enforce specific scope | Require e.g. 'mcp:read' or 'openid' on all tokens | |

**User's choice:** No required scopes (Claude's discretion). Scope enforcement deferred to future phases.

---

## scalekit-sdk-python Dependency

| Option | Description | Selected |
|--------|-------------|----------|
| Remove from Pipfile | ScalekitProvider uses JWKS internally — SDK not needed | ✓ |
| Keep in Pipfile | Leave even though unused | |

**User's choice:** Remove scalekit-sdk-python from Pipfile. fastapi also removed (no longer used by new server.py).

---

## D-06: /.well-known Endpoints

| Option | Description | Selected |
|--------|-------------|----------|
| Update D-06 | ScalekitProvider serves these automatically — update to reflect reality | ✓ |
| Keep D-06 as-is | Intent was "no manual implementation" — FastMCP handling is consistent | |

**User's choice:** Update D-06. ScalekitProvider automatically serves `/.well-known/oauth-protected-resource` (via RemoteAuthProvider) and proxies `/.well-known/oauth-authorization-server` from ScaleKit. Server does serve these — required and correct.

---

## Auth Test Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| FastMCP DebugAuthProvider | Use built-in debug provider for test tokens — no real ScaleKit needed | ✓ |
| Mock JWKS endpoint | Local JWKS server or httpx monkeypatch | |
| Skip auth in unit tests | Local mode only in tests; auth is integration-only | |

**User's choice:** Use `DebugAuthProvider` from `fastmcp.server.auth.providers.debug`. Issues test tokens without ScaleKit credentials. No live ScaleKit instance needed in CI.

---

## Claude's Discretion

- Whether `auth/oauth.py` is deleted or emptied in-file
- Exact lifespan context access pattern
- CORS middleware configuration
- How existing tool function signatures map to `@mcp.tool()` decorators

## Deferred Ideas

- Required scopes enforcement — future phase
- Per-user rate limiting (AUTH-05)
- Usage admin endpoint (AUTH-06)
