# Self-Deploy Guide

Deploy the LDS MCP server on a Linux machine with Docker Compose.

---

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker Engine and Docker Compose v2 (`docker compose version` prints v2.x+)
- Ollama installed and running on the host with the `nomic-embed-text` model pulled (`ollama pull nomic-embed-text`)
- A running ChromaDB instance accessible via URL (e.g. `http://chromadb.yourdomain.com:8000`)
- Git

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/lds-mcp.git
cd lds-mcp
```

The MCP server image is published at `h5wyxaa9vrvo/lds-mcp:latest` and is pulled automatically by Docker Compose — no local build required.

---

## Step 2: Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

All operator-facing variables with their meanings:

| Variable | Description | Example |
|----------|-------------|---------|
| `OLLAMA_URL` | Ollama base URL (use `host.docker.internal` for host-side Ollama) | `http://host.docker.internal:11434` |
| `CHROMADB_HOST` | ChromaDB server hostname or IP | `chromadb.yourdomain.com` |
| `CHROMADB_PORT` | ChromaDB server port | `8000` |
| `FASTMCP_HOST` | Bind address inside container | `0.0.0.0` |
| `FASTMCP_PORT` | Server port inside container | `7363` |
| `SCALEKIT_ENVIRONMENT_URL` | ScaleKit environment URL | `https://yourenv.scalekit.com` |
| `SCALEKIT_RESOURCE_ID` | ScaleKit MCP resource ID | `rid_...` |
| `MCP_BASE_URL` | Public URL of the MCP server | `https://mcp.yourdomain.com` |

> **ChromaDB:** The server connects to ChromaDB over HTTP using `CHROMADB_HOST` and `CHROMADB_PORT`. No local data directory or volume mount is needed — ChromaDB must be running and reachable before starting the MCP server.

> **Note on Ollama:** On Linux, `host.docker.internal` resolves to the host gateway via the `extra_hosts` setting in `docker-compose.yml`. This requires Ollama to listen on `0.0.0.0` (not just `127.0.0.1`). To check: `ss -tlnp | grep 11434`.

---

## Step 3: Start the MCP Server

```bash
docker compose up -d
```

Verify the container is running and healthy:

```bash
docker compose ps        # mcp-server should show "Up" / "healthy"
docker compose logs -f   # watch for FastMCP startup output
```

Test locally:

```bash
curl -f http://localhost:7363/health
```

Expected: JSON with `"status": "healthy"`.

> **Note:** The healthcheck has a 60-second `start_period` to allow the server to initialize. If the container shows `(health: starting)` briefly, that is normal.

---

## Step 4: Set Up Public Access (Caddy + Cloudflare Tunnel)

The `infra/` directory contains a separate Compose stack that provides TLS termination (Caddy) and a public URL (Cloudflare Tunnel). Follow the full setup walkthrough:

**[infra/SETUP.md](../infra/SETUP.md)**

After completing `infra/SETUP.md`, verify end-to-end access from outside your local network:

```bash
curl -f https://mcp.yourdomain.com/health
```

Expected: HTTP 200 with a JSON body like `{"status": "healthy", ...}`.

> **Start order matters.** The infra stack must be running before you start the MCP stack. If the `proxy` network does not exist yet, `docker compose up -d` for the MCP stack will fail with `network proxy declared as external, but could not be found`. Fix: start the infra stack first, then retry.

---

## Step 5: Configure ScaleKit (Optional)

ScaleKit provides the OAuth 2.1 flow for Claude.ai, Claude Desktop, and other OAuth-capable MCP clients.

**Without ScaleKit configured (local mode):** The server runs with no authentication — any request to `tools/list` and `tools/call` is accepted. Use this for local testing only.

**With ScaleKit configured (remote/hosted mode):** All tool requests require a valid ScaleKit JWT. The OAuth discovery endpoints are served at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`.

To configure ScaleKit:

1. Create an MCP Server resource in the [ScaleKit Dashboard](https://docs.scalekit.com/mcp/overview/)
2. Note the Resource ID → `SCALEKIT_RESOURCE_ID`
3. Set `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, and `MCP_BASE_URL` in `.env`
4. Restart the MCP stack:
   ```bash
   docker compose down && docker compose up -d
   ```

Leave all three ScaleKit variables blank to run in unauthenticated local mode.

---

## Updating

```bash
docker compose pull
docker compose up -d
```

No rebuild is required — the published image at `h5wyxaa9vrvo/lds-mcp:latest` is updated on each release.

---

## Troubleshooting

**1. Container exits immediately**
Check logs for the specific error:
```bash
docker compose logs mcp-server
```
Common causes: ChromaDB is unreachable at the configured `CHROMADB_HOST`/`CHROMADB_PORT`, or Ollama is unreachable at the configured `OLLAMA_URL`.

**2. Health returns unhealthy**
Two common causes:
- Ollama model not loaded: run `ollama pull nomic-embed-text` on the host
- ChromaDB is unreachable — verify it's running:
  ```bash
  curl http://<CHROMADB_HOST>:<CHROMADB_PORT>/api/v1/heartbeat
  ```

**3. `network proxy declared as external, but could not be found`**
The infra stack must be running before the MCP stack starts. Run:
```bash
cd ~/infra && docker compose up -d
```
Then retry starting the MCP stack.

**4. Cannot connect to Ollama**
On Linux, `host.docker.internal` requires the `extra_hosts: host-gateway` entry (already present in `docker-compose.yml`). Verify Ollama is listening on `0.0.0.0`, not just `127.0.0.1`:
```bash
ss -tlnp | grep 11434
```
If Ollama is only on `127.0.0.1`, edit `/etc/systemd/system/ollama.service` to set `Environment="OLLAMA_HOST=0.0.0.0"` and restart: `sudo systemctl restart ollama`.

**5. OAuth / ScaleKit not working**
Ensure all three ScaleKit variables are set (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, `MCP_BASE_URL`) and the server was restarted after adding them. Check `docker compose logs mcp-server` for JWT validation errors.
