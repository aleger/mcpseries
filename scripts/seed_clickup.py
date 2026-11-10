"""Builds the Northwind demo (Platform and Data teams) in the ClickUp demo space from data/northwind.json.

Idempotent: folders, lists, tasks, tags, fields and checklists are matched by name or story key and
updated in place. Run by hand.

    uv run python scripts/seed_clickup.py           # create or update
    uv run python scripts/seed_clickup.py --reset   # delete every task in the seeded lists first

Env: CLICKUP_API_TOKEN (write access), CLICKUP_SPACE_ID. Tokens are never printed.
"""

import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from seed_data import SEED, Json, cross_tool_needed_by, need, release_name, sprint_name

BASE = "https://api.clickup.com/api/v2"
RESET = "--reset" in sys.argv
SPACE = need("CLICKUP_SPACE_ID")
HTTP = httpx.Client(headers={"Authorization": need("CLICKUP_API_TOKEN")}, timeout=30)

# Status names the demo wants, with fallbacks. The ClickUp API cannot create or rename space statuses,
# so the closest existing one is used. Adapters read the status *type* (done/closed), not the name.
WANT = {
    "backlog": ["backlog"],
    "ready": ["ready for sprint", "ready for development"],
    "done": ["done", "shipped"],
    "notDone": ["not done", "backlog"],
}
warnings: list[str] = []
summary = {"created": 0, "updated": 0, "deleted": 0}


def api(method: str, path: str, body: Json | None = None) -> Json:
    for _ in range(6):
        res = HTTP.request(method, BASE + path, json=body)
        if res.status_code == 429:
            time.sleep(15)
            continue
        if res.is_error:
            raise RuntimeError(f"{method} {path.split('?')[0]} -> {res.status_code} {res.text[:200]}")
        return res.json() if res.text else {}
    raise RuntimeError(f"{method} {path.split('?')[0]} -> rate limited")


def story_description(s: Json) -> str:
    """The story sentence, a Dependencies section, and a Referenced by section for cross-tool links."""
    parts = [s["description"]]
    if s["dependencies"]:
        parts += ["", "Dependencies:"]
        parts += [
            f"- {d['key']}: {d['description']} (resolved: {str(d['resolved']).lower()})"
            for d in s["dependencies"]
        ]
    refs = cross_tool_needed_by(s)
    if refs:
        parts += ["", "Referenced by:", *(f"- {k} (Azure DevOps) depends on this story" for k in refs)]
    return "\n".join(parts)


def add_checklist(task_id: str, items: list[str]) -> None:
    cl = api("POST", f"/task/{task_id}/checklist", {"name": "Acceptance Criteria"})
    for a in items:
        api("POST", f"/checklist/{cl['checklist']['id']}/checklist_item", {"name": a})


def seed_releases() -> None:
    """Releases list in the space root, one task per release with a due date."""
    lists = api("GET", f"/space/{SPACE}/list?archived=false")["lists"]
    rel = next((x for x in lists if x["name"] == "Releases"), None)
    if rel is None:
        rel = api("POST", f"/space/{SPACE}/list", {"name": "Releases"})
        print("created list Releases")
    existing = api("GET", f"/list/{rel['id']}/task?include_closed=true")["tasks"]
    if RESET:
        for t in existing:
            api("DELETE", f"/task/{t['id']}")
        existing = []
    for r in SEED["releases"]:
        due = int(datetime.fromisoformat(f"{r['date']}T12:00:00+00:00").astimezone(UTC).timestamp() * 1000)
        description = f"{r['scope']}\n\nTeams: {', '.join(r['teams'])}"
        t = next((x for x in existing if x["name"] == r["name"]), None)
        if t:
            api("PUT", f"/task/{t['id']}", {"name": r["name"], "description": description, "due_date": due})
            print(f"updated release {r['name']}")
        else:
            api(
                "POST",
                f"/list/{rel['id']}/task",
                {"name": r["name"], "description": description, "due_date": due, "tags": r["teams"]},
            )
            print(f"created release {r['name']}")


def items_for(team: Json, list_name: str, status: Any) -> list[Json]:
    """Everything that belongs in a list: stories for Sprint 24 and Backlog, history for closed sprints."""
    if list_name in ("Backlog", "Sprint 24"):
        sprint_key = None if list_name == "Backlog" else "sprint-24"
        return [
            {
                "key": s["key"],
                "name": f"{s['key']}: {s['title']}",
                "description": story_description(s),
                "status": status("ready" if sprint_key else "backlog"),
                "points": s["storyPoints"],
                "tags": [
                    *([f"release-{release_name(s['releaseKey'])}"] if s["releaseKey"] else []),
                    *(["ui"] if s["hasUi"] else []),
                ],
                "story": s,
            }
            for s in SEED["stories"]
            if s["teamKey"] == team["key"] and s["sprintKey"] == sprint_key
        ]
    return [
        {
            "key": h["key"],
            "name": f"{h['key']}: {h['title']}",
            "description": "",
            "status": status("done" if h["status"] == "Done" else "notDone"),
            "points": h["storyPoints"],
            "tags": ["history"],
            "story": None,
        }
        for h in SEED["historyStories"]
        if h["teamKey"] == team["key"] and sprint_name(h["sprintKey"]) == list_name
    ]


