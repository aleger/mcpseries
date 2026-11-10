"""Common shapes both tracker adapters return. JSON uses camelCase, Python uses snake_case."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Tracker = Literal["clickup", "azure-devops"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Member(_Model):
    name: str
    role: str
    hours_per_day: float
    pto_days: dict[str, int]


class TeamConfig(_Model):
    key: str
    name: str
    tracker: Tracker
    #: Story key prefix, e.g. MOB. Used to tell which tracker a dependency lives in.
    key_prefix: str
    clickup: dict[str, str] | None = None
    azure_devops: dict[str, str] | None = None
    members: list[Member]


class Sprint(_Model):
    key: str
    name: str
    start: str
    end: str
    working_days: int
    state: str


class Company(_Model):
    name: str
    focus_factor: float
    hours_per_day: float


class Dependency(_Model):
    key: str
    description: str
    resolved: bool


class Story(_Model):
    key: str
    title: str
    description: str
    acceptance_criteria: list[str]
    story_points: float | None
    has_ui: bool
    design_link: str | None
    dependencies: list[Dependency]
    assignee: str | None
    release_name: str | None
    sprint_key: str | None
    status: str
    team_key: str


class DorRule(_Model):
    id: str
    name: str
    check: str
    severity: Literal["blocker", "warning"]
    fix: str


class TeamsConfig(_Model):
    company: Company
    sprints: list[Sprint]
    teams: list[TeamConfig]
