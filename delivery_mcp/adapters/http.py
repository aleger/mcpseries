"""Shared plumbing for the read-only adapters: TTL cache, errors, response checks."""

import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, Any]] = {}


async def cached[T](key: str, load: Callable[[], Awaitable[T]]) -> T:
    """Per-process 60 second cache so one tool call does not hit a tracker twice for the same request."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        return hit[1]
    value = await load()
    _cache[key] = (time.monotonic(), value)
    return value


def clear_cache() -> None:
    _cache.clear()


class TrackerError(Exception):
    """A tracker problem whose message is safe to show the client (never contains a secret)."""


def require(value: str | None, name: str) -> str:
    if not value:
        raise TrackerError(f"Server is missing configuration ({name}).")
    return value


def read_json(res: httpx.Response, service: str, credential: str, hint: str) -> Any:
    """Parse a tracker response as JSON. Azure DevOps answers a rejected or missing PAT with
    203 and an HTML sign-in page (which a status-only check accepts), so check the content type too."""
    ctype = res.headers.get("content-type", "")
    if res.status_code in (401, 403, 203) or "json" not in ctype:
        raise TrackerError(f"{service} rejected the server's credentials. Check {credential} ({hint}).")
    if res.is_error:
        raise TrackerError(f"{service} request failed ({res.status_code}).")
    return res.json()
