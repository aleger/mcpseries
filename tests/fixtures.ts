import northwind from "@/data/northwind.json";
import type { TrackerAdapter } from "@/lib/adapters/types";
import type { Story } from "@/lib/types";

/** Unit-test fixture adapter built from the seed JSON. The server itself never reads this file. */
interface SeedStory extends Omit<Story, "releaseName" | "assignee" | "sprintKey"> {
  releaseKey: string | null;
  assignee: string;
  sprintKey: string | null;
}
const seed = northwind as unknown as {
  releases: { key: string; name: string }[];
  stories: SeedStory[];
  historyStories: { teamKey: string; sprintKey: string; storyPoints: number; status: string }[];
};

export const fixtureAdapter: TrackerAdapter = {
  async getSprintStories(team, sprint) {
    return seed.stories
      .filter((s) => s.teamKey === team.key && s.sprintKey === sprint.key)
      .map(({ releaseKey, ...s }) => ({
        ...s,
        releaseName: seed.releases.find((r) => r.key === releaseKey)?.name ?? null,
      }));
  },
  async getCompletedPoints(team, sprint) {
    return seed.historyStories
      .filter((h) => h.teamKey === team.key && h.sprintKey === sprint.key && h.status === "Done")
      .reduce((n, h) => n + h.storyPoints, 0);
  },
};
