import type { DorRule, Story } from "@/lib/types";

export interface RuleFailure {
  ruleId: string;
  name: string;
  severity: "blocker" | "warning";
  fix: string;
}

export interface StoryCheck {
  key: string;
  title: string;
  storyPoints: number | null;
  ready: boolean;
  blockers: RuleFailure[];
  warnings: RuleFailure[];
}

/** Rule predicates keyed by rule id. Rule metadata (severity, fix text) comes from definition-of-ready.json. */
const predicates: Record<string, (s: Story) => boolean> = {
  "DOR-1": (s) => {
    const d = s.description.trim();
    return d.startsWith("As a") && d.includes("I want") && d.includes("so that");
  },
  "DOR-2": (s) => s.acceptanceCriteria.length >= 2,
  "DOR-3": (s) => s.storyPoints !== null && s.storyPoints >= 1 && s.storyPoints <= 8,
  "DOR-4": (s) => !s.dependencies.some((d) => d.resolved === false),
  "DOR-5": (s) => !s.hasUi || (s.designLink !== null && s.designLink !== ""),
};

export function checkStory(story: Story, rules: DorRule[]): StoryCheck {
  const failures: RuleFailure[] = rules
    .filter((r) => {
      const p = predicates[r.id];
      if (!p) throw new Error(`No evaluator for rule ${r.id}`);
      return !p(story);
    })
    .map((r) => ({ ruleId: r.id, name: r.name, severity: r.severity, fix: r.fix }));
  const blockers = failures.filter((f) => f.severity === "blocker");
  return {
    key: story.key,
    title: story.title,
    storyPoints: story.storyPoints,
    ready: blockers.length === 0,
    blockers,
    warnings: failures.filter((f) => f.severity === "warning"),
  };
}

export interface ReadinessSummary {
  stories: StoryCheck[];
  notReady: string[];
  committedPoints: number;
  readyPoints: number;
  avgVelocity: number;
  commitPctOfVelocity: number;
}

export function summarizeReadiness(
  stories: Story[],
  rules: DorRule[],
  completedVelocity: number[],
): ReadinessSummary {
  const checks = stories.map((s) => checkStory(s, rules));
  const committedPoints = checks.reduce((n, c) => n + (c.storyPoints ?? 0), 0);
  const readyPoints = checks.filter((c) => c.ready).reduce((n, c) => n + (c.storyPoints ?? 0), 0);
  const avgVelocity = completedVelocity.length
    ? completedVelocity.reduce((a, b) => a + b, 0) / completedVelocity.length
    : 0;
  return {
    stories: checks,
    notReady: checks.filter((c) => !c.ready).map((c) => c.key),
    committedPoints,
    readyPoints,
    avgVelocity,
    commitPctOfVelocity: avgVelocity ? Math.round((committedPoints / avgVelocity) * 100) : 0,
  };
}
