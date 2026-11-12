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


def _has_user_story_format(story: Story) -> bool:
    description = story.description.strip()
    return description.startswith("As a") and "I want" in description and "so that" in description


def _has_acceptance_criteria(story: Story) -> bool:
    return len(story.acceptance_criteria) >= 2


def _has_sprint_sized_estimate(story: Story) -> bool:
    return story.story_points is not None and 1 <= story.story_points <= 8


def _has_no_open_dependencies(story: Story) -> bool:
    return not any(dependency.resolved is False for dependency in story.dependencies)


def _has_design_link_if_ui(story: Story) -> bool:
    return not story.has_ui or bool(story.design_link)


# One check per rule id. A check returns True when the story passes. The rule's name,
# severity and fix text are not repeated here: they come from data/definition-of-ready.json.
PREDICATES: dict[str, Callable[[Story], bool]] = {
    "DOR-1": _has_user_story_format,
    "DOR-2": _has_acceptance_criteria,
    "DOR-3": _has_sprint_sized_estimate,
    "DOR-4": _has_no_open_dependencies,
    "DOR-5": _has_design_link_if_ui,
}


def no_known_tracker(key: str) -> str | None:
    """Default lookup for callers without team config: every dependency counts as external."""
    return None


def check_story(
    story: Story,
    rules: Sequence[DorRule],
    tracker_of_key: TrackerOfKey = no_known_tracker,
    story_tracker: str | None = None,
) -> StoryCheck:
    """Run every Definition of Ready rule against one story."""
    failures: list[RuleFailure] = []

    for rule in rules:
        passes = PREDICATES.get(rule.id)
        if passes is None:
            raise ValueError(f"No evaluator for rule {rule.id}")
        if passes(story):
            continue

        if rule.id != "DOR-4":
            failures.append(RuleFailure(rule.id, rule.name, rule.severity, rule.fix))
            continue

        # The dependency rule reports one failure per unresolved dependency, so the reader
        # sees what is blocking the story and where that work lives.
        for dependency in story.dependencies:
            if dependency.resolved:
                continue
            dependency_tracker = tracker_of_key(dependency.key)
            is_cross_tool = dependency_tracker is not None and dependency_tracker != story_tracker
            failures.append(
                RuleFailure(
                    rule.id,
                    rule.name,
                    rule.severity,
                    rule.fix,
                    depends_on=dependency.key,
                    description=dependency.description,
                    cross_tool=is_cross_tool,
                )
            )

    blockers = [failure for failure in failures if failure.severity == "blocker"]
    warnings = [failure for failure in failures if failure.severity == "warning"]

    # Warnings are reported but do not stop a story from being ready.
    return StoryCheck(
        key=story.key,
        title=story.title,
        story_points=story.story_points,
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
    )


def summarize_readiness(
    stories: Sequence[Story],
    rules: Sequence[DorRule],
    completed_velocity: Sequence[float],
    tracker_of_key: TrackerOfKey = no_known_tracker,
    story_tracker: str | None = None,
) -> ReadinessSummary:
    """Check every story, then compare the committed points with the team's recent velocity.

    `completed_velocity` holds the points completed in each earlier sprint.
    """
    checks = [check_story(story, rules, tracker_of_key, story_tracker) for story in stories]

    # A story without an estimate adds nothing to the totals. DOR-3 already reports it.
    committed_points = sum(check.story_points or 0 for check in checks)
    ready_points = sum(check.story_points or 0 for check in checks if check.ready)

    # A team with no closed sprints, or none that completed any points, has no velocity
    # to compare against. Report zero for both figures instead of dividing by zero.
    avg_velocity = 0.0
    if completed_velocity:
        avg_velocity = sum(completed_velocity) / len(completed_velocity)

    commit_pct_of_velocity = 0
    if avg_velocity:
        commit_pct_of_velocity = int(round_half_up(committed_points / avg_velocity * 100))

    return ReadinessSummary(
        stories=checks,
        not_ready=[check.key for check in checks if not check.ready],
        committed_points=committed_points,
        ready_points=ready_points,
        avg_velocity=avg_velocity,
        commit_pct_of_velocity=commit_pct_of_velocity,
    )
