import { beforeAll, afterAll, describe, expect, it } from "vitest";
import expected from "@/data/expected-answers.json";
import { setAdapterOverride } from "@/lib/adapters";
import { company, getSprint, getTeam } from "@/lib/data";
import { computeCapacity } from "@/lib/rules/capacity";
import { checkDefinitionOfReady } from "@/lib/tools/check-definition-of-ready";
import { checkStory } from "@/lib/rules/dor";
import { dorRules, trackerOfKey } from "@/lib/data";
import type { Story } from "@/lib/types";
import { fixtureAdapter } from "./fixtures";
import { dependencyBlockersOf } from "./helpers";

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
    expect(dependencyBlockersOf(r)).toEqual(exp.dependencyBlockers);
  });
});

describe("errors", () => {
  it("rejects unknown teams with a helpful message", () => {
    expect(() => getTeam("nope")).toThrow(/Valid teams/);
  });
});

describe("DOR-4 dependency detail", () => {
  const base: Story = {
    key: "MOB-999", title: "t", description: "As a x, I want y, so that z.", acceptanceCriteria: ["a", "b"],
    storyPoints: 3, hasUi: false, designLink: null, dependencies: [], assignee: null, releaseName: null,
    sprintKey: "sprint-24", status: "New", teamKey: "mobile",
  };
  const check = (deps: Story["dependencies"]) =>
    checkStory({ ...base, dependencies: deps }, dorRules(), trackerOfKey, "azure-devops").blockers;

  it("flags a dependency in the other tracker as crossTool", () => {
    expect(check([{ key: "DAT-307", description: "Delay prediction API from Data team", resolved: false }])).toMatchObject([
      { ruleId: "DOR-4", dependsOn: "DAT-307", description: "Delay prediction API from Data team", crossTool: true },
    ]);
  });
  it("does not flag a same-tracker or external dependency as crossTool", () => {
    const b = check([
      { key: "MOB-205", description: "same tracker", resolved: false },
      { key: "SEC-12", description: "external", resolved: false },
    ]);
    expect(b.map((x) => [x.dependsOn, x.crossTool])).toEqual([["MOB-205", false], ["SEC-12", false]]);
  });
  it("ignores resolved dependencies", () => {
    expect(check([{ key: "DAT-307", description: "done", resolved: true }])).toEqual([]);
  });
});
