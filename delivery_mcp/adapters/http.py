import time
from typing import Any

import httpx

# Tracker responses are kept per process for a minute, so follow-up questions about
# the same sprint do not hit the tracker again.
TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, Any]] = {}


def cache_get(key: str) -> Any | None:
    """Return the cached value for `key`, or None if there is none or it has expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.monotonic() - stored_at >= TTL_SECONDS:
        return None
    return value


def cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


def clear_cache() -> None:
    _cache.clear()


class TrackerError(Exception):
    """A tracker problem whose message is safe to show the client (never contains a secret)."""


def require(value: str | None, name: str) -> str:
    """Return a required setting, or fail with a message that names the missing variable."""
    if not value:
        raise TrackerError(f"Server is missing configuration ({name}).")
    return value


def read_json(response: httpx.Response, service: str, credential: str, hint: str) -> Any:
    """Parse a tracker response as JSON, turning credential and HTTP failures into TrackerError."""
    # Azure DevOps answers a rejected or missing PAT with status 203 and an HTML sign-in
    # page. A status-only check would accept that, so the content type is checked as well.
    content_type = response.headers.get("content-type", "")
    if response.status_code in (401, 403, 203) or "json" not in content_type:
        raise TrackerError(f"{service} rejected the server's credentials. Check {credential} ({hint}).")
    if response.is_error:
        raise TrackerError(f"{service} request failed ({response.status_code}).")
    return response.json()
