# Self-Deploy Guide

Deploy the LDS MCP server on a Linux machine with Docker Compose. The repository's `docker-compose.yml` is the worked example: copy it and adapt the paths and network names to your host.

The stack has three parts:

- **The MCP server** (`mcp-server`): a code-only image, `h5wyxaa9vrvo/lds-mcp:latest`. It holds no data.
- **Weaviate** (`weaviate`): the vector store the search tools query. The compose file runs it next to the server.
- **An embedding server**: an OpenAI-compatible `/v1/embeddings` endpoint (llama-server running `nomic-embed-text`). The server calls it for every search query, and the loading scripts call it for every object they store.

The data lives in SQLite files that you produce on the host and mount into the container read-only: `core.<N>.db` and `content.<N>.db` for talks, and `scripture.db` for the scriptures.

---

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker Engine and Docker Compose v2 (`docker compose version` prints v2.x+)
- An embedding server serving `nomic-embed-text`, reachable at **one address** from both the `mcp-server` container and the host (the loading scripts run on the host)
- Git, and Python with [pipenv](https://pipenv.pypa.io/) on the machine where you build the data files
- The `proxy` Docker network (created by the infra stack in Step 4)

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/lds-mcp.git
cd lds-mcp
pipenv install
```

The MCP server image is pulled automatically by Docker Compose, so no local build is required. `pipenv install` is for the scripts that produce and load the data (Steps 3 and 5).

---

## Step 2: Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

| Variable | Description | Example |
|----------|-------------|---------|
| `EMBEDDING_URL` | Base URL of the embedding server. The container (through `env_file`) and the host-side loading scripts both read this one value, so use a host and port both can reach | `http://<embedder-host>:<port>` |
| `WEAVIATE_HOST` | Weaviate hostname. The compose file sets it to the service name `weaviate`; set it in `.env` to the host your Weaviate runs on for scripts run on the host | `<weaviate-host>` |
| `WEAVIATE_PORT` | Weaviate HTTP port. Compose sets it for the container; set it in `.env` to the port your Weaviate listens on for scripts run on the host | `<weaviate-http-port>` |
| `WEAVIATE_GRPC_PORT` | Weaviate gRPC port. Compose sets it to `50051` for the container; set it in `.env` to the gRPC port your Weaviate listens on for scripts run on the host | `<weaviate-grpc-port>` |
| `SCI_DB_VERSION` | The SCI release number: selects `core.<N>.db` and `content.<N>.db` (compose defaults to `55`) | `55` |
| `SCI_DB_DIR` | Directory the server reads `core.<N>.db` and `content.<N>.db` from. Compose sets it to the mount point `/data`; unset, it is the `db/` folder next to the code, which is what scripts use | `/data` |
| `SCRIPTURE_DB_PATH` | Where the server reads `scripture.db`. Compose sets it to `/data/scripture.db`, in the same mounted directory; scripts default to `db/scripture.db` | `/data/scripture.db` |
| `FASTMCP_HOST` | Bind address inside container | `0.0.0.0` |
| `FASTMCP_PORT` | Server port inside container | `7363` |
| `SCALEKIT_ENVIRONMENT_URL` | ScaleKit environment URL | `https://yourenv.scalekit.com` |
| `SCALEKIT_RESOURCE_ID` | ScaleKit MCP resource ID | `rid_...` |
| `MCP_BASE_URL` | Public URL of the MCP server | `https://mcp.yourdomain.com` |

> **Weaviate:** The compose file sets `WEAVIATE_HOST: weaviate`, `WEAVIATE_PORT: "8080"` and `WEAVIATE_GRPC_PORT: "50051"` under `environment:`, and those win over `.env` inside the container. The loading scripts run on the host and read `.env`, so set all three there to the host and ports your Weaviate is reachable on from the host (the example compose file publishes `8080` and `50051` on the host).

> **Embedding server:** `pipenv run` loads `.env` and its values win over variables exported in your shell (`EMBEDDING_URL=... pipenv run python ...` still uses the `.env` value), so the loading scripts and the container share the `EMBEDDING_URL` in `.env`. Use whatever host and port the embedding server actually runs on, as long as the name resolves both on the host and inside the container (`localhost` inside the container is the container itself). The embedding server must listen on an address the container can reach, not only on `127.0.0.1`.

---

## Step 3: Produce the Database Files

Produce every file below on the host, under `db/`, **before** `docker compose up`. The whole `db/` directory is mounted, so a file you forgot to build is simply absent in the container.

### Talks: `core.<N>.db` and `content.<N>.db`

Built offline from the BYU Scripture Citation Index (SCI) release plus the Church data committed in the repo. Put the raw release files in `db/sci/` (`core.<N>.db`, `content.<N>.db`), then:

```bash
pipenv run python scripts/build.py --version 55
```

and set `SCI_DB_VERSION=55` in `.env`. The finished files appear as `db/core.55.db` and `db/content.55.db`. The raw release is never modified. See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md) for what `build` does.

