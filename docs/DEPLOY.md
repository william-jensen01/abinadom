# Self-Deploy Guide

Deploy the LDS MCP server on a Linux machine with Docker Compose. Everything, including building the data files and loading Weaviate, runs in containers from the repository's `docker-compose.yml`. The machine needs Docker, not a Python install.

The stack has four parts:

- **The MCP server** (`mcp-server`): a code-only image, `h5wyxaa9vrvo/lds-mcp:latest`. It holds no data.
- **The tools** (`tools`): an image, `h5wyxaa9vrvo/lds-mcp-tools:latest`, with the build, fetch, load and verify scripts. It is not started by `docker compose up`; you run one script at a time with `docker compose run --rm tools scripts/<script>.py ...`.
- **Weaviate** (`weaviate`): the vector store the search tools query. The compose file runs it next to the server.
- **An embedding server**: an OpenAI-compatible `/v1/embeddings` endpoint (llama-server running `nomic-embed-text`). The server calls it for every search query, and the load scripts call it for every object they store.

The data lives in SQLite files that the tools build into the host's `db/` directory. `mcp-server` mounts that directory read-only at `/data`; `tools` mounts it read-write at `/data`. Talks are `core.<N>.db` and `content.<N>.db`, scriptures are `scripture.db`.

---

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker Engine and Docker Compose v2 (`docker compose version` prints v2.x+)
- Git
- An embedding server serving `nomic-embed-text`, reachable from inside the containers (see Step 2)

---

## Step 1: Clone the Repository and Build the Images

```bash
git clone https://github.com/YOUR_USERNAME/lds-mcp.git
cd lds-mcp
docker compose build mcp-server tools
```

`docker compose build mcp-server tools` builds both images from the `Dockerfile` (name both: `tools` is in a compose profile, so a bare `docker compose build` builds only `mcp-server`): the lean `server` target (`mcp-server`) and the `tools` target (the server plus `scripts/` and what they import). A fresh clone needs it before the first `docker compose run` of `tools`. If the images are already published, `docker compose pull mcp-server tools` fetches them instead.

---

## Step 2: Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Both `mcp-server` and `tools` read `.env` (`env_file`).

| Variable | Description | Example |
|----------|-------------|---------|
| `EMBEDDING_URL` | Base URL of the embedding server. The containers call it, so the host and port must be reachable from inside a container (`localhost` there is the container itself), and the embedder must listen on an address the containers can reach, not only on `127.0.0.1` | `http://<embedder-host>:<port>` |
| `SCI_DB_VERSION` | The SCI release number: selects `core.<N>.db` and `content.<N>.db` (compose defaults to `55`) | `55` |
| `FASTMCP_HOST` | Bind address inside container | `0.0.0.0` |
| `FASTMCP_PORT` | Server port inside container | `7363` |
| `SCALEKIT_ENVIRONMENT_URL` | ScaleKit environment URL | `https://yourenv.scalekit.com` |
| `SCALEKIT_RESOURCE_ID` | ScaleKit MCP resource ID | `rid_...` |
| `MCP_BASE_URL` | Public URL of the MCP server | `https://mcp.yourdomain.com` |
| `COMPOSE_FILE` | Which compose files `docker compose` uses; see "Compose files" below | `docker-compose.yml:docker-compose.proxy.yml` |
| `HOST_UID`, `HOST_GID` | Owner of the files `tools` writes into `db/` (default `1000:1000`) | output of `id -u` and `id -g` |

> **Set by compose, not by `.env`.** `docker-compose.yml` sets the data paths (`SCI_DB_DIR=/data`, `SCI_REPORT_DIR=/data/reports`) and the Weaviate address (`WEAVIATE_HOST=weaviate`, `WEAVIATE_PORT=8080`, `WEAVIATE_GRPC_PORT=50051`) for both containers under `environment:`. Those win over `.env`, so a stale value there cannot reach a container. The `WEAVIATE_*` lines in `.env.example` are only for developers running scripts directly on a host.

### File ownership: `HOST_UID` and `HOST_GID`

`tools` runs as `${HOST_UID:-1000}:${HOST_GID:-1000}`, so everything it writes into `db/` belongs to that user rather than root. If your login is not `1000:1000`, set both in `.env`:

