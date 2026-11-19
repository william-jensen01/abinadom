"""The server's fastmcp version and the files that pin it.

fastmcp 4.2 brought `fastmcp.skills`, so the server needs 4.2 or later within 4.x. Pipfile, Pipfile.lock and
requirements.txt must agree: the Docker images install requirements.txt only, and CLAUDE.md regenerates it with
`pipenv requirements > requirements.txt` after any dependency change.
"""
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
ENV_DROP = {"SCALEKIT_ENVIRONMENT_URL", "SCALEKIT_RESOURCE_ID", "MCP_BASE_URL", "PYTHONPATH", "PIPENV_ACTIVE",
            "VIRTUAL_ENV"}


def _env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ENV_DROP}
    env.update(extra)
    return env


def _run_python(code: str, **env):
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=_env(**env), capture_output=True, text=True,
                          timeout=120)


def test_fastmcp_pinned_to_4x_from_4_2():
    spec = tomllib.loads((ROOT / "Pipfile").read_text())["packages"]["fastmcp"]
    spec = spec.get("version") if isinstance(spec, dict) else spec
    locked = Version(json.loads((ROOT / "Pipfile.lock").read_text())["default"]["fastmcp"]["version"].lstrip("="))
    assert locked.major == 4 and locked.minor >= 2, f"Pipfile.lock has fastmcp {locked}; the server needs 4.2+ in 4.x"
    allowed = SpecifierSet("" if spec == "*" else spec)
    assert locked in allowed, f"Pipfile's fastmcp {spec!r} does not admit the locked {locked}"
    for outside in ("4.1.0", "5.0.0"):
        assert Version(outside) not in allowed, f"Pipfile's fastmcp {spec!r} admits {outside}"
    req = [l for l in (ROOT / "requirements.txt").read_text().splitlines() if l.startswith("fastmcp==")]
    assert req and req[0].split(";")[0] == f"fastmcp=={locked}", f"requirements.txt has {req}, lock has {locked}"


@pytest.mark.skipif(shutil.which("pipenv") is None, reason="needs pipenv")
def test_requirements_txt_is_regenerated_from_the_lock():
    r = subprocess.run(["pipenv", "requirements"], cwd=ROOT, capture_output=True, text=True, timeout=120,
                       env=_env(PIPENV_VERBOSITY="-1", PIPENV_PIPFILE=str(ROOT / "Pipfile")))
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert r.stdout.splitlines() == (ROOT / "requirements.txt").read_text().splitlines(), \
        "requirements.txt is stale: run `pipenv requirements > requirements.txt`"


def test_requirements_txt_leaves_out_dev_packages():
    """chromadb is a dev package; the images, which install requirements.txt, must not need it."""
    names = {l.split("==")[0].split("[")[0].lower() for l in (ROOT / "requirements.txt").read_text().splitlines()
             if "==" in l}
    assert "chromadb" not in names


def test_scalekit_remote_mode_serves_mcp_and_protected_resource_metadata():
    probe = ("import server; "
             "from fastmcp.server.auth.providers.scalekit import ScalekitProvider; "
             "assert isinstance(server.mcp.auth, ScalekitProvider), type(server.mcp.auth); "
             "paths = [getattr(r, 'path', '') for r in server.mcp.http_app().routes]; "
             "assert '/mcp' in paths, paths; "
             "assert any(p.startswith('/.well-known/oauth-protected-resource') for p in paths), paths; "
             "print('ok')")
    r = _run_python(probe, SCALEKIT_ENVIRONMENT_URL="https://example.scalekit.dev", SCALEKIT_RESOURCE_ID="res_1",
                    MCP_BASE_URL="https://mcp.example.org")
    assert r.returncode == 0 and "ok" in r.stdout, (r.stdout + r.stderr)[-1200:]


def test_server_triggers_no_fastmcp_deprecation_warnings():
    probe = r'''
import asyncio, sys, warnings
from unittest.mock import MagicMock, patch
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    import server
    from fastmcp import Client
    async def go():
        async with Client(server.mcp) as c:
            await c.list_tools(); await c.list_resources()
    with patch("server._startup", return_value=server.AppContext(client=MagicMock())):
        asyncio.run(go())
    server.mcp.http_app()
bad = [f"{w.category.__name__}: {w.message} ({w.filename}:{w.lineno})" for w in caught
       if issubclass(w.category, DeprecationWarning)
       and ("fastmcp" in str(w.message).lower() or "/fastmcp/" in w.filename or "/mcp/" in w.filename)]
print("\n".join(bad)); sys.exit(1 if bad else 0)
'''
    r = _run_python(probe)
    assert r.returncode == 0, "fastmcp deprecation warnings:\n" + (r.stdout + r.stderr)[-1500:]
