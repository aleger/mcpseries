"""Unit-test fixture adapter built from the seed JSON. The server itself never reads northwind.json."""

import json
from pathlib import Path

from delivery_mcp.models import Sprint, Story, TeamConfig

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = json.loads((ROOT / "data" / "expected-answers.json").read_text())
_SEED = json.loads((ROOT / "data" / "northwind.json").read_text())
_RELEASES = {r["key"]: r["name"] for r in _SEED["releases"]}


class FixtureAdapter:
    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]:
        out = []
        for s in _SEED["stories"]:
            if s["teamKey"] == team.key and s["sprintKey"] == sprint.key:
                row = {k: v for k, v in s.items() if k != "releaseKey"}
                out.append(Story.model_validate({**row, "releaseName": _RELEASES.get(s.get("releaseKey"))}))
        return out

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        return sum(
            h["storyPoints"]
            for h in _SEED["historyStories"]
            if h["teamKey"] == team.key and h["sprintKey"] == sprint.key and h["status"] == "Done"
        )