### Scriptures: `scripture.db`

Built in two steps. The first is the only one that uses the network:

```bash
pipenv run python scripts/fetch_scriptures.py     # Church API -> raw layer of db/scripture.db
pipenv run python scripts/build_scriptures.py     # raw layer -> parsed tables, JST links, build_id
```

`fetch_scriptures.py` walks the tables of contents of the five standard works and the Joseph Smith Translation appendix, and stores every page. It runs one request at a time, within the Church site's rate limits, and takes a long time on the first run. It exits non-zero and names the pages it could not store; re-run it (`--only-missing` skips pages already stored). `build_scriptures.py` runs offline, reads the JST rows from `core.<N>.db` (so build that first), and fails naming any page that is missing. Rebuilding from the same raw pages and the same `core.<N>.db` gives the same `build_id`.

`scripture.db` is never committed, and `.dockerignore` keeps `*.db` out of the image.

---

## Step 4: Set Up Public Access (Caddy + Cloudflare Tunnel)

The `infra/` directory contains a separate Compose stack that provides TLS termination (Caddy) and a public URL (Cloudflare Tunnel). Follow the full setup walkthrough:

**[infra/SETUP.md](../infra/SETUP.md)**

Do this **before** starting the MCP stack: the infra stack creates the external `proxy` network that `docker-compose.yml` joins.

> **Start order matters.** Start the infra stack first. If the `proxy` network does not exist yet, `docker compose up -d` for the MCP stack will fail with `network proxy declared as external, but could not be found`. Fix: start the infra stack first, then retry.

---

## Step 5: Load Weaviate, Then Start the Server

The server checks Weaviate when it starts: it exits if it cannot reach it, or if any of the four talk collections (`ConferenceTalks`, `ConferenceTalkParagraphs`, `ConferenceTalkCitations`, `ConferenceTalkFootnotes`) is missing or empty. So on a new install, start Weaviate alone, load it, and only then start `mcp-server`. The loading scripts run on the host and use the `.env` from Step 2 (`WEAVIATE_HOST` and the ports for the host, and an `EMBEDDING_URL` both the host and the container can reach).

### Start Weaviate

```bash
docker compose up -d weaviate
docker compose ps        # weaviate should show "Up" / "healthy"
```

Weaviate starts empty and publishes ports `8080` (HTTP) and `50051` (gRPC) on the host.

### Load the talks

```bash
pipenv run python scripts/run_pipeline.py
pipenv run python scripts/verify_weaviate_pipeline.py    # exit 0 = the load checks out
```

This reads `db/core.<N>.db` and `db/content.<N>.db` from Step 3, calls the embedding server for every object, and takes a while. It resumes where it stopped if interrupted. See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md).

### Load the scriptures

```bash
pipenv run python scripts/run_scripture_pipeline.py
pipenv run python scripts/verify_weaviate_scripture.py    # exit 0 = the load checks out
```

