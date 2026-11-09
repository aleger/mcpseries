import northwind from "../../data/northwind.json" with { type: "json" };

export interface SeedStory {
  key: string;
  title: string;
  description: string;
  acceptanceCriteria: string[];
  storyPoints: number | null;
  hasUi: boolean;
  designLink: string | null;
  dependencies: { key: string; description: string; resolved: boolean }[];
  assignee: string;
  releaseKey: string | null;
  sprintKey: string | null;
  status: string;
  teamKey: string;
  injectionTest?: boolean;
}
export interface SeedHistory {
  key: string;
  teamKey: string;
  sprintKey: string;
  title: string;
  storyPoints: number;
  status: "Done" | "Not done";
}
export interface SeedData {
  teams: { key: string; name: string; tracker: "clickup" | "azure-devops" }[];
  sprints: { key: string; name: string; start: string; end: string }[];
  releases: { key: string; name: string; date: string; scope: string; teams: string[] }[];
  stories: SeedStory[];
  historyStories: SeedHistory[];
}

export const seed = northwind as unknown as SeedData;
export const releaseName = (key: string | null) => seed.releases.find((r) => r.key === key)?.name ?? null;
export const sprintName = (key: string | null) => seed.sprints.find((s) => s.key === key)?.name ?? null;

/** Cross-tool references: stories in one tracker that depend on a story in the other. */
export function crossToolRefs(story: SeedStory): { dependsOn: string[]; neededBy: string[] } {
  const tracker = (key: string) => seed.teams.find((t) => t.key === (seed.stories.find((s) => s.key === key)?.teamKey))?.tracker;
  const mine = tracker(story.key);
  return {
    dependsOn: story.dependencies.map((d) => d.key).filter((k) => tracker(k) && tracker(k) !== mine),
    neededBy: seed.stories
      .filter((s) => s.dependencies.some((d) => d.key === story.key) && tracker(s.key) !== mine)
      .map((s) => s.key),
  };
}

export function loadEnv(...names: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const n of names) {
    const v = process.env[n];
    if (!v) throw new Error(`${n} is not set (put it in .env.local).`);
    out[n] = v;
  }
  return out;
}
