"""docker-compose.yml mounts one read-only data directory (the image is code only) and reaches Weaviate; the
deploy and update guides describe the current stack.

The image holds code only (.dockerignore excludes *.db). core.<N>.db, content.<N>.db and scripture.db are all read
from SCI_DB_DIR; compose points it at one directory mounted once, read-only. Nothing may be
mounted at or under /app/db: it holds the `db` Python package baked into the image.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APP_DB = "/app/db"


def _compose():
    comp = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    svc = (comp.get("services") or {}).get("mcp-server")
    assert svc, "docker-compose.yml must keep the mcp-server service"
    return comp, svc


def _mounts(svc):
    """[(source, target, read_only)] for mcp-server's volumes, short or long syntax."""
    out = []
    for v in svc.get("volumes", []) or []:
        if isinstance(v, str):
            parts = re.split(r":(?![^{]*\})", v)   # not the ':' inside ${VAR:-default}
            src, tgt = parts[0], parts[1] if len(parts) > 1 else parts[0]
            mode = parts[2] if len(parts) > 2 else "rw"
            out.append((src, tgt, "ro" in mode.split(",")))
        else:
            out.append((str(v.get("source")), str(v.get("target")), bool(v.get("read_only"))))
    return out


def _env(svc):
    env = svc.get("environment", {}) or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) if "=" in e else (e, None) for e in env)
    return env


def _covering(mounts, path):
    """The mounts whose target is `path` or a directory above it."""
    path = path.rstrip("/")
    return [m for m in mounts if path == m[1].rstrip("/") or path.startswith(m[1].rstrip("/") + "/")]


def test_scripture_db_mounted_read_only_at_its_path():
    _, svc = _compose()
    env = _env(svc)
    assert "SCRIPTURE_DB_PATH" not in env, f"scripture.db is $SCI_DB_DIR/scripture.db, set no SCRIPTURE_DB_PATH: {json.dumps(env)}"
    path = str(env.get("SCI_DB_DIR") or "").rstrip("/") + "/scripture.db"
    mounts = _mounts(svc)
    hit = _covering(mounts, path)
    assert hit, f"{path} must be inside a mount: {mounts}"
    assert all(ro for _, _, ro in hit), f"the mount holding scripture.db must be read-only: {hit}"


def test_core_and_content_read_from_one_mounted_data_dir():
    _, svc = _compose()
    env = _env(svc)
    mounts = _mounts(svc)
    assert not any(tgt.rstrip("/") == APP_DB or tgt.startswith(APP_DB + "/") for _, tgt, _ in mounts), \
        f"mount nothing at or under {APP_DB}: it holds the db package in the image: {mounts}"
    data_dir = str(env.get("SCI_DB_DIR") or "").rstrip("/")
    assert data_dir and data_dir != APP_DB, f"mcp-server must set SCI_DB_DIR (not {APP_DB}): {json.dumps(env)}"
    hit = [m for m in mounts if m[1].rstrip("/") == data_dir]
    assert len(hit) == 1 and hit[0][2], f"mount the data directory once, read-only, at SCI_DB_DIR={data_dir}: {mounts}"
    assert not any(tgt.startswith(data_dir + "/") for _, tgt, _ in mounts), \
        f"one directory mount, not separate files under {data_dir}: {mounts}"


def test_db_package_reads_sci_db_dir(tmp_path):
    """db/__init__.py resolves core/content from SCI_DB_DIR; unset, it keeps its own folder."""
    code = "import db; print(db.CORE_DB_PATH); print(db.CONTENT_DB_PATH)"
    base = {k: v for k, v in os.environ.items() if k not in ("SCI_DB_DIR", "SCI_DB_VERSION")}

    def run(env):
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                              text=True, timeout=60)

    r = run({**base, "SCI_DB_DIR": str(tmp_path), "SCI_DB_VERSION": "55"})
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.split() == [str(tmp_path / "core.55.db"), str(tmp_path / "content.55.db")], r.stdout
    r = run({**base, "SCI_DB_VERSION": "55"})
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.split() == [str(ROOT / "db" / "core.55.db"), str(ROOT / "db" / "content.55.db")], r.stdout


def test_weaviate_ports_set_for_the_container():
    _, svc = _compose()
    env = _env(svc)
    for name in ("WEAVIATE_HOST", "WEAVIATE_PORT", "WEAVIATE_GRPC_PORT"):
        assert env.get(name), f"compose must set {name} under environment: {json.dumps(env)}"


def test_weaviate_service_reachable_from_mcp_server():
    comp, svc = _compose()
    services = comp.get("services") or {}
    host = str(_env(svc).get("WEAVIATE_HOST") or "")
    assert host in services and host != "mcp-server", \
        f"mcp-server must set WEAVIATE_HOST under environment to the Weaviate service in this file, got {host!r}"
    deps = svc.get("depends_on") or {}
    assert host in deps, f"mcp-server must depend on {host}: {deps}"
    port = str(_env(svc).get("WEAVIATE_PORT") or "8080")
    assert port == "8080", f"inside the compose network Weaviate listens on 8080, got WEAVIATE_PORT={port}"


def test_deploy_guide_describes_the_current_stack():
    # CHROMADB_HOST, OLLAMA_URL and SCRIPTURE_DB_PATH are env vars the server no longer reads: a guide that names them is stale.
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text()
    for s in ("WEAVIATE_HOST", "EMBEDDING_URL", "SCI_DB_DIR", "SCI_DB_VERSION", "build_id",
              "run_scripture_pipeline", "fetch_scriptures", "build_scriptures"):
        assert s in deploy, f"docs/DEPLOY.md must cover {s}"
    for stale in ("CHROMADB_HOST", "OLLAMA_URL", "SCRIPTURE_DB_PATH"):
        assert stale not in deploy, f"docs/DEPLOY.md still documents {stale}, which the server no longer reads"


