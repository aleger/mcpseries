import { describe, expect, it } from "vitest";
import expected from "@/data/expected-answers.json";
import { checkDefinitionOfReady } from "@/lib/tools/check-definition-of-ready";
import { getSprintCapacity } from "@/lib/tools/get-sprint-capacity";

// Opt-in: npm run test:live. Calls the real adapters against the demo workspaces. Run after every seed.
const teams = Object.keys(expected) as (keyof typeof expected)[];

describe.each(teams)("Sprint 24 (live trackers) – %s", (team) => {
  const exp = expected[team];

  it("capacity", () => {
    const c = getSprintCapacity(team, "sprint-24");
    expect(c.rawHours).toBe(exp.rawHours);
    expect(c.focusHours).toBeCloseTo(exp.focusHours, 5);
  });

  it("definition of ready", async () => {
    const r = await checkDefinitionOfReady(team, "sprint-24");
    expect(r.stories).toHaveLength(exp.stories);
    expect(r.notReady).toEqual(exp.notReady);
    expect(r.committedPoints).toBe(exp.committedPoints);
    expect(r.readyPoints).toBe(exp.readyPoints);
    expect(r.avgVelocity).toBe(exp.avgVelocity);
    expect(r.commitPctOfVelocity).toBe(exp.commitPctOfVelocity);
  });
});
