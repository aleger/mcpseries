"""Shared helpers for the seed scripts. Reads data/northwind.json, the only copy of the demo data.

Seed scripts are the only code that writes to ClickUp and Azure DevOps. Run by hand, never print tokens.
"""

import json
import sys
from typing import Any

from pydantic import SecretStr

from delivery_mcp.config import ROOT
from delivery_mcp.settings import get_settings

Json = dict[str, Any]
SEED: Json = json.loads((ROOT / "data" / "northwind.json").read_text())


def release_name(key: str | None) -> str | None:
    for release in SEED["releases"]:
        if release["key"] == key:
            return release["name"]
    return None


def sprint_name(key: str | None) -> str | None:
    for sprint in SEED["sprints"]:
        if sprint["key"] == key:
            return sprint["name"]
    return None


def release_and_ui_tags(story: Json) -> list[str]:
    """Tags both trackers put on a story. The adapters read the release name and the UI flag from them."""
    tags = []
    if story["releaseKey"]:
        tags.append(f"release-{release_name(story['releaseKey'])}")
    if story["hasUi"]:
        tags.append("ui")
    return tags


def tracker_of_story(key: str) -> str | None:
    """Tracker of the team that owns a story, or None for keys that are not in the seed data."""
    team_key = None
    for story in SEED["stories"]:
        if story["key"] == key:
            team_key = story["teamKey"]
            break

    for team in SEED["teams"]:
        if team["key"] == team_key:
            return team["tracker"]
    return None


def cross_tool_needed_by(story: Json) -> list[str]:
    """Keys of stories in the other tracker that depend on this story."""
    own_tracker = tracker_of_story(story["key"])

    dependents = []
    for other in SEED["stories"]:
        depends_on_story = any(dependency["key"] == story["key"] for dependency in other["dependencies"])
        if depends_on_story and tracker_of_story(other["key"]) != own_tracker:
            dependents.append(other["key"])
    return dependents


def need(name: str) -> str:
    """Read one setting through the shared parser (.env, .env.local, environment). Exit if unset."""
    value = getattr(get_settings(), name.lower())
    if value is None or value == "":
        sys.exit(f"{name} is not set (put it in .env.local).")
    return value.get_secret_value() if isinstance(value, SecretStr) else value
