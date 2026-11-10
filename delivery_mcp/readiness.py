"""check_definition_of_ready and get_sprint_capacity as plain functions. server.py only wraps these."""

import asyncio
import re
from dataclasses import asdict
from typing import Any

from delivery_mcp import config
from delivery_mcp.adapters import TrackerAdapter
from delivery_mcp.rules.capacity import compute_capacity
from delivery_mcp.rules.dor import RuleFailure, summarize_readiness


def _natural_key(key: str) -> list[Any]:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", key)]


def _trim_failure(f: RuleFailure) -> dict[str, Any]:
    """Trim a failure for the client. DOR-4 failures also say which dependency blocks and where it lives."""
    out: dict[str, Any] = {"rule": f.rule_id, "name": f.name, "fix": f.fix}
    if f.depends_on is not None:
        out |= {"dependsOn": f.depends_on, "description": f.description, "crossTool": f.cross_tool}
    return out


async def check_definition_of_ready(adapter: TrackerAdapter, team: str, sprint: str) -> dict[str, Any]:
    t = config.get_team(team)
    s = config.get_sprint(sprint)
    stories, velocity = await asyncio.gather(
        adapter.get_sprint_stories(t, s),
        asyncio.gather(*(adapter.get_completed_points(t, p) for p in config.prior_closed_sprints(s))),
    )
    stories = sorted(stories, key=lambda x: _natural_key(x.key))
    summary = summarize_readiness(
        stories, config.dor_rules(), list(velocity), config.tracker_of_key, t.tracker
    )
    return {
        "team": t.key,
        "sprint": s.key,
        "notReady": summary.not_ready,
        "committedPoints": summary.committed_points,
        "readyPoints": summary.ready_points,
        "avgVelocity": summary.avg_velocity,
        "commitPctOfVelocity": summary.commit_pct_of_velocity,
        "stories": [
            {
                "key": c.key,
                "title": c.title,
                "storyPoints": c.story_points,
                "ready": c.ready,
                "blockers": [_trim_failure(f) for f in c.blockers],
                "warnings": [_trim_failure(f) for f in c.warnings],
            }
            for c in summary.stories
        ],
    }


def get_sprint_capacity(team: str, sprint: str) -> dict[str, Any]:
    cap = compute_capacity(config.get_team(team), config.get_sprint(sprint), config.company())
    d = asdict(cap)
    camel = lambda k: re.sub(r"_([a-z])", lambda m: m.group(1).upper(), k)  # noqa: E731
    return {
        camel(k): ([{camel(a): b for a, b in m.items()} for m in v] if k == "members" else v)
        for k, v in d.items()
    }
