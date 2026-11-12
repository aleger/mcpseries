"""Adapter contract tests: recorded-shape payloads (fictional data, no tokens) map to Story."""

import json
from pathlib import Path

import httpx
import pytest

from delivery_mcp import config
from delivery_mcp.adapters import adapter_for
from delivery_mcp.adapters.azure_devops import AzureDevOpsAdapter, map_work_item
from delivery_mcp.adapters.clickup import ClickUpAdapter, map_task
from delivery_mcp.adapters.http import TrackerError, clear_cache, read_json
from delivery_mcp.adapters.parse import split_ado_description, split_description
from delivery_mcp.settings import Settings, get_settings

REC = Path(__file__).parent / "recordings"


def rec(name: str) -> dict:
    return json.loads((REC / name).read_text())


def test_split_description_ignores_referenced_by():
    desc, deps = split_description(rec("clickup_task_dat307.json")["description"])
    assert desc == "As a data engineer, I want an API, so that mobile can show delays."
    assert [(d.key, d.description, d.resolved) for d in deps] == [("DAT-302", "Telematics ingestion", False)]


def test_split_ado_description_reads_html():
    _, deps = split_ado_description(rec("ado_work_item_mob210.json")["fields"]["System.Description"])
    assert [(d.key, d.resolved) for d in deps] == [("DAT-307", False)]


def test_map_clickup_task():
    s = map_task(rec("clickup_task_dat307.json"), "data", "sprint-24")
    assert s is not None
    assert (s.key, s.title, s.story_points, s.has_ui, s.design_link) == (
        "DAT-307",
        "Delay prediction API",
        5,
        True,
        None,
    )
    assert s.acceptance_criteria == ["A", "B"]
    assert (s.release_name, s.assignee, s.status) == ("2027.01.2", "Sam Rivera", "ready for development")


async def test_clickup_velocity_counts_closed_tasks_with_native_points(monkeypatch):
    monkeypatch.setenv("CLICKUP_API_TOKEN", "not-a-real-token")
    monkeypatch.setenv("CLICKUP_SPACE_ID", "1")
    get_settings.cache_clear()
    clear_cache()
    done = rec("clickup_task_history.json")
    open_ = {
        **done,
        "name": "DAT-H02: Carried over",
        "points": 5,
        "status": {"status": "backlog", "type": "open"},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        if "/folder" in req.url.path:
            body = {"folders": [{"name": "Data", "lists": [{"id": "9", "name": "Sprint 22"}]}]}
        else:
            body = {"tasks": [done, open_], "last_page": True}
        return httpx.Response(200, headers={"content-type": "application/json"}, json=body)

    points = await ClickUpAdapter(httpx.MockTransport(handler)).get_completed_points(
        config.get_team("data"), config.get_sprint("sprint-22")
    )
    get_settings.cache_clear()
    clear_cache()
    assert points == 8  # only the closed task counts


def test_map_ado_work_item():
    s = map_work_item(rec("ado_work_item_mob210.json"), "mobile", "sprint-24")
    assert s is not None
    assert (s.key, s.story_points, s.has_ui, s.design_link) == (
        "MOB-210",
        3,
        True,
        "https://example.test/design",
    )
    assert s.acceptance_criteria == ["Banner shows", "Dismissable"]
    assert [(d.key, d.resolved) for d in s.dependencies] == [("DAT-307", False)]
    assert s.assignee == "Aisha Karim"


def test_unseeded_items_are_skipped():
    assert map_task({"name": "Random task"}, "data", None) is None
    assert map_work_item({"fields": {"System.Title": "Random"}}, "mobile", None) is None


def test_adapter_for_picks_by_tracker():
    assert isinstance(adapter_for("clickup"), ClickUpAdapter)
    assert isinstance(adapter_for("azure-devops"), AzureDevOpsAdapter)


# --- credential failures -------------------------------------------------------------------------


def test_ado_203_html_sign_in_page_is_a_clear_error():
    """A rejected PAT returns 203 and an HTML sign-in page, not JSON."""
    res = httpx.Response(203, headers={"content-type": "text/html"}, text="<html>Sign in</html>")
    with pytest.raises(TrackerError, match="Azure DevOps rejected the server's credentials"):
        read_json(res, "Azure DevOps", "ADO_PAT", "needs Work Items (Read)")


def test_html_200_is_also_rejected():
    res = httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")
    with pytest.raises(TrackerError, match="rejected"):
        read_json(res, "ClickUp", "CLICKUP_API_TOKEN", "a personal API token")


@pytest.fixture
def ado_env(monkeypatch):
    for k, v in {"ADO_ORG": "org", "ADO_PROJECT": "Northwind demo", "ADO_PAT": "not-a-real-token"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    clear_cache()
    yield
    get_settings.cache_clear()
    clear_cache()


async def test_ado_adapter_surfaces_203_through_a_request(ado_env):
    def sign_in_page(req: httpx.Request) -> httpx.Response:
        return httpx.Response(203, headers={"content-type": "text/html"}, text="<html>Sign in</html>")

    adapter = AzureDevOpsAdapter(httpx.MockTransport(sign_in_page))
    with pytest.raises(TrackerError, match="Azure DevOps rejected the server's credentials"):
        await adapter.get_sprint_stories(config.get_team("mobile"), config.get_sprint("sprint-24"))


async def test_ado_adapter_maps_wiql_and_items(ado_env):
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(f"{req.method} {req.url.path}")
        body = (
            {"workItems": [{"id": 1}]}
            if req.url.path.endswith("/wiql")
            else {"value": [rec("ado_work_item_mob210.json")]}
        )
        return httpx.Response(200, headers={"content-type": "application/json"}, json=body)

    stories = await AzureDevOpsAdapter(httpx.MockTransport(handler)).get_sprint_stories(
        config.get_team("mobile"), config.get_sprint("sprint-24")
    )
    assert [s.key for s in stories] == ["MOB-210"]
    assert seen[0].startswith("POST") and seen[1].startswith("GET")
    assert not any(m.startswith(("PUT", "PATCH", "DELETE")) for m in seen)  # read-only


# --- env loading ---------------------------------------------------------------------------------


def test_env_file_quoting_is_parsed_once_and_the_same_way(tmp_path):
    """The TypeScript server once read a quoted .env.local value differently from its tests."""
    env = tmp_path / ".env.local"
    env.write_text("ADO_ORG=info0624\nADO_PAT=\"quoted-value\"  # comment\nCLICKUP_SPACE_ID='123'\n")
    s = Settings(_env_file=env)
    assert s.ado_org == "info0624"
    assert s.ado_pat is not None and s.ado_pat.get_secret_value() == "quoted-value"
    assert s.clickup_space_id == "123"
    assert "quoted-value" not in repr(s)  # secrets never show up in logs
