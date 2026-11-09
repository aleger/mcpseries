import { NotFoundError } from "@/lib/data";
import { TrackerError } from "@/lib/adapters/http";

export const json = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }],
});

/**
 * Clear MCP error message, never a stack trace. NotFoundError and TrackerError messages are written
 * to be client-safe (no tokens, no response bodies); anything else is logged and reduced to a generic line.
 */
export function toolError(err: unknown) {
  const safe = err instanceof NotFoundError || err instanceof TrackerError;
  if (!safe) console.error("tool error", err);
  const message = safe ? err.message : "Internal error while computing the result.";
  return { isError: true, content: [{ type: "text" as const, text: message }] };
}
