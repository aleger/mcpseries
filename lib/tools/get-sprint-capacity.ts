import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/server";
import { company, getSprint, getTeam } from "@/lib/data";
import { computeCapacity } from "@/lib/rules/capacity";
import { json, toolError } from "./result";

export function getSprintCapacity(team: string, sprint: string) {
  return computeCapacity(getTeam(team), getSprint(sprint), company());
}

export function registerGetSprintCapacity(server: McpServer) {
  server.registerTool(
    "get_sprint_capacity",
    {
      title: "Get sprint capacity",
      description:
        "Returns a team's focus hours for a sprint after PTO: per-member hours (hoursPerDay x (workingDays - ptoDays)), rawHours, focusFactor and focusHours. Use when asked how much capacity a team has or whether PTO changes what they can commit.",
      inputSchema: z.object({
        team: z.string().describe("Team key or name, e.g. platform, mobile, data"),
        sprint: z.string().describe("Sprint key or name, e.g. sprint-24 or 'Sprint 24'"),
      }),
      annotations: { readOnlyHint: true },
    },
    async ({ team, sprint }) => {
      try {
        return json(getSprintCapacity(team, sprint));
      } catch (e) {
        return toolError(e);
      }
    },
  );
}
