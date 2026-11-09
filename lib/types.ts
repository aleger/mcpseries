export type Tracker = "clickup" | "azure-devops";

export interface Member {
  name: string;
  role: string;
  hoursPerDay: number;
  ptoDays: Record<string, number>;
}

export interface TeamConfig {
  key: string;
  name: string;
  tracker: Tracker;
  /** Story key prefix, e.g. MOB. Used to tell which tracker a dependency lives in. */
  keyPrefix: string;
  clickup?: { folder: string };
  azureDevops?: { areaPath: string };
  members: Member[];
}

export interface Sprint {
  key: string;
  name: string;
  start: string;
  end: string;
  workingDays: number;
  state: string;
}

export interface Dependency {
  key: string;
  description: string;
  resolved: boolean;
}

/** Common story shape both adapters return. */
export interface Story {
  key: string;
  title: string;
  description: string;
  acceptanceCriteria: string[];
  storyPoints: number | null;
  hasUi: boolean;
  designLink: string | null;
  dependencies: Dependency[];
  assignee: string | null;
  releaseName: string | null;
  sprintKey: string | null;
  status: string;
  teamKey: string;
}

export interface Company {
  name: string;
  focusFactor: number;
  hoursPerDay: number;
}

export interface TeamsConfig {
  company: Company;
  sprints: Sprint[];
  teams: TeamConfig[];
}

export interface DorRule {
  id: string;
  name: string;
  check: string;
  severity: "blocker" | "warning";
  fix: string;
}
