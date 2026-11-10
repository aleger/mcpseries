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
from seed_data import SEED, Json, need, release_name, sprint_name

ORG, PROJECT = need("ADO_ORG"), need("ADO_PROJECT")
BASE = f"https://dev.azure.com/{ORG}/{quote(PROJECT)}/_apis"
AUTH = "Basic " + base64.b64encode(f":{need('ADO_PAT')}".encode()).decode()
RESET, CHECK = "--reset" in sys.argv, "--check" in sys.argv
HTTP = httpx.Client(timeout=30)
V = "api-version=7.1"
PATCH_JSON = "application/json-patch+json"
summary = {"created": 0, "updated": 0, "unchanged": 0, "deleted": 0}


class AdoError(RuntimeError):
    pass


def api(method: str, path: str, body: Any = None, content_type: str = "application/json") -> tuple[int, Json]:
    res = HTTP.request(
        method, BASE + path, json=body, headers={"Authorization": AUTH, "Content-Type": content_type}
    )
    if res.status_code == 203 or "html" in res.headers.get("content-type", ""):
        raise AdoError("Azure DevOps rejected the credentials (HTML sign-in page). Check ADO_PAT.")
    data: Json = res.json() if res.text and "json" in res.headers.get("content-type", "") else {}
    if res.status_code >= 400 and res.status_code != 404:
        raise AdoError(f"{method} {path.split('?')[0]} -> {res.status_code} {res.text[:250]}")
    return res.status_code, data


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;")


def story_description(s: Json) -> str:
    deps = ""
    if s["dependencies"]:
        li = "".join(
            f"<li>{esc(d['key'])}: {esc(d['description'])} (resolved: {str(d['resolved']).lower()})</li>"
            for d in s["dependencies"]
        )
        deps = f"<h3>Dependencies</h3><ul>{li}</ul>"
    return f"<p>{esc(s['description'])}</p>{deps}"


def acceptance_html(items: list[str]) -> str:
    return f"<ul>{''.join(f'<li>{esc(a)}</li>' for a in items)}</ul>" if items else ""


def same_date(a: str | None, b: str | None) -> bool:
    return bool(a and b) and datetime.fromisoformat(a) == datetime.fromisoformat(b)


def ensure_node(kind: str, name: str, attributes: Json | None = None) -> str | None:
    """Create the classification node if missing; keep sprint dates in sync. Returns its identifier."""
    path = f"/wit/classificationnodes/{kind}/{quote(name)}?{V}"
    status, node = api("GET", path)
    if status == 404:
        if CHECK:
            print(f"would create {kind} {name}")
            return None
        _, node = api(
            "POST", f"/wit/classificationnodes/{kind}?{V}", {"name": name, "attributes": attributes}
        )
        print(f"created {kind} {name}")
        return node["identifier"]
    if attributes:
        have = node.get("attributes") or {}
        if not (
            same_date(have.get("startDate"), attributes["startDate"])
            and same_date(have.get("finishDate"), attributes["finishDate"])
        ):
            if CHECK:
                print(f"would update {kind} {name}")
            else:
                api("PATCH", path, {"name": name, "attributes": attributes})
                print(f"updated {kind} {name}")
    return node["identifier"]


def build_items(team: Json) -> list[Json]:
    stories = [
        {
            "key": s["key"],
            "title": f"{s['key']}: {s['title']}",
            "description": story_description(s),
            "acceptance": acceptance_html(s["acceptanceCriteria"]),
            "points": s["storyPoints"],
            "iteration": f"{PROJECT}\\{sprint_name(s['sprintKey'])}" if s["sprintKey"] else PROJECT,
            "state": "New",
            "tags": [
                *([f"release-{release_name(s['releaseKey'])}"] if s["releaseKey"] else []),
                *(["ui"] if s["hasUi"] else []),
                f"owner:{s['assignee']}",
            ],
            "designLink": s["designLink"],
        }
        for s in SEED["stories"]
        if s["teamKey"] == team["key"]
    ]
    history = [
        {
            "key": h["key"],
            "title": f"{h['key']}: {h['title']}",
            "description": "",
            "acceptance": "",
            "points": h["storyPoints"],
            "iteration": f"{PROJECT}\\{sprint_name(h['sprintKey'])}",
            "state": "Closed" if h["status"] == "Done" else "Active",
            "tags": ["northwind", "history"],
            "designLink": None,
        }
        for h in SEED["historyStories"]
        if h["teamKey"] == team["key"]
    ]
    return stories + history


def norm(value: Any) -> Any:
    """ADO normalizes HTML whitespace on save (for example a space before a closing tag)."""
    return re.sub(r"\s+(?=<)", "", value).strip() if isinstance(value, str) else value


def differs(fields: Json, it: Json, area: str) -> list[str]:
    """Names of the fields on an existing work item that do not match the seed item."""
    want = {
        "System.Title": it["title"],
        "System.Description": it["description"],
        "Microsoft.VSTS.Common.AcceptanceCriteria": it["acceptance"],
        "Microsoft.VSTS.Scheduling.StoryPoints": it["points"],
        "System.AreaPath": area,
        "System.IterationPath": it["iteration"],
        "System.State": it["state"],
    }
    bad = [k for k, v in want.items() if (norm(fields.get(k)) or None) != (norm(v) or None)]
    have_tags = {t.strip() for t in str(fields.get("System.Tags", "")).split(";") if t.strip()}
    if have_tags != set(it["tags"]):
        bad.append("System.Tags")
    return bad


