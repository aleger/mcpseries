"""Builds the Northwind demo (Mobile team) in the Azure DevOps demo project from data/northwind.json.

Targets the Agile process: User Story, Story Points, Acceptance Criteria field. Idempotent: area path,
iterations, team settings and work items are matched by name or story key, compared with the seed data,
and written only when they differ. A rerun against a finished workspace changes nothing.

    uv run python scripts/seed_ado.py            # create or update what differs
    uv run python scripts/seed_ado.py --check    # read only: report what would change, exit 1 if anything
    uv run python scripts/seed_ado.py --reset    # delete all Mobile work items first (recycle bin)

Env: ADO_ORG, ADO_PROJECT, ADO_PAT (read and write). Tokens are never printed.
"""

import base64
import re
import sys
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from seed_data import SEED, Json, need, release_and_ui_tags, sprint_name

ORG = need("ADO_ORG")
PROJECT = need("ADO_PROJECT")
BASE = f"https://dev.azure.com/{ORG}/{quote(PROJECT)}/_apis"
# A PAT is sent as HTTP Basic auth with an empty user name.
AUTH = "Basic " + base64.b64encode(f":{need('ADO_PAT')}".encode()).decode()
RESET = "--reset" in sys.argv
CHECK = "--check" in sys.argv
HTTP = httpx.Client(timeout=30)
API_VERSION = "api-version=7.1"
# Work item writes take a JSON Patch document, which has its own content type.
PATCH_JSON = "application/json-patch+json"
BATCH_SIZE = 100

TITLE = "System.Title"
DESCRIPTION = "System.Description"
ACCEPTANCE_CRITERIA = "Microsoft.VSTS.Common.AcceptanceCriteria"
STORY_POINTS = "Microsoft.VSTS.Scheduling.StoryPoints"
AREA_PATH = "System.AreaPath"
ITERATION_PATH = "System.IterationPath"
STATE = "System.State"
TAGS = "System.Tags"

summary = {"created": 0, "updated": 0, "unchanged": 0, "deleted": 0}


class AdoError(RuntimeError):
    pass


def api(method: str, path: str, body: Any = None, content_type: str = "application/json") -> tuple[int, Json]:
    """Call the Azure DevOps API. Returns the status and JSON body; a 404 is returned, not raised."""
    headers = {"Authorization": AUTH, "Content-Type": content_type}
    response = HTTP.request(method, BASE + path, json=body, headers=headers)
    response_type = response.headers.get("content-type", "")

    # A rejected PAT gets status 203 and an HTML sign-in page instead of an error status.
    if response.status_code == 203 or "html" in response_type:
        raise AdoError("Azure DevOps rejected the credentials (HTML sign-in page). Check ADO_PAT.")

    # Callers use 404 to tell that something does not exist yet, so only other errors are raised.
    if response.status_code >= 400 and response.status_code != 404:
        endpoint = path.split("?")[0]
        raise AdoError(f"{method} {endpoint} -> {response.status_code} {response.text[:250]}")

    data: Json = {}
    if response.text and "json" in response_type:
        data = response.json()
    return response.status_code, data


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def story_description(story: Json) -> str:
    """The story sentence as a paragraph, then a Dependencies list the adapter parses back out."""
    html = f"<p>{escape_html(story['description'])}</p>"
    if not story["dependencies"]:
        return html

    list_items = ""
    for dependency in story["dependencies"]:
        key = escape_html(dependency["key"])
        description = escape_html(dependency["description"])
        resolved = str(dependency["resolved"]).lower()
        list_items += f"<li>{key}: {description} (resolved: {resolved})</li>"
    return f"{html}<h3>Dependencies</h3><ul>{list_items}</ul>"


def acceptance_html(criteria: list[str]) -> str:
    if not criteria:
        return ""
    list_items = "".join(f"<li>{escape_html(criterion)}</li>" for criterion in criteria)
    return f"<ul>{list_items}</ul>"


def same_date(first: str | None, second: str | None) -> bool:
    """Compare two ISO timestamps as dates, so "...Z" and "...+00:00" count as equal."""
    if not first or not second:
        return False
    return datetime.fromisoformat(first) == datetime.fromisoformat(second)


