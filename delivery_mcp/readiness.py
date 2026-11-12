"""The logic behind check_definition_of_ready and get_sprint_capacity. server.py only wraps these."""

import asyncio
import re
from typing import Any

from delivery_mcp import config
from delivery_mcp.adapters import TrackerAdapter
from delivery_mcp.models import Story
from delivery_mcp.rules.capacity import MemberCapacity, compute_capacity
from delivery_mcp.rules.dor import RuleFailure, StoryCheck, summarize_readiness


def _natural_sort_key(story: Story) -> list[str | int]:
    """Sort key that compares the number in a story key as a number, so PLT-9 comes before PLT-10."""
    parts = re.split(r"(\d+)", story.key)
    return [int(part) if part.isdigit() else part for part in parts]


def _serialize_failure(failure: RuleFailure) -> dict[str, Any]:
    result: dict[str, Any] = {"rule": failure.rule_id, "name": failure.name, "fix": failure.fix}

    # Only dependency (DOR-4) failures have these. They tell the client which story is
    # blocking and whether it lives in the other tracker.
    if failure.depends_on is not None:
        result["dependsOn"] = failure.depends_on
        result["description"] = failure.description
        result["crossTool"] = failure.cross_tool

    return result


def _serialize_story_check(check: StoryCheck) -> dict[str, Any]:
    return {
        "key": check.key,
        "title": check.title,
        "storyPoints": check.story_points,
        "ready": check.ready,
        "blockers": [_serialize_failure(failure) for failure in check.blockers],
        "warnings": [_serialize_failure(failure) for failure in check.warnings],
    }


async def check_definition_of_ready(adapter: TrackerAdapter, team: str, sprint: str) -> dict[str, Any]:
    """Check a team's sprint stories against the Definition of Ready rules."""
    team_config = config.get_team(team)
    sprint_config = config.get_sprint(sprint)

    # Velocity comes from the closed sprints before this one. The current sprint is left
    # out because its completed points keep changing while work is in progress.
    velocity_requests = [
        adapter.get_completed_points(team_config, earlier_sprint)
        for earlier_sprint in config.prior_closed_sprints(sprint_config)
    ]

    # None of these requests depends on another, so they all run at once. gather returns
    # results in the order the requests were passed: the stories, then one total per sprint.
    stories, *completed_points = await asyncio.gather(
        adapter.get_sprint_stories(team_config, sprint_config),
        *velocity_requests,
    )

    stories = sorted(stories, key=_natural_sort_key)
    summary = summarize_readiness(
        stories,
        config.dor_rules(),
        completed_points,
        config.tracker_of_key,
        team_config.tracker,
    )

    return {
        "team": team_config.key,
        "sprint": sprint_config.key,
        "notReady": summary.not_ready,
        "committedPoints": summary.committed_points,
        "readyPoints": summary.ready_points,
        "avgVelocity": summary.avg_velocity,
        "commitPctOfVelocity": summary.commit_pct_of_velocity,
        "stories": [_serialize_story_check(check) for check in summary.stories],
    }


def _serialize_member(member: MemberCapacity) -> dict[str, Any]:
    return {
        "name": member.name,
        "role": member.role,
        "hoursPerDay": member.hours_per_day,
        "ptoDays": member.pto_days,
        "workingDays": member.working_days,
        "hours": member.hours,
    }


def get_sprint_capacity(team: str, sprint: str) -> dict[str, Any]:
    """Work out a team's capacity for a sprint from config/teams.json."""
    capacity = compute_capacity(config.get_team(team), config.get_sprint(sprint), config.company())

    return {
        "team": capacity.team,
        "sprint": capacity.sprint,
        "workingDays": capacity.working_days,
        "focusFactor": capacity.focus_factor,
        "members": [_serialize_member(member) for member in capacity.members],
        "rawHours": capacity.raw_hours,
        "focusHours": capacity.focus_hours,
        "source": capacity.source,
    }
