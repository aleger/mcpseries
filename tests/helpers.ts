/** DOR-4 blockers of a check_definition_of_ready result, shaped like expected-answers.json `dependencyBlockers`. */
export function dependencyBlockersOf(result: {
  stories: { key: string; blockers: { rule: string; dependsOn?: string; description?: string; crossTool?: boolean }[] }[];
}) {
  return Object.fromEntries(
    result.stories
      .map((s) => [
        s.key,
        s.blockers
          .filter((b) => b.rule === "DOR-4")
          .map((b) => ({ rule: b.rule, dependsOn: b.dependsOn, description: b.description, crossTool: b.crossTool })),
      ] as const)
      .filter(([, blockers]) => blockers.length > 0),
  );
}