def patch_ops(it: Json, area: str, op: str) -> list[Json]:
    return [
        {"op": op, "path": f"/fields/{k}", "value": v}
        for k, v in {
            "System.Title": it["title"],
            "System.Description": it["description"],
            "Microsoft.VSTS.Common.AcceptanceCriteria": it["acceptance"],
            "Microsoft.VSTS.Scheduling.StoryPoints": it["points"],
            "System.AreaPath": area,
            "System.IterationPath": it["iteration"],
            "System.Tags": "; ".join(it["tags"]),
        }.items()
    ]


def create(it: Json, area: str) -> None:
    ops = [*patch_ops(it, area, "add"), {"op": "add", "path": "/fields/System.State", "value": it["state"]}]
    if it["designLink"]:
        ops.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {"rel": "Hyperlink", "url": it["designLink"], "attributes": {"comment": "Design"}},
            }
        )
    url = f"/wit/workitems/$User%20Story?{V}"
    try:
        _, made = api("POST", url, ops, PATCH_JSON)
    except AdoError:
        if it["state"] == "New":
            raise
        # Some states cannot be set on create: create as New, then move.
        base = [o for o in ops if o["path"] != "/fields/System.State"]
        _, made = api("POST", url, base, PATCH_JSON)
        for state in ["Active", "Closed"] if it["state"] == "Closed" else [it["state"]]:
            api(
                "PATCH",
                f"/wit/workitems/{made['id']}?{V}",
                [{"op": "add", "path": "/fields/System.State", "value": state}],
                PATCH_JSON,
            )


def existing_items(area: str) -> dict[str, Json]:
    """Work items under the area, keyed by story key, with their current fields."""
    _, wiql = api(
        "POST",
        f"/wit/wiql?{V}",
        {
            "query": "select [System.Id] from workitems where [System.TeamProject] = @project "
            f"and [System.AreaPath] under '{area}'"
        },
    )
    ids = [w["id"] for w in wiql.get("workItems", [])]
    found: dict[str, Json] = {}
    for i in range(0, len(ids), 100):
        _, batch = api("GET", f"/wit/workitems?ids={','.join(map(str, ids[i : i + 100]))}&{V}")
        for w in batch["value"]:
            found[str(w["fields"]["System.Title"]).split(":")[0]] = w
    return found


def main() -> None:
    team = next(t for t in SEED["teams"] if t["tracker"] == "azure-devops")
    area = f"{PROJECT}\\{team['name']}"
    ensure_node("areas", team["name"])

    # Sprints 22 to 24, with dates, selected for the default project team so they show on its board.
    _, sel = api("GET", f"/work/teamsettings/iterations?{V}")
    selected = {i["id"] for i in sel["value"]}
    for s in SEED["sprints"]:
        node_id = ensure_node(
            "iterations",
            s["name"],
            {"startDate": f"{s['start']}T00:00:00Z", "finishDate": f"{s['end']}T00:00:00Z"},
        )
        if node_id not in selected:
            if CHECK or node_id is None:
                print(f"would select iteration {s['name']} for the team")
            else:
                api("POST", f"/work/teamsettings/iterations?{V}", {"id": node_id})
                print(f"selected iteration {s['name']} for the team")

    # Team area = project root with sub-areas included, so Mobile items show on the team backlog.
    _, tfv = api("GET", f"/work/teamsettings/teamfieldvalues?{V}")
    if tfv.get("defaultValue") != PROJECT or tfv.get("values") != [
        {"value": PROJECT, "includeChildren": True}
    ]:
        if CHECK:
            print("would update team area settings")
        else:
            api(
                "PATCH",
                f"/work/teamsettings/teamfieldvalues?{V}",
                {"defaultValue": PROJECT, "values": [{"value": PROJECT, "includeChildren": True}]},
            )
            print("updated team area settings")

    existing = existing_items(area)
    if RESET and not CHECK:
        for w in existing.values():
            api("DELETE", f"/wit/workitems/{w['id']}?{V}")  # recycle bin, restorable
            summary["deleted"] += 1
        existing = {}

    for it in build_items(team):
        w = existing.get(it["key"])
        if w is None:
            if CHECK:
                print(f"would create {it['title']}")
            else:
                create(it, area)
                print(f"created {it['title']}")
            summary["created"] += 1
            continue
        bad = differs(w["fields"], it, area)
        if not bad:
            summary["unchanged"] += 1
            continue
        if CHECK:
            print(f"would update {it['title']} ({', '.join(bad)})")
        else:
            ops = [
                *patch_ops(it, area, "replace"),
                {"op": "add", "path": "/fields/System.State", "value": it["state"]},
            ]
            api("PATCH", f"/wit/workitems/{w['id']}?{V}", ops, PATCH_JSON)
            print(f"updated {it['title']} ({', '.join(bad)})")
        summary["updated"] += 1
    # The MOB-210 -> DAT-307 dependency crosses trackers, so it stays a reference string in the description.

    print(
        f"\nsummary: {summary['created']} created, {summary['updated']} updated, "
        f"{summary['unchanged']} unchanged, {summary['deleted']} deleted"
    )
    if CHECK and (summary["created"] or summary["updated"]):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except AdoError as e:
        sys.exit(str(e))
