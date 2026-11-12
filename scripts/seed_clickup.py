"""Builds the Northwind demo (Platform and Data teams) in the ClickUp demo space from data/northwind.json.

Idempotent: folders, lists, tasks, tags, fields and checklists are matched by name or story key and
updated in place. Run by hand.

    uv run python scripts/seed_clickup.py           # create or update
    uv run python scripts/seed_clickup.py --reset   # delete every task in the seeded lists first

Env: CLICKUP_API_TOKEN (write access), CLICKUP_SPACE_ID. Tokens are never printed.
"""

import sys
import time
from datetime import datetime
from urllib.parse import quote

import httpx
from seed_data import SEED, Json, cross_tool_needed_by, need, release_and_ui_tags, sprint_name

BASE = "https://api.clickup.com/api/v2"
RESET = "--reset" in sys.argv
SPACE = need("CLICKUP_SPACE_ID")
HTTP = httpx.Client(headers={"Authorization": need("CLICKUP_API_TOKEN")}, timeout=30)

RATE_LIMIT_RETRIES = 6
RATE_LIMIT_WAIT_SECONDS = 15

# Status names the demo wants, with fallbacks. The ClickUp API cannot create or rename space statuses,
# so the closest existing one is used. Adapters read the status *type* (done/closed), not the name.
WANTED_STATUSES = {
    "backlog": ["backlog"],
    "ready": ["ready for sprint", "ready for development"],
    "done": ["done", "shipped"],
    "notDone": ["not done", "backlog"],
}

# Custom fields the lists need. They have to exist already because the API cannot create them.
STORY_POINTS_FIELD = ("Story Points", "number", '"Story Points" (number)')
DESIGN_LINK_FIELD = ("Design Link", "url", '"Design Link" (url)')
OWNER_FIELD = ("Owner", "short_text", '"Owner" (text)')

# ClickUp's error code for "this plan has used up its custom field uses".
FIELD_USAGE_LIMIT_ERROR = "FIELD_033"

warnings: list[str] = []
summary = {"created": 0, "updated": 0, "deleted": 0}


def api(method: str, path: str, body: Json | None = None) -> Json:
    """Call the ClickUp API, waiting and retrying when it answers 429 (rate limited)."""
    # The query string is left out of error messages to keep them short.
    endpoint = path.split("?")[0]

    for _attempt in range(RATE_LIMIT_RETRIES):
        response = HTTP.request(method, BASE + path, json=body)
        if response.status_code == 429:
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
            continue
        if response.is_error:
            raise RuntimeError(f"{method} {endpoint} -> {response.status_code} {response.text[:200]}")
        if not response.text:
            return {}
        return response.json()

    raise RuntimeError(f"{method} {endpoint} -> rate limited")


def status_name(wanted: str, space_statuses: set[str]) -> str:
    """The space status to use for one of the WANTED_STATUSES: the preferred name, or the first fallback."""
    candidates = WANTED_STATUSES[wanted]
    preferred = candidates[0]

    for candidate in candidates:
        if candidate in space_statuses:
            if candidate != preferred:
                warnings.append(f'status "{preferred}" not in space; using "{candidate}"')
            return candidate

    raise RuntimeError(f"space has none of the statuses: {', '.join(candidates)}")


def story_description(story: Json) -> str:
    """The story sentence, a Dependencies section, and a Referenced by section for cross-tool links."""
    lines = [story["description"]]

    if story["dependencies"]:
        lines += ["", "Dependencies:"]
        for dependency in story["dependencies"]:
            resolved = str(dependency["resolved"]).lower()
            lines.append(f"- {dependency['key']}: {dependency['description']} (resolved: {resolved})")

    # ClickUp cannot link to an Azure DevOps item, so stories that Mobile depends on say so in text.
    dependents = cross_tool_needed_by(story)
    if dependents:
        lines += ["", "Referenced by:"]
        for dependent_key in dependents:
            lines.append(f"- {dependent_key} (Azure DevOps) depends on this story")

    return "\n".join(lines)


def add_checklist(task_id: str, items: list[str]) -> None:
    created = api("POST", f"/task/{task_id}/checklist", {"name": "Acceptance Criteria"})
    checklist_id = created["checklist"]["id"]
    for item in items:
        api("POST", f"/checklist/{checklist_id}/checklist_item", {"name": item})


def due_date_ms(date: str) -> int:
    """ClickUp due dates are Unix milliseconds. Noon UTC keeps the same calendar date in most time zones."""
    noon_utc = datetime.fromisoformat(f"{date}T12:00:00+00:00")
    return int(noon_utc.timestamp() * 1000)


