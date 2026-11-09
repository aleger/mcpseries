import type { Sprint, Story, TeamConfig } from "@/lib/types";

/** Read-only view of a tracker. Adapters never write. */
export interface TrackerAdapter {
  /** Stories planned in a sprint, in the common Story shape. */
  getSprintStories(team: TeamConfig, sprint: Sprint): Promise<Story[]>;
  /** Story points that finished (Done / Closed) in a sprint. */
  getCompletedPoints(team: TeamConfig, sprint: Sprint): Promise<number>;
}
