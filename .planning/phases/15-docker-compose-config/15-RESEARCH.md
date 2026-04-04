# Phase 15: Docker Compose & Config - Research

**Researched:** 2026-04-04
**Domain:** Docker, Docker Compose, Python containerization, environment-driven configuration
**Confidence:** HIGH

## Summary

This phase containerizes an existing Python MCP server (FastMCP + uvicorn) using a `Dockerfile` and `docker-compose.yml`. The application is already env-var-driven (`os.environ.get()`), all internal paths are resolved from env vars, and the `/health` endpoint is ready for use as a Docker Compose healthcheck target. No application code changes are required — this phase is purely infrastructure.

The main technical decisions are locked in CONTEXT.md. The key complexity is correctly layering the Dockerfile for fast rebuilds, choosing the right Python base image (Python 3.14.2 is running on the host, but chromadb 1.5.5 requires `>= 3.9`; `python:3.12-slim` is the safe, well-tested target), and generating a `requirements.txt` from the Pipfile.lock so Docker does not need `pipenv` installed in the image.

The secondary concern is the `start_period` in the healthcheck: ChromaDB startup loads ONNX models (tokenizers, embeddings) which takes several seconds on first run. A `start_period` of 40–60s prevents false-positive `unhealthy` state during container startup.

**Primary recommendation:** Use `python:3.12-slim` base image, generate `requirements.txt` via `pipenv requirements > requirements.txt` at build time (or pre-committed as a generated artifact), set fixed container-internal env vars in Dockerfile, and wire all operator-facing variables through `.env` / `compose.yml` variable substitution.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** No Ollama container in Compose. `OLLAMA_URL` is purely `.env`-driven.
- **D-02:** No startup script or entrypoint logic for model pulling. `/health` returns 503 until Ollama is reachable with the model loaded.
- **D-03:** Bind mounts via `.env`-configured host paths. Two variables: `CHROMADB_DATA_PATH` and `AUTH_DATA_PATH`.
- **D-04:** `compose.yml` volume entries use `${CHROMADB_DATA_PATH}:/data/chromadb` and `${AUTH_DATA_PATH}:/data/auth.db`.
- **D-05:** Operator sets host paths to their storage mount (e.g. `/mnt/graviton/sci/chromadb`). No absolute paths in tracked files.
- **D-06:** `CHROMADB_PATH` is fixed at `/data/chromadb` inside the container — set via `ENV CHROMADB_PATH=/data/chromadb` in the Dockerfile. Not operator-facing.
- **D-07:** `AUTH_DB_PATH` is fixed at `/data/auth.db` inside the container — set via `ENV AUTH_DB_PATH=/data/auth.db` in the Dockerfile. Not operator-facing.
- **D-08:** Every configurable value documented in `.env.example` (committed). Operator copies to `.env`.
- **D-09:** Variables in `.env.example`: `OLLAMA_URL`, `MCP_HOST`, `MCP_PORT`, `CHROMADB_DATA_PATH`, `AUTH_DATA_PATH`. Internal paths (`CHROMADB_PATH`, `AUTH_DB_PATH`) are NOT in `.env.example`.

### Claude's Discretion

- Python base image choice (e.g. `python:3.11-slim`) and Dockerfile layer ordering
- Whether pipenv or pip is used inside Docker (Pipfile vs generated requirements.txt)
- Docker Compose healthcheck configuration (interval, retries, timeout) using `/health`
- Container restart policy (`unless-stopped` or `always`)
- Whether `MCP_HOST` and `MCP_PORT` default to `0.0.0.0` and `8000` in the Dockerfile or only in `.env.example`

### Deferred Ideas (OUT OF SCOPE)

- Ollama sidecar container — deferred due to CPU-only hardware (no GPU passthrough benefit)
- Caddy + TLS — Phase 16 scope
- Cloudflare Tunnel — Phase 16 scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Operator can run full stack via `docker compose up` (mcp-server + ollama) | Dockerfile + compose.yml with healthcheck; Ollama is external per D-01 |
| DEPLOY-02 | All secrets and paths configurable via .env file — no hardcoded values | `.env.example` contract (D-08/D-09), bind mount variables (D-03/D-04), fixed internal paths in Dockerfile (D-06/D-07) |
</phase_requirements>

---

## Standard Stack

### Core

| Library/Tool | Version | Purpose | Why Standard |
|--------------|---------|---------|--------------|
| Docker Engine | 28.4.0 (host) | Container runtime | Available on host, confirmed working |
| Docker Compose | v2.39.2 | Multi-container orchestration | Available on host; v2 syntax (`docker compose`) used throughout |
| `python:3.12-slim` | 3.12.x | Dockerfile base image | chromadb 1.5.5 requires Python >=3.9; 3.12 is the latest stable with full onnxruntime wheel support; host runs 3.14.2 but Docker image is independent |