`run_scripture_pipeline.py` creates the `ScriptureVerses`, `ScriptureChapters` and `ScriptureMeta` collections from `db/scripture.db` and embeds every object. It is resumable: an interrupted run continues where it stopped. Useful flags: `--book NAME` loads one book only (try `Jude` first as a smoke test; a partial load never records a finished build), and `--force` reloads instead of resuming. Only a complete load records the file's `build_id` in `ScriptureMeta`.

The scripture load is optional for the server to start: the server decides at startup whether the scripture collections exist and whether `scripture.db` opens. Without the collections, scripture search and `corpus_stats` answer "scripture corpus not available"; without a usable file, `get_verse`, `get_chapter_overview`, `get_citing_talks` and `find_cross_references` do. The talk tools are unaffected. Because this is decided once at startup, a load or a file added later takes effect only after the container is recreated.

### Mounts

The image holds code only. `mcp-server` reads every SQLite file from one data directory, mounted once and read-only:

```yaml
environment:
  SCI_DB_DIR: /data
  SCRIPTURE_DB_PATH: /data/scripture.db
volumes:
  - ./db:/data:ro
```

`core.<N>.db` and `content.<N>.db` are resolved inside `SCI_DB_DIR` from `SCI_DB_VERSION`, and `scripture.db` is read from `SCRIPTURE_DB_PATH`, which points into the same directory. Mount nothing at or under `/app/db`: it holds the `db` Python package that is baked into the image. The server reads only these three files from the mounted directory.

### Start the server

```bash
docker compose up -d
docker compose ps        # mcp-server and weaviate should show "Up" / "healthy"
docker compose exec mcp-server curl -f http://localhost:7363/health
```

Expected: HTTP 200 with JSON containing `"status": "ok"`. (`mcp-server` publishes no port on the host, so the check runs inside the container.) An unreachable embedder or Weaviate gives HTTP 503 and `"status": "degraded"`. The healthcheck has a 60-second `start_period`, so `(health: starting)` briefly is normal. `/health` also reports the scripture state under `"scripture"`, as it was when the server started (the embedder and Weaviate checks are live): whether the file opened (`db`), whether the three collections exist (`collections`), both build ids (`file_build_id`, `loaded_build_id`) and `mismatch`.

### Check public access

Once the stack is up, verify end-to-end access from outside your local network (see [infra/SETUP.md](../infra/SETUP.md)):

```bash
curl -f https://mcp.yourdomain.com/health
```

Expected: HTTP 200 with `{"status": "ok", ...}`.

---

## Step 6: Configure ScaleKit (Optional)

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

**Server code:**

```bash
docker compose pull
docker compose up -d
```

**Data files.** Updating means replacing the file on the host, reloading Weaviate, and recreating the container. The server compares the file's `build_id` with Weaviate's, and decides whether scripture is available, only when it starts, so recreate the container after every update.

New scripture data (the Church corrected text or footnotes). Work on a copy so the running server keeps a complete file, then `mv` it over:

```bash
cp db/scripture.db db/scripture.new.db
pipenv run python scripts/fetch_scriptures.py --db db/scripture.new.db
pipenv run python scripts/build_scriptures.py --db db/scripture.new.db
pipenv run python scripts/run_scripture_pipeline.py --db db/scripture.new.db
pipenv run python scripts/verify_weaviate_scripture.py --db db/scripture.new.db
mv db/scripture.new.db db/scripture.db
docker compose up -d --force-recreate mcp-server
```

A different `build_id` makes `run_scripture_pipeline.py` reset the three scripture collections and reload them in full. Until the `mv`, scripture search can return the new build's objects (incomplete while the reload runs) while footnotes, cross-references and JST text still come from the old file, with no warning. Recreating the container afterwards re-runs the startup checks against the new build.

New talk release (a new SCI version `<N>`): put the raw files in `db/sci/`, then

