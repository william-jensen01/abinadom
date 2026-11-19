"""The server serves the Agent Skills in skills/ : listed to a client that opts into the skills extension, and
readable as skill:// resources to one that does not. server.py is imported with its startup stubbed, so no
database or embedding service is needed."""
import ast
import asyncio
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastmcp import Client
from fastmcp.skills import SkillsClientExtension

import server

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_NAMES = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))


def _run(coro_fn):
    with patch("server._startup", return_value=server.AppContext(client=MagicMock())):
        return asyncio.run(coro_fn())


def test_skills_folder_is_resolved_from_server_py():
    assert server.SKILLS_DIR == Path(server.__file__).resolve().parent / "skills"
    assert "gospel-research" in SKILL_NAMES


def test_skills_extension_lists_and_serves_every_skill_byte_for_byte():
    async def go():
        async with Client(server.mcp, extensions=[SkillsClientExtension()]) as c:
            listed = {str(e.frontmatter.name): e for e in await c.list_skills()}
            served = {n: await c.read_skill(e.uri) for n, e in listed.items()}
        return listed, served

    listed, served = _run(go)
    assert sorted(listed) == SKILL_NAMES
    for name in SKILL_NAMES:
        folder = SKILLS_DIR / name
        files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        got = {k: (v.content if hasattr(v, "content") else bytes(v)) for k, v in served[name].files.items()}
        assert got == files, name


def test_skill_files_are_resources_for_a_client_without_the_extension():
    async def go():
        async with Client(server.mcp) as c:
            uris = {str(r.uri) for r in await c.list_resources()}
            body = await c.read_resource("skill://gospel-research/SKILL.md")
        return uris, body

    uris, body = _run(go)
    for name in SKILL_NAMES:
        assert f"skill://{name}/SKILL.md" in uris
    assert body[0].text == (SKILLS_DIR / "gospel-research" / "SKILL.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------------ what a skill must look like

ROOT = SKILLS_DIR.parent
TOOLS = {"search", "get_talk", "find_by_scripture", "corpus_stats", "get_talk_citations", "get_verse",
         "get_citing_talks", "get_chapter_overview", "find_cross_references"}
SKILLS = {"gospel-research", "study-scripture-passage", "prepare-talk-or-lesson"}
STUDY_FLOW_TOOLS = {"get_chapter_overview", "get_verse", "find_cross_references", "get_citing_talks"}
ROLES = ["research assistant", "discussion partner", "study guide"]

# Agent Skills format: allowed frontmatter keys and limits.
FRONTMATTER_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_SKILL_MD_LINES = 500
MAX_SKILL_MD_CHARS = 20000          # about 5000 tokens of body
COPIED_RUN_WORDS = 10               # this many identical consecutive words is copying, not paraphrase
MAX_INSTRUCTIONS_CHARS = 1600


def _files_of(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and not any(part.startswith(".") or part == "__pycache__"
                                       for part in p.relative_to(folder).parts)}


def _code_spans(md: str) -> list:
    fenced = re.findall(r"```[^\n]*\n(.*?)```", md, flags=re.S)
    rest = re.sub(r"```.*?```", " ", md, flags=re.S)
    return fenced + re.findall(r"`([^`\n]+)`", rest)


def _shingles(text: str) -> set:
    w = re.findall(r"[a-z0-9_']+", text.lower())
    return {" ".join(w[i:i + COPIED_RUN_WORDS]) for i in range(len(w) - COPIED_RUN_WORDS + 1)}


def _source_without_instructions(path: Path) -> str:
    """Source text minus the MCP_INSTRUCTIONS assignment, so the instructions cannot vouch for themselves."""
    text = path.read_text()
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                isinstance(t, ast.Name) and t.id == "MCP_INSTRUCTIONS" for t in targets):
            for i in range(node.lineno - 1, node.end_lineno):
                lines[i] = ""
    return "\n".join(lines)


