"""Opt-in: read the live ClickUp and Azure DevOps demo workspaces (pytest -m live). Read-only."""

import pytest

from delivery_mcp import config
from delivery_mcp.adapters import adapter_for
from delivery_mcp.readiness import check_definition_of_ready
from tests.fixtures import EXPECTED
from tests.test_rules import dependency_blockers_of

pytestmark = pytest.mark.live


@pytest.mark.parametrize("team", list(EXPECTED))
async def test_live_sprint_24_matches_expected(team):
    exp = EXPECTED[team]
    adapter = adapter_for(config.get_team(team).tracker)
    r = await check_definition_of_ready(adapter, team, "sprint-24")
    assert len(r["stories"]) == exp["stories"]
    assert r["notReady"] == exp["notReady"]
    assert r["committedPoints"] == exp["committedPoints"]
    assert r["readyPoints"] == exp["readyPoints"]
    assert r["avgVelocity"] == exp["avgVelocity"]
    assert r["commitPctOfVelocity"] == exp["commitPctOfVelocity"]
    assert dependency_blockers_of(r) == exp["dependencyBlockers"]
    failures = {
        s["key"]: sorted(f["rule"] for f in [*s["blockers"], *s["warnings"]])
        for s in r["stories"]
        if s["blockers"] or s["warnings"]
    }
    assert failures == exp["failures"]
