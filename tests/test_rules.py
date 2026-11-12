import pytest

from delivery_mcp import config
from delivery_mcp.adapters.http import TrackerError
from delivery_mcp.models import Dependency, Story
from delivery_mcp.readiness import check_definition_of_ready, get_sprint_capacity
from delivery_mcp.rules.capacity import compute_capacity
from delivery_mcp.rules.dor import check_story, summarize_readiness
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


def test_capacity_response_uses_camel_case_field_names():
    result = get_sprint_capacity("mobile", "sprint-24")
    assert list(result) == [
        "team", "sprint", "workingDays", "focusFactor", "members", "rawHours", "focusHours", "source",
    ]  # fmt: skip
    assert result["members"]
    for member in result["members"]:
        assert list(member) == ["name", "role", "hoursPerDay", "ptoDays", "workingDays", "hours"]


def test_member_hours_subtract_pto_days():
    result = get_sprint_capacity("mobile", "sprint-24")
    for member in result["members"]:
        assert member["workingDays"] == result["workingDays"] - member["ptoDays"]
        assert member["hours"] == member["hoursPerDay"] * member["workingDays"]
    assert result["rawHours"] == sum(member["hours"] for member in result["members"])


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


class StubAdapter:
    """Returns the given stories and the same completed points for every earlier sprint."""

    def __init__(self, stories: list[Story], completed_points: float = 0) -> None:
        self.stories = stories
        self.completed_points = completed_points

    async def get_sprint_stories(self, team, sprint) -> list[Story]:
        return self.stories

    async def get_completed_points(self, team, sprint) -> float:
        return self.completed_points


async def test_stories_are_sorted_by_the_number_in_their_key():
    keys = ["MOB-10", "MOB-9", "MOB-100", "MOB-1"]
    stories = [BASE.model_copy(update={"key": key}) for key in keys]
    result = await check_definition_of_ready(StubAdapter(stories), "mobile", "sprint-24")
    assert [story["key"] for story in result["stories"]] == ["MOB-1", "MOB-9", "MOB-10", "MOB-100"]


async def test_empty_sprint_reports_zero_points_and_no_stories():
    result = await check_definition_of_ready(StubAdapter([], completed_points=20), "mobile", "sprint-24")
    assert result["stories"] == []
    assert result["notReady"] == []
    assert (result["committedPoints"], result["readyPoints"]) == (0, 0)
    assert (result["avgVelocity"], result["commitPctOfVelocity"]) == (20, 0)


@pytest.mark.parametrize("completed_velocity", [[], [0, 0]])
def test_no_velocity_history_reports_zero_instead_of_dividing_by_zero(completed_velocity):
    summary = summarize_readiness([BASE], config.dor_rules(), completed_velocity)
    assert summary.committed_points == 3
    assert summary.avg_velocity == 0
    assert summary.commit_pct_of_velocity == 0


def test_story_failing_several_rules_lists_each_one():
    story = BASE.model_copy(
        update={"description": "Do the thing", "acceptance_criteria": [], "story_points": None}
    )
    check = check_story(story, config.dor_rules())
    failed = sorted(failure.rule_id for failure in [*check.blockers, *check.warnings])
    assert failed == ["DOR-1", "DOR-2", "DOR-3"]
    assert check.ready is False


async def test_tracker_errors_are_not_swallowed():
    class FailingAdapter(StubAdapter):
        async def get_completed_points(self, team, sprint) -> float:
            raise TrackerError("Azure DevOps request failed (500).")

    with pytest.raises(TrackerError, match="request failed"):
        await check_definition_of_ready(FailingAdapter([BASE]), "mobile", "sprint-24")
