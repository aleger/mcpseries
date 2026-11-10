"""Read-only Azure DevOps adapter (WIQL plus work items)."""

import base64
from typing import Any
from urllib.parse import quote

import httpx

from delivery_mcp.adapters.http import TrackerError, cached, read_json, require
from delivery_mcp.adapters.parse import KEY_RE, RELEASE_TAG_PREFIX, html_list_items, split_ado_description
from delivery_mcp.models import Sprint, Story, TeamConfig
from delivery_mcp.settings import get_settings

Json = dict[str, Any]
POINTS = "Microsoft.VSTS.Scheduling.StoryPoints"


def map_work_item(w: Json, team_key: str, sprint_key: str | None) -> Story | None:
    """Map one Azure DevOps User Story to the common Story shape (None if not a seeded story)."""
    f = w["fields"]
    m = KEY_RE.match(str(f.get("System.Title", "")))
    if not m:
        return None
    tags = [t.strip() for t in str(f.get("System.Tags", "")).split(";") if t.strip()]
    description, dependencies = split_ado_description(f.get("System.Description"))
    link = next((r for r in w.get("relations") or [] if r.get("rel") == "Hyperlink"), None)
    owner = next((t[len("owner:") :] for t in tags if t.startswith("owner:")), None)
    release = next((t[len(RELEASE_TAG_PREFIX) :] for t in tags if t.startswith(RELEASE_TAG_PREFIX)), None)
    points = f.get(POINTS)
    return Story(
        key=m[1],
        title=m[2],
        description=description,
        acceptance_criteria=html_list_items(f.get("Microsoft.VSTS.Common.AcceptanceCriteria")),
        story_points=float(points) if isinstance(points, int | float) else None,
        has_ui="ui" in tags,
        design_link=link.get("url") if link else None,
        dependencies=dependencies,
        assignee=owner,
        release_name=release,
        sprint_key=sprint_key,
        status=str(f.get("System.State", "")),
        team_key=team_key,
    )


class AzureDevOpsAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _base(self) -> str:
        s = get_settings()
        org = require(s.ado_org, "ADO_ORG")
        project = quote(require(s.ado_project, "ADO_PROJECT"))
        return f"https://dev.azure.com/{org}/{project}/_apis"

    async def _call(self, method: str, path: str, body: Json | None = None) -> Json:
        pat = get_settings().ado_pat
        secret = require(pat and pat.get_secret_value(), "ADO_PAT")
        auth = "Basic " + base64.b64encode(f":{secret}".encode()).decode()
        async with httpx.AsyncClient(transport=self._transport, timeout=30) as client:
            res = await client.request(
                method, self._base() + path, json=body, headers={"Authorization": auth}
            )
        return read_json(
            res, "Azure DevOps", "ADO_PAT", "needs Work Items (Read) and Project and Team (Read)"
        )

    async def _work_items(self, team: TeamConfig, sprint: Sprint, extra_where: str = "") -> list[Json]:
        """Work items under a team's area path in one sprint iteration. WIQL is read-only."""
        area = (team.azure_devops or {}).get("areaPath")
        if not area:
            raise TrackerError(f"Team {team.key} has no Azure DevOps area path configured.")
        project = require(get_settings().ado_project, "ADO_PROJECT")
        wiql = (
            "select [System.Id] from workitems where [System.TeamProject] = @project "
            "and [System.WorkItemType] = 'User Story' "
            f"and [System.AreaPath] under '{area}' "
            f"and [System.IterationPath] = '{project}\\{sprint.name}'{extra_where}"
        )

        async def load() -> list[Json]:
            res = await self._call("POST", "/wit/wiql?api-version=7.1", {"query": wiql})
            ids = [w["id"] for w in res.get("workItems") or []]
            if not ids:
                return []
            items = await self._call(
                "GET", f"/wit/workitems?ids={','.join(map(str, ids))}&$expand=all&api-version=7.1"
            )
            return items["value"]

        return await cached(f"ado:{wiql}", load)

    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]:
        items = await self._work_items(team, sprint, " and [System.Tags] not contains 'history'")
        return [s for w in items if (s := map_work_item(w, team.key, sprint.key))]

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        items = await self._work_items(team, sprint, " and [System.State] = 'Closed'")
        return sum(float(w["fields"].get(POINTS) or 0) for w in items)
