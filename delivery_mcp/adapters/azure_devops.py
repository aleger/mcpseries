"""Read-only Azure DevOps adapter (WIQL plus work items)."""

import base64
from typing import Any
from urllib.parse import quote

import httpx

from delivery_mcp.adapters.http import TrackerError, cache_get, cache_set, read_json, require
from delivery_mcp.adapters.parse import (
    KEY_RE,
    RELEASE_TAG_PREFIX,
    html_list_items,
    split_ado_description,
    tag_value,
)
from delivery_mcp.models import Sprint, Story, TeamConfig
from delivery_mcp.settings import get_settings

Json = dict[str, Any]
POINTS = "Microsoft.VSTS.Scheduling.StoryPoints"
ACCEPTANCE_CRITERIA = "Microsoft.VSTS.Common.AcceptanceCriteria"
OWNER_TAG_PREFIX = "owner:"


def _design_link(work_item: Json) -> str | None:
    """The design link is stored as the work item's first Hyperlink relation."""
    for relation in work_item.get("relations") or []:
        if relation.get("rel") == "Hyperlink":
            return relation.get("url")
    return None


def map_work_item(work_item: Json, team_key: str, sprint_key: str | None) -> Story | None:
    """Map one Azure DevOps User Story to the common Story shape, or None if the seed did not create it."""
    fields = work_item["fields"]
    title_match = KEY_RE.match(str(fields.get("System.Title", "")))
    if title_match is None:
        return None

    # Azure DevOps returns tags as one string separated by semicolons.
    tags = []
    for tag in str(fields.get("System.Tags", "")).split(";"):
        if tag.strip():
            tags.append(tag.strip())

    description, dependencies = split_ado_description(fields.get("System.Description"))

    points = fields.get(POINTS)
    story_points = float(points) if isinstance(points, int | float) else None

    return Story(
        key=title_match[1],
        title=title_match[2],
        description=description,
        acceptance_criteria=html_list_items(fields.get(ACCEPTANCE_CRITERIA)),
        story_points=story_points,
        has_ui="ui" in tags,
        design_link=_design_link(work_item),
        dependencies=dependencies,
        # The seed records the story owner in an "owner:<name>" tag.
        assignee=tag_value(tags, OWNER_TAG_PREFIX),
        release_name=tag_value(tags, RELEASE_TAG_PREFIX),
        sprint_key=sprint_key,
        status=str(fields.get("System.State", "")),
        team_key=team_key,
    )


class AzureDevOpsAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Tests pass a mock transport. In production this stays None and httpx uses the network.
        self._transport = transport

    def _base_url(self) -> str:
        settings = get_settings()
        org = require(settings.ado_org, "ADO_ORG")
        project = quote(require(settings.ado_project, "ADO_PROJECT"))
        return f"https://dev.azure.com/{org}/{project}/_apis"

    async def _request(self, method: str, path: str, body: Json | None = None) -> Json:
        pat = get_settings().ado_pat
        secret = require(pat.get_secret_value() if pat else None, "ADO_PAT")

        # A PAT is sent as HTTP Basic auth with an empty user name.
        credentials = base64.b64encode(f":{secret}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}"}

        async with httpx.AsyncClient(transport=self._transport, timeout=30) as client:
            response = await client.request(method, self._base_url() + path, json=body, headers=headers)
        return read_json(
            response, "Azure DevOps", "ADO_PAT", "needs Work Items (Read) and Project and Team (Read)"
        )

    async def _work_items(self, team: TeamConfig, sprint: Sprint, extra_where: str = "") -> list[Json]:
        """Work items under a team's area path in one sprint iteration."""
        area_path = (team.azure_devops or {}).get("areaPath")
        if not area_path:
            raise TrackerError(f"Team {team.key} has no Azure DevOps area path configured.")
        project = require(get_settings().ado_project, "ADO_PROJECT")

        wiql = (
            "select [System.Id] from workitems where [System.TeamProject] = @project "
            "and [System.WorkItemType] = 'User Story' "
            f"and [System.AreaPath] under '{area_path}' "
            f"and [System.IterationPath] = '{project}\\{sprint.name}'{extra_where}"
        )

        cache_key = f"ado:{wiql}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        # A WIQL query only returns ids, so the items are fetched in a second request.
        # The query is sent with POST but it does not change anything in Azure DevOps.
        query_result = await self._request("POST", "/wit/wiql?api-version=7.1", {"query": wiql})
        ids = [str(reference["id"]) for reference in query_result.get("workItems") or []]

        work_items: list[Json] = []
        if ids:
            id_list = ",".join(ids)
            # $expand=all includes relations, which is where the design link lives.
            response = await self._request("GET", f"/wit/workitems?ids={id_list}&$expand=all&api-version=7.1")
            work_items = response["value"]

        cache_set(cache_key, work_items)
        return work_items

    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]:
        # Items tagged "history" are finished work seeded for velocity, not sprint stories.
        work_items = await self._work_items(team, sprint, " and [System.Tags] not contains 'history'")

        stories = []
        for work_item in work_items:
            story = map_work_item(work_item, team.key, sprint.key)
            if story is not None:
                stories.append(story)
        return stories

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        closed_items = await self._work_items(team, sprint, " and [System.State] = 'Closed'")

        total = 0.0
        for work_item in closed_items:
            total += float(work_item["fields"].get(POINTS) or 0)
        return total
