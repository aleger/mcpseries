"""POST /mcp over HTTP (pytest -m http). Targets MCP_URL, or starts the ASGI app locally.

Sprint 24 answers come from the live trackers, so this needs the tracker env vars (read-only).
"""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.fixtures import EXPECTED
from tests.test_rules import dependency_blockers_of

pytestmark = pytest.mark.http


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_url():
    if url := os.environ.get("MCP_URL"):
        yield url
        return
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "delivery_mcp.server:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]
    )
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(50):
        try:
            httpx.get(url, timeout=1)
            break
        except httpx.HTTPError as err:
            if isinstance(err, httpx.HTTPStatusError):
                break
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(params=["auto", "legacy", "2026-07-28"])
async def client(request, mcp_url):
    """Every handshake: modern, 2025-style initialize from older clients, and auto-detect."""
    async with Client(mcp_url, mode=request.param) as c:
        yield c


async def test_lists_both_tools_as_read_only(client):
    tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == {"get_sprint_capacity", "check_definition_of_ready"}
    for t in tools.values():
        assert t.annotations.read_only_hint is True


async def test_mobile_capacity(client):
    r = (await client.call_tool("get_sprint_capacity", {"team": "mobile", "sprint": "Sprint 24"})).data
    assert r["rawHours"] == 266
    assert r["focusHours"] == 186.2


async def test_unknown_team_lists_valid_values(client):
    with pytest.raises(ToolError, match="Valid teams: .*platform"):
        await client.call_tool("get_sprint_capacity", {"team": "nope", "sprint": "sprint-24"})


async def test_unknown_sprint_lists_valid_values(client):
    with pytest.raises(ToolError, match="Valid sprints: .*sprint-24"):
        await client.call_tool("check_definition_of_ready", {"team": "platform", "sprint": "sprint-99"})


@pytest.mark.parametrize("team", list(EXPECTED))
async def test_sprint_24_readiness_matches_expected(client, team):
    exp = EXPECTED[team]
    r = (await client.call_tool("check_definition_of_ready", {"team": team, "sprint": "Sprint 24"})).data
    assert r["notReady"] == exp["notReady"]
    assert r["committedPoints"] == exp["committedPoints"]
    assert r["readyPoints"] == exp["readyPoints"]
    assert r["avgVelocity"] == exp["avgVelocity"]
    assert r["commitPctOfVelocity"] == exp["commitPctOfVelocity"]
    assert dependency_blockers_of(r) == exp["dependencyBlockers"]
