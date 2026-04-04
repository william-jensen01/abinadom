# Phase 16: Caddy & Cloudflare Tunnel - Discussion Log

**Date:** 2026-04-04
**Phase:** 16 — Caddy & Cloudflare Tunnel

---

## Gray Areas Selected

User selected all three areas: Tunnel type, Routing chain, Caddyfile delivery.

---

## Area: Tunnel Type

**Q:** Named tunnel or quick tunnel for cloudflared?

**Options presented:**
- Named tunnel — persistent TUNNEL_TOKEN, same URL on every restart
- Quick tunnel — zero-config trycloudflare.com, URL changes on restart

**Selected:** Named tunnel

---

## Area: Routing Chain

**Q:** What role does Caddy play? Cloudflare handles external TLS — what does Caddy add?

**Discussion summary:**
User asked for clarification on what Caddy is and its value. Key exchange:

- Caddy explained as a reverse proxy with automatic HTTPS, valued primarily as a single ingress point for multi-service routing
- User asked about the single ingress point concept specifically and what adding more services would look like
- Caddy's multi-service routing value explained: one tunnel, one domain, subdomains per service, Caddyfile additions only
- User asked whether Caddy and cloudflared would be separate containers — confirmed yes, separate from mcp-server
- User revealed broader context: server also runs Jellyfin and *arr stack — asked whether those would get their own Caddy + cloudflared
- Recommended shared infra pattern explained: one Caddy + one cloudflared for all services on the machine
- User confirmed they do not have a Caddy + cloudflared setup and want Phase 16 to cover setup AND wiring MCP to it

**Decision:** cloudflared → Caddy → mcp-server routing chain. Caddy + cloudflared in a separate shared infra Compose stack (not inside MCP's docker-compose.yml). Cross-stack communication via shared Docker external network.

---

## Area: Caddyfile Delivery

**Q:** Baked into image or bind-mount volume?

**Selected:** Bind-mount volume (operator can edit without rebuilding)

---

## Additional Decisions (from open discussion)

**Infra stack location:** Separate directory (`infra/`) committed to this repo as reference artifacts; operator copies to server (e.g. `~/infra/`)

**Cloudflare starting point:** User has no Cloudflare account or domain. Phase 16 must include full setup walkthrough from account creation through first verified HTTPS request.

**Scope clarification:** Roadmap success criteria said "inside the Compose stack" — updated interpretation is "inside the shared infra Compose stack" given multi-service server context.

---

## Deferred Ideas

- Jellyfin/*arr wiring into Caddy — operator self-service after Phase 16 establishes the pattern
- Caddy LAN HTTPS — future, not needed for tunnel use case
- Cloudflare Access (zero-trust layer) — future consideration
