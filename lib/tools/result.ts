import { NotFoundError } from "@/lib/data";

export const json = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }],
});

/** Clear MCP error message, no stack traces to the client. */
export function toolError(err: unknown) {
  const message = err instanceof NotFoundError ? err.message : "Internal error while computing the result.";
  if (!(err instanceof NotFoundError)) console.error("tool error", err);
  return { isError: true, content: [{ type: "text" as const, text: message }] };
}