def seed_list(lst: Json, team: Json, status: Any, task_ids: dict[str, str]) -> None:
    fields = api("GET", f"/list/{lst['id']}/field")["fields"]

    def by(name: str, kind: str) -> str | None:
        return next((f["id"] for f in fields if f["name"] == name and f["type"] == kind), None)

    points_f, design_f, owner_f = (
        by("Story Points", "number"),
        by("Design Link", "url"),
        by("Owner", "short_text"),
    )
    for fid, label in (
        (points_f, '"Story Points" (number)'),
        (design_f, '"Design Link" (url)'),
        (owner_f, '"Owner" (text)'),
    ):
        if not fid:
            warnings.append(f"missing custom field {label}")
    existing = api("GET", f"/list/{lst['id']}/task?include_closed=true&subtasks=true")["tasks"]
    if RESET:
        for t in existing:
            api("DELETE", f"/task/{t['id']}")
            summary["deleted"] += 1
        existing = []

    for item in items_for(team, lst["name"], status):
        story = item["story"]
        task = next((t for t in existing if str(t["name"]).startswith(f"{item['key']}:")), None)
        custom: list[Json] = []
        # Free plans cap custom field uses (60), so only real stories get Story Points as a custom field.
        # History items store points in ClickUp's native points field; the adapter reads either.
        native = None if story else item["points"]
        if story and points_f and item["points"] is not None:
            custom.append({"id": points_f, "value": item["points"]})
        if design_f and story and story["designLink"]:
            custom.append({"id": design_f, "value": story["designLink"]})
        if owner_f and story and story["assignee"]:
            custom.append({"id": owner_f, "value": story["assignee"]})
        has_ac = bool(story and story["acceptanceCriteria"])

        if task is None:
            body: Json = {
                "name": item["name"],
                "description": item["description"],
                "status": item["status"],
                "tags": item["tags"],
                "custom_fields": custom,
            }
            if native is not None:
                body["points"] = native
            task = api("POST", f"/list/{lst['id']}/task", body)
            if has_ac:
                add_checklist(task["id"], story["acceptanceCriteria"])
            summary["created"] += 1
            print(f"created {item['name']}")
        else:
            # Update in place so reruns converge on the seed data.
            body = {"name": item["name"], "description": item["description"], "status": item["status"]}
            if native is not None:
                body["points"] = native
            api("PUT", f"/task/{task['id']}", body)
            have = {t["name"] for t in task["tags"]}
            for tag in (t for t in item["tags"] if t not in have):
                api("POST", f"/task/{task['id']}/tag/{quote(tag, safe='')}")
            # Only write values that differ: free plans cap custom field uses.
            for cf in custom:
                cur = next(
                    (c.get("value") for c in task.get("custom_fields", []) if c["id"] == cf["id"]), None
                )
                if cur is not None and str(cur) == str(cf["value"]):
                    continue
                try:
                    api("POST", f"/task/{task['id']}/field/{cf['id']}", {"value": cf["value"]})
                except RuntimeError as e:
                    if "FIELD_033" not in str(e):
                        raise
                    warnings.append(
                        "ClickUp plan limit on custom field uses reached; some field values were not set"
                    )
            if has_ac and not any(c["name"] == "Acceptance Criteria" for c in task.get("checklists", [])):
                add_checklist(task["id"], story["acceptanceCriteria"])
            summary["updated"] += 1
            print(f"updated {item['name']}")
        task_ids[item["key"]] = task["id"]


def main() -> None:
    have = {str(s["status"]).lower() for s in api("GET", f"/space/{SPACE}")["statuses"]}

    def status(want: str) -> str:
        hit = next((n for n in WANT[want] if n in have), None)
        if not hit:
            raise RuntimeError(f"space has none of the statuses: {', '.join(WANT[want])}")
        if hit != WANT[want][0]:
            warnings.append(f'status "{WANT[want][0]}" not in space; using "{hit}"')
        return hit

    folders = api("GET", f"/space/{SPACE}/folder?archived=false")["folders"]
    task_ids: dict[str, str] = {}  # story key -> task id, for native dependencies
    list_names = [*(s["name"] for s in SEED["sprints"]), "Backlog"]
    for team in (t for t in SEED["teams"] if t["tracker"] == "clickup"):
        folder = next((f for f in folders if f["name"] == team["name"]), None)
        if folder is None:
            folder = api("POST", f"/space/{SPACE}/folder", {"name": team["name"]})
            print(f"created folder {team['name']}")
        lists = api("GET", f"/folder/{folder['id']}/list?archived=false")["lists"]
        for name in list_names:
            if not any(x["name"] == name for x in lists):
                lists.append(api("POST", f"/folder/{folder['id']}/list", {"name": name}))
                print(f"created list {team['name']}/{name}")
        for lst in (x for x in lists if x["name"] in list_names):
            seed_list(lst, team, status, task_ids)

    seed_releases()

    # Native task dependencies between stories that both live in ClickUp.
    for s in SEED["stories"]:
        for d in s["dependencies"]:
            tid, target = task_ids.get(s["key"]), task_ids.get(d["key"])
            if not tid or not target:
                continue
            try:
                api("POST", f"/task/{tid}/dependency", {"depends_on": target})
                print(f"dependency {s['key']} waits on {d['key']}")
            except RuntimeError as e:
                if not any(w in str(e).lower() for w in ("already", "exists")):
                    raise

    print(
        f"\nsummary: {summary['created']} created, {summary['updated']} updated, {summary['deleted']} deleted"
    )
    if warnings:
        print("\nwarnings:\n" + "\n".join(f"- {w}" for w in dict.fromkeys(warnings)), file=sys.stderr)
        print(
            "The ClickUp API cannot create custom fields or statuses. Add missing ones, then rerun.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(str(e))
