/**
 * Builds the Northwind demo (Mobile team) in the Azure DevOps demo project from data/northwind.json.
 * Targets the Agile process: User Story, Story Points, Acceptance Criteria field.
 * Idempotent: area path, iterations, team settings and work items are matched by name or story key
 * and updated in place. This is the only code in the repo that writes to Azure DevOps. Run by hand.
 *
 *   npm run seed:ado             # create or update
 *   npm run seed:ado -- --reset  # delete every work item under the Mobile area first (recycle bin)
 *
 * Env: ADO_ORG, ADO_PROJECT, ADO_PAT (read and write). Tokens are never printed.
 */
import { loadEnv, releaseName, seed, sprintName, type SeedStory } from "./lib/seed-data.ts";

const env = loadEnv("ADO_ORG", "ADO_PROJECT", "ADO_PAT");
const PROJECT = env.ADO_PROJECT;
const BASE = `https://dev.azure.com/${env.ADO_ORG}/${encodeURIComponent(PROJECT)}/_apis`;
const AUTH = "Basic " + Buffer.from(`:${env.ADO_PAT}`).toString("base64");
const reset = process.argv.includes("--reset");
type Json = Record<string, any>;

async function api(method: string, path: string, body?: unknown, contentType = "application/json") {
  const res = await fetch(BASE + path, {
    method,
    headers: { Authorization: AUTH, "Content-Type": contentType },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json: Json = {};
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    /* non-JSON error page */
  }
  return { status: res.status, json, text };
}

async function must(method: string, path: string, body?: unknown, contentType?: string) {
  const r = await api(method, path, body, contentType);
  if (r.status >= 400) throw new Error(`${method} ${path.split("?")[0]} -> ${r.status} ${r.text.slice(0, 250)}`);
  return r.json;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
const summary = { created: 0, updated: 0, deleted: 0 };

function storyDescription(s: SeedStory): string {
  const deps = s.dependencies.length
    ? `<h3>Dependencies</h3><ul>${s.dependencies
        .map((d) => `<li>${esc(d.key)}: ${esc(d.description)} (resolved: ${d.resolved})</li>`)
        .join("")}</ul>`
    : "";
  return `<p>${esc(s.description)}</p>${deps}`;
}
const acceptanceHtml = (items: string[]) => (items.length ? `<ul>${items.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "");

async function ensureNode(kind: "areas" | "iterations", name: string, attributes?: Json): Promise<string> {
  const r = await api("POST", `/wit/classificationnodes/${kind}?api-version=7.1`, { name, attributes });
  if (r.status < 400) {
    console.log(`created ${kind} ${name}`);
    return r.json.identifier;
  }
  if (r.status !== 409) throw new Error(`create ${kind} ${name} -> ${r.status} ${r.text.slice(0, 200)}`);
  const node = await must("GET", `/wit/classificationnodes/${kind}/${encodeURIComponent(name)}?api-version=7.1`);
  // Keep sprint dates in sync on reruns.
  if (attributes && JSON.stringify(node.attributes ?? {}) !== JSON.stringify(attributes)) {
    await must("PATCH", `/wit/classificationnodes/${kind}/${encodeURIComponent(name)}?api-version=7.1`, { name, attributes });
    console.log(`updated ${kind} ${name}`);
  }
  return node.identifier;
}

async function main() {
  const team = seed.teams.find((t) => t.tracker === "azure-devops")!;
  const area = `${PROJECT}\\${team.name}`;
  await ensureNode("areas", team.name);

  // Sprints 22 to 24, with dates, selected for the default project team so they show on its board.
  const selected = new Set<string>(
    ((await must("GET", "/work/teamsettings/iterations?api-version=7.1")).value as Json[]).map((i) => i.id),
  );
  for (const s of seed.sprints) {
    const id = await ensureNode("iterations", s.name, {
      startDate: `${s.start}T00:00:00Z`,
      finishDate: `${s.end}T00:00:00Z`,
    });
    if (!selected.has(id)) {
      await must("POST", "/work/teamsettings/iterations?api-version=7.1", { id });
      console.log(`selected iteration ${s.name} for the team`);
    }
  }

  // Team area = project root with sub-areas included, so Mobile items show on the team backlog.
  await must("PATCH", "/work/teamsettings/teamfieldvalues?api-version=7.1", {
    defaultValue: PROJECT,
    values: [{ value: PROJECT, includeChildren: true }],
  });

  // Existing work items under the Mobile area, keyed by story key.
  const wiql = await must("POST", "/wit/wiql?api-version=7.1", {
    query: `select [System.Id] from workitems where [System.TeamProject] = @project and [System.AreaPath] under '${area}'`,
  });
  const ids: number[] = (wiql.workItems ?? []).map((w: Json) => w.id);
  const existing = new Map<string, number>();
  for (let i = 0; i < ids.length; i += 100) {
    const batch = await must("GET", `/wit/workitems?ids=${ids.slice(i, i + 100).join(",")}&fields=System.Title&api-version=7.1`);
    for (const w of batch.value) existing.set(String(w.fields["System.Title"]).split(":")[0], w.id);
  }
  if (reset) {
    for (const id of existing.values()) {
      await must("DELETE", `/wit/workitems/${id}?api-version=7.1`); // recycle bin, restorable
      summary.deleted++;
    }
    existing.clear();
  }

  type Item = {
    key: string;
    title: string;
    description: string;
    acceptance: string;
    points: number | null;
    iteration: string;
    state: string;
    tags: string[];
    designLink?: string | null;
  };
  const items: Item[] = [
    ...seed.stories
      .filter((s) => s.teamKey === team.key)
      .map((s) => ({
        key: s.key,
        title: `${s.key}: ${s.title}`,
        description: storyDescription(s),
        acceptance: acceptanceHtml(s.acceptanceCriteria),
        points: s.storyPoints,
        iteration: s.sprintKey ? `${PROJECT}\\${sprintName(s.sprintKey)}` : PROJECT,
        state: "New",
        tags: [
          ...(s.releaseKey ? [`release-${releaseName(s.releaseKey)}`] : []),
          ...(s.hasUi ? ["ui"] : []),
          `owner:${s.assignee}`,
        ],
        designLink: s.designLink,
      })),
    ...seed.historyStories
      .filter((h) => h.teamKey === team.key)
      .map((h) => ({
        key: h.key,
        title: `${h.key}: ${h.title}`,
        description: "",
        acceptance: "",
        points: h.storyPoints,
        iteration: `${PROJECT}\\${sprintName(h.sprintKey)}`,
        state: h.status === "Done" ? "Closed" : "Active",
        tags: ["northwind", "history"],
      })),
  ];

  for (const it of items) {
    const fields = (op: "add" | "replace") => [
      { op, path: "/fields/System.Title", value: it.title },
      { op, path: "/fields/System.Description", value: it.description },
      { op, path: "/fields/Microsoft.VSTS.Common.AcceptanceCriteria", value: it.acceptance },
      { op, path: "/fields/Microsoft.VSTS.Scheduling.StoryPoints", value: it.points },
      { op, path: "/fields/System.AreaPath", value: area },
      { op, path: "/fields/System.IterationPath", value: it.iteration },
      { op, path: "/fields/System.Tags", value: it.tags.join("; ") },
    ];
    const id = existing.get(it.key);
    if (id) {
      await must("PATCH", `/wit/workitems/${id}?api-version=7.1`, [...fields("replace"), { op: "add", path: "/fields/System.State", value: it.state }], "application/json-patch+json");
      summary.updated++;
      console.log(`updated ${it.title}`);
      continue;
    }
    const ops: Json[] = [...fields("add"), { op: "add", path: "/fields/System.State", value: it.state }];
    if (it.designLink) {
      ops.push({ op: "add", path: "/relations/-", value: { rel: "Hyperlink", url: it.designLink, attributes: { comment: "Design" } } });
    }
    let r = await api("POST", "/wit/workitems/$User%20Story?api-version=7.1", ops, "application/json-patch+json");
    if (r.status >= 400 && it.state !== "New") {
      // Some states cannot be set on create: create as New, then move.
      const base = ops.filter((o) => o.path !== "/fields/System.State");
      r = await api("POST", "/wit/workitems/$User%20Story?api-version=7.1", base, "application/json-patch+json");
      if (r.status < 400) {
        for (const state of it.state === "Closed" ? ["Active", "Closed"] : [it.state]) {
          await must("PATCH", `/wit/workitems/${r.json.id}?api-version=7.1`, [{ op: "add", path: "/fields/System.State", value: state }], "application/json-patch+json");
        }
      }
    }
    if (r.status >= 400) throw new Error(`create ${it.key} -> ${r.status} ${r.text.slice(0, 250)}`);
    summary.created++;
    console.log(`created ${it.title}`);
  }
  // The MOB-210 -> DAT-307 dependency crosses trackers, so it stays a reference string in the Dependencies section.

  console.log(`\nsummary: ${summary.created} created, ${summary.updated} updated, ${summary.deleted} deleted`);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