@pytest.fixture(scope="module")
def served_tools():
    async def go():
        async with Client(server.mcp) as c:
            return [t.model_dump(mode="json", by_alias=True) for t in await c.list_tools()]
    return _run(go)


@pytest.fixture(scope="module")
def tool_universe(served_tools):
    """({tool: its parameters}, every word in the served tools and the code behind them, all tool description text)."""
    params = {t["name"]: set((t.get("inputSchema") or {}).get("properties", {})) for t in served_tools}
    words = set(re.findall(r"[A-Za-z0-9_]+", json.dumps(served_tools)))
    for src in [ROOT / "server.py", *(p for d in ("tools", "db", "loaders", "models", "config")
                                     for p in sorted((ROOT / d).glob("*.py")))]:
        words |= set(re.findall(r"[A-Za-z0-9_]+", _source_without_instructions(src)))
    texts = []
    for t in served_tools:
        texts.append(t.get("description") or "")
        texts += [p.get("description") or "" for p in ((t.get("inputSchema") or {}).get("properties") or {}).values()]
    return params, words, "\n".join(texts)


def _skill_problems(name, tool_universe) -> list:
    folder = SKILLS_DIR / name
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, flags=re.S)
    if not m:
        return [f"{name}: SKILL.md must start with YAML frontmatter between --- lines"]
    fm, body = yaml.safe_load(m.group(1)), m.group(2)
    probs = []
    if set(fm) - FRONTMATTER_KEYS:
        probs.append(f"{name}: unknown frontmatter keys {sorted(set(fm) - FRONTMATTER_KEYS)}")
    if fm.get("name") != name:
        probs.append(f"{name}: frontmatter name {fm.get('name')!r} must equal the folder name")
    if not isinstance(fm.get("name"), str) or not NAME_RE.match(fm["name"]):
        probs.append(f"{name}: name is not lowercase letters, digits and single hyphens, 1-64 characters")
    d = fm.get("description")
    if not isinstance(d, str) or not d.strip() or len(d) > MAX_DESCRIPTION:
        probs.append(f"{name}: description must be non-empty and at most {MAX_DESCRIPTION} characters")
    c = fm.get("compatibility")
    if c is not None and (not isinstance(c, str) or not 1 <= len(c) <= MAX_COMPATIBILITY):
        probs.append(f"{name}: compatibility must be 1-{MAX_COMPATIBILITY} characters")
    md = fm.get("metadata")
    if md is not None and not (isinstance(md, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                            for k, v in md.items())):
        probs.append(f"{name}: metadata must map strings to strings")
    if fm.get("allowed-tools") is not None and not isinstance(fm["allowed-tools"], str):
        probs.append(f"{name}: allowed-tools must be a space-separated string")
    n_lines = text.count("\n") + 1
    if n_lines >= MAX_SKILL_MD_LINES or len(body) > MAX_SKILL_MD_CHARS:
        probs.append(f"{name}: SKILL.md is {n_lines} lines / {len(body)} body characters")

    files = _files_of(folder)
    for rel in files:
        if rel != "SKILL.md" and rel not in text:
            probs.append(f"{name}: {rel} is not referenced from SKILL.md by its path in the skill folder")
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        if not re.match(r"^[a-z]+:", target) and target not in files:
            probs.append(f"{name}: SKILL.md links to {target}, which is not a file in the skill")

    params, universe, desc_text = tool_universe
    desc_runs = _shingles(desc_text)
    for rel, raw in files.items():
        if not rel.endswith((".md", ".txt")):
            continue
        content = raw.decode("utf-8")
        for span in _code_spans(content):
            for fn, args in re.findall(r"\b([a-z_][a-z0-9_]*)\(([^()]*)\)", span):
                if fn not in params:
                    probs.append(f"{name}/{rel}: `{fn}(...)` is not a tool on this server")
                    continue
                probs += [f"{name}/{rel}: `{fn}` has no parameter `{kw}`"
                          for kw in re.findall(r"\b([a-z_][a-z0-9_]*)\s*=", args) if kw not in params[fn]]
            probs += [f"{name}/{rel}: `{i}` is not a tool, parameter or field this server has"
                      for i in re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", span) if i not in universe]
        copied = _shingles(content) & desc_runs
        if copied:
            probs.append(f"{name}/{rel}: copies tool description text ({len(copied)} runs), "
                         f"e.g. \"{sorted(copied)[0]}\"")
    return probs


def _mentioned_tools(name) -> set:
    text = "\n".join(b.decode("utf-8") for r, b in _files_of(SKILLS_DIR / name).items() if r.endswith(".md"))
    spans = "\n".join(_code_spans(text))
    return {t for t in TOOLS if re.search(rf"\b{t}\b", spans)}


def test_exactly_the_three_skills_ship():
    assert set(SKILL_NAMES) == SKILLS


@pytest.mark.parametrize("name", sorted(SKILLS))
def test_skill_follows_the_format_and_names_only_real_tools(name, tool_universe):
    problems = _skill_problems(name, tool_universe)
    assert not problems, "\n".join(problems[:20])


def test_skills_come_from_the_skills_directory_provider():
    providers = [f"{type(p).__module__}.{type(p).__name__}" for p in getattr(server.mcp, "providers", [])]
    assert "fastmcp.skills.provider.SkillsDirectoryProvider" in providers


def test_deprecated_skills_module_is_not_used():
    deprecated = "fastmcp.server.providers.skills"
    hits = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py")
            if p.relative_to(ROOT).parts[0] not in (".git", "tests") and not p.relative_to(ROOT).parts[0].startswith(".") and "site-packages" not in p.parts
            and deprecated in p.read_text(errors="replace")]
    assert not hits, f"{deprecated} is removed from fastmcp; used in {hits}"