### Supporting

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `pipenv requirements` | Generate pinned `requirements.txt` from Pipfile.lock | Run once before/during image build; output committed as `requirements.txt` |
| curl (in container) | Healthcheck probe via `CMD curl -f http://localhost:8000/health` | Required in slim image — add `RUN apt-get install -y --no-install-recommends curl` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `python:3.12-slim` | `python:3.11-slim` | 3.11 also works; 3.12 is preferred as it's the latest with confirmed onnxruntime wheel availability |
| `python:3.12-slim` | `python:3.14-slim` | 3.14 is the host version but onnxruntime 1.24 wheels may not be available for 3.14; 3.12-slim is safer |
| `pipenv requirements` | `pipenv install` inside Docker | `pipenv install` inside Docker inflates image size significantly and is slower; pre-generated requirements.txt is standard Docker practice |
| `curl` in healthcheck | `wget` or Python `urllib` | curl is conventional and widely documented; wget also works in slim images; Python one-liner avoids extra package but is more fragile |

**Installation in Dockerfile:**
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

**Generate requirements.txt (run once on host before build):**
```bash
pipenv requirements > requirements.txt
```

---

## Architecture Patterns

### Recommended File Layout

```
(project root)/
├── Dockerfile            # New file — image definition
├── docker-compose.yml    # New file — service orchestration
├── .env.example          # New file — committed, documents all variables
├── .env                  # New file — NOT committed, operator copy of .env.example
├── .gitignore            # Existing — must include .env
├── requirements.txt      # New file — generated from Pipfile.lock, committed
├── server.py             # Unchanged
├── auth/                 # Unchanged
├── config/               # Unchanged
└── extractors/           # Unchanged
```

### Pattern 1: Dockerfile Layer Ordering for Cache Efficiency

**What:** Copy and install dependencies before copying application source. This ensures that `pip install` is only re-run when `requirements.txt` changes, not on every source file edit.

**When to use:** Always — this is the standard Docker best practice for Python applications.

**Example:**
```dockerfile
FROM python:3.12-slim

# Install system deps (curl for healthcheck probe)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: requirements only — cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: application source — invalidates on any source change
COPY . .

# Fixed internal paths — not operator-facing (D-06, D-07)
ENV CHROMADB_PATH=/data/chromadb
ENV AUTH_DB_PATH=/data/auth.db

# Defaults for host/port (MCP_HOST/MCP_PORT can be overridden via .env)
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
```

### Pattern 2: Compose File with Variable Substitution and Healthcheck

**What:** `docker-compose.yml` uses `${VAR}` substitution from `.env`. Bind mounts reference operator-set host paths. Healthcheck uses the existing `/health` endpoint.

**When to use:** This is the only compose pattern compatible with D-03/D-04.

**Example:**
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8000}:${MCP_PORT:-8000}"
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
```

**Note on `start_period`:** ChromaDB PersistentClient loads ONNX/tokenizer models on first connect. On a cold start, `/health` may return 503 for 10–30 seconds while ChromaDB initializes. `start_period: 60s` prevents Docker from counting these early failures against `retries`. After `start_period` elapses, normal healthcheck retry logic applies.

**Note on `env_file`:** Using `env_file: .env` passes all variables from `.env` into the container environment. This means `OLLAMA_URL`, `MCP_HOST`, `MCP_PORT` are passed through to `server.py`'s `os.environ.get()` calls. The fixed `ENV` lines in the Dockerfile (`CHROMADB_PATH`, `AUTH_DB_PATH`) serve as defaults but `env_file` values override Dockerfile `ENV` if present — keep internal paths out of `.env.example` to avoid confusion (D-09).

### Pattern 3: `.env.example` Contract

**What:** A committed file documenting every operator-facing variable with example values and comments. Operator copies to `.env`.

**Example:**
```bash
# .env.example — copy to .env and fill in your values

# Ollama endpoint (wherever Ollama is running — host machine, remote box, etc.)
# On Linux host with Docker: use host.docker.internal or the LAN IP
# Example: http://host.docker.internal:11434 or http://192.168.1.10:11434
OLLAMA_URL=http://host.docker.internal:11434

# MCP server bind address and port
MCP_HOST=0.0.0.0
MCP_PORT=8000

