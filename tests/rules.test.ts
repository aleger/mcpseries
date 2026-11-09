import { beforeAll, afterAll, describe, expect, it } from "vitest";
import expected from "@/data/expected-answers.json";
import { setAdapterOverride } from "@/lib/adapters";
import { company, getSprint, getTeam } from "@/lib/data";
import { computeCapacity } from "@/lib/rules/capacity";
import { checkDefinitionOfReady } from "@/lib/tools/check-definition-of-ready";
import { fixtureAdapter } from "./fixtures";

beforeAll(() => setAdapterOverride({ clickup: fixtureAdapter, "azure-devops": fixtureAdapter }));
afterAll(() => setAdapterOverride(null));

const teams = Object.keys(expected) as (keyof typeof expected)[];

describe.each(teams)("Sprint 24 (fixtures) – %s", (team) => {
  const exp = expected[team];

  it("capacity matches expected", () => {
    const c = computeCapacity(getTeam(team), getSprint("sprint-24"), company());
    expect(c.rawHours).toBe(exp.rawHours);
    expect(c.focusHours).toBeCloseTo(exp.focusHours, 5);
    expect(c.source).toBe("config");
  });

  it("definition of ready matches expected", async () => {
    const r = await checkDefinitionOfReady(team, "sprint-24");
    expect(r.stories).toHaveLength(exp.stories);
    expect(r.notReady).toEqual(exp.notReady);
    expect(r.committedPoints).toBe(exp.committedPoints);
    expect(r.readyPoints).toBe(exp.readyPoints);
    expect(r.avgVelocity).toBe(exp.avgVelocity);
    expect(r.commitPctOfVelocity).toBe(exp.commitPctOfVelocity);
    const failures = Object.fromEntries(
      r.stories
        .filter((s) => s.blockers.length || s.warnings.length)
        .map((s) => [s.key, [...s.blockers, ...s.warnings].map((f) => f.rule).sort()]),
    );
    expect(failures).toEqual(exp.failures);
    expect(r.stories.filter((s) => s.ready && s.warnings.length).map((s) => s.key)).toEqual(exp.warningsOnly);
  });
});

describe("errors", () => {
  it("rejects unknown teams with a helpful message", () => {
    expect(() => getTeam("nope")).toThrow(/Valid teams/);
  });
});
