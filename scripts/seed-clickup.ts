/**
 * Builds the Northwind demo (Platform and Data teams) in the ClickUp demo space from data/northwind.json.
 * Idempotent: folders, lists, tasks, tags, fields and checklists are matched by name or story key and
 * updated in place. This is the only code in the repo that writes to ClickUp. Run by hand.
 *
 *   npm run seed:clickup             # create or update
 *   npm run seed:clickup -- --reset  # delete every task in the seeded lists first
 *
 * Env: CLICKUP_API_TOKEN, CLICKUP_SPACE_ID. Tokens are never printed.
 */
import { crossToolRefs, loadEnv, releaseName, seed, sprintName, type SeedStory } from "./lib/seed-data.ts";

const env = loadEnv("CLICKUP_API_TOKEN", "CLICKUP_SPACE_ID");
const SPACE = env.CLICKUP_SPACE_ID;
const BASE = "https://api.clickup.com/api/v2";
const reset = process.argv.includes("--reset");
type Json = Record<string, any>;

async function api(method: string, path: string, body?: unknown): Promise<Json> {
  for (let attempt = 0; attempt < 6; attempt++) {
    const res = await fetch(BASE + path, {
      method,
      headers: { Authorization: env.CLICKUP_API_TOKEN, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 429) {
      await new Promise((r) => setTimeout(r, 15_000));
      continue;
    }
    const text = await res.text();
    if (!res.ok) throw new Error(`${method} ${path.split("?")[0]} -> ${res.status} ${text.slice(0, 200)}`);
    return text ? JSON.parse(text) : {};
  }
  throw new Error(`${method} ${path.split("?")[0]} -> rate limited`);
}

// Status names the demo wants, with fallbacks. The ClickUp API cannot create or rename space statuses
// (the Update Space call ignores them), so when the space lacks a wanted status the closest existing
// one is used. Adapters read the status *type* (done/closed), not the name, so velocity is unaffected.
const WANT = {
  backlog: ["backlog"],
  ready: ["ready for sprint", "ready for development"],
  done: ["done", "shipped"],
  notDone: ["not done", "backlog"],
};
const warnings: string[] = [];
const summary = { created: 0, updated: 0, deleted: 0 };

async function main() {
  const have = new Set<string>(
    (await api("GET", `/space/${SPACE}`)).statuses.map((s: Json) => String(s.status).toLowerCase()),
  );
  const status = (want: keyof typeof WANT) => {
    const hit = WANT[want].find((n) => have.has(n));
    if (!hit) throw new Error(`space has none of the statuses: ${WANT[want].join(", ")}`);
    if (hit !== WANT[want][0]) warnings.push(`status "${WANT[want][0]}" not in space; using "${hit}"`);
    return hit;
  };

  const folders: Json[] = (await api("GET", `/space/${SPACE}/folder?archived=false`)).folders;
  const teams = seed.teams.filter((t) => t.tracker === "clickup");
  const taskIds = new Map<string, string>(); // story key -> task id, for native dependencies

  for (const team of teams) {
    let folder = folders.find((f) => f.name === team.name);
    if (!folder) {
      folder = await api("POST", `/space/${SPACE}/folder`, { name: team.name });
      console.log(`created folder ${team.name}`);
    }
    const lists: Json[] = (await api("GET", `/folder/${folder.id}/list?archived=false`)).lists;
    const listNames = [...seed.sprints.map((s) => s.name), "Backlog"];
    for (const name of listNames) {
      let list = lists.find((l) => l.name === name);
      if (!list) {
        list = await api("POST", `/folder/${folder.id}/list`, { name });
        lists.push(list);
        console.log(`created list ${team.name}/${name}`);
      }
    }

    const fieldsOf = async (listId: string) => {
      const fields: Json[] = (await api("GET", `/list/${listId}/field`)).fields;
      const by = (n: string, type: string) => fields.find((f) => f.name === n && f.type === type)?.id as string | undefined;
      return {
        points: by("Story Points", "number"),
        design: by("Design Link", "url"),
        owner: by("Owner", "short_text"),
      };
    };

    // Everything that belongs in each list: stories for Sprint 24 and Backlog, history for closed sprints.
    type Item = { key: string; name: string; description: string; status: string; points: number | null; tags: string[]; story?: SeedStory };
    const itemsFor = (listName: string): Item[] => {
      if (listName === "Backlog" || listName === "Sprint 24") {
        const sk = listName === "Backlog" ? null : "sprint-24";
        return seed.stories
          .filter((s) => s.teamKey === team.key && s.sprintKey === sk)
          .map((s) => ({
            key: s.key,
            name: `${s.key}: ${s.title}`,
            description: storyDescription(s),
            status: status(sk ? "ready" : "backlog"),
            points: s.storyPoints,
            tags: [
              ...(s.releaseKey ? [`release-${releaseName(s.releaseKey)}`] : []),
              ...(s.hasUi ? ["ui"] : []),
            ],
            story: s,
          }));
      }
      return seed.historyStories
        .filter((h) => h.teamKey === team.key && sprintName(h.sprintKey) === listName)
        .map((h) => ({
          key: h.key,
          name: `${h.key}: ${h.title}`,
          description: "",
          status: status(h.status === "Done" ? "done" : "notDone"),
          points: h.storyPoints,
          tags: ["history"],
        }));
    };

    for (const list of lists.filter((l) => listNames.includes(l.name))) {
      const f = await fieldsOf(list.id);
      if (!f.points) warnings.push('missing custom field "Story Points" (number)');
      if (!f.design) warnings.push('missing custom field "Design Link" (url)');
      if (!f.owner) warnings.push('missing custom field "Owner" (text)');
      const existing: Json[] = (await api("GET", `/list/${list.id}/task?include_closed=true&subtasks=true`)).tasks;
      if (reset) {
        for (const t of existing) {
          await api("DELETE", `/task/${t.id}`);
          summary.deleted++;
        }
        existing.length = 0;
      }

      for (const item of itemsFor(list.name)) {
        let task = existing.find((t) => String(t.name).startsWith(`${item.key}:`));
        const customFields: Json[] = [];
        // Free plans cap custom field uses (60), so only real stories get Story Points as a custom field.
        // History items store points in ClickUp's native points field; the adapter reads either.
        const nativePoints = item.story ? undefined : (item.points ?? undefined);
        if (item.story && f.points && item.points !== null) customFields.push({ id: f.points, value: item.points });
        if (f.design && item.story?.designLink) customFields.push({ id: f.design, value: item.story.designLink });
        if (f.owner && item.story?.assignee) customFields.push({ id: f.owner, value: item.story.assignee });

        if (!task) {
          task = await api("POST", `/list/${list.id}/task`, {
            name: item.name,
            description: item.description,
            status: item.status,
            tags: item.tags,
            points: nativePoints,
            custom_fields: customFields,
          });
          if (item.story?.acceptanceCriteria.length) {
            const cl = await api("POST", `/task/${task.id}/checklist`, { name: "Acceptance Criteria" });
            for (const a of item.story.acceptanceCriteria) {
              await api("POST", `/checklist/${cl.checklist.id}/checklist_item`, { name: a });
            }
          }
          summary.created++;
          console.log(`created ${item.name}`);
        } else {
          // Update in place so reruns converge on the seed data.
          await api("PUT", `/task/${task.id}`, { name: item.name, description: item.description, status: item.status, points: nativePoints });
          const haveTags = new Set<string>((task.tags as Json[]).map((t) => t.name));
          for (const tag of item.tags.filter((t) => !haveTags.has(t))) {
            await api("POST", `/task/${task.id}/tag/${encodeURIComponent(tag)}`);
          }
          // Only write values that differ: free plans cap custom field uses, and unchanged values are no-ops.
          for (const cf of customFields) {
            const cur = (task.custom_fields as Json[] | undefined)?.find((c) => c.id === cf.id)?.value;
            if (cur !== undefined && cur !== null && String(cur) === String(cf.value)) continue;
            try {
              await api("POST", `/task/${task.id}/field/${cf.id}`, { value: cf.value });
            } catch (e) {
              if (!String(e).includes("FIELD_033")) throw e;
              warnings.push("ClickUp plan limit on custom field uses reached; some field values were not set");
            }
          }
          if (item.story?.acceptanceCriteria.length && !(task.checklists ?? []).some((c: Json) => c.name === "Acceptance Criteria")) {
            const cl = await api("POST", `/task/${task.id}/checklist`, { name: "Acceptance Criteria" });
            for (const a of item.story.acceptanceCriteria) {
              await api("POST", `/checklist/${cl.checklist.id}/checklist_item`, { name: a });
            }
          }
          summary.updated++;
          console.log(`updated ${item.name}`);
        }
        taskIds.set(item.key, task.id);
      }
    }
  }

  await seedReleases();

  // Native task dependencies between stories that both live in ClickUp.
  for (const s of seed.stories) {
    const id = taskIds.get(s.key);
    for (const d of s.dependencies) {
      const target = taskIds.get(d.key);
      if (!id || !target) continue;
      try {
        await api("POST", `/task/${id}/dependency`, { depends_on: target });
        console.log(`dependency ${s.key} waits on ${d.key}`);
      } catch (e) {
        if (!/already|exists/i.test(String(e))) throw e;
      }
    }
  }

  console.log(`\nsummary: ${summary.created} created, ${summary.updated} updated, ${summary.deleted} deleted`);
  if (warnings.length) {
    console.warn(`\nwarnings:\n${[...new Set(warnings)].map((w) => `- ${w}`).join("\n")}`);
    console.warn("The ClickUp API cannot create custom fields or statuses. Add missing ones in the space, then rerun.");
  }
}

/** Description: the story sentence, a Dependencies section, and a Referenced by section for cross-tool links. */
function storyDescription(s: SeedStory): string {
  const parts = [s.description];
  if (s.dependencies.length) {
    parts.push("", "Dependencies:", ...s.dependencies.map((d) => `- ${d.key}: ${d.description} (resolved: ${d.resolved})`));
  }
  const refs = crossToolRefs(s).neededBy;
  if (refs.length) {
    parts.push("", "Referenced by:", ...refs.map((k) => `- ${k} (Azure DevOps) depends on this story`));
  }
  return parts.join("\n");
}

/** Releases list in the space root, one task per release with a due date. */
async function seedReleases() {
  const lists: Json[] = (await api("GET", `/space/${SPACE}/list?archived=false`)).lists;
  let list = lists.find((l) => l.name === "Releases");
  if (!list) {
    list = await api("POST", `/space/${SPACE}/list`, { name: "Releases" });
    console.log("created list Releases");
  }
  const existing: Json[] = (await api("GET", `/list/${list.id}/task?include_closed=true`)).tasks;
  if (reset) {
    for (const t of existing) await api("DELETE", `/task/${t.id}`);
    existing.length = 0;
  }
  for (const r of seed.releases) {
    const due = Date.parse(`${r.date}T12:00:00Z`);
    const body = { name: r.name, description: `${r.scope}\n\nTeams: ${r.teams.join(", ")}`, due_date: due, tags: r.teams };
    const t = existing.find((x) => x.name === r.name);
    if (t) {
      await api("PUT", `/task/${t.id}`, { name: body.name, description: body.description, due_date: due });
      console.log(`updated release ${r.name}`);
    } else {
      await api("POST", `/list/${list.id}/task`, body);
      console.log(`created release ${r.name}`);
    }
  }
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