# Host-side paths for persistent data (bind mounted into container)
# Set these to your storage locations — they must exist on the host before compose up
CHROMADB_DATA_PATH=/mnt/graviton/sci/chromadb
AUTH_DATA_PATH=/mnt/graviton/sci/auth
```

### Anti-Patterns to Avoid

- **Hardcoding absolute host paths in `compose.yml`:** Violates D-05 and breaks portability. Always use `${VARIABLE}` substitution.
- **Installing pipenv inside Docker and running `pipenv install`:** Slows builds, increases image size by 100–300MB, adds pip-within-pipenv complexity. Use pre-generated `requirements.txt`.
- **Setting `CHROMADB_PATH` or `AUTH_DB_PATH` in `.env.example`:** These are fixed container-internal paths (D-06/D-07). Exposing them as operator variables creates confusion and risk of sync errors.
- **No `start_period` in healthcheck:** Without it, Docker marks the container unhealthy during the ChromaDB/ONNX initialization window, which can cause dependent services (Phase 16 Caddy) to not start.
- **Using `COPY . .` before `COPY requirements.txt .`:** Breaks layer caching — any source change triggers full `pip install`.
- **Storing `.env` in git:** Contains secrets (auth tokens, paths). Must be in `.gitignore`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Healthcheck probe | Custom Python health script | `curl -f http://localhost:8000/health` | `/health` endpoint already exists and returns correct HTTP codes; curl is standard, requires no application code |
| requirements.txt generation | Manually maintaining `requirements.txt` | `pipenv requirements > requirements.txt` | Pipfile.lock already has pinned versions; `pipenv requirements` outputs them in pip-compatible format |
| Container-internal path config | Env vars in `.env.example` for internal paths | `ENV` in Dockerfile | Internal paths never need to change per-deployment; Dockerfile `ENV` is the correct mechanism |

---

## Runtime State Inventory

Step 2.5 SKIPPED — this phase is a greenfield containerization, not a rename/refactor/migration. No string renaming or data migration occurs.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | Container build and run | Yes | 28.4.0 | — |
| Docker Compose | `docker compose up` | Yes | v2.39.2 | — |
| curl (in container) | Healthcheck CMD | Must be installed in image | n/a (slim has none) | `wget -q --spider http://localhost:8000/health` |
| pipenv | Generate `requirements.txt` | Yes | 2026.0.3 | `pip freeze > requirements.txt` (less precise) |

**Missing dependencies with no fallback:** None — all are available or resolvable.

**Missing dependencies with fallback:**
- `curl` not present in `python:3.12-slim` by default — add `RUN apt-get install -y --no-install-recommends curl` to Dockerfile, or use `wget` as alternative healthcheck probe.

---

## Common Pitfalls

### Pitfall 1: ChromaDB Startup Latency Causes False Unhealthy State

**What goes wrong:** Docker marks the container `unhealthy` during the first 10–30 seconds after start, before ChromaDB and ONNX tokenizer models finish loading. Without `start_period`, this burns through all `retries` and the container is permanently unhealthy.

**Why it happens:** ChromaDB's PersistentClient loads ONNX runtime models (tokenizers for nomic-embed-text embedding support) on first instantiation. The `/health` endpoint calls `chromadb.PersistentClient()` inline, so it fails with 503 until ChromaDB is ready.

**How to avoid:** Set `start_period: 60s` in the healthcheck stanza. This tells Docker not to count failures against `retries` during the startup window.

**Warning signs:** Container shows `unhealthy` immediately after start; logs show successful ChromaDB initialization followed by `unhealthy` status.

### Pitfall 2: `env_file` Overrides Dockerfile `ENV` for Internal Paths

**What goes wrong:** If an operator accidentally puts `CHROMADB_PATH` or `AUTH_DB_PATH` in their `.env`, it overrides the Dockerfile `ENV` directive, pointing the server at a path that doesn't exist in the container.

**Why it happens:** Docker `env_file` values take precedence over `ENV` instructions in the Dockerfile.

**How to avoid:** Keep `CHROMADB_PATH` and `AUTH_DB_PATH` out of `.env.example` entirely (D-09). Add a comment in `.env.example` explicitly stating these are fixed inside the container.

### Pitfall 3: Bind Mount Directories Must Pre-Exist on Host

**What goes wrong:** `docker compose up` fails with a bind mount error if `CHROMADB_DATA_PATH` or `AUTH_DATA_PATH` do not exist on the host before running compose.

**Why it happens:** Docker does not create host directories for bind mounts (unlike named volumes, which Docker manages). If the host path is absent, compose fails.

**How to avoid:** Document in `.env.example` that host paths must exist before `docker compose up`. Optionally add a comment like `# mkdir -p /mnt/graviton/sci/chromadb /mnt/graviton/sci/auth`.

