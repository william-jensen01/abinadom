"""The rendered compose config (docker compose config; no daemon, no images).

Renders base, base+proxy, base+weaviate-ports and all three, in a temp project dir holding copies of the compose
files and a .env with dev-style values for every path and Weaviate variable (none may reach a container).
"""
import re
import shutil
from pathlib import Path

import pytest
import yaml

from tests.deploy_helpers import CODE_DIR, EMBED_CANARY, LEAK_ENV, compose_project, render

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")

BASE = "docker-compose.yml"
PROXY = "docker-compose.proxy.yml"
WPORTS = "docker-compose.weaviate-ports.yml"
COMBOS = {"base": [BASE], "proxy": [BASE, PROXY], "wports": [BASE, WPORTS], "both": [BASE, PROXY, WPORTS]}
IMAGE = "h5wyxaa9vrvo/lds-mcp"
SERVER_PORT = 7363            # fact: FASTMCP_PORT in .env.example and the Dockerfile's EXPOSE
WEAVIATE_PORTS = {8080, 50051}  # fact: Weaviate's HTTP and gRPC ports in docker-compose.yml today


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    for name in (BASE, PROXY, WPORTS):
        assert (CODE_DIR / name).exists(), f"{name} is missing"
    return compose_project(tmp_path_factory.mktemp("compose"))


@pytest.fixture(scope="module")
def configs(proj):
    return {k: render(proj, files) for k, files in COMBOS.items()}


def _svc(cfg, name):
    s = (cfg.get("services") or {}).get(name)
    assert s, f"service {name!r} missing; have {sorted(cfg.get('services') or {})}"
    return s


def _binds(svc):
    return [(v.get("source"), v.get("target"), bool(v.get("read_only"))) for v in svc.get("volumes") or []]


def _nets(cfg, svc):
    """{rendered network name: external?} for the networks a service joins."""
    top = cfg.get("networks") or {}
    return {(top.get(k) or {}).get("name", k): bool((top.get(k) or {}).get("external")) for k in (svc.get("networks") or {})}


@pytest.mark.parametrize("combo", COMBOS)
def test_tools_service_is_behind_a_profile(combo, proj, configs):
    tools = _svc(configs[combo], "tools")
    assert tools.get("profiles"), "tools must sit under a compose profile"
    default = render(proj, COMBOS[combo], profile=None, services_only=True)
    assert "tools" not in default and {"mcp-server", "weaviate"} <= default, f"`up` would start: {sorted(default)}"


@pytest.mark.parametrize("combo", COMBOS)
def test_mounts(combo, proj, configs):
    cfg = configs[combo]
    for name, ro in (("mcp-server", True), ("tools", False)):
        binds = _binds(_svc(cfg, name))
        assert not any(t == "/app/db" or str(t).startswith("/app/db/") for _, t, _ in binds), f"{name}: {binds}"
        data = [b for b in binds if b[1] == "/data"]
        assert len(data) == 1 and Path(data[0][0]) == proj / "db" and data[0][2] is ro, \
            f"{name} must mount ./db at /data {'read-only' if ro else 'read-write'}: {binds}"


@pytest.mark.parametrize("combo", COMBOS)
def test_environment(combo, configs):
    cfg = configs[combo]
    want = {"SCI_DB_DIR": "/data",
            "WEAVIATE_HOST": "weaviate", "WEAVIATE_PORT": "8080", "WEAVIATE_GRPC_PORT": "50051"}
    envs = {n: {k: str(v) for k, v in (_svc(cfg, n).get("environment") or {}).items()} for n in ("mcp-server", "tools")}
    for name, env in envs.items():
        for k, v in want.items():
            assert env.get(k) == v, f"{name}: {k}={env.get(k)!r}, want {v!r}"
        assert env.get("EMBEDDING_URL") == EMBED_CANARY, f"{name} must get EMBEDDING_URL from .env: {env.get('EMBEDDING_URL')!r}"
        assert "SCRIPTURE_DB_PATH" not in env, f"{name}: scripture.db is $SCI_DB_DIR/scripture.db, no variable: {env}"
        leaked = {k: v for k, v in env.items() if v in LEAK_ENV.values()}
        assert not leaked, f"{name}: .env values reached the container: {leaked}"
    assert envs["tools"].get("SCI_REPORT_DIR") == "/data/reports", f"tools SCI_REPORT_DIR={envs['tools'].get('SCI_REPORT_DIR')!r}"