def seed_releases() -> None:
    """Releases list in the space root, one task per release with a due date."""
    lists = api("GET", f"/space/{SPACE}/list?archived=false")["lists"]
    releases_list = None
    for candidate in lists:
        if candidate["name"] == "Releases":
            releases_list = candidate
            break
    if releases_list is None:
        releases_list = api("POST", f"/space/{SPACE}/list", {"name": "Releases"})
        print("created list Releases")

    existing = api("GET", f"/list/{releases_list['id']}/task?include_closed=true")["tasks"]
    if RESET:
        for task in existing:
            api("DELETE", f"/task/{task['id']}")
        existing = []
    existing_by_name = {}
    for task in existing:
        existing_by_name.setdefault(task["name"], task)

    for release in SEED["releases"]:
        name = release["name"]
        due_date = due_date_ms(release["date"])
        description = f"{release['scope']}\n\nTeams: {', '.join(release['teams'])}"

        task = existing_by_name.get(name)
        if task:
            api(
                "PUT", f"/task/{task['id']}", {"name": name, "description": description, "due_date": due_date}
            )
            print(f"updated release {name}")
        else:
            api(
                "POST",
                f"/list/{releases_list['id']}/task",
                {"name": name, "description": description, "due_date": due_date, "tags": release["teams"]},
            )
            print(f"created release {name}")


def story_items(team: Json, sprint_key: str | None, space_statuses: set[str]) -> list[Json]:
    """The team's stories in one sprint, or its backlog when `sprint_key` is None."""
    items = []
    for story in SEED["stories"]:
        if story["teamKey"] != team["key"] or story["sprintKey"] != sprint_key:
            continue
        items.append(
            {
                "key": story["key"],
                "name": f"{story['key']}: {story['title']}",
                "description": story_description(story),
                "status": status_name("ready" if sprint_key else "backlog", space_statuses),
                "points": story["storyPoints"],
                "tags": release_and_ui_tags(story),
                "story": story,
            }
        )
    return items


def history_items(team: Json, list_name: str, space_statuses: set[str]) -> list[Json]:
    """Finished work from a closed sprint. It only exists so the team has a velocity."""
    items = []
    for history in SEED["historyStories"]:
        if history["teamKey"] != team["key"] or sprint_name(history["sprintKey"]) != list_name:
            continue
        wanted_status = "done" if history["status"] == "Done" else "notDone"
        items.append(
            {
                "key": history["key"],
                "name": f"{history['key']}: {history['title']}",
                "description": "",
                "status": status_name(wanted_status, space_statuses),
                "points": history["storyPoints"],
                "tags": ["history"],
                "story": None,
            }
        )
    return items


def items_for(team: Json, list_name: str, space_statuses: set[str]) -> list[Json]:
    """Everything that belongs in a list: stories for Sprint 24 and Backlog, history for closed sprints."""
    if list_name == "Backlog":
        return story_items(team, None, space_statuses)
    if list_name == "Sprint 24":
        return story_items(team, "sprint-24", space_statuses)
    return history_items(team, list_name, space_statuses)


def custom_field_id(fields: list[Json], field: tuple[str, str, str]) -> str | None:
    """Id of a custom field on a list, matched by name and type. Records a warning when it is missing."""
    name, kind, label = field
    for candidate in fields:
        if candidate["name"] == name and candidate["type"] == kind:
            return candidate["id"]
    warnings.append(f"missing custom field {label}")
    return None


def custom_field_values(item: Json, field_ids: dict[str, str | None]) -> list[Json]:
    """Custom field values to write for an item. History items get none."""
    story = item["story"]
    if not story:
        return []

    values: list[Json] = []
    if field_ids["points"] and item["points"] is not None:
        values.append({"id": field_ids["points"], "value": item["points"]})
    if field_ids["design"] and story["designLink"]:
        values.append({"id": field_ids["design"], "value": story["designLink"]})
    if field_ids["owner"] and story["assignee"]:
        values.append({"id": field_ids["owner"], "value": story["assignee"]})
    return values


def create_task(list_id: str, item: Json, custom_values: list[Json]) -> Json:
    body: Json = {
        "name": item["name"],
        "description": item["description"],
        "status": item["status"],
        "tags": item["tags"],
        "custom_fields": custom_values,
    }
    if item["story"] is None and item["points"] is not None:
        body["points"] = item["points"]
    task = api("POST", f"/list/{list_id}/task", body)

    story = item["story"]
    if story and story["acceptanceCriteria"]:
        add_checklist(task["id"], story["acceptanceCriteria"])
    return task


def update_task(task: Json, item: Json, custom_values: list[Json]) -> None:
    """Bring an existing task in line with the seed data, so reruns converge on it."""
    task_id = task["id"]

    body: Json = {"name": item["name"], "description": item["description"], "status": item["status"]}
    if item["story"] is None and item["points"] is not None:
        body["points"] = item["points"]
    api("PUT", f"/task/{task_id}", body)

    existing_tags = {tag["name"] for tag in task["tags"]}
    for tag in item["tags"]:
        if tag not in existing_tags:
            api("POST", f"/task/{task_id}/tag/{quote(tag, safe='')}")

    # Only write values that differ: free plans cap custom field uses.
    current_values = {}
    for field in task.get("custom_fields", []):
        current_values.setdefault(field["id"], field.get("value"))
    for custom_value in custom_values:
        current = current_values.get(custom_value["id"])
        if current is not None and str(current) == str(custom_value["value"]):
            continue
        try:
            api("POST", f"/task/{task_id}/field/{custom_value['id']}", {"value": custom_value["value"]})
        except RuntimeError as error:
            if FIELD_USAGE_LIMIT_ERROR not in str(error):
                raise
            warnings.append("ClickUp plan limit on custom field uses reached; some field values were not set")

    story = item["story"]
    if story and story["acceptanceCriteria"]:
        checklist_names = [checklist["name"] for checklist in task.get("checklists", [])]
        if "Acceptance Criteria" not in checklist_names:
            add_checklist(task_id, story["acceptanceCriteria"])


