from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from delivery_mcp.models import DorRule, Story
from delivery_mcp.rules.mathutil import round_half_up

#: Tracker lookup for a story key, or None for external keys such as SEC-12.
TrackerOfKey = Callable[[str], str | None]


@dataclass(frozen=True)
class RuleFailure:
    rule_id: str
    name: str
    severity: str
    fix: str
    #: DOR-4 only: the unresolved dependency behind this failure.
    depends_on: str | None = None
    description: str | None = None
    #: DOR-4 only: true when the dependency lives in a different tracker than the story.
    cross_tool: bool | None = None


@dataclass(frozen=True)
class StoryCheck:
    key: str
    title: str
    story_points: float | None
    ready: bool
    blockers: list[RuleFailure] = field(default_factory=list)
    warnings: list[RuleFailure] = field(default_factory=list)


@dataclass(frozen=True)
class ReadinessSummary:
    stories: list[StoryCheck]
    not_ready: list[str]
    committed_points: float
    ready_points: float
    avg_velocity: float
    commit_pct_of_velocity: int


# Rule predicates keyed by rule id. Rule metadata (severity, fix text) comes from definition-of-ready.json.
PREDICATES: dict[str, Callable[[Story], bool]] = {
    "DOR-1": lambda s: (d := s.description.strip()).startswith("As a") and "I want" in d and "so that" in d,
    "DOR-2": lambda s: len(s.acceptance_criteria) >= 2,
    "DOR-3": lambda s: s.story_points is not None and 1 <= s.story_points <= 8,
    "DOR-4": lambda s: not any(d.resolved is False for d in s.dependencies),
    "DOR-5": lambda s: not s.has_ui or bool(s.design_link),
}


def check_story(
    story: Story,
    rules: Sequence[DorRule],
    tracker_of_key: TrackerOfKey = lambda _key: None,
    story_tracker: str | None = None,
) -> StoryCheck:
    failures: list[RuleFailure] = []
    for rule in rules:
        predicate = PREDICATES.get(rule.id)
        if predicate is None:
            raise ValueError(f"No evaluator for rule {rule.id}")
        if predicate(story):
            continue
        if rule.id != "DOR-4":
            failures.append(RuleFailure(rule.id, rule.name, rule.severity, rule.fix))
            continue
        # One failure per unresolved dependency, so the reader sees what is blocking and where it lives.
        for dep in (d for d in story.dependencies if not d.resolved):
            dep_tracker = tracker_of_key(dep.key)
            failures.append(
                RuleFailure(
                    rule.id,
                    rule.name,
                    rule.severity,
                    rule.fix,
                    depends_on=dep.key,
                    description=dep.description,
                    cross_tool=dep_tracker is not None and dep_tracker != story_tracker,
                )
            )
    blockers = [f for f in failures if f.severity == "blocker"]
    return StoryCheck(
        key=story.key,
        title=story.title,
        story_points=story.story_points,
        ready=not blockers,
        blockers=blockers,
        warnings=[f for f in failures if f.severity == "warning"],
    )


def summarize_readiness(
    stories: Sequence[Story],
    rules: Sequence[DorRule],
    completed_velocity: Sequence[float],
    tracker_of_key: TrackerOfKey | None = None,
    story_tracker: str | None = None,
) -> ReadinessSummary:
    lookup = tracker_of_key or (lambda _key: None)
    checks = [check_story(s, rules, lookup, story_tracker) for s in stories]
    committed = sum(c.story_points or 0 for c in checks)
    ready = sum(c.story_points or 0 for c in checks if c.ready)
    avg = sum(completed_velocity) / len(completed_velocity) if completed_velocity else 0.0
    return ReadinessSummary(
        stories=checks,
        not_ready=[c.key for c in checks if not c.ready],
        committed_points=committed,
        ready_points=ready,
        avg_velocity=avg,
        commit_pct_of_velocity=int(round_half_up(committed / avg * 100)) if avg else 0,
    )
