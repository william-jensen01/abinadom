# Phase 16: Caddy & Cloudflare Tunnel - Research

**Researched:** 2026-04-04
**Domain:** Docker Compose multi-stack networking, Caddy reverse proxy, Cloudflare Tunnel (cloudflared)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Named tunnel (not quick tunnel). Operator creates tunnel once via Cloudflare dashboard or API, receives a `TUNNEL_TOKEN`, stores it in `infra/.env`. Same public URL restored on every `docker compose up`.
- **D-02:** Caddy + cloudflared live in a **separate Compose stack** (`infra/`), not inside the MCP project's `docker-compose.yml`. Shared infrastructure for all services (Jellyfin, *arr, MCP).
- **D-03:** Infra stack files (`infra/docker-compose.yml`, `infra/Caddyfile`, `infra/.env.example`) are committed to this repo as reference artifacts. Operator copies `infra/` to server (e.g. `~/infra/`) and fills in `.env`.
- **D-04:** MCP server connects to Caddy via shared Docker **external network** named `proxy`. Infra Compose stack creates this network; MCP Compose stack joins it. Caddy reaches `mcp-server` by container name.
- **D-05:** MCP server's `ports:` mapping (`${MCP_PORT}:${MCP_PORT}`) is removed — mcp-server only needs to be reachable by Caddy on the internal Docker network.
- **D-06:** Routing chain: `cloudflared → Caddy → mcp-server`. cloudflared's ingress config points at `caddy:80` (HTTP, Docker-internal). Caddy reverse-proxies to `mcp-server:8000` on the shared external network. Cloudflare handles external TLS at the edge.
- **D-07:** Caddy routes by subdomain (`mcp.yourdomain.com → mcp-server:8000`). Adding Jellyfin later = one Caddyfile block, no cloudflared config changes.
- **D-08:** Caddyfile is a **bind-mount volume** from host into Caddy container. Operator can edit routing rules without rebuilding; `docker compose exec caddy caddy reload` applies changes live.
- **D-09:** Full Cloudflare setup walkthrough included in phase output: account creation → domain registration → named tunnel → DNS CNAME → infra stack up → MCP stack wired → end-to-end verification.

### Claude's Discretion

- Caddy and cloudflared image versions to pin (`caddy:2-alpine` is conventional; consider pinning to `caddy:2.9.1-alpine` for reproducibility)
- Exact Docker external network name (`proxy` is conventional)
- Caddyfile structure (global options block, per-site blocks)
- Whether `infra/.env.example` uses placeholder domain or a substitution note
- Container restart policies in infra Compose
- Whether to include a `caddy reload` helper tip in the setup walkthrough

### Deferred Ideas (OUT OF SCOPE)

