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
    """Find a team by key or display name, ignoring case."""
    teams = load_config().teams
    wanted = key.lower()
    for team in teams:
        if wanted in (team.key, team.name.lower()):
            return team

    valid = ", ".join(team.key for team in teams)
    raise NotFoundError(f'Unknown team "{key}". Valid teams: {valid}.')


def get_sprint(key: str) -> Sprint:
    """Find a sprint by key. The display name works too: "Sprint 24" is read as "sprint-24"."""
    sprints = load_config().sprints
    wanted = "-".join(key.lower().split())
    for sprint in sprints:
        if sprint.key == wanted:
            return sprint

    valid = ", ".join(sprint.key for sprint in sprints)
    raise NotFoundError(f'Unknown sprint "{key}". Valid sprints: {valid}.')


def tracker_of_key(key: str) -> str | None:
    """Tracker that holds a story key (by its prefix), or None for keys outside both trackers."""
    prefix = key.split("-")[0].upper()
    for team in load_config().teams:
        if team.key_prefix == prefix:
            return team.tracker
    return None


def prior_closed_sprints(sprint: Sprint) -> list[Sprint]:
    """Up to the two closed sprints before `sprint`, oldest first."""
    # Sprints are listed in date order in config/teams.json.
    sprints = load_config().sprints
    sprint_keys = [candidate.key for candidate in sprints]
    earlier_sprints = sprints[: sprint_keys.index(sprint.key)]

    closed = [earlier for earlier in earlier_sprints if earlier.state == "closed"]
    return closed[-2:]
