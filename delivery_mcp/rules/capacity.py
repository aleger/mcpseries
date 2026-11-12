from dataclasses import dataclass
from typing import Literal

from delivery_mcp.models import Company, Sprint, TeamConfig
from delivery_mcp.rules.mathutil import round_half_up


@dataclass(frozen=True)
class MemberCapacity:
    name: str
    role: str
    hours_per_day: float
    pto_days: int
    working_days: int
    hours: float


@dataclass(frozen=True)
class TeamCapacity:
    team: str
    sprint: str
    working_days: int
    focus_factor: float
    members: list[MemberCapacity]
    raw_hours: float
    focus_hours: float
    #: Neither tracker exposes per-sprint capacity for the demo personas, so it comes from config/teams.json.
    source: Literal["config"] = "config"


def compute_capacity(team: TeamConfig, sprint: Sprint, company: Company) -> TeamCapacity:
    """hours = hoursPerDay x (workingDays - ptoDays); focusHours = rawHours x focusFactor."""
    members = []
    for member in team.members:
        pto_days = member.pto_days.get(sprint.key, 0)
        # More PTO than the sprint has working days still means zero hours, not negative.
        working_days = max(0, sprint.working_days - pto_days)
        members.append(
            MemberCapacity(
                name=member.name,
                role=member.role,
                hours_per_day=member.hours_per_day,
                pto_days=pto_days,
                working_days=working_days,
                hours=member.hours_per_day * working_days,
            )
        )

    raw_hours = sum(member.hours for member in members)

    # The focus factor is the share of raw hours a team can expect to spend on sprint work.
    focus_hours = round_half_up(raw_hours * company.focus_factor, 1)

    return TeamCapacity(
        team=team.key,
        sprint=sprint.key,
        working_days=sprint.working_days,
        focus_factor=company.focus_factor,
        members=members,
        raw_hours=raw_hours,
        focus_hours=focus_hours,
    )