def test_updates_guide_has_a_scripture_section():
    upd = (ROOT / "docs" / "update" / "HOW_UPDATES_WORK.md").read_text()
    for s in ("fetch_scriptures", "build_scriptures", "run_scripture_pipeline"):
        assert s in upd, f"docs/update/HOW_UPDATES_WORK.md needs a scripture section naming {s}"


def _file(name):
    return yaml.safe_load((ROOT / name).read_text())


def test_tools_service_runs_scripts_with_a_writable_data_mount():
    comp, _ = _compose()
    tools = (comp.get("services") or {}).get("tools")
    assert tools, "docker-compose.yml needs a tools service for the build and load scripts"
    assert tools.get("profiles"), "tools must sit under a profile so `up` does not start it"
    assert tools.get("entrypoint") == ["python"]
    assert "HOST_UID" in str(tools.get("user")) and "HOST_GID" in str(tools.get("user"))
    mounts = _mounts(tools)
    assert [m for m in mounts if m[1] == "/data" and not m[2]], f"tools mounts ./db read-write at /data: {mounts}"
    env = _env(tools)
    assert env.get("SCI_REPORT_DIR") == "/data/reports"
    assert env.get("SCI_DB_DIR") == "/data"


def test_weaviate_address_is_shared_between_services():
    comp, svc = _compose()
    tools = comp["services"]["tools"]
    for name in ("WEAVIATE_HOST", "WEAVIATE_PORT", "WEAVIATE_GRPC_PORT"):
        assert _env(svc)[name] == _env(tools)[name]


def test_base_file_publishes_no_weaviate_ports_and_no_external_network():
    comp, svc = _compose()
    assert not comp["services"]["weaviate"].get("ports"), "weaviate is published only by the ports override"
    assert not any((v or {}).get("external") for v in (comp.get("networks") or {}).values())
    assert svc.get("ports") == ["127.0.0.1:7363:7363"]


def test_override_files():
    proxy = _file("docker-compose.proxy.yml")
    assert "proxy" in proxy["networks"] and proxy["networks"]["proxy"]["external"] is True
    assert "default" in proxy["services"]["mcp-server"]["networks"], "mcp-server must stay on Weaviate's network"
    ports = _file("docker-compose.weaviate-ports.yml")["services"]["weaviate"]["ports"]
    assert sorted(ports) == ["127.0.0.1:50051:50051", "127.0.0.1:8080:8080"]


def test_env_example_documents_proxy_override_and_host_script_settings():
    ex = (ROOT / ".env.example").read_text()
    assert "COMPOSE_FILE=docker-compose.yml:docker-compose.proxy.yml" in ex
    assert "WEAVIATE_HOST=" in ex and "not in Docker" in ex


# --- deploy guide: Docker-only path, in start order ---

TOOLS_RUN = "docker compose run --rm tools scripts/"
LOAD_SCRIPTS = ["build.py", "fetch_scriptures.py", "build_scriptures.py", "run_pipeline.py",
                "verify_weaviate_pipeline.py", "run_scripture_pipeline.py", "verify_weaviate_scripture.py"]


def _deploy_text():
    return (ROOT / "docs" / "DEPLOY.md").read_text()


def test_deploy_guide_documents_only_the_docker_path():
    d = _deploy_text()
    assert "pipenv" not in d.lower(), "docs/DEPLOY.md still documents pipenv"
    assert "one address" not in d.lower(), "docs/DEPLOY.md keeps the 'one address from host and container' EMBEDDING_URL rule"
    m = re.search(r"^## Prerequisites\n(.*?)(?=^## )", d, re.M | re.S)
    assert m, "docs/DEPLOY.md needs a '## Prerequisites' section"
    assert "python" not in m.group(1).lower(), f"Prerequisites still list Python:\n{m.group(1)[:400]}"


def test_deploy_guide_runs_scripts_in_the_tools_container():
    d = _deploy_text()
    missing = [s for s in LOAD_SCRIPTS if TOOLS_RUN + s not in d]
    assert not missing, f"docs/DEPLOY.md must run these as `{TOOLS_RUN}<script>`: {missing}"


def test_deploy_guide_start_order():
    d = _deploy_text()
    w = d.find("docker compose up -d weaviate")
    t = d.find(TOOLS_RUN + "run_pipeline.py")
    up = re.search(r"^docker compose up -d[ \t]*$", d[t:] if t >= 0 else "", re.M)
    assert 0 <= w < t and up, "docs/DEPLOY.md order must be: `docker compose up -d weaviate`, then the tools loads, then `docker compose up -d`"


def test_deploy_guide_covers_overrides_and_build():
    d = _deploy_text()
    for s in ("docker-compose.proxy.yml", "COMPOSE_FILE", "docker-compose.weaviate-ports.yml", "HOST_UID",
              "docker compose build", "scripts/fetch.py", "/data/reports"):
        assert s in d, f"docs/DEPLOY.md must cover {s}"


def test_claude_md_keeps_pipenv_commands():
    c = (ROOT / "CLAUDE.md").read_text()
    assert "pipenv run python -m pytest" in c and "pipenv requirements > requirements.txt" in c, \
        "CLAUDE.md must keep the pipenv developer commands"
