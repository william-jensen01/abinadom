"""docker-compose.yml mounts every SQLite file read-only (the image is code only) and reaches Weaviate; the deploy
and update guides describe the current stack.

The image holds code only (.dockerignore excludes *.db), so every SQLite file the server reads at runtime is
mounted: scripture.db at SCRIPTURE_DB_PATH, and core.<N>.db / content.<N>.db at /app/db/ (db/__init__.py resolves
them there from SCI_DB_VERSION; the path is not configurable). Mounting the whole db/ directory over /app/db is
wrong: it hides the `db` Python package baked into the image.
"""
import json
import re
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


def test_scripture_db_mounted_read_only_at_its_path():
    _, svc = _compose()
    env = _env(svc)
    assert "SCRIPTURE_DB_PATH" in env and env["SCRIPTURE_DB_PATH"], \
        f"mcp-server must set SCRIPTURE_DB_PATH under environment: {json.dumps(env)}"
    mounts = _mounts(svc)
    hit = [m for m in mounts if m[1] == env["SCRIPTURE_DB_PATH"]]
    assert hit, f"SCRIPTURE_DB_PATH={env['SCRIPTURE_DB_PATH']} must be the target of a mount: {mounts}"
    assert all(ro for _, _, ro in hit), f"the scripture.db mount must be read-only: {hit}"
    assert any("scripture" in src and src.endswith(".db") for src, _, _ in hit), f"mount a scripture .db file: {hit}"


def test_core_and_content_db_mounted_read_only():
    _, svc = _compose()
    mounts = _mounts(svc)
    assert not any(tgt.rstrip("/") == APP_DB for _, tgt, _ in mounts), \
        f"do not mount a directory over {APP_DB}: it hides the db package in the image: {mounts}"
    version = str(_env(svc).get("SCI_DB_VERSION") or "").strip()
    for kind in ("core", "content"):
        # a literal release number, or compose interpolation of SCI_DB_VERSION (e.g. ${SCI_DB_VERSION:-55})
        pat = re.compile(rf"^{APP_DB}/{kind}\.(\d+|\$\{{SCI_DB_VERSION[^}}]*\}})\.db$")
        hit = [(src, tgt, ro) for src, tgt, ro in mounts if pat.match(tgt)]
        assert hit, f"mcp-server needs {APP_DB}/{kind}.<N>.db mounted (read at runtime): {mounts}"
        assert all(ro for _, _, ro in hit), f"the {kind} db mount must be read-only: {hit}"
        if version.isdigit():
            assert any(pat.match(tgt).group(1) in (version,) or pat.match(tgt).group(1).startswith("$")
                       for _, tgt, _ in hit), \
                f"SCI_DB_VERSION={version} but the {kind} mount is {hit}"


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
    # CHROMADB_HOST and OLLAMA_URL are env vars the server no longer reads: a guide that names them is stale.
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text()
    for s in ("WEAVIATE_HOST", "EMBEDDING_URL", "SCRIPTURE_DB_PATH", "SCI_DB_VERSION", "build_id",
              "run_scripture_pipeline", "fetch_scriptures", "build_scriptures"):
        assert s in deploy, f"docs/DEPLOY.md must cover {s}"
    for stale in ("CHROMADB_HOST", "OLLAMA_URL"):
        assert stale not in deploy, f"docs/DEPLOY.md still documents {stale}, which the server no longer reads"


def test_updates_guide_has_a_scripture_section():
    upd = (ROOT / "docs" / "update" / "HOW_UPDATES_WORK.md").read_text()
    for s in ("fetch_scriptures", "build_scriptures", "run_scripture_pipeline"):
        assert s in upd, f"docs/update/HOW_UPDATES_WORK.md needs a scripture section naming {s}"
