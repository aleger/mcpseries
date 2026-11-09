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
