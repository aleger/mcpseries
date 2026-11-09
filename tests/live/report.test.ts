import { it } from "vitest";
import expected from "@/data/expected-answers.json";
import { checkDefinitionOfReady } from "@/lib/tools/check-definition-of-ready";

// Prints live results next to expected-answers.json. Asserted in live.test.ts.
it("report", async () => {
  const rows: Record<string, unknown>[] = [];
  for (const team of Object.keys(expected) as (keyof typeof expected)[]) {
    const e = expected[team];
    const r = await checkDefinitionOfReady(team, "sprint-24");
    const same = (a: unknown, b: unknown) => (JSON.stringify(a) === JSON.stringify(b) ? "ok" : "MISMATCH");
    rows.push({
      team,
      notReady: `${r.notReady.join(",")} [${same(r.notReady, e.notReady)}]`,
      committed: `${r.committedPoints} vs ${e.committedPoints} [${same(r.committedPoints, e.committedPoints)}]`,
      ready: `${r.readyPoints} vs ${e.readyPoints} [${same(r.readyPoints, e.readyPoints)}]`,
      velocity: `${r.avgVelocity} vs ${e.avgVelocity} [${same(r.avgVelocity, e.avgVelocity)}]`,
      commitPct: `${r.commitPctOfVelocity} vs ${e.commitPctOfVelocity} [${same(r.commitPctOfVelocity, e.commitPctOfVelocity)}]`,
    });
  }
  console.table(rows);
});
