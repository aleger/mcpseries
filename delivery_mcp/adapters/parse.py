"""Seeded descriptions are a user story sentence, then an optional
    Dependencies:
    - KEY: text (resolved: false)
section. These helpers split that back apart. Pure, no I/O."""

import re

from delivery_mcp.models import Dependency

# Seeded stories are titled "KEY-123: Title". Anything else in the tracker is not a story.
KEY_RE = re.compile(r"^([A-Z]{3}-\d+):\s*(.*)$")
RELEASE_TAG_PREFIX = "release-"

_HEADING = re.compile(r"^[A-Za-z][A-Za-z -]*:\s*$")
_BULLET = re.compile(r"^[-*]\s*")
_DEPENDENCY = re.compile(r"^([A-Z]+-\d+):\s*(.*?)\s*\(resolved:\s*(true|false)\)\s*$", re.IGNORECASE)
_HTML_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&nbsp;", " "))


def tag_value(tags: list[str], prefix: str) -> str | None:
    """Return the rest of the first tag that starts with `prefix`, e.g. "release-2027.01.2" -> "2027.01.2"."""
    for tag in tags:
        if tag.startswith(prefix):
            return tag[len(prefix) :]
    return None


def parse_dependency_line(line: str) -> Dependency | None:
    """Parse one "KEY: text (resolved: true|false)" line. Returns None for any other line."""
    without_bullet = _BULLET.sub("", line.strip())
    match = _DEPENDENCY.match(without_bullet)
    if match is None:
        return None
    return Dependency(key=match[1], description=match[2], resolved=match[3].lower() == "true")


def split_description(text: str) -> tuple[str, list[Dependency]]:
    """Split a plain-text description into the user story and its dependencies."""
    lines = text.replace("\r", "").split("\n")

    # The user story runs up to the first "Heading:" line, or to the end if there is none.
    first_heading = len(lines)
    for index, line in enumerate(lines):
        if _HEADING.match(line.strip()):
            first_heading = index
            break
    description = "\n".join(lines[:first_heading]).strip()

    # Only the Dependencies section is read. Lines under any other heading are skipped.
    dependencies: list[Dependency] = []
    in_dependencies = False
    for line in lines[first_heading:]:
        stripped = line.strip()
        if _HEADING.match(stripped):
            in_dependencies = stripped.lower().startswith("dependencies:")
            continue
        if not in_dependencies:
            continue
        dependency = parse_dependency_line(line)
        if dependency is not None:
            dependencies.append(dependency)

    return description, dependencies


def html_to_text(html: str) -> str:
    """Strip tags and decode the few entities the seed writes."""
    text = re.sub(r"</(p|li|h\d|div)>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    for entity, character in _HTML_ENTITIES:
        text = text.replace(entity, character)

    stripped_lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in stripped_lines if line)


def html_list_items(html: str | None) -> list[str]:
    """Return the text of each non-empty <li> in an HTML fragment."""
    if not html:
        return []

    items = []
    for match in re.finditer(r"<li[^>]*>([\s\S]*?)</li>", html, re.IGNORECASE):
        text = html_to_text(match[1])
        if text:
            items.append(text)
    return items


def split_ado_description(html: str | None) -> tuple[str, list[Dependency]]:
    """Split an Azure DevOps HTML description the same way split_description splits plain text."""
    if not html:
        return "", []

    # The seed writes dependencies as a list under an <h3>Dependencies</h3> heading.
    parts = re.split(r"<h3[^>]*>\s*Dependencies\s*</h3>", html, maxsplit=1, flags=re.IGNORECASE)
    story_html = parts[0]
    dependencies_html = parts[1] if len(parts) > 1 else ""

    dependencies: list[Dependency] = []
    for item in html_list_items(dependencies_html):
        dependency = parse_dependency_line(item)
        if dependency is not None:
            dependencies.append(dependency)

    return html_to_text(story_html), dependencies
