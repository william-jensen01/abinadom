---
phase: quick
plan: 260404-qft
type: execute
wave: 1
depends_on: []
files_modified:
  - server.py
  - Dockerfile
  - .env.example
  - docker-compose.yml
  - infra/Caddyfile
  - infra/SETUP.md
  - tests/test_server.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "MCP server default port is 7363 everywhere (code, config, docs)"
    - "Existing MCP_PORT env var override mechanism still works"
    - "All tests pass with updated default"
  artifacts:
    - path: "server.py"
      provides: "MCP server entry point"
      contains: '"7363"'
    - path: "Dockerfile"
      provides: "Container image definition"
      contains: "EXPOSE 7363"
    - path: ".env.example"
      provides: "Operator env config template"
      contains: "MCP_PORT=7363"
    - path: "docker-compose.yml"
      provides: "Compose service definition"
      contains: "localhost:7363"
    - path: "infra/Caddyfile"
      provides: "Caddy reverse proxy config"
      contains: "mcp-server:7363"
  key_links:
    - from: "server.py"
      to: "Dockerfile"
      via: "MCP_PORT env var default"
      pattern: "MCP_PORT.*7363"
    - from: "infra/Caddyfile"
      to: "docker-compose.yml"
      via: "Caddy proxies to mcp-server container on port 7363"
      pattern: "mcp-server:7363"
---

<objective>
Change the MCP server default port from 8000 to 7363 across all source code, configuration files, infrastructure config, documentation, and tests.

Purpose: Avoid conflict with common port 8000 and use a project-specific port.
Output: All references to port 8000 updated to 7363; tests pass.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@server.py
@Dockerfile
@.env.example
@docker-compose.yml
@infra/Caddyfile
@infra/SETUP.md
@tests/test_server.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update default port from 8000 to 7363 in all source and config files</name>
  <files>server.py, Dockerfile, .env.example, docker-compose.yml, infra/Caddyfile, infra/SETUP.md</files>
  <action>
Replace every occurrence of port 8000 with 7363 in the following files:

1. **server.py** (line 259): Change `"8000"` default to `"7363"` in `MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))`. This is the only 8000 reference in server.py — the FastMCP constructor and uvicorn.run both read from MCP_PORT variable, so they inherit automatically.

2. **Dockerfile** (lines 19, 21): Change `ENV MCP_PORT=8000` to `ENV MCP_PORT=7363`. Change `EXPOSE 8000` to `EXPOSE 7363`.

3. **.env.example** (line 15): Change `MCP_PORT=8000` to `MCP_PORT=7363`.

4. **docker-compose.yml** (line 10): Change healthcheck `http://localhost:8000/health` to `http://localhost:7363/health`.

5. **infra/Caddyfile** (line 6): Change `reverse_proxy mcp-server:8000` to `reverse_proxy mcp-server:7363`.

6. **infra/SETUP.md** (line 68): Change `mcp-server:8000` to `mcp-server:7363` in the routing chain description.

Do NOT change any .planning/ phase docs (RESEARCH.md, CONTEXT.md, old PLANs) — those are historical records.
  </action>
  <verify>
    <automated>grep -rn "8000" server.py Dockerfile .env.example docker-compose.yml infra/Caddyfile infra/SETUP.md && echo "FAIL: 8000 still present" || echo "PASS: no 8000 references"</automated>
  </verify>
  <done>All 6 files use port 7363 instead of 8000. No stale 8000 references in source/config/infra.</done>
</task>

<task type="auto">
  <name>Task 2: Update test expectations for new default port</name>
  <files>tests/test_server.py</files>
  <action>
Update the two test functions that assert on port values:

1. **test_mcp_host_port_defaults** (~line 651): Change `assert mcp.settings.port == 8000` to `assert mcp.settings.port == 7363`.

2. **test_mcp_host_port_env_override** (~line 661): This test sets MCP_PORT=9000 and asserts port == 9000. This test should remain unchanged — it tests the override mechanism, not the default.

Run the full test suite to confirm nothing breaks.
  </action>
  <verify>
    <automated>cd "C:/Users/wbjen/OneDrive/Documents/LDS MCP" && pipenv run py -m pytest tests/test_server.py::test_mcp_host_port_defaults tests/test_server.py::test_mcp_host_port_env_override -x -v</automated>
  </verify>
  <done>test_mcp_host_port_defaults asserts port 7363. test_mcp_host_port_env_override still asserts port 9000. Both tests pass.</done>
</task>

</tasks>

<verification>
- `grep -rn "8000" server.py Dockerfile .env.example docker-compose.yml infra/Caddyfile infra/SETUP.md` returns no results
- `grep -rn "7363" server.py Dockerfile .env.example docker-compose.yml infra/Caddyfile infra/SETUP.md` returns expected hits in all 6 files
- `pipenv run py -m pytest tests/test_server.py -x` passes
</verification>

<success_criteria>
- Default MCP server port is 7363 in server.py, Dockerfile, .env.example
- Docker healthcheck uses port 7363
- Caddy reverse_proxy targets mcp-server:7363
- infra/SETUP.md routing chain shows port 7363
- All server tests pass
</success_criteria>

<output>
After completion, create `.planning/quick/260404-qft-update-mcp-server-port-to-7363/260404-qft-SUMMARY.md`
</output>
