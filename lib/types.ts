export type Tracker = "clickup" | "azure-devops";

export interface Member {
  name: string;
  role: string;
  hoursPerDay: number;
  ptoDays: Record<string, number>;
}

export interface Team {
  key: string;
  name: string;
  tracker: Tracker;
  description: string;
  members: Member[];
}

export interface Sprint {
  key: string;
  name: string;
  start: string;
  end: string;
  workingDays: number;
  state: string;
  note?: string;
}

export interface Dependency {
  key: string;
  description: string;
  resolved: boolean;
}

export interface Story {
  key: string;
  title: string;
  description: string;
  acceptanceCriteria: string[];
  storyPoints: number | null;
  hasUi: boolean;
  designLink: string | null;
  dependencies: Dependency[];
  assignee: string;
  releaseKey: string | null;
  sprintKey: string;
  status: string;
  teamKey: string;
  injectionTest?: boolean;
}

export interface Release {
  key: string;
  name: string;
  date: string;
  scope: string;
  status: string;
  teams: string[];
}

export interface Company {
  name: string;
  note: string;
  timezone: string;
  focusFactor: number;
  hoursPerDay: number;
}

export interface Dataset {
  company: Company;
  teams: Team[];
  sprints: Sprint[];
  velocity: Record<string, Record<string, { committed: number; completed: number }>>;
  releases: Release[];
  stories: Story[];
}

export interface DorRule {
  id: string;
  name: string;
  check: string;
  severity: "blocker" | "warning";
  fix: string;
}
