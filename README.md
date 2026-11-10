# delivery-mcp

An MCP server that tells you whether a sprint is ready to commit. It checks team capacity, scores every story against a Definition of Ready, and reads the release calendar, across teams on ClickUp and Azure DevOps.

Built for the video series [MCP for Delivery Teams](https://andrewleger.com/insights) by Andrew Leger.

## Why build this when ClickUp and Azure DevOps ship MCP servers?

Their servers read and write tickets. They do not know your capacity rules, your Definition of Ready, or how a ClickUp team and an Azure DevOps team compare. This server holds that logic and nothing else. It never writes to your tracker. Use the official vendor servers for that.

## Spec and versions

- MCP spec revision 2026-07-28 (stateless)
- Python 3.12, FastMCP 4 on the official mcp 2.x SDK
- Deployed on Vercel's Python runtime

## Tools

| Tool | What it answers |
| --- | --- |
| get_sprint_capacity | How many focus hours does a team have this sprint after PTO? |
| check_definition_of_ready | Which stories are not ready, and why? Is the team overcommitted? |
| list_release_dates | What ships when? |
| compare_readiness | How do teams on different trackers compare? |

Also a `dod://team/{team}` resource and a `sprint-readiness-review` prompt.

## Run locally

The server reads live data from your ClickUp workspace and Azure DevOps project. It never writes to them.

```bash
uv sync
cp .env.example .env.local                  # add ClickUp and Azure DevOps tokens and IDs
uv run python scripts/seed_clickup.py       # optional: build the Northwind demo in a test ClickUp space
uv run python scripts/seed_ado.py           # optional: build the Northwind demo in a test Azure DevOps project
uv run fastmcp run delivery_mcp/server.py --transport http --port 8000
npx @modelcontextprotocol/inspector         # connect to http://localhost:8000/mcp
```

## Connect to Claude

Add the deployed URL as a custom connector in Claude, or add it to Claude Code:

```bash
claude mcp add --transport http delivery-mcp https://<your-deployment>/mcp
```

## Auth

v0.1 and v0.2 have no auth by design. Point them only at test workspaces with demo data. v0.3 adds sign-in with Microsoft Entra ID, and Azure DevOps reads run with the signed-in user's own permissions. Do not point v0.1 or v0.2 at real tracker data.

## Demo data

Northwind Logistics is a fictional company: three teams, Sprints 22 to 24, four releases. Platform and Data run in ClickUp, Mobile runs in Azure DevOps. `data/northwind.json` is the seed source for the demo workspaces and the test fixtures. The server never reads it at runtime. One story contains a planted prompt injection for the security episode.

## Releases

| Tag | Episode | Adds |
| --- | --- | --- |
| v0.1 | 1. Concept | Capacity and DoR tools on live ClickUp and Azure DevOps data |
| v0.2 | 2. Build | Release calendar, cross-tracker comparison, resource, prompt |
| v0.3 | 3. Govern | Entra ID sign-in, audit log, evals |

## License

MIT