```bash
pipenv run python scripts/build.py --version <N>     # writes db/core.<N>.db and db/content.<N>.db
# set SCI_DB_VERSION=<N> in .env
pipenv run python scripts/run_pipeline.py --force    # reload the talk collections
cp db/scripture.db db/scripture.new.db               # the scripture JST rows come from core.<N>.db, so rebuild it too
pipenv run python scripts/build_scriptures.py --db db/scripture.new.db
pipenv run python scripts/run_scripture_pipeline.py --db db/scripture.new.db
pipenv run python scripts/verify_weaviate_scripture.py --db db/scripture.new.db
mv db/scripture.new.db db/scripture.db
docker compose up -d --force-recreate mcp-server     # picks up the new SCI_DB_VERSION
```

The same applies here: until the container is recreated, the running server answers talk queries with the reloaded Weaviate objects and the old `core.<N>.db`/`content.<N>.db`. See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md) for what each command does.

### Build-id mismatch warning

Scripture search hits come from Weaviate, while footnotes, cross-references and JST text come from `scripture.db`; both must come from the same build. The server compares the file's `build_id` with the one stored in `ScriptureMeta` once, when it starts. If they differ it still starts, logs a warning and sets `mismatch` and a `hint` naming the fix in `/health` (which then keeps reporting that startup result):

```
scripture build mismatch: scripture.db build_id <file>, Weaviate ScriptureMeta build_id <loaded>; re-run `run_scripture_pipeline.py`
```

Fix: run `pipenv run python scripts/run_scripture_pipeline.py` to reload Weaviate from the file you mounted, then recreate `mcp-server` (`docker compose up -d --force-recreate mcp-server`), because a running server does not re-check. If you mounted an older file by mistake, put the right one back and recreate the container instead. The warning appears only when both ids are known: a Weaviate with no finished load reports `loaded_build_id` null, which is not a mismatch. A partial `--book` load leaves no finished `build_id` for the same reason.

---

## Troubleshooting

**1. Container exits immediately**
```bash
docker compose logs mcp-server
```
Common causes:
- Weaviate is not reachable at `WEAVIATE_HOST`/`WEAVIATE_PORT`.
- A talk collection is missing or empty: `ERROR: Weaviate collection '…' not found. Run the pipeline first.` or `ERROR: Collection '…' has 0 records. Re-run the pipeline.` Load the talks (Step 5), then start the container again.

A missing or mis-named `core.<N>.db`/`content.<N>.db` does not stop the container: those files are opened when a tool first reads them, so the symptom is tool errors rather than an exit. Check that `SCI_DB_VERSION` matches the files in `db/` and `docker compose exec mcp-server ls -l /data/`.

**2. Health returns 503 / `"degraded"`**
Two common causes:
- The embedding server is down or `EMBEDDING_URL` is wrong. Check it from inside the container: `docker compose exec mcp-server sh -c 'curl -s "$EMBEDDING_URL/health"'`
- Weaviate is not ready: `curl http://<weaviate-host>:<weaviate-http-port>/v1/.well-known/ready`

**3. `network proxy declared as external, but could not be found`**
The infra stack must be running before the MCP stack starts. Run:
```bash
cd ~/infra && docker compose up -d
```
Then retry starting the MCP stack.

**4. Scripture tools say "scripture corpus not available"**
Either `scripture.db` is not mounted at `SCRIPTURE_DB_PATH` (check `docker compose exec mcp-server ls -l /data/`; if the file is missing there, build it on the host in `db/`, then recreate the container), or the `Scripture*` collections were not loaded in Weaviate when the server started (run `run_scripture_pipeline.py`, then recreate the container: the check happens only at startup).

**5. Cannot reach the embedding server from the container**
Set `EMBEDDING_URL` to the host and port the embedding server actually runs on, reachable from inside the container (`localhost` there is the container itself). Verify the server listens on that address, not just `127.0.0.1`.

**6. OAuth / ScaleKit not working**
Ensure all three ScaleKit variables are set (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, `MCP_BASE_URL`) and the server was restarted after adding them. Check `docker compose logs mcp-server` for JWT validation errors.
