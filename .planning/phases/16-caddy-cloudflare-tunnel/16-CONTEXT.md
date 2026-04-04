# Phase 16: Caddy & Cloudflare Tunnel - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up a shared reverse-proxy infrastructure (Caddy + cloudflared) as a separate Compose stack, and wire the MCP server into it. The operator goes from zero (no Cloudflare account, no domain, no reverse proxy) to a stable public HTTPS URL for the MCP server with the host IP hidden.

This phase delivers two things:
1. **Infra Compose stack** — `infra/docker-compose.yml` + `infra/Caddyfile` + `infra/.env.example` (lives in this repo as a reference; operator copies to a directory like `~/infra/` on the server)
2. **Setup walkthrough** — Step-by-step instructions: Cloudflare account → domain → named tunnel → running the infra stack → wiring MCP into it

**Scope note:** The roadmap success criteria say "Caddy and cloudflared run as services inside the Compose stack." This was written before the operator's broader server context was known (Jellyfin, *arr stack also running on the same machine). The correct interpretation is a **separate shared infra Compose stack**, not embedded in `docker-compose.yml` alongside `mcp-server`. The MCP Compose stack (`docker-compose.yml`) is unchanged — it joins a shared Docker external network so Caddy can reach it.

This phase does NOT include end-user or operator reference docs (Phase 17 scope).

</domain>

<decisions>
## Implementation Decisions

### Tunnel Type

- **D-01:** Named tunnel (not quick tunnel). The operator creates a tunnel once via `cloudflared tunnel create`, receives a `TUNNEL_TOKEN`, and stores it in the infra `.env`. The same public URL is restored on every `docker compose up` restart. Quick tunnel (`trycloudflare.com`) was explicitly rejected — it changes URL on restart and doesn't meet "stable public URL."

### Infra Stack Architecture

- **D-02:** Caddy + cloudflared live in a **separate Compose stack** (`infra/`), not inside the MCP project's `docker-compose.yml`. This is shared infrastructure — when Jellyfin, *arr stack, or other services are added later, they join the same Caddy router without touching the MCP stack. The infra stack is intended to be always-on and independent of any individual app stack.
- **D-03:** The infra stack files (`infra/docker-compose.yml`, `infra/Caddyfile`, `infra/.env.example`) are committed to this repo as reference artifacts. The operator copies the `infra/` directory to their server (e.g. `~/infra/`) and fills in the `.env`.

### Cross-Stack Networking

- **D-04:** MCP server connects to Caddy via a shared Docker **external network** (e.g. `proxy`). The infra Compose stack creates this network; the MCP Compose stack joins it. Caddy reaches `mcp-server` by container name on this shared network.
- **D-05:** The MCP server's `ports:` mapping (currently `${MCP_PORT}:${MCP_PORT}`) can be removed — mcp-server only needs to be reachable by Caddy on the internal Docker network, not published to the host.

### Routing Chain

- **D-06:** `cloudflared → Caddy → mcp-server`. cloudflared's ingress config points at `caddy:80` (HTTP, Docker-internal). Caddy reverse-proxies to `mcp-server:8000` on the shared external network. Cloudflare handles external TLS at the edge; Caddy handles internal routing and is the sole ingress point for all future services.
- **D-07:** Caddy routes by subdomain (e.g. `mcp.yourdomain.com → mcp-server:8000`). When Jellyfin is added later, the operator adds one block to the Caddyfile — cloudflared config is unchanged.

### Caddyfile Delivery

- **D-08:** Caddyfile is a **bind-mount volume** from the host into the Caddy container. The operator can edit routing rules without rebuilding the image. `docker compose exec caddy caddy reload` applies changes live.

### Cloudflare Setup (Starting from Scratch)

- **D-09:** The operator does not have a Cloudflare account or domain. Phase 16 must include a full setup walkthrough:
  1. Create Cloudflare account
  2. Register or transfer a domain (Cloudflare Registrar recommended — at-cost pricing, simplest DNS management)
  3. Create a named tunnel via Cloudflare dashboard or `cloudflared tunnel create`
  4. Add DNS CNAME record pointing the subdomain at the tunnel
  5. Store `TUNNEL_TOKEN` in `infra/.env`
  6. `docker compose up -d` in `~/infra/`
  7. Update MCP `docker-compose.yml` to join the shared `proxy` network
  8. Verify: HTTPS request to `mcp.yourdomain.com` reaches `/health`

