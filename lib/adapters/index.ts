import type { Tracker } from "@/lib/types";
import type { TrackerAdapter } from "./types";
import { clickupAdapter } from "./clickup";
import { azureDevopsAdapter } from "./azure-devops";

const adapters: Record<Tracker, TrackerAdapter> = {
  clickup: clickupAdapter,
  "azure-devops": azureDevopsAdapter,
};

let override: Partial<Record<Tracker, TrackerAdapter>> | null = null;

/** Tests inject fixture adapters here. Production never calls this. */
export function setAdapterOverride(o: Partial<Record<Tracker, TrackerAdapter>> | null) {
  override = o;
}

export function adapterFor(tracker: Tracker): TrackerAdapter {
  return override?.[tracker] ?? adapters[tracker];
}
