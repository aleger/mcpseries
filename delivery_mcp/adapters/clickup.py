"""Read-only ClickUp REST v2 adapter."""

from typing import Any

import httpx

from delivery_mcp.adapters.http import TrackerError, cache_get, cache_set, read_json, require
from delivery_mcp.adapters.parse import KEY_RE, RELEASE_TAG_PREFIX, split_description, tag_value
from delivery_mcp.models import Sprint, Story, TeamConfig
from delivery_mcp.settings import get_settings

BASE = "https://api.clickup.com/api/v2"
PAGE_SIZE = 100
Json = dict[str, Any]


def _custom_field(task: Json, name: str) -> Any:
    for field in task.get("custom_fields") or []:
        if field.get("name") == name:
            return field.get("value")
    return None


def _points(task: Json) -> float | None:
    """Story Points custom field, falling back to ClickUp's native points (history items use it)."""
    value = _custom_field(task, "Story Points")
    if value is None:
        value = task.get("points")
    if value is None or value == "":
        return None
    return float(value)


def _acceptance_criteria(task: Json) -> list[str]:
    """Item names from the task's "Acceptance Criteria" checklist."""
    for checklist in task.get("checklists") or []:
        if checklist.get("name") == "Acceptance Criteria":
            return [str(item["name"]) for item in checklist.get("items") or []]
    return []


def _is_completed(task: Json) -> bool:
    # Status names are customizable per list. The status type is what ClickUp itself
    # uses to mark a task finished.
    status_type = (task.get("status") or {}).get("type")
    return str(status_type) in ("done", "closed")


def map_task(task: Json, team_key: str, sprint_key: str | None) -> Story | None:
    """Map one ClickUp task to the common Story shape, or None if the seed did not create it."""
    title_match = KEY_RE.match(str(task.get("name", "")))
    if title_match is None:
        return None

    raw_description = str(task.get("description") or task.get("text_content") or "")
    description, dependencies = split_description(raw_description)
    tags = [str(tag["name"]) for tag in task.get("tags") or []]

    # The Owner custom field wins over the ClickUp assignee when both are set.
    owner = _custom_field(task, "Owner")
    if not owner:
        assignees = task.get("assignees") or []
        owner = assignees[0].get("username") if assignees else None

    return Story(
        key=title_match[1],
        title=title_match[2],
        description=description,
        acceptance_criteria=_acceptance_criteria(task),
        story_points=_points(task),
        has_ui="ui" in tags,
        design_link=_custom_field(task, "Design Link") or None,
        dependencies=dependencies,
        assignee=owner,
        release_name=tag_value(tags, RELEASE_TAG_PREFIX),
        sprint_key=sprint_key,
        status=str((task.get("status") or {}).get("status", "")),
        team_key=team_key,
    )


class ClickUpAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Tests pass a mock transport. In production this stays None and httpx uses the network.
        self._transport = transport

    async def _get(self, path: str) -> Json:
        cache_key = f"clickup:{path}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        token = get_settings().clickup_api_token
        secret = require(token.get_secret_value() if token else None, "CLICKUP_API_TOKEN")

        async with httpx.AsyncClient(transport=self._transport, timeout=30) as client:
            response = await client.get(BASE + path, headers={"Authorization": secret})
        data = read_json(response, "ClickUp", "CLICKUP_API_TOKEN", "a personal API token")

        cache_set(cache_key, data)
        return data

    async def _find_sprint_list_id(self, team: TeamConfig, sprint: Sprint) -> str | None:
        """Id of the list named after the sprint in the team's folder, or None if there is no such list."""
        folder_name = (team.clickup or {}).get("folder")
        if not folder_name:
            raise TrackerError(f"Team {team.key} has no ClickUp folder configured.")
        space_id = require(get_settings().clickup_space_id, "CLICKUP_SPACE_ID")

        response = await self._get(f"/space/{space_id}/folder?archived=false")
        for folder in response["folders"]:
            if folder["name"] != folder_name:
                continue
            for sprint_list in folder["lists"]:
                if sprint_list["name"] == sprint.name:
                    return sprint_list["id"]
            return None
        return None

    async def _tasks_in(self, list_id: str) -> list[Json]:
        tasks: list[Json] = []
        page = 0
        while True:
            response = await self._get(f"/list/{list_id}/task?include_closed=true&subtasks=true&page={page}")
            page_tasks = response["tasks"]
            tasks.extend(page_tasks)

            # If the response does not say whether this is the last page, a page that
            # is not full means there is nothing more to fetch.
            if "last_page" in response:
                is_last_page = response["last_page"]
            else:
                is_last_page = len(page_tasks) < PAGE_SIZE
            if is_last_page:
                return tasks
            page += 1

    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]:
        list_id = await self._find_sprint_list_id(team, sprint)
        if not list_id:
            return []

        stories = []
        for task in await self._tasks_in(list_id):
            story = map_task(task, team.key, sprint.key)
            if story is not None:
                stories.append(story)
        return stories

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        list_id = await self._find_sprint_list_id(team, sprint)
        if not list_id:
            return 0

        total = 0.0
        for task in await self._tasks_in(list_id):
            if _is_completed(task):
                total += _points(task) or 0
        return total
