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
    return next((r["name"] for r in SEED["releases"] if r["key"] == key), None)


def sprint_name(key: str | None) -> str | None:
    return next((s["name"] for s in SEED["sprints"] if s["key"] == key), None)


def cross_tool_needed_by(story: Json) -> list[str]:
    """Keys of stories in the other tracker that depend on this story."""

    def tracker(key: str) -> str | None:
        team = next((s["teamKey"] for s in SEED["stories"] if s["key"] == key), None)
        return next((t["tracker"] for t in SEED["teams"] if t["key"] == team), None)

    mine = tracker(story["key"])
    return [
        s["key"]
        for s in SEED["stories"]
        if any(d["key"] == story["key"] for d in s["dependencies"]) and tracker(s["key"]) != mine
    ]


def need(name: str) -> str:
    """Read one setting through the shared parser (.env, .env.local, environment). Exit if unset."""
    value = getattr(get_settings(), name.lower())
    if value is None or value == "":
        sys.exit(f"{name} is not set (put it in .env.local).")
    return value.get_secret_value() if isinstance(value, SecretStr) else value
