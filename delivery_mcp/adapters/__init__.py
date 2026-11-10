"""Read-only tracker adapters. Both return the common Story shape."""

from typing import Protocol

from delivery_mcp.models import Sprint, Story, TeamConfig


class TrackerAdapter(Protocol):
    async def get_sprint_stories(self, team: TeamConfig, sprint: Sprint) -> list[Story]: ...

    async def get_completed_points(self, team: TeamConfig, sprint: Sprint) -> float:
        """Story points closed in `sprint`, read from the tracker."""
        ...


def adapter_for(tracker: str) -> TrackerAdapter:
    """Pick the adapter for a team's tracker (config/teams.json)."""
    if tracker == "clickup":
        from delivery_mcp.adapters.clickup import ClickUpAdapter

        return ClickUpAdapter()
    if tracker == "azure-devops":
        from delivery_mcp.adapters.azure_devops import AzureDevOpsAdapter

        return AzureDevOpsAdapter()
    raise ValueError(f"Unknown tracker {tracker}")
