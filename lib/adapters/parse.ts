import type { Dependency } from "@/lib/types";

/**
 * Seeded descriptions are: a user story sentence, then an optional
 *   Dependencies:
 *   - KEY: text (resolved: false)
 * section. These helpers split that back apart. Pure, no I/O.
 */
export function splitDescription(text: string): { description: string; dependencies: Dependency[] } {
  const lines = text.replace(/\r/g, "").split("\n");
  const isHeading = (l: string) => /^[A-Za-z][A-Za-z -]*:\s*$/.test(l.trim());
  const first = lines.findIndex(isHeading);
  const description = (first === -1 ? lines : lines.slice(0, first)).join("\n").trim();
  const dependencies: Dependency[] = [];
  let inDeps = false;
  for (const l of first === -1 ? [] : lines.slice(first)) {
    if (isHeading(l)) inDeps = /^dependencies:/i.test(l.trim());
    else if (inDeps) {
      const d = parseDependencyLine(l);
      if (d) dependencies.push(d);
    }
  }
  return { description, dependencies };
}

export function parseDependencyLine(line: string): Dependency | null {
  const m = line.trim().replace(/^[-*]\s*/, "").match(/^([A-Z]+-\d+):\s*(.*?)\s*\(resolved:\s*(true|false)\)\s*$/i);
  return m ? { key: m[1], description: m[2], resolved: m[3].toLowerCase() === "true" } : null;
}

/** Strip tags and decode the few entities the seed writes. */
export function htmlToText(html: string): string {
  return html
    .replace(/<\/(p|li|h\d|div)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&nbsp;/g, " ")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .join("\n");
}

export function htmlListItems(html: string | undefined): string[] {
  if (!html) return [];
  return [...html.matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)].map((m) => htmlToText(m[1])).filter(Boolean);
}

/** ADO description HTML -> same shape splitDescription expects. */
export function splitAdoDescription(html: string | undefined): { description: string; dependencies: Dependency[] } {
  if (!html) return { description: "", dependencies: [] };
  const [main, deps = ""] = html.split(/<h3[^>]*>\s*Dependencies\s*<\/h3>/i);
  return {
    description: htmlToText(main),
    dependencies: htmlListItems(deps).map(parseDependencyLine).filter((d): d is Dependency => d !== null),
  };
}

export const sprintNameToKey = (name: string) => name.toLowerCase().replace(/\s+/g, "-");
export const KEY_RE = /^([A-Z]{3}-\d+):\s*(.*)$/;
export const RELEASE_TAG_PREFIX = "release-";