```bash
echo "HOST_UID=$(id -u)" >> .env
echo "HOST_GID=$(id -g)" >> .env
```

### Compose files

`docker compose` reads the base `docker-compose.yml` alone unless `COMPOSE_FILE` says otherwise. With the base file alone:

- `mcp-server` is published on `127.0.0.1:7363` only, and the stack uses its own network.
- Weaviate publishes no host ports. The tools reach it by service name inside the network.

Two override files change that. Add them to `COMPOSE_FILE` in `.env` (colon-separated) to make them permanent, or pass them with `-f`.

- **`docker-compose.proxy.yml`**: also joins `mcp-server` to the external `proxy` Docker network, so a reverse proxy or tunnel can reach it by service name (Step 4). It stays on the default network too, where Weaviate is. For the hosted deploy:
  ```
  COMPOSE_FILE=docker-compose.yml:docker-compose.proxy.yml
  ```
  The `proxy` network must exist first, or `docker compose up` fails with `network proxy declared as external, but could not be found`.
- **`docker-compose.weaviate-ports.yml`**: publishes Weaviate's HTTP and gRPC ports (`8080`, `50051`) on `127.0.0.1` only, for inspecting it from the host. The load scripts do not need it.
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.weaviate-ports.yml up -d weaviate
  ```
  Passing `-f` replaces `COMPOSE_FILE`, so list every file you want (add `-f docker-compose.proxy.yml` if you use it).

---

## Step 3: Produce the Database Files

Every file below is built into `db/` on the host, by the `tools` container, **before** `docker compose up -d`. The whole `db/` directory is mounted into the containers as `/data`, so a file you forgot to build is simply absent.

Start Weaviate first (the `tools` service waits for it to be healthy before running):

```bash
docker compose up -d weaviate
docker compose ps        # weaviate should show "Up" / "healthy"
```

### Talks: `core.<N>.db` and `content.<N>.db`

Built from the BYU Scripture Citation Index (SCI) release plus the Church data committed in the repository and baked into the `tools` image. One command downloads the release and builds from it:

```bash
docker compose run --rm tools scripts/setup_data.py talks --version 55
docker compose run --rm tools scripts/setup_data.py talks --version latest   # or: the newest release on the site
```

It runs `fetch_sci.py` to download the release, then `build.py` for that release, and ends by printing the line for `.env`, for example `SCI_DB_VERSION=55`: set `SCI_DB_VERSION` in `.env` to what it prints. Without `--version` it uses `SCI_DB_VERSION` (default `55`). Add `--force` to overwrite an existing build (it does not download the release again). It never touches Weaviate; loading is Step 5.

The finished files appear as `db/core.<N>.db` and `db/content.<N>.db`, with `db/build_report.<N>.json` beside them (rebuilding overwrites it). See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md) for what `build` does.

**Before building a newer release**, run `git pull` and `docker compose build tools`. The Church JSON that `build.py` reads is baked into the `tools` image, and a new SCI release can contain talks an older image's JSON does not know about. If setup warns that SCI talks are missing Church data, do exactly that, then run the same setup command again with `--force`.

About the release download:

- Releases come from `https://scriptures.byu.edu/sci.<N>.zip`; the site has no index. `latest` starts at the higher of `SCI_DB_VERSION` (default `55`) and the newest release already in `db/sci/`, tries the next three numbers past the newest one found, and stops after three misses in a row. There was never a release 54.
- The release is installed in `db/sci/` as `core.<N>.db`, `content.<N>.db`, `lucene.<N>/` (the release's search index: kept, but nothing uses it) and `sci.<N>.json` (a download record). Other releases there are left alone, and the build never modifies any of it.
- Re-running downloads nothing unless the release changed on the site (it compares the ETag in `sci.<N>.json`). A release you put in `db/sci/` by hand, without a record, is kept as it is. `fetch_sci.py --force` downloads it again.
- A failed or cut-off download, or a zip that does not look right, leaves `db/sci/` as it was.

The same work as separate steps:

```bash
docker compose run --rm tools scripts/fetch_sci.py --version 55     # or --version latest; installs the release in db/sci/
docker compose run --rm tools scripts/build.py --version 55         # add --force to overwrite an existing build
```

then set `SCI_DB_VERSION=55` in `.env` yourself.

### Scriptures: `scripture.db`

One command runs both steps:

```bash
docker compose run --rm tools scripts/setup_data.py scriptures
```

Or run them separately. The first is the only one that uses the network:

```bash
docker compose run --rm tools scripts/fetch_scriptures.py     # Church API -> raw layer of db/scripture.db
docker compose run --rm tools scripts/build_scriptures.py     # raw layer -> parsed tables, JST links, build_id
```

`fetch_scriptures.py` walks the tables of contents of the five standard works and the Joseph Smith Translation appendix, and stores every page. It runs one request at a time, within the Church site's rate limits, and takes a long time on the first run. It exits non-zero and names the pages it could not store; re-run it (`--only-missing` skips pages already stored). `build_scriptures.py` runs offline, reads the JST rows from `core.<N>.db` (so build that first), and fails naming any page that is missing. Rebuilding from the same raw pages and the same `core.<N>.db` gives the same `build_id`.

`scripture.db` is never committed, and `.dockerignore` keeps `*.db` out of the images.

### About `scripts/fetch.py`

`scripts/fetch.py` downloads Church conference data. It runs in the container like every other script (`docker compose run --rm tools scripts/fetch.py ...`), but its output is not kept: the Church JSON files (the ones the build reads and the topics index) are baked into the `tools` image from the repository, and what a container writes there vanishes with it. To refresh that JSON, run `fetch.py` on a development machine (see [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md)), commit the result, and run `docker compose build tools` again.

---

## Step 4: Set Up Public Access (Optional: Caddy + Cloudflare Tunnel)

Skip this step to run the server on `127.0.0.1:7363` only (the base compose file).

For a public URL, the `infra/` directory holds a separate Compose stack that provides TLS termination (Caddy) and a Cloudflare Tunnel. Follow the full walkthrough:

**[infra/SETUP.md](../infra/SETUP.md)**

That stack creates the external `proxy` network. Start it **before** the MCP stack, and enable `docker-compose.proxy.yml` (Step 2) so `mcp-server` joins that network.

> **Start order matters.** With the proxy override enabled and no `proxy` network, `docker compose up -d` fails with `network proxy declared as external, but could not be found`. Start the infra stack first (or run `docker network create proxy`), then retry.

---

## Step 5: Load Weaviate, Then Start the Server

The server checks Weaviate when it starts: it exits if it cannot reach it, or if any of the four talk collections (`ConferenceTalks`, `ConferenceTalkParagraphs`, `ConferenceTalkCitations`, `ConferenceTalkFootnotes`) is missing or empty. So on a new install the order is: Weaviate (Step 3), then the loads below, then `docker compose up -d`.

The load and verify scripts run in the `tools` container, on the compose network, so they reach Weaviate by service name and the embedder at `EMBEDDING_URL`. `run_pipeline.py` writes `failed_talks.json` and `verify_weaviate_pipeline.py` writes `weaviate_verification_report.json` under `/data/reports`, which is `db/reports/` on the host. The scripture load and verify scripts write no report.

### Load the talks

```bash
docker compose run --rm tools scripts/run_pipeline.py
docker compose run --rm tools scripts/verify_weaviate_pipeline.py    # exit 0 = the load checks out
```

This reads `core.<N>.db` and `content.<N>.db` from Step 3, calls the embedding server for every object, and takes a while. It resumes where it stopped if interrupted. See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md).

