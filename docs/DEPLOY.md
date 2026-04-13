# Self-Deploy Guide

Deploy the LDS MCP server on a Linux machine with Docker Compose.

---

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker Engine and Docker Compose v2 (`docker compose version` prints v2.x+)
- Ollama installed and running on the host with the `nomic-embed-text` model pulled (`ollama pull nomic-embed-text`)
- A populated ChromaDB directory (from running the pipeline, or copied from another machine)
- Git

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/lds-mcp.git
cd lds-mcp
```

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
| `MCP_HOST` | Bind address inside container | `0.0.0.0` |
| `MCP_PORT` | Server port inside container | `7363` |
| `CHROMADB_DATA_PATH` | Host path to ChromaDB data directory | `/home/user/data/chromadb` |
| `AUTH_DATA_PATH` | Host path to auth data directory | `/home/user/data/auth` |
| `AUTH0_DOMAIN` | Auth0 tenant domain (for OAuth) | `your-tenant.auth0.com` |
| `AUTH0_AUDIENCE` | Auth0 API audience | `https://mcp.yourdomain.com` |
| `MCP_BASE_URL` | Public URL of the MCP server | `https://mcp.yourdomain.com` |

> **Note:** `CHROMADB_DATA_PATH` and `AUTH_DATA_PATH` are host-side directories that are bind-mounted into the container. They must exist before starting the stack:
>
> ```bash
> mkdir -p /home/user/data/chromadb /home/user/data/auth
> ```

> **Note on Ollama:** On Linux, `host.docker.internal` resolves to the host gateway via the `extra_hosts` setting in `docker-compose.yml`. This requires Ollama to listen on `0.0.0.0` (not just `127.0.0.1`). To check: `ss -tlnp | grep 11434`.

---

## Step 3: Start the MCP Server

```bash
docker compose up -d
```

Verify the container is running and healthy:

```bash
docker compose ps        # mcp-server should show "Up" / "healthy"
docker compose logs -f   # watch for "Uvicorn running on http://0.0.0.0:7363"
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

## Step 5: Configure Auth0 (Optional)

Auth0 is needed to enable the OAuth 2.0 flow for Claude.ai and other OAuth-capable clients. Without it, only static bearer tokens (via `scripts/manage_keys.py`) are available.

1. Create an Auth0 tenant at <https://manage.auth0.com>
2. Create an API with the identifier matching your `AUTH0_AUDIENCE` value (e.g. `https://mcp.yourdomain.com`)
3. Set `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, and `MCP_BASE_URL` in `.env`
4. Restart the MCP stack:
   ```bash
   docker compose down && docker compose up -d
   ```

> **Without Auth0 configured**, the OAuth discovery endpoints return 404 and only static bearer tokens (via `scripts/manage_keys.py`) are available. See [docs/KEY-MANAGEMENT.md](KEY-MANAGEMENT.md) for token management.

---

## Updating

```bash
cd /path/to/lds-mcp
git pull
docker compose build
docker compose up -d
```

If schema or data changes require a pipeline re-run, follow the pipeline instructions in `docs/PIPELINE_SPEC.md`.

---

## Troubleshooting

**1. Container exits immediately**
Check logs for the specific error:
```bash
docker compose logs mcp-server
```
Common causes: `CHROMADB_DATA_PATH` does not exist on the host, or Ollama is unreachable at the configured `OLLAMA_URL`.

**2. Health returns unhealthy**
Two common causes:
- Ollama model not loaded: run `ollama pull nomic-embed-text` on the host
- ChromaDB collections are empty: the pipeline must be run before starting the server

**3. `network proxy declared as external, but could not be found`**
The infra stack must be running before the MCP stack starts. Run:
```bash
cd ~/infra && docker compose up -d
```
Then retry starting the MCP stack.

**4. Permission denied on auth directory**
Ensure `AUTH_DATA_PATH` exists and is writable by the process running Docker:
```bash
mkdir -p /home/user/data/auth
chmod 755 /home/user/data/auth
```

**5. Cannot connect to Ollama**
On Linux, `host.docker.internal` requires the `extra_hosts: host-gateway` entry (already present in `docker-compose.yml`). Verify Ollama is listening on `0.0.0.0`, not just `127.0.0.1`:
```bash
ss -tlnp | grep 11434
```
If Ollama is only on `127.0.0.1`, edit `/etc/systemd/system/ollama.service` to set `Environment="OLLAMA_HOST=0.0.0.0"` and restart: `sudo systemctl restart ollama`.
