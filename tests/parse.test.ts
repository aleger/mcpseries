import { describe, expect, it } from "vitest";
import { splitAdoDescription, splitDescription } from "@/lib/adapters/parse";
import { mapTask } from "@/lib/adapters/clickup";
import { mapWorkItem } from "@/lib/adapters/azure-devops";

// Contract tests: recorded-shape API payloads (no tokens, fictional data) map to the common Story shape.
const clickupTask = {
  name: "DAT-307: Delay prediction API",
  description:
    "As a data engineer, I want an API, so that mobile can show delays.\n\nDependencies:\n- DAT-302: Telematics ingestion (resolved: false)\n\nReferenced by:\n- MOB-210 (Azure DevOps) depends on this story",
  status: { status: "ready for sprint", type: "custom" },
  tags: [{ name: "release-2027.01.2" }, { name: "ui" }],
  custom_fields: [
    { name: "Story Points", value: "5" },
    { name: "Design Link", value: null },
    { name: "Owner", value: "Sam Rivera" },
  ],
  checklists: [{ name: "Acceptance Criteria", items: [{ name: "A" }, { name: "B" }] }],
};

const adoItem = {
  fields: {
    "System.Title": "MOB-210: Delay prediction banner",
    "System.Description":
      "<p>As a driver, I want a banner, so that I can warn customers. </p><h3>Dependencies </h3><ul><li>DAT-307: Delay prediction API (resolved: false) </li> </ul>",
    "Microsoft.VSTS.Common.AcceptanceCriteria": "<ul><li>Banner shows </li><li>Dismissable </li> </ul>",
    "Microsoft.VSTS.Scheduling.StoryPoints": 3,
    "System.Tags": "release-2027.01.2; ui; owner:Aisha Karim",
    "System.State": "New",
  },
  relations: [{ rel: "Hyperlink", url: "https://example.test/design" }],
};

describe("description parsing", () => {
  it("splits sentence and dependencies, ignoring Referenced by", () => {
    const r = splitDescription(clickupTask.description);
    expect(r.description).toBe("As a data engineer, I want an API, so that mobile can show delays.");
    expect(r.dependencies).toEqual([{ key: "DAT-302", description: "Telematics ingestion", resolved: false }]);
  });
  it("handles ADO html", () => {
    expect(splitAdoDescription(adoItem.fields["System.Description"]).dependencies[0].key).toBe("DAT-307");
  });
});

describe("adapter mapping", () => {
  it("maps a ClickUp task", () => {
    expect(mapTask(clickupTask, "data", "sprint-24")).toMatchObject({
      key: "DAT-307",
      title: "Delay prediction API",
      storyPoints: 5,
      hasUi: true,
      designLink: null,
      acceptanceCriteria: ["A", "B"],
      releaseName: "2027.01.2",
      assignee: "Sam Rivera",
      status: "ready for sprint",
    });
  });
  it("maps an Azure DevOps work item", () => {
    expect(mapWorkItem(adoItem, "mobile", "sprint-24")).toMatchObject({
      key: "MOB-210",
      storyPoints: 3,
      hasUi: true,
      designLink: "https://example.test/design",
      acceptanceCriteria: ["Banner shows", "Dismissable"],
      dependencies: [{ key: "DAT-307", resolved: false }],
      assignee: "Aisha Karim",
    });
  });
  it("skips items that are not seeded stories", () => {
    expect(mapTask({ name: "Random task" }, "data", null)).toBeNull();
  });
});
