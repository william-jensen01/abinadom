---
phase: 19-create-an-alternative-mcp-server-using-fastmcp-and-scalekit-
reviewed: 2026-04-15T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - .env.example
  - Pipfile
  - docker-compose.yml
  - requirements.txt
  - server.py
  - tests/test_server.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 19: Code Review Report

**Reviewed:** 2026-04-15
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 19 rewrites the MCP server using FastMCP 3.2.4 with ScalekitProvider auth and removes the previous FastAPI + BaseHTTPMiddleware stack. The code is architecturally clean and the test suite covers the core tool logic well. Five warnings were found: two are crash-risk bugs (unguarded `int()` conversion on a module-level env var, and a `None`-default `ctx` parameter that will produce cryptic `AttributeError`s); two are correctness issues (Ollama URL inconsistency in the search path, and a flawed env-guard assertion in tests); one is a Docker healthcheck concern. Three info-level findings cover Pipfile wildcard versions, a spurious first line in `requirements.txt`, and test structure.

---

## Warnings

### WR-01: Unguarded `int()` on `FASTMCP_PORT` crashes at import

**File:** `server.py:247`
**Issue:** `FASTMCP_PORT = int(os.environ.get("FASTMCP_PORT", "7363"))` will raise a bare `ValueError` if the env var contains a non-integer value (e.g. `"abc"`, an empty string from a misconfigured `.env`). This crash happens at module import time, before any error handling or logging is configured, producing an unhelpful traceback.
**Fix:**
```python
_raw_port = os.environ.get("FASTMCP_PORT", "7363")
try:
    FASTMCP_PORT = int(_raw_port)
except ValueError:
    logger.error("FASTMCP_PORT must be an integer, got: %r — using default 7363", _raw_port)
    FASTMCP_PORT = 7363
```

---

### WR-02: `ctx: Context = None` default causes `AttributeError` instead of a clear error

**File:** `server.py:331, 399`
**Issue:** Both `search` and `get_talk` declare `ctx: Context = None` as a default parameter. Inside each function, `ctx.lifespan_context["app"]` is called immediately. If `ctx` is `None` (e.g. called from a test that forgets to pass it, or from a FastMCP version that handles missing context differently), this raises `AttributeError: 'NoneType' object has no attribute 'lifespan_context'` with no useful message. In FastMCP tools, `ctx` is injected automatically; the `= None` default is a footgun — it silences the "required argument" signal and produces a confusing crash rather than a `TypeError`.
**Fix:** Remove the `= None` default so Python raises `TypeError: search() missing required argument: 'ctx'` on miscall, which is far easier to debug:
```python
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context,   # no default — FastMCP always injects this
) -> str:
```
Apply the same fix to `get_talk`.

---

### WR-03: `search` tool ignores `OLLAMA_URL` env var — always hits localhost

**File:** `server.py:362-364`
**Issue:** The `search` tool calls `get_embedding_function()` with no `url=` argument, which falls back to `http://localhost:11434/api/embeddings`. The startup helper `_check_ollama` (line 121) correctly calls `resolve_ollama_url()` and passes the result as `url=`. In Docker deployments where `OLLAMA_URL` is set to `http://host.docker.internal:11434`, all live search queries will silently fail against localhost while the startup health check passes against the correct host.
**Fix:**
```python
try:
    ollama_url = resolve_ollama_url()
    ef = get_embedding_function(url=ollama_url)
    query_vector = ef([query])
except Exception as e:
    return f"Search unavailable: Ollama is unreachable ({e})."
```

---

### WR-04: `test_env_vars_no_hardcoded_values` assertion always passes (logic error)

**File:** `tests/test_server.py:784`
**Issue:** The guard `assert "http://" not in source or "os.environ" in source` uses OR, not AND. Since `os.environ` is guaranteed to be present in the source file, the right operand is always `True`, making the entire assertion a no-op. A hardcoded URL like `SCALEKIT_ENVIRONMENT_URL = "https://foo.scalekit.com"` would pass this test.
**Fix:** The assertion should verify that no literal `http://` string appears in *non-comment, non-env-var* context. A simpler reformulation:
```python
# Ensure no hardcoded URLs exist outside of os.environ.get() calls
import re
hardcoded = re.findall(r'(?<!os\.environ[^)]{0,60})https?://[^\s\'"]+', source)
assert not hardcoded, f"Hardcoded URL(s) found in server.py: {hardcoded}"
```
At minimum, flip to an AND assertion: `assert "http://" not in source and "os.environ" in source` — though this would also break on any `http://` in comments; a targeted regex is better.

---

### WR-05: Docker healthcheck requires `curl` — not guaranteed in container image

**File:** `docker-compose.yml:9`
**Issue:** `test: ["CMD", "curl", "-f", "http://localhost:7363/health"]` assumes `curl` is present in the container image. If the base image is a slim Python image (e.g. `python:3.12-slim`), `curl` is not installed by default. The healthcheck silently fails as "unhealthy" without any startup error, making the container appear broken even when the server is running correctly.
**Fix:** Either install `curl` in the Dockerfile (`RUN apt-get install -y --no-install-recommends curl`), or use the Python-based alternative which is always available:
```yaml
test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:7363/health')"]
```

---

## Info

### IN-01: `requirements.txt` line 1 is not a valid pip requirement

**File:** `requirements.txt:1`
**Issue:** The first line reads `Loading .env environment variables...` — this is output injected by `pipenv` when `PIPENV_DOTENV_LOCATION` or automatic `.env` loading is active during `pipenv lock`. Running `pip install -r requirements.txt` directly (outside pipenv) will fail with a parse error on this line, which could surprise contributors or CI pipelines that bypass pipenv.
**Fix:** Add a comment noting this file is managed by pipenv, or strip the first line during CI:
```
# Generated by pipenv. Use 'pipenv install' to install, not 'pip install -r'.
```
Alternatively, configure pipenv to suppress the `.env` echo during lock generation.

---

### IN-02: `Pipfile` uses wildcard versions for all packages

**File:** `Pipfile:14-15`
**Issue:** `fastmcp = "*"` and `mcp = "*"` will resolve to whatever the latest version is at the time of `pipenv install`. The `requirements.txt` lockfile pins `fastmcp==3.2.4`, but a fresh `pipenv install` on a new machine will pull whatever is current — potentially `fastmcp==4.x` with breaking API changes. The server is explicitly designed for `fastmcp==3.2.4` patterns (e.g. `ScalekitProvider` import path, `mcp.http_app()`, `mcp.run_http_async()`).
**Fix:** Pin to at least a major version in `Pipfile`:
```toml
fastmcp = "~=3.2"
mcp = "~=1.27"
```

---

### IN-03: Module-level `headers` dict in test file is a hidden coupling point

**File:** `tests/test_server.py:731-733`
**Issue:** The `headers` dict is defined at module scope (not inside a fixture or class), meaning any test that modifies it (or any future test mistakenly shadowing it) could cause hard-to-diagnose inter-test pollution. This is a minor test-structure concern, not a correctness bug today.
**Fix:** Move `headers` into the test functions that use it, or define it as a pytest fixture:
```python
@pytest.fixture
def mcp_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
```

---

_Reviewed: 2026-04-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
