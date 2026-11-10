"""Team, sprint and capacity config plus the DoR rule set. Story data never comes from here:
it comes from the trackers through delivery_mcp.adapters on every request."""

import json
from functools import lru_cache
from pathlib import Path

from delivery_mcp.models import Company, DorRule, Sprint, TeamConfig, TeamsConfig

ROOT = Path(__file__).resolve().parent.parent


class NotFoundError(Exception):
    """Unknown team or sprint. The message lists the valid values and is safe to show the client."""


@lru_cache
def load_config() -> TeamsConfig:
    return TeamsConfig.model_validate_json((ROOT / "config" / "teams.json").read_text())


@lru_cache
def dor_rules() -> list[DorRule]:
    raw = json.loads((ROOT / "data" / "definition-of-ready.json").read_text())
    return [DorRule.model_validate(r) for r in raw["rules"]]


def company() -> Company:
    return load_config().company


def get_team(key: str) -> TeamConfig:
    k = key.lower()
    for t in load_config().teams:
        if k in (t.key, t.name.lower()):
            return t
    valid = ", ".join(t.key for t in load_config().teams)
    raise NotFoundError(f'Unknown team "{key}". Valid teams: {valid}.')


def get_sprint(key: str) -> Sprint:
    norm = "-".join(key.lower().split())
    for s in load_config().sprints:
        if s.key == norm:
            return s
    valid = ", ".join(s.key for s in load_config().sprints)
    raise NotFoundError(f'Unknown sprint "{key}". Valid sprints: {valid}.')


def tracker_of_key(key: str) -> str | None:
    """Tracker that holds a story key (by its prefix), or None for keys outside both trackers."""
    prefix = key.split("-")[0].upper()
    return next((t.tracker for t in load_config().teams if t.key_prefix == prefix), None)


def prior_closed_sprints(sprint: Sprint) -> list[Sprint]:
    """Up to the two closed sprints before `sprint`, oldest first."""
    sprints = load_config().sprints
    idx = next(i for i, s in enumerate(sprints) if s.key == sprint.key)
    return [s for s in sprints[:idx] if s.state == "closed"][-2:]
