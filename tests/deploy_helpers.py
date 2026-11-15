"""Shared helpers for the deployment tests (path defaults, compose rendering, Dockerfile and .dockerignore reading).

CODE_DIR is the repo root. Nothing here opens a database file; the only *.db files touched are empty placeholders
the tests create in tmp dirs.
"""
import fnmatch
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable
# SCRIPTURE_DB_PATH is no longer read (scripture.db is $SCI_DB_DIR/scripture.db); dropping it keeps a stale value out.
PATH_VARS = ("SCI_DB_DIR", "SCRIPTURE_DB_PATH", "SCI_REPORT_DIR")
PROBE = Path(__file__).resolve().parent / "script_arg_probe.py"


def clean_env(**extra):
    """os.environ without the path vars, the compose vars or ScaleKit, plus `extra`."""
    drop = set(PATH_VARS) | {"HOST_UID", "HOST_GID", "COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME",
                             "SCALEKIT_ENVIRONMENT_URL", "SCALEKIT_RESOURCE_ID", "MCP_BASE_URL",
                             "PIPENV_ACTIVE", "PYTHONPATH"}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update({k: str(v) for k, v in extra.items()})
    return env


# --------------------------------------------------------------------------- copy of the code tree
_SKIP_DIRS = {".git", ".goal", "data", "output", "benchmark", ".planning", "tests", "docs", "__pycache__",
              ".pytest_cache", "sci", "tasks", "examples", "hymns-research", ".claude", ".vscode", "node_modules"}
_SKIP_FILE = re.compile(r"(\.db|\.db-shm|\.db-wal|\.sqlite|\.building|\.txt)$")


def copy_code_tree(dest: Path) -> Path:
    """Copy the code (no data, no databases, no .env) so 'unset' defaults resolve under a root the test controls."""
    for dirpath, dirnames, filenames in os.walk(CODE_DIR):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel = Path(dirpath).relative_to(CODE_DIR)
        for f in filenames:
            if _SKIP_FILE.search(f) or f in (".env",) or (rel == Path(".") and f.endswith(".json")):
                continue
            (dest / rel).mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(dirpath) / f, dest / rel / f)
    return dest


def run(cmd, cwd, env, timeout=120):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def probe_args(root: Path, script: str, args=(), env=None, cwd=None):
    """Run <root>/scripts/<script> until argparse has parsed its arguments; return the namespace as a dict."""
    r = run([PY, str(PROBE), str(root / "scripts" / script), *args], cwd=cwd or tempfile.gettempdir(),
            env=env if env is not None else clean_env())
    for line in r.stdout.splitlines():
        if line.startswith("PROBE_ARGS "):
            return json.loads(line[len("PROBE_ARGS "):])
    raise AssertionError(f"{script} {' '.join(args)}: argparse never ran (exit {r.returncode})\n"
                         f"{(r.stdout + r.stderr)[-1500:]}")


def same_path(a, b):
    return os.path.normpath(str(a)) == os.path.normpath(str(b))


# --------------------------------------------------------------------------- docker compose
def render(proj: Path, files=None, profile="*", extra_env=None, fmt_json=True, services_only=False):
    cmd = ["docker", "compose", "--project-directory", str(proj)]
    for f in files or []:
        cmd += ["-f", str(proj / f)]
    if profile:
        cmd += ["--profile", profile]
    cmd += ["config"] + (["--services"] if services_only else (["--format", "json"] if fmt_json else []))
    env = clean_env(**(extra_env or {}))
    r = run(cmd, cwd=proj, env=env)
    assert r.returncode == 0, f"{' '.join(cmd[4:])} failed:\n{r.stderr[-1500:]}"
    if services_only:
        return set(r.stdout.split())
    return json.loads(r.stdout)


# Values a developer .env might hold; none may reach a container's path or Weaviate settings.
LEAK_ENV = {
    "SCI_DB_DIR": "/leak/db", "SCI_REPORT_DIR": "/leak/reports",
    "WEAVIATE_HOST": "leak-weaviate-host", "WEAVIATE_PORT": "18080", "WEAVIATE_GRPC_PORT": "15051",
}
EMBED_CANARY = "http://embed-canary.invalid:9999"


def compose_project(tmp: Path, env_lines=()) -> Path:
    """Copy every docker-compose*.yml (and the Dockerfile) into tmp, with a .env holding dev-style leak values."""
    files = sorted(CODE_DIR.glob("docker-compose*.yml")) + sorted(CODE_DIR.glob("docker-compose*.yaml"))
    for f in files + [CODE_DIR / "Dockerfile"]:
        if f.exists():
            shutil.copy2(f, tmp / f.name)
    lines = [f"{k}={v}" for k, v in LEAK_ENV.items()] + [f"EMBEDDING_URL={EMBED_CANARY}"] + list(env_lines)
    (tmp / ".env").write_text("\n".join(lines) + "\n")
    (tmp / "db").mkdir(exist_ok=True)
    return tmp


# --------------------------------------------------------------------------- .dockerignore and the Dockerfile
def ignore_rules(root: Path = None):
    """[(negated, regex, raw)] in file order; same reading of Docker's patterns as test_dockerignore.py."""
    rules = []
    p = (root or CODE_DIR) / ".dockerignore"
    for line in (p.read_text().splitlines() if p.exists() else []):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = os.path.normpath(line.lstrip("!").strip()).strip("/")
        rules.append((negated, re.compile(glob.translate(pattern, recursive=True, include_hidden=True)), pattern))
    return rules


