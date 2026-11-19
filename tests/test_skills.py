"""The server serves the Agent Skills in skills/ : listed to a client that opts into the skills extension, and
readable as skill:// resources to one that does not. server.py is imported with its startup stubbed, so no
database or embedding service is needed."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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