### Load the scriptures

```bash
docker compose run --rm tools scripts/run_scripture_pipeline.py
docker compose run --rm tools scripts/verify_weaviate_scripture.py    # exit 0 = the load checks out
```

`run_scripture_pipeline.py` creates the `ScriptureVerses`, `ScriptureChapters` and `ScriptureMeta` collections from `scripture.db` and embeds every object. It is resumable: an interrupted run continues where it stopped. Useful flags: `--book NAME` loads one book only (try `Jude` first as a smoke test; a partial load never records a finished build), and `--force` reloads instead of resuming. Only a complete load records the file's `build_id` in `ScriptureMeta`.

The scripture load is optional for the server to start: the server decides at startup whether the scripture collections exist and whether `scripture.db` opens. Without the collections, scripture search and `corpus_stats` answer "scripture corpus not available"; without a usable file, `get_verse`, `get_chapter_overview`, `get_citing_talks` and `find_cross_references` do. The talk tools are unaffected. Because this is decided once at startup, a load or a file added later takes effect only after the container is recreated.

### Mounts

The images hold code only. Both services mount the same host directory:

```yaml
# mcp-server: reads only
environment:
  SCI_DB_DIR: /data
volumes:
  - ./db:/data:ro

# tools: reads and writes
volumes:
  - ./db:/data
```