### Pitfall 4: `python:3.14-slim` Breaks onnxruntime

**What goes wrong:** onnxruntime does not publish wheels for Python 3.14 (as of April 2026). Building with `python:3.14-slim` causes `pip install` to fail on onnxruntime during image build.

**Why it happens:** The host runs Python 3.14.2, which may tempt the planner to match base images. The Docker image is independent — use `python:3.12-slim`.

**How to avoid:** Use `python:3.12-slim` as base image. chromadb 1.5.5 requires `>= 3.9`; onnxruntime 1.24.4 has wheels for 3.9–3.12.

**Warning signs:** `pip install` failing on `onnxruntime` during `docker build`.

### Pitfall 5: Ollama Unreachable from Container

**What goes wrong:** `OLLAMA_URL=http://localhost:11434` in `.env` makes the container try to connect to itself — but Ollama runs on the host, not in the container. The server fails to start (startup Ollama check in `_check_ollama()` exits with code 1).

**Why it happens:** Inside the container, `localhost` is the container, not the host.

**How to avoid:** Document in `.env.example` that the correct value on Linux is `http://host.docker.internal:11434` or the LAN IP of the host running Ollama. On Linux Docker hosts, `host.docker.internal` requires `extra_hosts: ["host.docker.internal:host-gateway"]` in `compose.yml`.

### Pitfall 6: `.env` Committed to Git Accidentally

**What goes wrong:** Bearer tokens, host paths, or other sensitive values are committed to git.

**Why it happens:** `.env` is in the project root like other tracked files; easy to `git add .` accidentally.

**How to avoid:** Confirm `.env` is in `.gitignore` before the plan begins. This is a Wave 0 verification step.

---

## Code Examples

Verified patterns from official sources and current project code:

### Dockerfile — Complete Reference

```dockerfile
# Source: Docker official Python docs + project conventions
FROM python:3.12-slim

# Install curl for healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Fixed container-internal paths (D-06, D-07) — NOT operator-facing
ENV CHROMADB_PATH=/data/chromadb
ENV AUTH_DB_PATH=/data/auth.db

# Default host/port — can be overridden via .env
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
```

### docker-compose.yml — Complete Reference

```yaml
# Source: Docker Compose v2 docs + CONTEXT.md D-04
services:
  mcp-server:
    build: .
    ports:
      - "${MCP_PORT:-8000}:${MCP_PORT:-8000}"
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
```

**Note on `extra_hosts`:** Required on Linux Docker hosts for `OLLAMA_URL=http://host.docker.internal:11434` to resolve. This stanza is harmless on macOS/Windows Docker Desktop (where `host.docker.internal` resolves natively).

### .env.example — Complete Reference

```bash
# .env.example
# Copy this file to .env and fill in your values.
# DO NOT commit .env to git.
#
# Note: CHROMADB_PATH and AUTH_DB_PATH are fixed inside the container.
# Only set CHROMADB_DATA_PATH and AUTH_DATA_PATH (the host-side paths).

# Ollama — wherever Ollama is running (must be accessible from inside the container)
# On Linux host: http://host.docker.internal:11434
# On LAN: http://192.168.x.x:11434
OLLAMA_URL=http://host.docker.internal:11434

# MCP server network configuration
MCP_HOST=0.0.0.0
MCP_PORT=8000

# Host-side data directories (bind mounted into container as /data/chromadb and /data/auth.db)
# These directories MUST exist on the host BEFORE running docker compose up.
# Example: mkdir -p /mnt/graviton/sci/chromadb /mnt/graviton/sci/auth
CHROMADB_DATA_PATH=/mnt/graviton/sci/chromadb
AUTH_DATA_PATH=/mnt/graviton/sci/auth
```

### Generate requirements.txt

```bash
# Run on host before building — output committed to git
pipenv requirements > requirements.txt
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker-compose` (v1, separate binary) | `docker compose` (v2, Docker plugin) | Docker 20.10+ | Use `docker compose up`, not `docker-compose up`; v2 is installed and confirmed |
| `mcp.run()` stdio transport | `uvicorn.run()` with ASGI app | Phase 14 | Container CMD must invoke `python server.py` (not a uvicorn CLI command); server.py `__main__` block already calls `uvicorn.run()` |
| `pipenv run` in production | Pre-built `requirements.txt` | Docker best practice | Pipenv is a dev tool; production containers use pinned requirements.txt |

**Deprecated/outdated:**
- `version: '3'` top-level key in compose.yml: Deprecated in Compose v2 spec — omit it entirely. Modern compose files do not need a `version` field.