def test_gospel_research_names_every_tool_and_the_three_roles():
    missing = TOOLS - _mentioned_tools("gospel-research")
    assert not missing, f"gospel-research never names these tools in code: {sorted(missing)}"
    text = "\n".join(b.decode() for r, b in _files_of(SKILLS_DIR / "gospel-research").items()
                     if r.endswith(".md")).lower()
    assert [r for r in ROLES if r not in text] == []


def test_study_skill_names_the_tools_of_its_flow():
    missing = STUDY_FLOW_TOOLS - _mentioned_tools("study-scripture-passage")
    assert not missing, f"study-scripture-passage never names these tools in code: {sorted(missing)}"


# ------------------------------------------------------------------------ the server instructions

def _initialize_instructions() -> str:
    """The instructions in the initialize result over streamable HTTP, as a remote client receives them."""
    from starlette.testclient import TestClient
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}}}
    with patch("server._startup", return_value=server.AppContext(client=MagicMock())), \
            TestClient(server.mcp.http_app()) as tc:
        r = tc.post("/mcp", json=body, headers=headers)
    assert r.status_code == 200, r.text[:300]
    text = r.text
    if "data:" in text:
        text = [l[5:] for l in text.splitlines() if l.startswith("data:")][-1]
    return json.loads(text)["result"].get("instructions") or ""


def test_instructions_are_short_and_name_every_tool_and_skill(tool_universe):
    text = _initialize_instructions()
    assert text, "initialize returns no instructions"
    probs = []
    if len(text) > MAX_INSTRUCTIONS_CHARS:
        probs.append(f"{len(text)} characters; at most {MAX_INSTRUCTIONS_CHARS}")
    probs += [f"does not name tool {t}" for t in sorted(TOOLS) if not re.search(rf"\b{t}\b", text)]
    probs += [f"does not name skill {s}" for s in sorted(SKILLS) if s not in text]
    if re.search(r"\b4 collections\b|\bfour collections\b", text, re.I):
        probs.append("still says 4 collections")
    _, universe, _ = tool_universe
    probs += [f"names `{i}`, which is not a tool, parameter or field of this server"
              for i in sorted(set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", text))) if i not in universe]
    assert not probs, "; ".join(probs)
