"""Read-only ClickUp REST v2 adapter."""

from typing import Any

import httpx

from delivery_mcp.adapters.http import TrackerError, cached, read_json, require
from delivery_mcp.adapters.parse import KEY_RE, RELEASE_TAG_PREFIX, split_description
from delivery_mcp.models import Sprint, Story, TeamConfig
from delivery_mcp.settings import get_settings

BASE = "https://api.clickup.com/api/v2"
Json = dict[str, Any]


def _field(task: Json, name: str) -> Any:
    for c in task.get("custom_fields") or []:
        if c.get("name") == name:
            return c.get("value")
    return None


def _points(task: Json) -> float | None:
    """Story Points custom field, falling back to ClickUp's native points (history items use it)."""
    v = _field(task, "Story Points")
    if v is None:
        v = task.get("points")
    return None if v is None or v == "" else float(v)


def map_task(t: Json, team_key: str, sprint_key: str | None) -> Story | None:
    """Map one ClickUp task to the common Story shape."""
    m = KEY_RE.match(str(t.get("name", "")))
    if not m:
        return None
    description, dependencies = split_description(str(t.get("description") or t.get("text_content") or ""))
    tags = [str(x["name"]) for x in t.get("tags") or []]
    checklist = next((c for c in t.get("checklists") or [] if c.get("name") == "Acceptance Criteria"), None)
    assignees = t.get("assignees") or []
    owner = _field(t, "Owner") or (assignees[0].get("username") if assignees else None)
    release = next((x[len(RELEASE_TAG_PREFIX) :] for x in tags if x.startswith(RELEASE_TAG_PREFIX)), None)
    return Story(
        key=m[1],
        title=m[2],
        description=description,
        acceptance_criteria=[str(i["name"]) for i in (checklist or {}).get("items") or []],
        story_points=_points(t),
        has_ui="ui" in tags,
        design_link=_field(t, "Design Link") or None,
        dependencies=dependencies,
        assignee=owner,
        release_name=release,
        sprint_key=sprint_key,
        status=str((t.get("status") or {}).get("status", "")),
        team_key=team_key,
    )


class ClickUpAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _get(self, path: str) -> Json:
        async def load() -> Json:
            token = require(
                get_settings().clickup_api_token and get_settings().clickup_api_token.get_secret_value(),
                "CLICKUP_API_TOKEN",
            )
            async with httpx.AsyncClient(transport=self._transport, timeout=30) as client:
                res = await client.get(BASE + path, headers={"Authorization": token})
            return read_json(res, "ClickUp", "CLICKUP_API_TOKEN", "a personal API token")

        return await cached(f"clickup:{path}", load)

    async def _list_for(self, team: TeamConfig, sprint: Sprint) -> str | None:
        folder_name = (team.clickup or {}).get("folder")
        if not folder_name:
            raise TrackerError(f"Team {team.key} has no ClickUp folder configured.")
        space = require(get_settings().clickup_space_id, "CLICKUP_SPACE_ID")
        folders = (await self._get(f"/space/{space}/folder?archived=false"))["folders"]
        for f in folders:
            if f["name"] == folder_name:
                return next((lst["id"] for lst in f["lists"] if lst["name"] == sprint.name), None)
        return None

    async def _tasks_in(self, list_id: str) -> list[Json]:
        out: list[Json] = []
        page = 0
        while True:
            res = await self._get(f"/list/{list_id}/task?include_closed=true&subtasks=true&page={page}")
            out += res["tasks"]
            if res.get("last_page", len(res["tasks"]) < 100):
                return out
            page += 1

    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]:
        list_id = await self._list_for(team, sprint)
        if not list_id:
            return []
        return [s for t in await self._tasks_in(list_id) if (s := map_task(t, team.key, sprint.key))]

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        list_id = await self._list_for(team, sprint)
        if not list_id:
            return 0
        return sum(
            _points(t) or 0
            for t in await self._tasks_in(list_id)
            if str((t.get("status") or {}).get("type")) in ("done", "closed")
        )
