"""Spike: read MOB-210 from Azure DevOps on behalf of the signed-in Entra user. No PAT.

Local only. Run: uv run uvicorn spikes.entra_obo.server:app --port 8000
Then connect with: uv run python spikes/entra_obo/client.py

Success means the Azure DevOps call below is authorised by the user's own identity,
so a user without project access gets Azure DevOps's own refusal instead of data.
"""

from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth.providers.azure import AzureProvider, EntraOBOToken
from fastmcp.server.dependencies import get_access_token

from delivery_mcp.settings import get_settings

ADO_RESOURCE_ID = "499b84ac-1321-427f-aa17-267ca6975798"  # Azure DevOps first-party resource
BASE_URL = "http://localhost:8000"

s = get_settings()
assert s.entra_tenant_id and s.entra_client_id and s.entra_client_secret, "Set the ENTRA_* values"

auth = AzureProvider(
    client_id=s.entra_client_id,
    client_secret=s.entra_client_secret.get_secret_value(),
    tenant_id=s.entra_tenant_id,
    base_url=BASE_URL,
    required_scopes=["read"],
)

# Spike only: show real errors locally. The production server keeps mask_error_details=True.
mcp = FastMCP(name="delivery-mcp-obo-spike", auth=auth, mask_error_details=False)


@mcp.tool(annotations={"readOnlyHint": True})
async def read_mob_210(
    ado_token: str = EntraOBOToken([f"{ADO_RESOURCE_ID}/.default"]),
) -> dict[str, Any]:
    """Read story MOB-210 from Azure DevOps using the caller's own identity (on-behalf-of)."""
    token = get_access_token()
    caller = (token.claims or {}).get("preferred_username") if token else None
    org, project = s.ado_org, s.ado_project
    base = f"https://dev.azure.com/{org}/{project}/_apis"
    headers = {"Authorization": f"Bearer {ado_token}"}
    wiql = {
        "query": "select [System.Id] from workitems where [System.TeamProject] = @project "
        "and [System.Title] contains 'MOB-210:'"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(f"{base}/wit/wiql?api-version=7.1", json=wiql, headers=headers)
        out: dict[str, Any] = {"caller": caller, "wiql_status": res.status_code}
        if res.status_code != 200 or "json" not in res.headers.get("content-type", ""):
            out["ok"] = False
            out["error"] = _short(res)
            return out
        ids = [w["id"] for w in res.json().get("workItems") or []]
        if not ids:
            return {**out, "ok": True, "found": False, "note": "Query ran but returned no MOB-210."}
        item = await client.get(f"{base}/wit/workitems/{ids[0]}?api-version=7.1", headers=headers)
        out["item_status"] = item.status_code
        if item.status_code != 200:
            out["ok"] = False
            out["error"] = _short(item)
            return out
        f = item.json()["fields"]
        return {
            **out,
            "ok": True,
            "found": True,
            "title": f.get("System.Title"),
            "state": f.get("System.State"),
            "points": f.get("Microsoft.VSTS.Scheduling.StoryPoints"),
        }


def _short(res: httpx.Response) -> str:
    """First 200 characters of an error body. Bodies are Azure DevOps messages, never tokens."""
    return f"{res.headers.get('content-type', '')}: {res.text[:200]}"


app = mcp.http_app(path="/mcp")