def excluded(path: str, rules) -> bool:
    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    out = False
    for negated, rx, _ in rules:
        if any(rx.match(p) for p in prefixes):
            out = not negated
    return out


def context_files(root: Path = None):
    """Relative paths of every file Docker would send in the build context."""
    root = root or CODE_DIR
    rules = ignore_rules(root)
    negs = [raw for neg, _, raw in rules if neg]
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        keep = []
        for d in dirnames:
            rel = d if rel_dir == "." else f"{rel_dir}/{d}"
            if d == ".git":
                continue
            could_reinclude = any(n.startswith(rel + "/") or n.startswith("**") or "*" in n.split("/")[0] for n in negs)
            if excluded(rel, rules) and not could_reinclude:
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            rel = f if rel_dir == "." else f"{rel_dir}/{f}"
            if not excluded(rel, rules):
                out.add(rel)
    return out


def _logical_lines(text):
    buf = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not buf and (not s or s.startswith("#")):
            continue
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        yield buf
        buf = ""
    if buf:
        yield buf


def parse_dockerfile(text):
    """[{name, base, instrs: [(OP, rest)]}] in order."""
    stages = []
    for line in _logical_lines(text):
        op, _, rest = line.partition(" ")
        op = op.upper()
        if op == "FROM":
            toks = [t for t in rest.split() if not t.startswith("--")]
            name = toks[2].lower() if len(toks) >= 3 and toks[1].lower() == "as" else None
            stages.append({"name": name, "base": toks[0], "instrs": []})
        elif stages:
            stages[-1]["instrs"].append((op, rest.strip()))
    return stages


def _copy_args(rest):
    rest = rest.strip()
    flags = {}
    while rest.startswith("--"):
        tok, _, rest = rest.partition(" ")
        k, _, v = tok[2:].partition("=")
        flags[k] = v
        rest = rest.strip()
    if rest.startswith("["):
        parts = json.loads(rest)
    else:
        parts = shlex.split(rest)
    return flags, parts[:-1], parts[-1]


def _ctx_matches(src, ctx):
    """Context files a COPY source names: (path-in-context, path-relative-to-the-source) pairs."""
    src = os.path.normpath(src).lstrip("/")
    if src in (".", ""):
        return [(f, f) for f in ctx]
    out = []
    if any(c in src for c in "*?["):
        tops = {f for f in ctx if fnmatch.fnmatchcase(f, src)}
        dirs = {"/".join(f.split("/")[:n]) for f in ctx for n in range(1, f.count("/") + 1)}
        out += [(f, os.path.basename(f)) for f in tops]
        for d in dirs:
            if fnmatch.fnmatchcase(d, src):
                out += [(f, os.path.relpath(f, d)) for f in ctx if f.startswith(d + "/")]
        return out
    if src in ctx:
        return [(src, None)]          # a single file
    return [(f, os.path.relpath(f, src)) for f in ctx if f.startswith(src + "/")]


def stage_filesystems(dockerfile_text=None, ctx=None):
    """{stage name or index: {abs path in image: path in context}} for COPY/ADD from the context and from stages."""
    text = dockerfile_text if dockerfile_text is not None else (CODE_DIR / "Dockerfile").read_text()
    ctx = ctx if ctx is not None else context_files()
    stages = parse_dockerfile(text)
    fs_by, wd_by, result = {}, {}, {}
    for i, st in enumerate(stages):
        base = st["base"].lower()
        fs = dict(fs_by.get(base, {}))
        wd = wd_by.get(base, "/")
        for op, rest in st["instrs"]:
            if op == "WORKDIR":
                wd = os.path.normpath(os.path.join(wd, rest.strip()))
            elif op in ("COPY", "ADD"):
                flags, srcs, dest = _copy_args(rest)
                dest_abs = os.path.normpath(os.path.join(wd, dest))
                dest_is_dir = dest.endswith("/") or len(srcs) > 1 or dest in (".", "./")
                if "from" in flags:
                    other = fs_by.get(flags["from"].lower())
                    if other is None:
                        continue              # an external image: nothing from the context
                    for s in srcs:
                        s_abs = os.path.normpath(os.path.join(wd_by.get(flags["from"].lower(), "/"), s))
                        for path, origin in other.items():
                            if path == s_abs:
                                fs[os.path.join(dest_abs, os.path.basename(path)) if dest_is_dir else dest_abs] = origin
                            elif path.startswith(s_abs.rstrip("/") + "/"):
                                fs[os.path.join(dest_abs, os.path.relpath(path, s_abs))] = origin
                    continue
                for s in srcs:
                    for f, sub in _ctx_matches(s, ctx):
                        if sub is None:
                            target = os.path.join(dest_abs, os.path.basename(f)) if dest_is_dir else dest_abs
                        else:
                            target = os.path.join(dest_abs, sub)
                        fs[os.path.normpath(target)] = f
        key = st["name"] or str(i)
        fs_by[key], wd_by[key] = fs, wd
        result[key] = {"fs": fs, "workdir": wd, "instrs": st["instrs"], "base": st["base"]}
    return result


def materialize(stage, dest: Path):
    """Write a stage's files (from CODE_DIR) under dest; return the path that is the stage's WORKDIR."""
    for path, origin in stage["fs"].items():
        if not (CODE_DIR / origin).is_file():
            continue                          # a file only a deploy machine holds; the no-data test reports it
        out = dest / path.lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CODE_DIR / origin, out)
    wd = dest / stage["workdir"].lstrip("/")
    wd.mkdir(parents=True, exist_ok=True)
    return wd