@pytest.mark.parametrize("combo", COMBOS)
def test_tools_entrypoint_and_user(combo, proj, configs):
    tools = _svc(configs[combo], "tools")
    assert tools.get("entrypoint") == ["python"], f"entrypoint {tools.get('entrypoint')!r}"
    assert str(tools.get("user")) == "1000:1000", f"default user {tools.get('user')!r}"
    other = render(proj, COMBOS[combo], extra_env={"HOST_UID": "1234", "HOST_GID": "5678"})
    assert str(_svc(other, "tools").get("user")) == "1234:5678", f"HOST_UID/HOST_GID ignored: {_svc(other, 'tools').get('user')!r}"


@pytest.mark.parametrize("combo", COMBOS)
def test_images_and_build_targets(combo, proj, configs):
    cfg = configs[combo]
    srv, tools = _svc(cfg, "mcp-server"), _svc(cfg, "tools")
    assert str(srv.get("image", "")).split(":")[0] == IMAGE, f"mcp-server image {srv.get('image')!r}"
    for svc, target in ((srv, "server"), (tools, "tools")):
        b = svc.get("build") or {}
        assert b.get("target") == target and Path(b.get("context", "")) == proj, f"build {b!r}, want target {target!r} context ."
    if tools.get("image"):
        assert tools["image"] != srv["image"], "both targets would be tagged as the same image"


@pytest.mark.parametrize("combo", COMBOS)
def test_tools_and_server_reach_weaviate(combo, configs):
    cfg = configs[combo]
    w = set(_nets(cfg, _svc(cfg, "weaviate")))
    for name in ("mcp-server", "tools"):
        assert set(_nets(cfg, _svc(cfg, name))) & w, f"{name} shares no network with weaviate"


@pytest.mark.parametrize("combo", COMBOS)
def test_published_ports(combo, configs):
    cfg = configs[combo]
    sp = _svc(cfg, "mcp-server").get("ports") or []
    assert all(p.get("host_ip") == "127.0.0.1" for p in sp), f"mcp-server ports not loopback-only: {sp}"
    assert any(p.get("target") == SERVER_PORT and str(p.get("published")) == str(SERVER_PORT) for p in sp), \
        f"mcp-server must publish 127.0.0.1:{SERVER_PORT}: {sp}"
    wp = _svc(cfg, "weaviate").get("ports") or []
    if combo in ("base", "proxy"):
        assert not wp, f"weaviate publishes ports without the override: {wp}"
    else:
        assert wp and all(p.get("host_ip") == "127.0.0.1" for p in wp), f"weaviate ports not loopback-only: {wp}"
        assert WEAVIATE_PORTS <= {p.get("target") for p in wp}, f"weaviate override must publish {WEAVIATE_PORTS}: {wp}"
    for name in ("tools",):
        assert not _svc(cfg, name).get("ports"), f"{name} publishes ports"


@pytest.mark.parametrize("combo", COMBOS)
def test_proxy_network_only_with_override(combo, configs):
    cfg = configs[combo]
    srv = _nets(cfg, _svc(cfg, "mcp-server"))
    top = {(v or {}).get("name", k): bool((v or {}).get("external")) for k, v in (cfg.get("networks") or {}).items()}
    if combo in ("base", "wports"):
        assert not any(top.values()), f"external network without the proxy override: {top}"
        assert "proxy" not in top, f"proxy network without the override: {top}"
    else:
        assert srv.get("proxy") is True, f"mcp-server must join the external proxy network: {srv}"


def test_compose_file_in_env_enables_proxy(tmp_path):
    proj = compose_project(tmp_path, [f"COMPOSE_FILE={BASE}:{PROXY}"])
    cfg = render(proj, None)
    assert _nets(cfg, _svc(cfg, "mcp-server")).get("proxy") is True, "COMPOSE_FILE in .env did not apply the proxy override"


def test_weaviate_settings_written_once():
    text = (CODE_DIR / BASE).read_text()
    code = "\n".join(l.split("#", 1)[0] for l in text.splitlines())
    raw = yaml.safe_load(text)
    xblocks = {k: v for k, v in raw.items() if str(k).startswith("x-")}
    for var in ("WEAVIATE_HOST", "WEAVIATE_PORT", "WEAVIATE_GRPC_PORT"):
        n = len(re.findall(rf"\b{var}\b", code))
        assert n == 1, f"{var} appears {n} times in {BASE} outside comments; set it once in a shared x- block"
        assert var in yaml.safe_dump(xblocks), f"{var} is not in a top-level x- block: {sorted(xblocks)}"


def test_env_example():
    ex = (CODE_DIR / ".env.example").read_text()
    for s in ("COMPOSE_FILE", PROXY, "WEAVIATE_HOST", "WEAVIATE_PORT", "WEAVIATE_GRPC_PORT"):
        assert s in ex, f".env.example must mention {s}"
