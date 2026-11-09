import { createMcpHandler } from "mcp-handler";
import { registerGetSprintCapacity } from "@/lib/tools/get-sprint-capacity";
import { registerCheckDefinitionOfReady } from "@/lib/tools/check-definition-of-ready";

// Stateless MCP endpoint (spec 2026-07-28). Served at /mcp.
const handler = createMcpHandler(
  (server) => {
    registerGetSprintCapacity(server);
    registerCheckDefinitionOfReady(server);
  },
  { serverInfo: { name: "delivery-mcp", version: "0.1.0" } },
);

export { handler as GET, handler as POST };
