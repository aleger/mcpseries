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
    for m in team.members:
        pto = m.pto_days.get(sprint.key, 0)
        days = max(0, sprint.working_days - pto)
        members.append(MemberCapacity(m.name, m.role, m.hours_per_day, pto, days, m.hours_per_day * days))
    raw = sum(m.hours for m in members)
    return TeamCapacity(
        team=team.key,
        sprint=sprint.key,
        working_days=sprint.working_days,
        focus_factor=company.focus_factor,
        members=members,
        raw_hours=raw,
        focus_hours=round_half_up(raw * company.focus_factor, 1),
    )
