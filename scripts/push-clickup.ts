/**
 * Pushes the ClickUp-tracked Northwind teams (Platform, Data) into the demo space.
 * Idempotent: folders, lists and tasks are matched by name / story key and never duplicated.
 *
 *   npm run push:clickup            # create what is missing
 *   npm run push:clickup -- --reset # delete the Northwind tasks first, then recreate
 *
 * Needs CLICKUP_TOKEN (personal API token) in .env.local. Writes only to the demo space.
 */
import northwind from "../data/northwind.json" with { type: "json" };
import type { Dataset, Story } from "../lib/types.ts";

const SPACE_ID = "90115249921"; // "Northwind demo" in workspace 9010034792
const BASE = "https://api.clickup.com/api/v2";
const token = process.env.CLICKUP_TOKEN;
if (!token) throw new Error("CLICKUP_TOKEN is not set (put it in .env.local).");
const reset = process.argv.includes("--reset");
const data = northwind as unknown as Dataset;

type Json = Record<string, any>;

async function api(method: string, path: string, body?: unknown): Promise<Json> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await fetch(BASE + path, {
      method,
      headers: { Authorization: token!, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 429) {
      await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
      continue;
    }
    const text = await res.text();
    if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text.slice(0, 300)}`);
    return text ? JSON.parse(text) : {};
  }
  throw new Error(`${method} ${path} -> rate limited`);
}

const RELEASE_NAMES = Object.fromEntries(data.releases.map((r) => [r.key, r.name]));

function description(s: Story): string {
  const lines = [s.description];
  if (s.dependencies.length) {
    lines.push("", "Dependencies:", ...s.dependencies.map((d) => `- ${d.key}: ${d.description} (resolved: ${d.resolved})`));
  }
  if (s.releaseKey) lines.push("", `Release: ${RELEASE_NAMES[s.releaseKey]}`);
  return lines.join("\n");
}

async function main() {
  const teams = data.teams.filter((t) => t.tracker === "clickup");
  const fieldWarnings = new Set<string>();
  const taskIds = new Map<string, string>(); // story key -> ClickUp task id

  const folders: Json[] = (await api("GET", `/space/${SPACE_ID}/folder?archived=false`)).folders;

  for (const team of teams) {
    let folder = folders.find((f) => f.name === team.name);
    if (!folder) {
      folder = await api("POST", `/space/${SPACE_ID}/folder`, { name: team.name });
      console.log(`created folder ${team.name}`);
    }
    const lists: Json[] = (await api("GET", `/folder/${folder.id}/list?archived=false`)).lists;
    const listFor = async (name: string) => {
      let l = lists.find((x) => x.name === name);
      if (!l) {
        l = await api("POST", `/folder/${folder.id}/list`, { name });
        lists.push(l);
        console.log(`created list ${team.name}/${name}`);
      }
      return l;
    };

    for (const sprintKey of ["sprint-24", null] as const) {
      const sprint = sprintKey ? data.sprints.find((s) => s.key === sprintKey)! : null;
      const list = await listFor(sprint ? sprint.name : "Backlog");
      const fields: Json[] = (await api("GET", `/list/${list.id}/field`)).fields;
      const points = fields.find((f) => f.name === "Story Points" && f.type === "number");
      const design = fields.find((f) => f.name === "Design Link" && f.type === "url");
      if (!points) fieldWarnings.add("Story Points (number)");
      if (!design) fieldWarnings.add("Design Link (url)");

      const existing: Json[] = (await api("GET", `/list/${list.id}/task?include_closed=true&subtasks=true`)).tasks;
      const stories = data.stories.filter((s) => s.teamKey === team.key && (s.sprintKey ?? null) === sprintKey);

      for (const s of stories) {
        const name = `${s.key}: ${s.title}`;
        let task = existing.find((t) => t.name.startsWith(`${s.key}:`));
        if (task && reset) {
          await api("DELETE", `/task/${task.id}`);
          task = undefined;
        }
        if (!task) {
          const custom_fields: Json[] = [];
          if (points && s.storyPoints !== null) custom_fields.push({ id: points.id, value: s.storyPoints });
          if (design && s.designLink) custom_fields.push({ id: design.id, value: s.designLink });
          task = await api("POST", `/list/${list.id}/task`, {
            name,
            description: description(s),
            tags: s.releaseKey ? [`release-${RELEASE_NAMES[s.releaseKey]}`] : [],
            custom_fields,
          });
          if (s.acceptanceCriteria.length) {
            const cl = await api("POST", `/task/${task.id}/checklist`, { name: "Acceptance Criteria" });
            for (const item of s.acceptanceCriteria) {
              await api("POST", `/checklist/${cl.checklist.id}/checklist_item`, { name: item });
            }
          }
          console.log(`created ${name}`);
        } else {
          console.log(`exists  ${name}`);
        }
        taskIds.set(s.key, task.id);
      }
    }
  }

  // Dependencies between tasks that both live in ClickUp. Others stay as text in the description.
  for (const s of data.stories) {
    const id = taskIds.get(s.key);
    if (!id) continue;
    for (const d of s.dependencies) {
      const target = taskIds.get(d.key);
      if (!target) continue;
      try {
        await api("POST", `/task/${id}/dependency`, { depends_on: target });
        console.log(`dependency ${s.key} waits on ${d.key}`);
      } catch (e) {
        if (!String(e).includes("already")) throw e;
      }
    }
  }

  if (fieldWarnings.size) {
    console.warn(
      `\nCustom fields missing: ${[...fieldWarnings].join(", ")}.\n` +
        `The ClickUp API cannot create fields. Add them in the space (Settings > Custom Fields), then rerun --reset.`,
    );
  }
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
