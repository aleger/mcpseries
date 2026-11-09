/**
 * Pushes the Azure DevOps-tracked Northwind team (Mobile) into the "Northwind demo" project.
 * Idempotent: area path, iteration and work items are matched by name / story key and never duplicated.
 *
 *   npm run push:ado            # create what is missing
 *   npm run push:ado -- --reset # delete the Northwind work items first, then recreate
 *
 * Needs ADO_TOKEN (personal access token, Work Items read/write + Project and Team read/write)
 * in .env.local. Writes only to the demo project.
 */
import northwind from "../data/northwind.json" with { type: "json" };
import type { Dataset, Story } from "../lib/types.ts";

const ORG = "info0624";
const PROJECT = "Northwind demo";
const BASE = `https://dev.azure.com/${ORG}/${encodeURIComponent(PROJECT)}/_apis`;
const token = process.env.ADO_TOKEN;
if (!token) throw new Error("ADO_TOKEN is not set (put it in .env.local).");
const reset = process.argv.includes("--reset");
const data = northwind as unknown as Dataset;
const AUTH = "Basic " + Buffer.from(`:${token}`).toString("base64");

type Json = Record<string, any>;

async function api(method: string, path: string, body?: unknown, contentType = "application/json") {
  const res = await fetch(BASE + path, {
    method,
    headers: { Authorization: AUTH, "Content-Type": contentType },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: (text ? safeParse(text) : {}) as Json, text };
}

function safeParse(t: string): unknown {
  try {
    return JSON.parse(t);
  } catch {
    return {};
  }
}

async function must(method: string, path: string, body?: unknown, contentType?: string) {
  const r = await api(method, path, body, contentType);
  if (r.status >= 400) throw new Error(`${method} ${path} -> ${r.status} ${r.text.slice(0, 300)}`);
  return r.json;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
const RELEASE_NAMES = Object.fromEntries(data.releases.map((r) => [r.key, r.name]));

function descriptionHtml(s: Story): string {
  const ac = s.acceptanceCriteria.length
    ? `<ul>${s.acceptanceCriteria.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`
    : "<p>(none)</p>";
  const deps = s.dependencies.length
    ? `<h3>Dependencies</h3><ul>${s.dependencies
        .map((d) => `<li>${esc(d.key)}: ${esc(d.description)} (resolved: ${d.resolved})</li>`)
        .join("")}</ul>`
    : "";
  return `<p>${esc(s.description)}</p><h3>Acceptance Criteria</h3>${ac}${deps}`;
}

/** Create a classification node (area or iteration) if it does not exist. */
async function ensureNode(kind: "areas" | "iterations", name: string, attributes?: Json) {
  const r = await api("POST", `/wit/classificationnodes/${kind}?api-version=7.1`, { name, attributes });
  if (r.status === 409) return console.log(`exists  ${kind} ${name}`);
  if (r.status >= 400) throw new Error(`create ${kind} ${name} -> ${r.status} ${r.text.slice(0, 300)}`);
  console.log(`created ${kind} ${name}`);
}

async function main() {
  const team = data.teams.find((t) => t.tracker === "azure-devops")!;
  const area = team.name; // area path per team
  await ensureNode("areas", area);

  for (const sprint of data.sprints.filter((s) => data.stories.some((x) => x.teamKey === team.key && x.sprintKey === s.key))) {
    await ensureNode("iterations", sprint.name, {
      startDate: `${sprint.start}T00:00:00Z`,
      finishDate: `${sprint.end}T00:00:00Z`,
    });
  }

  const wiql = await must("POST", "/wit/wiql?api-version=7.1", {
    query: `select [System.Id], [System.Title] from workitems where [System.TeamProject] = @project and [System.AreaPath] under '${PROJECT}\\${area}'`,
  });
  const ids: number[] = (wiql.workItems ?? []).map((w: Json) => w.id);
  const existing = new Map<string, number>(); // story key -> work item id
  if (ids.length) {
    const items = await must("GET", `/wit/workitems?ids=${ids.join(",")}&fields=System.Title&api-version=7.1`);
    for (const w of items.value) existing.set(String(w.fields["System.Title"]).split(":")[0], w.id);
  }

  for (const s of data.stories.filter((x) => x.teamKey === team.key)) {
    const title = `${s.key}: ${s.title}`;
    let id = existing.get(s.key);
    if (id && reset) {
      await must("DELETE", `/wit/workitems/${id}?api-version=7.1`); // goes to the recycle bin
      id = undefined;
    }
    if (id) {
      console.log(`exists  ${title}`);
      continue;
    }
    const sprint = data.sprints.find((x) => x.key === s.sprintKey);
    const ops: Json[] = [
      { op: "add", path: "/fields/System.Title", value: title },
      { op: "add", path: "/fields/System.Description", value: descriptionHtml(s) },
      { op: "add", path: "/fields/Microsoft.VSTS.Scheduling.Effort", value: s.storyPoints },
      { op: "add", path: "/fields/System.AreaPath", value: `${PROJECT}\\${area}` },
      { op: "add", path: "/fields/System.IterationPath", value: sprint ? `${PROJECT}\\${sprint.name}` : PROJECT },
      { op: "add", path: "/fields/System.Tags", value: s.releaseKey ? `release-${RELEASE_NAMES[s.releaseKey]}` : "" },
    ];
    if (s.designLink) {
      ops.push({
        op: "add",
        path: "/relations/-",
        value: { rel: "Hyperlink", url: s.designLink, attributes: { comment: "Design" } },
      });
    }
    await must("POST", "/wit/workitems/$Issue?api-version=7.1", ops, "application/json-patch+json");
    console.log(`created ${title}`);
  }
  // Cross-tracker dependencies (MOB-210 -> DAT-307) stay as text in the description: the other end lives in ClickUp.
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
