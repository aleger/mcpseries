import type { Sprint, Story, TeamConfig } from "@/lib/types";
import type { TrackerAdapter } from "./types";
import { cached, requireEnv, TrackerError } from "./http";
import { KEY_RE, RELEASE_TAG_PREFIX, splitDescription } from "./parse";

const BASE = "https://api.clickup.com/api/v2";
type Json = Record<string, any>;

async function get(path: string): Promise<Json> {
  return cached(`clickup:${path}`, async () => {
    const res = await fetch(BASE + path, { headers: { Authorization: requireEnv("CLICKUP_API_TOKEN") } });
    if (!res.ok) throw new TrackerError(`ClickUp request failed (${res.status}).`);
    return (await res.json()) as Json;
  });
}

async function listFor(team: TeamConfig, sprint: Sprint): Promise<string | null> {
  const folderName = team.clickup?.folder;
  if (!folderName) throw new TrackerError(`Team ${team.key} has no ClickUp folder configured.`);
  const space = requireEnv("CLICKUP_SPACE_ID");
  const folders = (await get(`/space/${space}/folder?archived=false`)).folders as Json[];
  const folder = folders.find((f) => f.name === folderName);
  return folder?.lists.find((l: Json) => l.name === sprint.name)?.id ?? null;
}

async function tasksIn(listId: string): Promise<Json[]> {
  const all: Json[] = [];
  for (let page = 0; ; page++) {
    const res = await get(`/list/${listId}/task?include_closed=true&subtasks=true&page=${page}`);
    all.push(...res.tasks);
    if (res.last_page ?? res.tasks.length < 100) return all;
  }
}

const field = (t: Json, name: string) => (t.custom_fields as Json[] | undefined)?.find((c) => c.name === name)?.value ?? null;

/** Story Points custom field, falling back to ClickUp's native points (history items use it). */
const pointsOf = (t: Json): number | null => {
  const v = field(t, "Story Points") ?? t.points ?? null;
  return v === null || v === "" ? null : Number(v);
};

/** Map one ClickUp task to the common Story shape. Exported for contract tests. */
export function mapTask(t: Json, teamKey: string, sprintKey: string | null): Story | null {
  const m = String(t.name).match(KEY_RE);
  if (!m) return null; // not a seeded story
  const { description, dependencies } = splitDescription(String(t.description ?? t.text_content ?? ""));
  const tags = ((t.tags as Json[]) ?? []).map((x) => String(x.name));
  const checklist = ((t.checklists as Json[]) ?? []).find((c) => c.name === "Acceptance Criteria");
  const owner = field(t, "Owner") ?? t.assignees?.[0]?.username ?? null;
  return {
    key: m[1],
    title: m[2],
    description,
    acceptanceCriteria: ((checklist?.items as Json[]) ?? []).map((i) => String(i.name)),
    storyPoints: pointsOf(t),
    hasUi: tags.includes("ui"),
    designLink: field(t, "Design Link") || null,
    dependencies,
    assignee: owner,
    releaseName: tags.find((x) => x.startsWith(RELEASE_TAG_PREFIX))?.slice(RELEASE_TAG_PREFIX.length) ?? null,
    sprintKey,
    status: String(t.status?.status ?? ""),
    teamKey,
  };
}

export const clickupAdapter: TrackerAdapter = {
  async getSprintStories(team, sprint) {
    const id = await listFor(team, sprint);
    if (!id) return [];
    return (await tasksIn(id)).map((t) => mapTask(t, team.key, sprint.key)).filter((s): s is Story => s !== null);
  },

  async getCompletedPoints(team, sprint) {
    const id = await listFor(team, sprint);
    if (!id) return 0;
    return (await tasksIn(id))
      .filter((t) => ["done", "closed"].includes(String(t.status?.type)))
      .reduce((n, t) => n + (pointsOf(t) ?? 0), 0);
  },
};
