/** Tiny per-process TTL cache so one tool call does not hit a tracker twice for the same request. */
const TTL_MS = 60_000;
const cache = new Map<string, { at: number; value: Promise<unknown> }>();

export function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value as Promise<T>;
  const value = load();
  cache.set(key, { at: Date.now(), value });
  value.catch(() => cache.delete(key));
  return value;
}

export function clearCache() {
  cache.clear();
}

export class TrackerError extends Error {}

export function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new TrackerError(`Server is missing configuration (${name}).`);
  return v;
}

/**
 * Parse a tracker response as JSON. Azure DevOps answers a rejected or missing PAT with
 * 203 and an HTML sign-in page (which `res.ok` accepts), so check the content type, not just the status.
 */
export async function readJson(res: Response, service: string, credential: string, hint: string): Promise<any> {
  const type = res.headers.get("content-type") ?? "";
  if (res.status === 401 || res.status === 403 || res.status === 203 || !type.includes("json")) {
    console.error(`${service} auth/format failure: status ${res.status}, content-type "${type}"`);
    throw new TrackerError(`${service} rejected the server's credentials. Check ${credential} (${hint}).`);
  }
  if (!res.ok) throw new TrackerError(`${service} request failed (${res.status}).`);
  return res.json();
}