`core.<N>.db` and `content.<N>.db` are resolved inside `SCI_DB_DIR` from `SCI_DB_VERSION`, the raw release is read from `/data/sci`, and `scripture.db` sits in the same directory (`/data/scripture.db`). Mount nothing at or under `/app/db`: it holds the `db` Python package that is baked into the images. Inside `tools`, name your own files by their `/data/...` path (for example `--db /data/scripture.new.db`), never `db/...`, which would be the package directory.

### Start the server

```bash
docker compose up -d
docker compose ps        # mcp-server and weaviate should show "Up" / "healthy"
curl -f http://127.0.0.1:7363/health
```

Expected: HTTP 200 with JSON containing `"status": "ok"`. (`mcp-server` is published on `127.0.0.1:7363` only. To check from inside the container instead: `docker compose exec mcp-server curl -f http://localhost:7363/health`.) An unreachable embedder or Weaviate gives HTTP 503 and `"status": "degraded"`. The healthcheck has a 60-second `start_period`, so `(health: starting)` briefly is normal. `/health` also reports the scripture state under `"scripture"`, as it was when the server started (the embedder and Weaviate checks are live): whether the file opened (`db`), whether the three collections exist (`collections`), both build ids (`file_build_id`, `loaded_build_id`) and `mismatch`.

Confirm the files the tools created in `db/` are owned by you, not root: `ls -l db/`.

### Check public access