def ensure_node(kind: str, name: str, attributes: Json | None = None) -> str | None:
    """Create the classification node if missing; keep sprint dates in sync. Returns its identifier."""
    path = f"/wit/classificationnodes/{kind}/{quote(name)}?{API_VERSION}"
    status, node = api("GET", path)

    if status == 404:
        if CHECK:
            print(f"would create {kind} {name}")
            return None
        _, node = api(
            "POST",
            f"/wit/classificationnodes/{kind}?{API_VERSION}",
            {"name": name, "attributes": attributes},
        )
        print(f"created {kind} {name}")
        return node["identifier"]

    # Areas have no attributes. Iterations carry the sprint's start and finish dates.
    if attributes:
        current = node.get("attributes") or {}
        dates_match = same_date(current.get("startDate"), attributes["startDate"]) and same_date(
            current.get("finishDate"), attributes["finishDate"]
        )
        if not dates_match:
            if CHECK:
                print(f"would update {kind} {name}")
            else:
                api("PATCH", path, {"name": name, "attributes": attributes})
                print(f"updated {kind} {name}")

    return node["identifier"]


def story_item(story: Json) -> Json:
    # Backlog stories have no sprint, so they sit at the project's root iteration.
    iteration = PROJECT
    if story["sprintKey"]:
        iteration = f"{PROJECT}\\{sprint_name(story['sprintKey'])}"

    return {
        "key": story["key"],
        "title": f"{story['key']}: {story['title']}",
        "description": story_description(story),
        "acceptance": acceptance_html(story["acceptanceCriteria"]),
        "points": story["storyPoints"],
        "iteration": iteration,
        "state": "New",
        "tags": [*release_and_ui_tags(story), f"owner:{story['assignee']}"],
        "designLink": story["designLink"],
    }


def history_item(history: Json) -> Json:
    """Finished work from a closed sprint. It only exists so the team has a velocity."""
    return {
        "key": history["key"],
        "title": f"{history['key']}: {history['title']}",
        "description": "",
        "acceptance": "",
        "points": history["storyPoints"],
        "iteration": f"{PROJECT}\\{sprint_name(history['sprintKey'])}",
        "state": "Closed" if history["status"] == "Done" else "Active",
        "tags": ["northwind", "history"],
        "designLink": None,
    }


def build_items(team: Json) -> list[Json]:
    """Every work item the team should have: its stories first, then its history."""
    items = []
    for story in SEED["stories"]:
        if story["teamKey"] == team["key"]:
            items.append(story_item(story))
    for history in SEED["historyStories"]:
        if history["teamKey"] == team["key"]:
            items.append(history_item(history))
    return items


def seed_fields(item: Json, area: str) -> Json:
    """The plain field values a work item should have. State and tags are handled separately."""
    return {
        TITLE: item["title"],
        DESCRIPTION: item["description"],
        ACCEPTANCE_CRITERIA: item["acceptance"],
        STORY_POINTS: item["points"],
        AREA_PATH: area,
        ITERATION_PATH: item["iteration"],
    }


def comparable(value: Any) -> Any:
    """Reduce a field value to a form where the seed value and the saved value can be compared."""
    # ADO normalizes HTML whitespace on save (for example a space before a closing tag).
    if isinstance(value, str):
        value = re.sub(r"\s+(?=<)", "", value).strip()
    # An empty value in the seed and a field ADO does not return mean the same thing.
    return value or None


def differing_fields(fields: Json, item: Json, area: str) -> list[str]:
    """Names of the fields on an existing work item that do not match the seed item."""
    wanted = seed_fields(item, area)
    wanted[STATE] = item["state"]

    differing = []
    for name, wanted_value in wanted.items():
        if comparable(fields.get(name)) != comparable(wanted_value):
            differing.append(name)

    # ADO returns tags as one "a; b; c" string and may reorder them, so compare as sets.
    current_tags = set()
    for tag in str(fields.get(TAGS, "")).split(";"):
        if tag.strip():
            current_tags.add(tag.strip())
    if current_tags != set(item["tags"]):
        differing.append(TAGS)

    return differing


def state_op(state: str) -> Json:
    return {"op": "add", "path": f"/fields/{STATE}", "value": state}


def field_ops(item: Json, area: str, op: str) -> list[Json]:
    """JSON Patch operations that set every seeded field except the state."""
    values = seed_fields(item, area)
    values[TAGS] = "; ".join(item["tags"])

    operations = []
    for name, value in values.items():
        operations.append({"op": op, "path": f"/fields/{name}", "value": value})
    return operations


def create(item: Json, area: str) -> None:
    field_operations = field_ops(item, area, "add")
    link_operations = []
    if item["designLink"]:
        link_operations.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {"rel": "Hyperlink", "url": item["designLink"], "attributes": {"comment": "Design"}},
            }
        )
    url = f"/wit/workitems/$User%20Story?{API_VERSION}"

    try:
        operations = [*field_operations, state_op(item["state"]), *link_operations]
        api("POST", url, operations, PATCH_JSON)
        return
    except AdoError:
        if item["state"] == "New":
            raise

    # Some states cannot be set on create: create as New, then move. Closed is reached through Active.
    _, created = api("POST", url, [*field_operations, *link_operations], PATCH_JSON)
    steps = ["Active", "Closed"] if item["state"] == "Closed" else [item["state"]]
    for state in steps:
        api("PATCH", f"/wit/workitems/{created['id']}?{API_VERSION}", [state_op(state)], PATCH_JSON)


