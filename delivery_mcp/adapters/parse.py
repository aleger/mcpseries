"""Seeded descriptions are a user story sentence, then an optional
    Dependencies:
    - KEY: text (resolved: false)
section. These helpers split that back apart. Pure, no I/O."""

import re

from delivery_mcp.models import Dependency

KEY_RE = re.compile(r"^([A-Z]{3}-\d+):\s*(.*)$")
RELEASE_TAG_PREFIX = "release-"
_HEADING = re.compile(r"^[A-Za-z][A-Za-z -]*:\s*$")
_DEP = re.compile(r"^([A-Z]+-\d+):\s*(.*?)\s*\(resolved:\s*(true|false)\)\s*$", re.I)


def parse_dependency_line(line: str) -> Dependency | None:
    m = _DEP.match(re.sub(r"^[-*]\s*", "", line.strip()))
    return Dependency(key=m[1], description=m[2], resolved=m[3].lower() == "true") if m else None


def split_description(text: str) -> tuple[str, list[Dependency]]:
    lines = text.replace("\r", "").split("\n")
    first = next((i for i, line in enumerate(lines) if _HEADING.match(line.strip())), -1)
    description = "\n".join(lines if first == -1 else lines[:first]).strip()
    deps: list[Dependency] = []
    in_deps = False
    for line in [] if first == -1 else lines[first:]:
        if _HEADING.match(line.strip()):
            in_deps = bool(re.match(r"^dependencies:", line.strip(), re.I))
        elif in_deps and (d := parse_dependency_line(line)):
            deps.append(d)
    return description, deps


def html_to_text(html: str) -> str:
    """Strip tags and decode the few entities the seed writes."""
    s = re.sub(r"</(p|li|h\d|div)>", "\n", html, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    return "\n".join(t for line in s.split("\n") if (t := line.strip()))


def html_list_items(html: str | None) -> list[str]:
    if not html:
        return []
    return [t for m in re.finditer(r"<li[^>]*>([\s\S]*?)</li>", html, re.I) if (t := html_to_text(m[1]))]


def split_ado_description(html: str | None) -> tuple[str, list[Dependency]]:
    """ADO description HTML -> the same (description, dependencies) split_description returns."""
    if not html:
        return "", []
    main, *rest = re.split(r"<h3[^>]*>\s*Dependencies\s*</h3>", html, maxsplit=1, flags=re.I)
    deps = [d for item in html_list_items(rest[0] if rest else "") if (d := parse_dependency_line(item))]
    return html_to_text(main), deps
