# delivery-mcp

An MCP server that tells you whether a sprint is ready to commit. It checks team capacity, scores every story against a Definition of Ready, and reads the release calendar, across teams on ClickUp and Azure DevOps.

Built for the video series [MCP for Delivery Teams](https://andrewleger.com/insights) by Andrew Leger.

## Why build this when ClickUp and Azure DevOps ship MCP servers?

Their servers read and write tickets. They do not know your capacity rules, your Definition of Ready, or how a ClickUp team and an Azure DevOps team compare. This server holds that logic and nothing else. It never writes to your tracker. Use the official vendor servers for that.

## Spec and versions

- MCP spec revision 2026-07-28 (stateless)
- mcp-handler 2.x, @modelcontextprotocol/server 2.x, zod 4
- Next.js on Vercel, Node 22.18 or later

## Tools

| Tool | What it answers |
| --- | --- |
| get_sprint_capacity | How many focus hours does a team have this sprint after PTO? |
| check_definition_of_ready | Which stories are not ready, and why? Is the team overcommitted? |
| list_release_dates | What ships when? |
| compare_readiness | How do teams on different trackers compare? |

Also a `dod://team/{team}` resource and a `sprint-readiness-review` prompt.

## Run locally

```bash
npm install
npm test
npm run dev
npx @modelcontextprotocol/inspector   # connect to http://localhost:3000/mcp
```

v0.1 reads the bundled Northwind JSON in `data/`. Postgres and Prisma seeding are not wired up yet.

## Connect to Claude

Add the deployed URL as a custom connector in Claude, or add it to Claude Code:

```bash
claude mcp add --transport http delivery-mcp https://<your-deployment>/mcp
```

## Auth

v0.1 and v0.2 have no auth by design. They serve fictional demo data only. v0.3 adds OAuth with Clerk. Do not point v0.1 or v0.2 at real tracker data.

## Demo data

Northwind Logistics is a fictional company: three teams, Sprint 22 to 24, four releases. See `data/`. One story contains a planted prompt injection for the security episode.

## Releases

| Tag | Episode | Adds |
| --- | --- | --- |
| v0.1 | 1. Concept | Capacity and DoR tools on seeded data |
| v0.2 | 2. Build | Release calendar, cross-tracker comparison, read-only adapters |
| v0.3 | 3. Govern | OAuth, audit log, evals |

## License

MIT
