import type { Company, Sprint, TeamConfig } from "@/lib/types";

export interface MemberCapacity {
  name: string;
  role: string;
  hoursPerDay: number;
  ptoDays: number;
  workingDays: number;
  hours: number;
}

export interface TeamCapacity {
  team: string;
  sprint: string;
  workingDays: number;
  focusFactor: number;
  members: MemberCapacity[];
  rawHours: number;
  focusHours: number;
  /** Neither tracker exposes per-sprint capacity for the demo personas, so it comes from config/teams.json. */
  source: "config";
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/** hours = hoursPerDay x (workingDays - ptoDays); focusHours = rawHours x focusFactor. */
export function computeCapacity(
  team: TeamConfig,
  sprint: Sprint,
  company: Pick<Company, "focusFactor">,
): TeamCapacity {
  const members = team.members.map((m) => {
    const ptoDays = m.ptoDays[sprint.key] ?? 0;
    const days = Math.max(0, sprint.workingDays - ptoDays);
    return {
      name: m.name,
      role: m.role,
      hoursPerDay: m.hoursPerDay,
      ptoDays,
      workingDays: days,
      hours: m.hoursPerDay * days,
    };
  });
  const rawHours = members.reduce((sum, m) => sum + m.hours, 0);
  return {
    team: team.key,
    sprint: sprint.key,
    workingDays: sprint.workingDays,
    focusFactor: company.focusFactor,
    members,
    rawHours,
    focusHours: round1(rawHours * company.focusFactor),
    source: "config",
  };
}
