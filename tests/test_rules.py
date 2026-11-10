import pytest

from delivery_mcp import config
from delivery_mcp.models import Dependency, Story
from delivery_mcp.readiness import check_definition_of_ready, get_sprint_capacity
from delivery_mcp.rules.capacity import compute_capacity
from delivery_mcp.rules.dor import check_story
from tests.fixtures import EXPECTED, FixtureAdapter

TEAMS = list(EXPECTED)


def dependency_blockers_of(result: dict) -> dict:
    """DOR-4 blockers of a check_definition_of_ready result, shaped like expected-answers.json."""
    out = {}
    for s in result["stories"]:
        blockers = [
            {k: b.get(k) for k in ("rule", "dependsOn", "description", "crossTool")}
            for b in s["blockers"]
            if b["rule"] == "DOR-4"
        ]
        if blockers:
            out[s["key"]] = blockers
    return out


@pytest.mark.parametrize("team", TEAMS)
def test_capacity_matches_expected(team):
    exp = EXPECTED[team]
    c = compute_capacity(config.get_team(team), config.get_sprint("sprint-24"), config.company())
    assert c.raw_hours == exp["rawHours"]
    assert c.focus_hours == pytest.approx(exp["focusHours"])
    assert c.source == "config"
    assert get_sprint_capacity(team, "sprint-24")["focusHours"] == pytest.approx(exp["focusHours"])


@pytest.mark.parametrize("team", TEAMS)
async def test_definition_of_ready_matches_expected(team):
    exp = EXPECTED[team]
    r = await check_definition_of_ready(FixtureAdapter(), team, "sprint-24")
    assert len(r["stories"]) == exp["stories"]
    assert r["notReady"] == exp["notReady"]
    assert r["committedPoints"] == exp["committedPoints"]
    assert r["readyPoints"] == exp["readyPoints"]
    assert r["avgVelocity"] == exp["avgVelocity"]
    assert r["commitPctOfVelocity"] == exp["commitPctOfVelocity"]
    failures = {
        s["key"]: sorted(f["rule"] for f in [*s["blockers"], *s["warnings"]])
        for s in r["stories"]
        if s["blockers"] or s["warnings"]
    }
    assert failures == exp["failures"]
    assert [s["key"] for s in r["stories"] if s["ready"] and s["warnings"]] == exp["warningsOnly"]
    assert dependency_blockers_of(r) == exp["dependencyBlockers"]


def test_unknown_team_lists_valid_values():
    with pytest.raises(config.NotFoundError, match="Valid teams"):
        config.get_team("nope")


def test_unknown_sprint_lists_valid_values():
    with pytest.raises(config.NotFoundError, match="Valid sprints"):
        config.get_sprint("sprint-99")


def test_sprint_name_with_space_is_accepted():
    assert config.get_sprint("Sprint 24").key == "sprint-24"


BASE = Story(
    key="MOB-999", title="t", description="As a x, I want y, so that z.", acceptance_criteria=["a", "b"],
    story_points=3, has_ui=False, design_link=None, dependencies=[], assignee=None, release_name=None,
    sprint_key="sprint-24", status="New", team_key="mobile",
)  # fmt: skip


def blockers_for(deps: list[Dependency]):
    story = BASE.model_copy(update={"dependencies": deps})
    return check_story(story, config.dor_rules(), config.tracker_of_key, "azure-devops").blockers


def test_dor4_flags_dependency_in_other_tracker_as_cross_tool():
    (b,) = blockers_for(
        [Dependency(key="DAT-307", description="Delay prediction API from Data team", resolved=False)]
    )
    assert (b.rule_id, b.depends_on, b.description, b.cross_tool) == (
        "DOR-4", "DAT-307", "Delay prediction API from Data team", True,
    )  # fmt: skip


def test_dor4_same_tracker_and_external_are_not_cross_tool():
    bs = blockers_for([
        Dependency(key="MOB-205", description="same tracker", resolved=False),
        Dependency(key="SEC-12", description="external", resolved=False),
    ])  # fmt: skip
    assert [(b.depends_on, b.cross_tool) for b in bs] == [("MOB-205", False), ("SEC-12", False)]


def test_dor4_ignores_resolved_dependencies():
    assert blockers_for([Dependency(key="DAT-307", description="done", resolved=True)]) == []