def seed_list(seeded_list: Json, team: Json, space_statuses: set[str], task_ids: dict[str, str]) -> None:
    """Create or update every task that belongs in one list, recording each task id by story key."""
    list_id = seeded_list["id"]

    fields = api("GET", f"/list/{list_id}/field")["fields"]
    field_ids = {
        "points": custom_field_id(fields, STORY_POINTS_FIELD),
        "design": custom_field_id(fields, DESIGN_LINK_FIELD),
        "owner": custom_field_id(fields, OWNER_FIELD),
    }

    existing = api("GET", f"/list/{list_id}/task?include_closed=true&subtasks=true")["tasks"]
    if RESET:
        for task in existing:
            api("DELETE", f"/task/{task['id']}")
            summary["deleted"] += 1
        existing = []

    for item in items_for(team, seeded_list["name"], space_statuses):
        # Free plans cap custom field uses (60), so only real stories get Story Points as a custom field.
        # History items store points in ClickUp's native points field; the adapter reads either.
        custom_values = custom_field_values(item, field_ids)

        task = None
        for candidate in existing:
            if str(candidate["name"]).startswith(f"{item['key']}:"):
                task = candidate
                break

        if task is None:
            task = create_task(list_id, item, custom_values)
            summary["created"] += 1
            print(f"created {item['name']}")
        else:
            update_task(task, item, custom_values)
            summary["updated"] += 1
            print(f"updated {item['name']}")

        task_ids[item["key"]] = task["id"]


def seed_team(team: Json, folders: list[Json], space_statuses: set[str], task_ids: dict[str, str]) -> None:
    """One folder per team, holding a list per sprint and a Backlog list."""
    folder = None
    for candidate in folders:
        if candidate["name"] == team["name"]:
            folder = candidate
            break
    if folder is None:
        folder = api("POST", f"/space/{SPACE}/folder", {"name": team["name"]})
        print(f"created folder {team['name']}")

    list_names = [sprint["name"] for sprint in SEED["sprints"]] + ["Backlog"]
    lists = api("GET", f"/folder/{folder['id']}/list?archived=false")["lists"]
    existing_names = {existing["name"] for existing in lists}
    for name in list_names:
        if name not in existing_names:
            lists.append(api("POST", f"/folder/{folder['id']}/list", {"name": name}))
            print(f"created list {team['name']}/{name}")

    # The folder may hold other lists. Only the ones this script owns are touched.
    for seeded_list in lists:
        if seeded_list["name"] in list_names:
            seed_list(seeded_list, team, space_statuses, task_ids)


def seed_dependencies(task_ids: dict[str, str]) -> None:
    """Native task dependencies between stories that both live in ClickUp."""
    for story in SEED["stories"]:
        for dependency in story["dependencies"]:
            task_id = task_ids.get(story["key"])
            depends_on_id = task_ids.get(dependency["key"])
            if not task_id or not depends_on_id:
                continue
            try:
                api("POST", f"/task/{task_id}/dependency", {"depends_on": depends_on_id})
                print(f"dependency {story['key']} waits on {dependency['key']}")
            except RuntimeError as error:
                # A rerun finds the dependency already in place, which is fine.
                message = str(error).lower()
                if "already" not in message and "exists" not in message:
                    raise


def print_summary() -> None:
    print(
        f"\nsummary: {summary['created']} created, {summary['updated']} updated, {summary['deleted']} deleted"
    )
    if not warnings:
        return

    # The same warning can be recorded once per list. Print each one once, in the order first seen.
    unique_warnings = list(dict.fromkeys(warnings))
    warning_lines = "\n".join(f"- {warning}" for warning in unique_warnings)
    print("\nwarnings:\n" + warning_lines, file=sys.stderr)
    print(
        "The ClickUp API cannot create custom fields or statuses. Add missing ones, then rerun.",
        file=sys.stderr,
    )


def main() -> None:
    space = api("GET", f"/space/{SPACE}")
    space_statuses = {str(status["status"]).lower() for status in space["statuses"]}

    folders = api("GET", f"/space/{SPACE}/folder?archived=false")["folders"]
    task_ids: dict[str, str] = {}  # story key -> task id, for native dependencies
    for team in SEED["teams"]:
        if team["tracker"] == "clickup":
            seed_team(team, folders, space_statuses, task_ids)

    seed_releases()
    seed_dependencies(task_ids)
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        sys.exit(str(error))
