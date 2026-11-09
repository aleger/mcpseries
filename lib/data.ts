import northwind from "@/data/northwind.json";
import dor from "@/data/definition-of-ready.json";
import type { Dataset, DorRule, Sprint, Story, Team } from "@/lib/types";

// v0.1 reads the seeded Northwind demo data bundled with the app. Read-only by design.
const dataset = northwind as unknown as Dataset;
const rules = dor.rules as DorRule[];

export class NotFoundError extends Error {}

export const company = () => dataset.company;
export const dorRules = () => rules;

export function getTeam(key: string): Team {
  const t = dataset.teams.find((x) => x.key === key.toLowerCase() || x.name.toLowerCase() === key.toLowerCase());
  if (!t) throw new NotFoundError(`Unknown team "${key}". Valid teams: ${dataset.teams.map((x) => x.key).join(", ")}.`);
  return t;
}

export function getSprint(key: string): Sprint {
  const norm = key.toLowerCase().replace(/\s+/g, "-");
  const s = dataset.sprints.find((x) => x.key === norm);
  if (!s) throw new NotFoundError(`Unknown sprint "${key}". Valid sprints: ${dataset.sprints.map((x) => x.key).join(", ")}.`);
  return s;
}

export function getStories(teamKey: string, sprintKey: string): Story[] {
  return dataset.stories.filter((s) => s.teamKey === teamKey && s.sprintKey === sprintKey);
}

/** Average `completed` points over the sprints that closed before `sprintKey`. */
export function priorCompletedVelocity(teamKey: string, sprintKey: string): number[] {
  const order = dataset.sprints.map((s) => s.key);
  const idx = order.indexOf(sprintKey);
  const byTeam = dataset.velocity[teamKey] ?? {};
  return order
    .slice(0, idx)
    .filter((k) => byTeam[k])
    .map((k) => byTeam[k].completed);
}
