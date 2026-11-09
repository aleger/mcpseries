import teamsConfig from "@/config/teams.json";
import dor from "@/data/definition-of-ready.json";
import { adapterFor } from "@/lib/adapters";
import type { DorRule, Sprint, Story, TeamConfig, TeamsConfig } from "@/lib/types";

// Team and capacity config and the DoR rule set are config. Story data is never read from here:
// it comes from the trackers through lib/adapters on every request.
const config = teamsConfig as unknown as TeamsConfig;
const rules = dor.rules as DorRule[];

export class NotFoundError extends Error {}

export const company = () => config.company;
export const dorRules = () => rules;

export function getTeam(key: string): TeamConfig {
  const k = key.toLowerCase();
  const t = config.teams.find((x) => x.key === k || x.name.toLowerCase() === k);
  if (!t) throw new NotFoundError(`Unknown team "${key}". Valid teams: ${config.teams.map((x) => x.key).join(", ")}.`);
  return t;
}

export function getSprint(key: string): Sprint {
  const norm = key.toLowerCase().replace(/\s+/g, "-");
  const s = config.sprints.find((x) => x.key === norm);
  if (!s) throw new NotFoundError(`Unknown sprint "${key}". Valid sprints: ${config.sprints.map((x) => x.key).join(", ")}.`);
  return s;
}

export async function getStories(team: TeamConfig, sprint: Sprint): Promise<Story[]> {
  const stories = await adapterFor(team.tracker).getSprintStories(team, sprint);
  return stories.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
}

/** Completed points in each of the (up to) two closed sprints before `sprint`, read from the tracker. */
export async function priorCompletedVelocity(team: TeamConfig, sprint: Sprint): Promise<number[]> {
  const idx = config.sprints.findIndex((s) => s.key === sprint.key);
  const prior = config.sprints.slice(0, idx).filter((s) => s.state === "closed").slice(-2);
  const adapter = adapterFor(team.tracker);
  return Promise.all(prior.map((s) => adapter.getCompletedPoints(team, s)));
}
