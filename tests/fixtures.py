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
        stories = []
        for seed_story in _SEED["stories"]:
            if seed_story["teamKey"] != team.key or seed_story["sprintKey"] != sprint.key:
                continue
            # The seed refers to a release by key. Story carries the release name instead.
            fields = {name: value for name, value in seed_story.items() if name != "releaseKey"}
            fields["releaseName"] = _RELEASES.get(seed_story.get("releaseKey"))
            stories.append(Story.model_validate(fields))
        return stories

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        total = 0.0
        for history_story in _SEED["historyStories"]:
            in_sprint = history_story["teamKey"] == team.key and history_story["sprintKey"] == sprint.key
            if in_sprint and history_story["status"] == "Done":
                total += history_story["storyPoints"]
        return total