### Claude's Discretion

- Caddy and cloudflared image versions to pin (e.g. `caddy:2-alpine`, `cloudflare/cloudflared:latest`)
- Exact Docker external network name (`proxy` is conventional)
- Caddyfile structure (global options block, per-site blocks)
- Whether `infra/.env.example` uses placeholder domain or a note to substitute
- Container restart policies in infra Compose
- Whether to include a `caddy reload` helper in the setup walkthrough

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing MCP Stack
- `docker-compose.yml` — Current MCP Compose config; D-05 requires removing `ports:` mapping and adding network join
- `.env.example` — Current operator-facing env vars; no changes needed for Phase 16
- `server.py` — MCP server entry point; no code changes needed — it already binds to `MCP_HOST`/`MCP_PORT`

### Requirements
- `.planning/REQUIREMENTS.md` §DEPLOY-03, DEPLOY-04 — Caddy TLS termination and cloudflared tunnel requirements

### Roadmap
- `.planning/ROADMAP.md` §Phase 16 — Success criteria (interpret "inside the Compose stack" as "inside the infra Compose stack" per D-02)

### Prior Phase Context
- `.planning/phases/15-docker-compose-config/15-CONTEXT.md` — Full MCP Compose decisions; D-05 modifies the `ports:` mapping established there
- `.planning/phases/13-http-transport/13-CONTEXT.md` — `/health` endpoint is the verification target; must be reachable via Caddy after wiring

No external specs beyond standard Caddy and Cloudflare Tunnel documentation.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker-compose.yml` — Starting point; needs two changes: remove `ports:` mapping, add `networks:` block to join the shared `proxy` network
- `.env.example` — No changes needed; `TUNNEL_TOKEN` goes in `infra/.env`, not the MCP `.env`
- `GET /health` — Already implemented; used as the end-to-end verification step after wiring

### Established Patterns
- All secrets and paths via `.env` (never committed) — infra stack follows the same pattern with `infra/.env`
- Bind mounts for operator-configurable files — Caddyfile follows this pattern (D-08)
- `extra_hosts: host.docker.internal:host-gateway` — already in MCP Compose; not needed in infra stack (Caddy routes to named containers on the shared network)

### Integration Points
- MCP `docker-compose.yml` `networks:` block — add `proxy: external: true`
- Infra `docker-compose.yml` `networks:` block — define `proxy` as an external-creatable network
- Caddyfile — add `mcp.yourdomain.com { reverse_proxy mcp-server:8000 }` block

</code_context>

<specifics>
## Specific Ideas

- Deployment target: Dell PowerEdge R720, running Jellyfin and *arr stack alongside MCP. Caddy + cloudflared are shared infrastructure for all services on this machine — not MCP-specific.
- The operator wants to understand Caddy's value as a single ingress point: one tunnel token, one domain, subdomains per service. Adding Jellyfin later = one Caddyfile block, no cloudflared changes.
- Cloudflare Registrar recommended for domain purchase — at-cost pricing, and DNS is already in Cloudflare (required for tunnel DNS records).
- The operator explicitly wants Phase 16 to include the full Cloudflare setup walkthrough, not just config files. They are starting from zero (no account, no domain).

</specifics>

<deferred>
## Deferred Ideas

- **Jellyfin/arr wiring** — Phase 16 establishes the infra stack; wiring other services is operator self-service using the Caddyfile pattern. Not in scope.
- **Caddy TLS for LAN access** — Caddy can serve HTTPS on the local network (self-signed or ACME). Not in scope for Phase 16 — tunnel covers the public URL use case.
- **Cloudflare Access** (zero-trust auth in front of the tunnel) — Could add a second auth layer before requests even reach MCP. Future consideration.
- **Rate limiting / WAF rules** — Cloudflare dashboard features, not Compose config. Future if abuse is observed.

</deferred>

---

*Phase: 16-caddy-cloudflare-tunnel*
*Context gathered: 2026-04-04*