def existing_items(area: str) -> dict[str, Json]:
    """Work items under the area, keyed by story key, with their current fields."""
    query = (
        "select [System.Id] from workitems where [System.TeamProject] = @project "
        f"and [System.AreaPath] under '{area}'"
    )
    _, result = api("POST", f"/wit/wiql?{API_VERSION}", {"query": query})
    ids = [str(reference["id"]) for reference in result.get("workItems", [])]

    # The query only returns ids. The items themselves are fetched in batches.
    found: dict[str, Json] = {}
    for start in range(0, len(ids), BATCH_SIZE):
        id_list = ",".join(ids[start : start + BATCH_SIZE])
        _, batch = api("GET", f"/wit/workitems?ids={id_list}&{API_VERSION}")
        for work_item in batch["value"]:
            story_key = str(work_item["fields"][TITLE]).split(":")[0]
            found[story_key] = work_item
    return found


def sync_iterations() -> None:
    """Sprints 22 to 24, with dates, selected for the default project team so they show on its board."""
    _, team_iterations = api("GET", f"/work/teamsettings/iterations?{API_VERSION}")
    selected_ids = {iteration["id"] for iteration in team_iterations["value"]}

    for sprint in SEED["sprints"]:
        dates = {"startDate": f"{sprint['start']}T00:00:00Z", "finishDate": f"{sprint['end']}T00:00:00Z"}
        node_id = ensure_node("iterations", sprint["name"], dates)
        if node_id in selected_ids:
            continue
        # node_id is None when --check found the iteration missing, so there is nothing to select yet.
        if CHECK or node_id is None:
            print(f"would select iteration {sprint['name']} for the team")
        else:
            api("POST", f"/work/teamsettings/iterations?{API_VERSION}", {"id": node_id})
            print(f"selected iteration {sprint['name']} for the team")


def sync_team_area() -> None:
    """Team area = project root with sub-areas included, so Mobile items show on the team backlog."""
    wanted_values = [{"value": PROJECT, "includeChildren": True}]

    _, current = api("GET", f"/work/teamsettings/teamfieldvalues?{API_VERSION}")
    if current.get("defaultValue") == PROJECT and current.get("values") == wanted_values:
        return

    if CHECK:
        print("would update team area settings")
    else:
        api(
            "PATCH",
            f"/work/teamsettings/teamfieldvalues?{API_VERSION}",
            {"defaultValue": PROJECT, "values": wanted_values},
        )
        print("updated team area settings")


def sync_work_items(team: Json, area: str) -> None:
    """Create missing work items and update the ones that differ from the seed data."""
    existing = existing_items(area)
    if RESET and not CHECK:
        for work_item in existing.values():
            api("DELETE", f"/wit/workitems/{work_item['id']}?{API_VERSION}")  # recycle bin, restorable
            summary["deleted"] += 1
        existing = {}

    for item in build_items(team):
        work_item = existing.get(item["key"])

        if work_item is None:
            if CHECK:
                print(f"would create {item['title']}")
            else:
                create(item, area)
                print(f"created {item['title']}")
            summary["created"] += 1
            continue

        differing = differing_fields(work_item["fields"], item, area)
        if not differing:
            summary["unchanged"] += 1
            continue

        if CHECK:
            print(f"would update {item['title']} ({', '.join(differing)})")
        else:
            operations = [*field_ops(item, area, "replace"), state_op(item["state"])]
            api("PATCH", f"/wit/workitems/{work_item['id']}?{API_VERSION}", operations, PATCH_JSON)
            print(f"updated {item['title']} ({', '.join(differing)})")
        summary["updated"] += 1


def main() -> None:
    team = next(team for team in SEED["teams"] if team["tracker"] == "azure-devops")
    area = f"{PROJECT}\\{team['name']}"
    ensure_node("areas", team["name"])

    sync_iterations()
    sync_team_area()
    # The MOB-210 -> DAT-307 dependency crosses trackers, so it stays a reference string in the description.
    sync_work_items(team, area)

    print(
        f"\nsummary: {summary['created']} created, {summary['updated']} updated, "
        f"{summary['unchanged']} unchanged, {summary['deleted']} deleted"
    )
    if CHECK and (summary["created"] or summary["updated"]):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except AdoError as error:
        sys.exit(str(error))