If you set up Step 4, verify end-to-end access from outside your local network (see [infra/SETUP.md](../infra/SETUP.md)):

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
docker compose pull mcp-server tools      # or: docker compose build mcp-server tools
docker compose up -d
```

If you pulled only `mcp-server`, rebuild `tools` (`docker compose build tools`) so the scripts and the Church JSON match the new code.

**Data files.** Updating means replacing the file in `db/`, reloading Weaviate, and recreating the container. The server compares the file's `build_id` with Weaviate's, and decides whether scripture is available, only when it starts, so recreate the container after every update.

New scripture data (the Church corrected text or footnotes). Work on a copy so the running server keeps a complete file, then `mv` it over:

```bash
cp db/scripture.db db/scripture.new.db
docker compose run --rm tools scripts/fetch_scriptures.py --db /data/scripture.new.db
docker compose run --rm tools scripts/build_scriptures.py --db /data/scripture.new.db
docker compose run --rm tools scripts/run_scripture_pipeline.py --db /data/scripture.new.db
docker compose run --rm tools scripts/verify_weaviate_scripture.py --db /data/scripture.new.db
mv db/scripture.new.db db/scripture.db
docker compose up -d --force-recreate mcp-server
```

A different `build_id` makes `run_scripture_pipeline.py` reset the three scripture collections and reload them in full. Until the `mv`, scripture search can return the new build's objects (incomplete while the reload runs) while footnotes, cross-references and JST text still come from the old file, with no warning. Recreating the container afterwards re-runs the startup checks against the new build.

New talk release (a new SCI version `<N>`): run `git pull` and `docker compose build tools` first (see Step 3), then

```bash
docker compose run --rm tools scripts/setup_data.py talks --version <N>   # or latest; writes db/core.<N>.db and db/content.<N>.db
# set SCI_DB_VERSION=<N> in .env, as setup prints
docker compose run --rm tools scripts/run_pipeline.py --force    # reload the talk collections
cp db/scripture.db db/scripture.new.db                           # the scripture JST rows come from core.<N>.db, so rebuild it too
docker compose run --rm tools scripts/build_scriptures.py --db /data/scripture.new.db
docker compose run --rm tools scripts/run_scripture_pipeline.py --db /data/scripture.new.db
docker compose run --rm tools scripts/verify_weaviate_scripture.py --db /data/scripture.new.db
mv db/scripture.new.db db/scripture.db
docker compose up -d --force-recreate mcp-server                 # picks up the new SCI_DB_VERSION
```

The same applies here: until the container is recreated, the running server answers talk queries with the reloaded Weaviate objects and the old `core.<N>.db`/`content.<N>.db`. See [update/HOW_UPDATES_WORK.md](update/HOW_UPDATES_WORK.md) for what each command does.

### Build-id mismatch warning

Scripture search hits come from Weaviate, while footnotes, cross-references and JST text come from `scripture.db`; both must come from the same build. The server compares the file's `build_id` with the one stored in `ScriptureMeta` once, when it starts. If they differ it still starts, logs a warning and sets `mismatch` and a `hint` naming the fix in `/health` (which then keeps reporting that startup result):

```
scripture build mismatch: scripture.db build_id <file>, Weaviate ScriptureMeta build_id <loaded>; re-run `run_scripture_pipeline.py`
```

Fix: run `docker compose run --rm tools scripts/run_scripture_pipeline.py` to reload Weaviate from the file you mounted, then recreate `mcp-server` (`docker compose up -d --force-recreate mcp-server`), because a running server does not re-check. If you mounted an older file by mistake, put the right one back and recreate the container instead. The warning appears only when both ids are known: a Weaviate with no finished load reports `loaded_build_id` null, which is not a mismatch. A partial `--book` load leaves no finished `build_id` for the same reason.

---

## Troubleshooting

**1. Container exits immediately**
```bash
docker compose logs mcp-server
```
Common causes:
- Weaviate is not reachable (it must be healthy; `docker compose ps`).
- A talk collection is missing or empty: `ERROR: Weaviate collection '…' not found. Run the pipeline first.` or `ERROR: Collection '…' has 0 records. Re-run the pipeline.` Load the talks (Step 5), then start the container again.

A missing or mis-named `core.<N>.db`/`content.<N>.db` does not stop the container: those files are opened when a tool first reads them, so the symptom is tool errors rather than an exit. Check that `SCI_DB_VERSION` matches the files in `db/` and `docker compose exec mcp-server ls -l /data/`.

**2. Health returns 503 / `"degraded"`**
Two common causes:
- The embedding server is down or `EMBEDDING_URL` is wrong. Check it from inside the container: `docker compose exec mcp-server sh -c 'curl -s "$EMBEDDING_URL/health"'`
- Weaviate is not ready: `docker compose ps`, or `docker compose logs weaviate`.

**3. `network proxy declared as external, but could not be found`**
Only with `docker-compose.proxy.yml` enabled. The infra stack must be running before the MCP stack starts. Run:
```bash
cd ~/infra && docker compose up -d
```
Then retry starting the MCP stack. Without a reverse proxy, remove the override from `COMPOSE_FILE`.

**4. Scripture tools say "scripture corpus not available"**
Either `scripture.db` is not in the data directory (check `docker compose exec mcp-server ls -l /data/`; if the file is missing there, build it in `db/`, then recreate the container), or the `Scripture*` collections were not loaded in Weaviate when the server started (run `run_scripture_pipeline.py` in `tools`, then recreate the container: the check happens only at startup).

**5. Cannot reach the embedding server from a container**
Set `EMBEDDING_URL` to the host and port the embedding server actually runs on, reachable from inside the container (`localhost` there is the container itself). Verify the server listens on that address, not just `127.0.0.1`. The load scripts fail the same way when they cannot reach it.

**6. Files in `db/` are owned by root, or `tools` cannot write**
Set `HOST_UID` and `HOST_GID` in `.env` to your user's ids (`id -u`, `id -g`) and make `db/` writable by that user. Fix files already created as root with `sudo chown -R "$(id -u):$(id -g)" db/`.

**7. OAuth / ScaleKit not working**
Ensure all three ScaleKit variables are set (`SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_RESOURCE_ID`, `MCP_BASE_URL`) and the server was restarted after adding them. Check `docker compose logs mcp-server` for JWT validation errors.
