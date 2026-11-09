import type { Sprint, Story, TeamConfig } from "@/lib/types";
import type { TrackerAdapter } from "./types";
import { cached, readJson, requireEnv, TrackerError } from "./http";
import { htmlListItems, KEY_RE, RELEASE_TAG_PREFIX, splitAdoDescription } from "./parse";

type Json = Record<string, any>;

function base() {
  return `https://dev.azure.com/${requireEnv("ADO_ORG")}/${encodeURIComponent(requireEnv("ADO_PROJECT"))}/_apis`;
}

async function call(method: "GET" | "POST", path: string, body?: unknown): Promise<Json> {
  const auth = "Basic " + Buffer.from(`:${requireEnv("ADO_PAT")}`).toString("base64");
  const res = await fetch(base() + path, {
    method,
    headers: { Authorization: auth, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return (await readJson(res, "Azure DevOps", "ADO_PAT", "needs Work Items (Read) and Project and Team (Read)")) as Json;
}

/** Work items under a team's area path in one sprint iteration. WIQL is read-only. */
async function workItems(team: TeamConfig, sprint: Sprint, extraWhere = ""): Promise<Json[]> {
  const area = team.azureDevops?.areaPath;
  if (!area) throw new TrackerError(`Team ${team.key} has no Azure DevOps area path configured.`);
  const project = requireEnv("ADO_PROJECT");
  const wiql = `select [System.Id] from workitems where [System.TeamProject] = @project and [System.WorkItemType] = 'User Story' and [System.AreaPath] under '${area}' and [System.IterationPath] = '${project}\\${sprint.name}'${extraWhere}`;
  return cached(`ado:${wiql}`, async () => {
    const ids: number[] = ((await call("POST", "/wit/wiql?api-version=7.1", { query: wiql })).workItems ?? []).map(
      (w: Json) => w.id,
    );
    if (!ids.length) return [];
    return (await call("GET", `/wit/workitems?ids=${ids.join(",")}&$expand=all&api-version=7.1`)).value as Json[];
  });
}

/** Map one Azure DevOps User Story to the common Story shape. Exported for contract tests. */
export function mapWorkItem(w: Json, teamKey: string, sprintKey: string | null): Story | null {
  const f = w.fields as Json;
  const m = String(f["System.Title"] ?? "").match(KEY_RE);
  if (!m) return null;
  const tags = String(f["System.Tags"] ?? "").split(";").map((t) => t.trim()).filter(Boolean);
  const { description, dependencies } = splitAdoDescription(f["System.Description"]);
  const link = ((w.relations as Json[]) ?? []).find((r) => r.rel === "Hyperlink");
  const owner = tags.find((t) => t.startsWith("owner:"))?.slice("owner:".length) ?? null;
  const points = f["Microsoft.VSTS.Scheduling.StoryPoints"];
  return {
    key: m[1],
    title: m[2],
    description,
    acceptanceCriteria: htmlListItems(f["Microsoft.VSTS.Common.AcceptanceCriteria"]),
    storyPoints: typeof points === "number" ? points : null,
    hasUi: tags.includes("ui"),
    designLink: link?.url ?? null,
    dependencies,
    assignee: owner,
    releaseName: tags.find((t) => t.startsWith(RELEASE_TAG_PREFIX))?.slice(RELEASE_TAG_PREFIX.length) ?? null,
    sprintKey,
    status: String(f["System.State"] ?? ""),
    teamKey,
  };
}

export const azureDevopsAdapter: TrackerAdapter = {
  async getSprintStories(team, sprint) {
    return (await workItems(team, sprint, " and [System.Tags] not contains 'history'"))
      .map((w) => mapWorkItem(w, team.key, sprint.key))
      .filter((s): s is Story => s !== null);
  },

  async getCompletedPoints(team, sprint) {
    return (await workItems(team, sprint, " and [System.State] = 'Closed'")).reduce(
      (n, w) => n + (Number(w.fields["Microsoft.VSTS.Scheduling.StoryPoints"]) || 0),
      0,
    );
  },
};