---

## Open Questions

1. **`.env` file path resolution when `compose.yml` is not in project root**
   - What we know: Compose looks for `.env` in the directory where `docker compose` is run (the project root), same directory as `compose.yml`.
   - What's unclear: Not unclear — `.env` and `compose.yml` will both be in the project root.
   - Recommendation: No issue; document that operator must `cd` to project root before `docker compose up`.

2. **Whether `requirements.txt` should be committed or generated during build**
   - What we know: `pipenv requirements` produces a fully pinned, pip-compatible requirements file from Pipfile.lock. It is 96 lines.
   - What's unclear: Committing it means it can drift from Pipfile.lock if someone updates Pipfile without regenerating. Generating at build time requires pipenv in the build environment.
   - Recommendation: Commit `requirements.txt` generated from `pipenv requirements`. Add a note in `.env.example` (or README) to regenerate after `pipenv update`. This is the simplest Docker-compatible approach and avoids adding pipenv to the build stage.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (current project standard) |
| Config file | none — invoked directly |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-01 | `docker compose up` starts mcp-server | smoke/manual | `docker compose up -d && sleep 10 && curl -f http://localhost:8000/health` | No — manual only |
| DEPLOY-01 | Container healthcheck passes after start | smoke/manual | `docker compose ps` (verify `healthy`) | No — manual only |
| DEPLOY-02 | No hardcoded secrets/paths in Dockerfile | static/lint | `grep -rn "graviton\|/mnt\|password\|secret" Dockerfile compose.yml` | No — Wave 0 check |
| DEPLOY-02 | Changing .env value takes effect on `compose up` | smoke/manual | Update `MCP_PORT`, `docker compose up -d`, verify new port | No — manual only |
| DEPLOY-02 | `.env.example` documents all operator variables | static | `diff <(grep -E '^[A-Z_]+=.*' .env.example | cut -d= -f1 | sort) <(echo -e "OLLAMA_URL\nMCP_HOST\nMCP_PORT\nCHROMADB_DATA_PATH\nAUTH_DATA_PATH" | sort)` | No — Wave 0 |

**Justification for manual-only tests:** DEPLOY-01/DEPLOY-02 require Docker daemon, a running Ollama instance with nomic-embed-text loaded, and real filesystem paths. These cannot be automated in unit tests without full integration test infrastructure. Smoke checks against the running compose stack are the correct verification mechanism.

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q` (existing server tests still pass — no regressions)
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green + smoke check `docker compose up` before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Verify `.env` is in `.gitignore` (or add it) — prerequisite before any files are committed
- [ ] Generate `requirements.txt` via `pipenv requirements > requirements.txt` — prerequisite for Dockerfile `COPY requirements.txt .`
- [ ] No new test files required — DEPLOY-01/DEPLOY-02 verified by smoke checks against live compose stack

---

## Sources

### Primary (HIGH confidence)

- Docker Engine 28.4.0 / Compose v2.39.2 — confirmed installed on host via `docker --version`
- Project codebase inspection — `server.py` env var block (lines 258–263), `/health` endpoint (lines 415–443), entry point (lines 450–455)
- CONTEXT.md — all locked decisions (D-01 through D-09) directly consulted
- `pipenv requirements` output — 96-line pinned requirements file confirmed working

### Secondary (MEDIUM confidence)

- Docker official Python deployment guide (via WebSearch) — `python:3.12-slim` recommendation, `start_period` usage, layer ordering for caching
- chromadb 1.5.5 PyPI metadata — `python_version >= '3.9'` requirement confirmed
- onnxruntime 1.24.4 wheel availability — Python 3.13 support via issue tracking (GitHub), 3.12 confirmed safe

### Tertiary (LOW confidence)

- `start_period: 60s` value for ChromaDB startup — estimated from ONNX model load times; may need tuning on the specific R720 hardware. Flag for validation during smoke testing.
- `extra_hosts: host.docker.internal:host-gateway` for Linux — documented in Docker docs; behavior on the specific R720 deployment target (Ubuntu assumed) should be verified during smoke testing.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Docker/Compose versions confirmed on host; Python base image choice based on wheel availability evidence
- Architecture: HIGH — all env var patterns verified in existing server.py code; compose syntax confirmed with running Docker version
- Pitfalls: MEDIUM-HIGH — onnxruntime/Python 3.14 pitfall confirmed by search evidence; `start_period` timing is estimated and may need adjustment

**Research date:** 2026-04-04
**Valid until:** 2026-07-04 (stable Docker/Compose spec; Python base image advice stable unless onnxruntime releases 3.13/3.14 wheels)