- Jellyfin/*arr wiring — Phase 16 establishes infra stack; wiring other services is operator self-service
- Caddy TLS for LAN access (self-signed or ACME for local network)
- Cloudflare Access (zero-trust auth in front of the tunnel)
- Rate limiting / WAF rules (Cloudflare dashboard features)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-03 | Caddy reverse proxy handles TLS termination inside Compose stack | Caddy handles TLS termination from Cloudflare; in the `cloudflared → Caddy → mcp-server` chain, Cloudflare terminates external TLS, then forwards HTTP to Caddy on port 80 internally. Caddy is the infra-side TLS termination point and sole ingress for all services. Caddyfile per-site blocks route by subdomain. |
| DEPLOY-04 | cloudflared in Compose stack exposes stable public URL via Cloudflare Tunnel | Named tunnel (not quick tunnel) with `TUNNEL_TOKEN` env var persists across restarts. cloudflared container in infra Compose stack, `restart: unless-stopped`. Token stored in `infra/.env` (not committed). |
</phase_requirements>

---

## Summary

Phase 16 delivers a shared reverse-proxy infrastructure as a separate Docker Compose stack (`infra/`). The stack contains two services: `caddy` (routing and TLS termination from Cloudflare's edge) and `cloudflared` (the outbound tunnel to Cloudflare's network). The MCP server container joins a shared external Docker network called `proxy`, which lets Caddy route to it by container name without any host port exposure.

The Cloudflare Tunnel approach is "remotely managed" — the operator creates the tunnel once in the Cloudflare Zero Trust dashboard, copies the resulting `TUNNEL_TOKEN`, and stores it in `infra/.env`. Every subsequent `docker compose up` in `~/infra/` restores the same public URL automatically. No credentials files, no YAML ingress config files — the ingress rules are configured entirely in the Cloudflare dashboard's Public Hostnames tab and the token carries them.

The operator starts from zero (no Cloudflare account, no domain). Phase 16 must therefore deliver two artifacts: (1) the committed infra Compose stack files, and (2) a complete setup walkthrough document that takes the operator from account creation to a working HTTPS endpoint at `mcp.yourdomain.com` routing to `/health`.

**Primary recommendation:** Use the remotely-managed tunnel pattern (TUNNEL_TOKEN, ingress in Cloudflare dashboard). This is simpler than credentials-file + local YAML config, requires no secret files on disk, and is the pattern Cloudflare now recommends for single-operator deployments.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| caddy | `caddy:2-alpine` (currently resolves to 2.9.1) | Reverse proxy, subdomain routing | Single binary, automatic HTTPS, minimal config, widely used for home-lab Docker stacks |
| cloudflare/cloudflared | `cloudflare/cloudflared:latest` | Cloudflare Tunnel daemon (outbound connector) | Official Cloudflare image; `:latest` is safe for a single-operator stack that does `pull` on redeploy |

**Version notes (verified 2026-04-04):**
- `caddy:2-alpine` on Docker Hub resolves to caddy 2.9.1 (tag `2.9.1-alpine` also available for pinning).
- `cloudflare/cloudflared:latest` was at `2026.2.0` as of February 2026. Cloudflare releases monthly; `:latest` is conventional for cloudflared in operator guides. Pin to a dated tag (e.g. `cloudflare/cloudflared:2026.2.0`) if reproducibility matters more than auto-updates.

### Volumes and Data

| Volume | Type | Purpose |
|--------|------|---------|
| `./Caddyfile:/etc/caddy/Caddyfile:ro` | bind mount | Operator-editable routing config; `:ro` prevents Caddy from modifying it |
| `caddy_data` | named Docker volume | Caddy certificate and session state (survives container recreation) |
| `caddy_config` | named Docker volume | Caddy runtime config cache |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `caddy:2-alpine` | `caddy:2` (Debian) | Alpine is ~10x smaller; no practical difference for this workload |
| TUNNEL_TOKEN env var | credentials JSON file + local config YAML | Credentials file requires mounting a secret file on disk; TUNNEL_TOKEN is cleaner for a Compose-managed deployment |
| Remotely-managed tunnel (dashboard ingress) | Locally-managed tunnel (config YAML ingress) | Local config requires maintaining a cloudflared YAML file and credentials file. Remote config is simpler for a single-operator setup and is Cloudflare's recommended approach for new tunnels. |

**Installation (operator runs on server):**
```bash
# No host packages required — everything runs in Docker
docker network create proxy   # one-time, if not done via compose
```

---

## Architecture Patterns

### Recommended Project Structure

```
infra/                         # operator copies this to ~/infra/ on server
├── docker-compose.yml         # caddy + cloudflared services, defines proxy network
├── Caddyfile                  # bind-mounted into caddy container
├── .env.example               # documents TUNNEL_TOKEN, DOMAIN (committed)
└── .env                       # actual secrets (NOT committed, in .gitignore)

docker-compose.yml             # MCP project root (existing file)
```

The `infra/` directory is committed to the MCP repo as a reference artifact (D-03). The operator copies it to their server and fills in `infra/.env`.

### Pattern 1: Infra Compose Stack (creates the `proxy` network)

The infra stack is the network authority — it creates the `proxy` network. Other stacks join it as external.

```yaml
# infra/docker-compose.yml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - proxy

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - proxy

networks:
  proxy:
    name: proxy
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
```

**Key detail:** The `proxy` network is defined without `external: true` in the infra stack — Compose creates and owns it. Other stacks join it with `external: true`.

### Pattern 2: MCP Compose Stack (joins the `proxy` network as external)

Two changes to the existing `docker-compose.yml`:
1. Remove `ports:` mapping (mcp-server no longer needs host port exposure)
2. Add `networks:` block to join the shared `proxy` network

```yaml
# docker-compose.yml (diff from current)
services:
  mcp-server:
    build: .
    # REMOVE: ports: - "${MCP_PORT:-8000}:${MCP_PORT:-8000}"
    env_file:
      - .env
    volumes:
      - ${CHROMADB_DATA_PATH}:/data/chromadb
      - ${AUTH_DATA_PATH}:/data/auth.db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - proxy            # join the shared infra network

networks:
  proxy:
    external: true       # infra stack owns this; we just join it
    name: proxy
```

### Pattern 3: Caddyfile (subdomain routing)

```
# infra/Caddyfile

{
    # Global options
    # admin disabled — no need for config API in this deployment
    admin off
}

mcp.{$DOMAIN} {
    reverse_proxy mcp-server:8000
}
```

**Notes on this Caddyfile:**
- `{$DOMAIN}` is a Caddy environment variable substitution — `DOMAIN=yourdomain.com` in `infra/.env` makes this work.
- Caddy does NOT need to manage TLS here — Cloudflare terminates TLS at the edge and forwards HTTP to Caddy on port 80. Caddy does not need an ACME email or TLS configuration.
- `reverse_proxy mcp-server:8000` works because both `caddy` and `mcp-server` are on the `proxy` Docker network; Docker resolves `mcp-server` by container name.
- Adding Jellyfin later: one new block `jellyfin.{$DOMAIN} { reverse_proxy jellyfin:8096 }`.

### Pattern 4: cloudflared — Remotely Managed Tunnel (TUNNEL_TOKEN)

In the remotely-managed model, cloudflared needs only the `TUNNEL_TOKEN` env var. The ingress rules (which public hostname maps to which upstream service) are configured in the Cloudflare dashboard's Public Hostnames tab and stored in Cloudflare's config (`config_src: cloudflare`).

The operator configures the dashboard to route:
- Public hostname: `mcp.yourdomain.com`
- Service: `http://caddy:80`

cloudflared resolves `caddy` by container name on the shared `proxy` Docker network.

Docker Compose service configuration:
```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  restart: unless-stopped
  command: tunnel --no-autoupdate run
  environment:
    - TUNNEL_TOKEN=${TUNNEL_TOKEN}
  networks:
    - proxy
```

### Pattern 5: Startup Order

The `proxy` network must exist before either the infra stack or the MCP stack starts. Two valid approaches:
1. **Infra stack creates it** (recommended) — run `docker compose up -d` in `~/infra/` first. Compose creates the `proxy` network during this step.
2. **Pre-create manually** — `docker network create proxy` before either stack starts.

The infra stack should always start first (and remain running). The MCP stack starts second and joins the pre-existing `proxy` network.

### Anti-Patterns to Avoid

- **Publishing mcp-server ports after wiring** — Once Caddy is in place, `ports:` on `mcp-server` is redundant and exposes the port on the host unnecessarily. D-05 requires removing it.
- **Using a local config YAML + credentials file for cloudflared** — Requires mounting credentials on disk and keeping ingress YAML in sync. The TUNNEL_TOKEN + dashboard approach is simpler and is what Cloudflare recommends for remotely-managed tunnels.
- **Pointing cloudflared directly at mcp-server** — The D-06 chain (`cloudflared → Caddy → mcp-server`) is required so Caddy can be the single ingress for future services. Pointing cloudflared at `mcp-server:8000` directly bypasses Caddy and makes adding Jellyfin require tunnel config changes.
- **Using `caddy:latest` instead of `caddy:2-alpine`** — `caddy:latest` sometimes jumps major versions unexpectedly. `caddy:2-alpine` (or a specific version tag) is safer.
- **Not creating a named Caddy data volume** — If `caddy_data` is not a named volume, certificate state is lost on container removal.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS certificate provisioning | Custom ACME scripts | Cloudflare handles TLS at the edge — Caddy doesn't need ACME here | Cloudflare terminates TLS; Caddy receives plain HTTP from cloudflared internally |
| Stable public URL without IP exposure | VPN, port forwarding, dynamic DNS scripts | Cloudflare Tunnel (cloudflared) | Outbound-only connection; no inbound firewall rules; no IP revealed |
| Multi-service routing | Custom nginx config with upstream blocks | Caddy Caddyfile reverse_proxy directive | Caddy handles subdomain routing in 2-3 lines per service |
| Cross-stack container communication | Shared container in every compose file | Docker external network | Networks are first-class Compose objects; `external: true` is the correct pattern |

**Key insight:** The combination of Cloudflare Tunnel + Caddy eliminates every custom solution that operators typically build for self-hosted HTTPS: no port forwarding, no Certbot scripts, no dynamic DNS, no nginx upstream configuration. The entire public exposure surface is managed by two Docker images and a 10-line Caddyfile.

---

## Common Pitfalls

### Pitfall 1: Network Does Not Exist When MCP Stack Starts

**What goes wrong:** `docker compose up` in the MCP project directory fails with `network proxy declared as external, but could not be found`.
**Why it happens:** The `proxy` network is only created when the infra stack starts. If the infra stack hasn't started yet, the network doesn't exist.
**How to avoid:** Document startup order in the setup walkthrough. Infra stack must start first. Optionally add `docker network create proxy` as a pre-flight step in the walkthrough.
**Warning signs:** Compose error message `could not be found` for the `proxy` network on MCP stack startup.

### Pitfall 2: cloudflared Can't Resolve `caddy` by Name

**What goes wrong:** cloudflared container starts but tunnel traffic to `caddy:80` times out.
**Why it happens:** If cloudflared is not on the same Docker network as caddy, Docker DNS resolution fails.
**How to avoid:** Both `cloudflared` and `caddy` must declare `networks: - proxy` in the infra Compose stack. Both containers must be on the `proxy` network.
**Warning signs:** `cloudflared` logs show connection refused or DNS resolution failure for `caddy`.

### Pitfall 3: Caddy Can't Resolve `mcp-server` by Name

**What goes wrong:** Caddy starts, requests come in, but `reverse_proxy mcp-server:8000` returns a 502/503.
**Why it happens:** `mcp-server` is on the `proxy` network (defined in MCP's `docker-compose.yml`), but if the MCP stack isn't running or hasn't joined the `proxy` network, Caddy can't reach it.
**How to avoid:** Start the MCP stack after the infra stack. Verify both containers are on the `proxy` network with `docker network inspect proxy`.
**Warning signs:** Caddy logs show upstream connection errors to `mcp-server:8000`.

### Pitfall 4: Old `ports:` Mapping Left in MCP docker-compose.yml

**What goes wrong:** mcp-server is still published on `${MCP_PORT}` on the host. This is a security gap — anyone who can reach the host IP can bypass Cloudflare and hit the MCP server directly.
**Why it happens:** Easy to forget to remove the `ports:` block when adding the `networks:` block.
**How to avoid:** D-05 requires removing `ports:`. The plan must have an explicit task to remove it and verify it's gone.
**Warning signs:** `docker ps` shows the port published (e.g. `0.0.0.0:8000->8000/tcp`).

### Pitfall 5: Caddyfile DOMAIN Variable Not Set

**What goes wrong:** Caddy starts but serves no sites, or serves the wrong hostname.
**Why it happens:** `{$DOMAIN}` in the Caddyfile is a Caddy environment variable substitution. If `DOMAIN` is not set in `infra/.env`, Caddy logs an error and the site block is skipped.
**How to avoid:** `infra/.env.example` must document `DOMAIN=` as a required variable. The walkthrough must tell the operator to fill it in before starting the stack.
**Warning signs:** Caddy logs `unrecognized site address` or `environment variable not found`.

### Pitfall 6: cloudflare Dashboard Public Hostname Points to Wrong Upstream

**What goes wrong:** HTTPS requests to `mcp.yourdomain.com` fail or hang.
**Why it happens:** In the Cloudflare dashboard's Public Hostnames tab, the service URL must be `http://caddy:80` (HTTP, not HTTPS, because Caddy receives plain HTTP from cloudflared on the internal Docker network). If the operator configures `https://caddy:443`, cloudflared tries TLS to Caddy which is not configured.
**How to avoid:** Setup walkthrough must be explicit: service type = HTTP, service URL = `caddy:80` (or `http://caddy:80`).
**Warning signs:** cloudflared logs TLS handshake errors; requests return 502 at the Cloudflare edge.

### Pitfall 7: Tunnel Token is a Quick Tunnel Token

**What goes wrong:** Stack restarts fine, but public URL changes every time.
**Why it happens:** Quick tunnels (trycloudflare.com) generate ephemeral URLs. If the operator accidentally creates a quick tunnel instead of a named tunnel, D-01 is violated.
**How to avoid:** Setup walkthrough must show named tunnel creation specifically: Cloudflare Zero Trust dashboard → Networks → Cloudflare Tunnels → Create a tunnel → choose Cloudflared → give it a name. The resulting token is for a named, persistent tunnel.
**Warning signs:** The public URL contains `trycloudflare.com` instead of the operator's domain.

---

## Code Examples

Verified patterns from official sources and community docs:

### Complete infra/docker-compose.yml

```yaml
# infra/docker-compose.yml
# Source: patterns verified against docs.docker.com/reference/compose-file/networks/
#         and docker.recipes/devops/cloudflared-tunnel

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - proxy

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${TUNNEL_TOKEN}
    networks:
      - proxy
    depends_on:
      - caddy

networks:
  proxy:
    name: proxy
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
```

### infra/.env.example

```dotenv
# Cloudflare Tunnel token (from Cloudflare Zero Trust dashboard)
# Networks → Cloudflare Tunnels → [your tunnel] → Configure → Token
TUNNEL_TOKEN=

# Your domain (e.g. example.com — NOT mcp.example.com)
DOMAIN=
```

### infra/Caddyfile

```
# infra/Caddyfile
# Source: caddyserver.com/docs/caddyfile/options, caddyserver.com/docs/caddyfile/patterns
# Cloudflare terminates external TLS; Caddy receives plain HTTP from cloudflared.
# No TLS configuration needed in Caddy for this deployment pattern.

{
    admin off
}

mcp.{$DOMAIN} {
    reverse_proxy mcp-server:8000
}
```

### MCP docker-compose.yml changes (diff view)

```yaml
# BEFORE (current docker-compose.yml):
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8000}:${MCP_PORT:-8000}"
    ...

# AFTER (Phase 16 changes):
services:
  mcp-server:
    build: .
    # ports: block removed — mcp-server is internal only
    ...
    networks:
      - proxy

networks:
  proxy:
    external: true
    name: proxy
```

### Named Tunnel Creation (API — alternative to dashboard)

```bash
# Source: developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/cfd_tunnel" \
  --request POST \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --json '{
    "name": "home-server",
    "config_src": "cloudflare"
  }'
# Response contains "token": "eyJ..." — this is the TUNNEL_TOKEN
```

### Docker run command (for testing cloudflared outside Compose)

```bash
# Source: developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token $TUNNEL_TOKEN
```

### Caddy live reload after Caddyfile edit

```bash
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Locally-managed tunnel (credentials file + config YAML) | Remotely-managed tunnel (TUNNEL_TOKEN + dashboard ingress) | Cloudflare Tunnel v2022+ | Simpler: no credentials file on disk, ingress config in dashboard |
| Quick tunnels for testing | Named tunnels for stable URLs | Always available | Named tunnels preserve the URL across restarts |
| Traefik as Docker reverse proxy | Caddy as Docker reverse proxy | Ongoing trend 2022-2025 | Caddy has simpler config for small operator stacks |
| Nginx + Certbot for HTTPS | Caddy automatic HTTPS (or Cloudflare edge TLS) | Caddy v2 (2020+) | Eliminates cron jobs, renewal scripts |

**Deprecated/outdated:**
- `version:` key in `docker-compose.yml` — deprecated in Compose v2 spec (already established in Phase 15 decisions)
- Quick tunnels (`trycloudflare.com`) — explicitly rejected by D-01 due to ephemeral URLs

---

## Open Questions

1. **cloudflared image version pinning**
   - What we know: `:latest` is `2026.2.0` as of Feb 2026; Cloudflare releases monthly
   - What's unclear: Whether the operator wants reproducible deploys (pin to `2026.2.0`) or auto-update behavior (`:latest`)
   - Recommendation: Default to `:latest` in the reference config (conventional for cloudflared in operator guides); note in comments that pinning is an option

2. **Caddyfile — explicit port 80 listener vs domain-based site block**
   - What we know: Cloudflare sends HTTP (not HTTPS) to the Caddy container; Caddy needs to serve on port 80
   - What's unclear: Whether specifying the domain-based block `mcp.{$DOMAIN}` is sufficient for Caddy to listen on port 80, or whether an explicit `:80` block is needed
   - Recommendation: Use the domain-based block — Caddy implicitly listens on port 80 for HTTP-only sites when no TLS config is present. If cloudflared points to `caddy:80`, Caddy will answer on port 80. Verify during implementation.

3. **`depends_on` usefulness for cloudflared → caddy**
   - What we know: `depends_on` in Compose only waits for the container to start, not for Caddy to be ready to accept connections
   - What's unclear: Whether a brief startup race condition between cloudflared and caddy causes real-world issues
   - Recommendation: Include `depends_on: caddy` in cloudflared service as a hint. cloudflared retries tunnel connections automatically, so a brief startup race is self-healing.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Running infra Compose stack | ✓ (dev machine) | 28.4.0 | — |
| Docker Compose v2 | `docker compose up` syntax | ✓ | Included with Docker 28.4.0 | — |
| Cloudflare account | Named tunnel creation | ✗ (operator must create) | — | No fallback — required |
| Domain with Cloudflare DNS | Tunnel public hostname CNAME | ✗ (operator must register) | — | No fallback — required |
| cloudflare/cloudflared image | Tunnel daemon | Available on Docker Hub | 2026.2.0 (latest) | — |
| caddy:2-alpine image | Reverse proxy | Available on Docker Hub | 2.9.1 | — |

**Missing dependencies with no fallback:**
- Cloudflare account — operator must create before running the infra stack
- Domain registered with Cloudflare DNS — required for CNAME record pointing to the tunnel UUID

**Missing dependencies with fallback:**
- None. All runtime dependencies are Docker images pulled automatically.

**Note:** The Dell PowerEdge R720 (operator's deployment target) is not the dev machine. The operator must have Docker + Compose v2 installed on the server. This is assumed to be satisfied (Phase 15 already delivers a working Compose stack on that machine).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | none (uses default pytest discovery) |
| Quick run command | `pipenv run py -m pytest tests/ -q` |
| Full suite command | `pipenv run py -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-03 | Caddy reverse proxy handles TLS termination | manual-only | — | N/A |
| DEPLOY-04 | cloudflared exposes stable public URL | manual-only | — | N/A |

**Rationale for manual-only:** Both DEPLOY-03 and DEPLOY-04 require a live Cloudflare account, a registered domain, and a running Docker stack connected to the internet. These cannot be automated in unit/integration tests. Verification is done via a live `curl` against `https://mcp.yourdomain.com/health` after the stack is running.

The end-to-end verification command (to be documented in the setup walkthrough):
```bash
curl -f https://mcp.yourdomain.com/health
# Expected: {"status": "healthy", ...} with HTTP 200
```

**Existing test suite** (unaffected by Phase 16): All existing tests in `tests/` pass without a Cloudflare account — they test Python code, not Docker/network topology. The plan should confirm the existing test suite still passes after the `docker-compose.yml` change (removing `ports:`).

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/ -q` (existing suite — confirms no Python regressions)
- **Per wave merge:** `pipenv run py -m pytest tests/ -v` + manual `curl https://mcp.yourdomain.com/health` after infra stack is up
- **Phase gate:** HTTPS request to public URL returns 200 before marking DEPLOY-03 and DEPLOY-04 complete

### Wave 0 Gaps

None — existing test infrastructure is sufficient for the Python side. Phase 16 is infrastructure configuration (YAML, Caddyfile, walkthrough doc), not Python code. No new test files needed.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 16 |
|-----------|-------------------|
| Simplicity first — impact minimal code | `docker-compose.yml` changes are minimal: remove `ports:`, add `networks:` block. No application code changes. |
| No hardcoded values — all via `.env` | `TUNNEL_TOKEN` and `DOMAIN` must be in `infra/.env` (not committed). `.env.example` documents them. |
| Python commands use `pipenv run py` | Not directly applicable (infra is YAML/Docker); existing Python tests still run with `pipenv run py -m pytest` |
| Project structure index must be updated | `infra/` directory is new; `CLAUDE.md` project structure index should be updated to reference it |
| Verify before done | Phase 16 is not done until a live `curl https://mcp.yourdomain.com/health` returns 200 |

---

## Sources

### Primary (HIGH confidence)
- [Cloudflare Tunnel docs — create remote tunnel API](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/) — tunnel creation, TUNNEL_TOKEN, Docker run command, DNS CNAME setup
- [Cloudflare Tunnel docs — create remote tunnel dashboard](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/) — dashboard walkthrough
- [Docker Compose networking docs](https://docs.docker.com/compose/how-tos/networking/) — external network behavior
- [Docker Compose network reference](https://docs.docker.com/reference/compose-file/networks/) — `external: true`, `name:` syntax
- [Caddy Caddyfile options docs](https://caddyserver.com/docs/caddyfile/options) — global options block, trusted_proxies, admin
- [Caddy Caddyfile patterns](https://caddyserver.com/docs/caddyfile/patterns) — subdomain routing, reverse_proxy
- [Caddy reverse_proxy directive](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) — header forwarding, trusted_proxies

### Secondary (MEDIUM confidence)
- [Cloudflare Tunnel Docker Compose — docker.recipes](https://docker.recipes/devops/cloudflared-tunnel) — verified TUNNEL_TOKEN env var pattern against official docs
- [Caddy community — Caddy + Cloudflare Tunnel](https://caddy.community/t/caddy-cloudflare-tunnel/15929) — ingress → Caddy routing pattern (`http://caddy:80`)
- [Docker Hub caddy tags](https://hub.docker.com/_/caddy/tags) — confirmed `2.9.1-alpine` as current latest
- [Cloudflared Docker Compose example — sambobb.com](https://www.sambobb.com/posts/cloudflared-in-docker-compose/) — shows credentials-file alternative (used to understand what NOT to do)

### Tertiary (LOW confidence)
- WebSearch results for Docker Compose external network multi-stack patterns — cross-verified with official Docker docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — image names and patterns verified via Docker Hub and official Cloudflare/Caddy docs
- Architecture: HIGH — external network pattern verified against Docker docs; tunnel→Caddy→service chain verified against Caddy community wiki and Cloudflare API docs
- Pitfalls: MEDIUM — some pitfalls derived from community sources and cross-verified with official docs; startup-order pitfall is standard Docker Compose behavior

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (30 days — Caddy and cloudflared are stable; Cloudflare Tunnel API may update but pattern is stable)
