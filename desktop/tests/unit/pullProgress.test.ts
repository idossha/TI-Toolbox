import { describe, expect, it } from "vitest";
import { formatPullEvent, parseProgressLine } from "../../src/shared/pullProgress";

/**
 * `formatPullEvent` is what keeps the launcher's progress line identical now that pulls arrive as
 * the Engine API's NDJSON objects instead of `docker compose` stdout: it produces the same
 * `ParsedProgressLine` shape, with the same "<layer> <status> <percent>" wording.
 */
describe("formatPullEvent", () => {
  it("renders a layer download with a percentage from progressDetail", () => {
    const r = formatPullEvent({ id: "a1b2c3d4", status: "Downloading", progressDetail: { current: 1024, total: 4096 } });
    expect(r.message).toBe("a1b2c3d4 Downloading 25%");
    expect(r.layerId).toBe("a1b2c3d4");
    expect(r.status).toBe("Downloading");
    expect(r.isComplete).toBe(false);
    expect(r.isSpinner).toBe(false);
  });

  it("marks the same terminal statuses parseProgressLine does", () => {
    expect(formatPullEvent({ id: "a1", status: "Pull complete" }).isComplete).toBe(true);
    expect(formatPullEvent({ id: "a1", status: "Already exists" }).isComplete).toBe(true);
    expect(formatPullEvent({ id: "a1", status: "Extracting" }).isComplete).toBe(false);
  });

  it("omits the percentage when Docker sends no total, and the layer id when there is none", () => {
    expect(formatPullEvent({ id: "a1", status: "Waiting" }).message).toBe("a1 Waiting");
    expect(formatPullEvent({ id: "a1", status: "Downloading", progressDetail: { current: 5 } }).message).toBe("a1 Downloading");
    const noLayer = formatPullEvent({ status: "Status: Downloaded newer image for idossha/ti-toolbox:v3.0.0-dev" });
    expect(noLayer.message).toBe("Status: Downloaded newer image for idossha/ti-toolbox:v3.0.0-dev");
    expect(noLayer.layerId).toBeUndefined();
  });

  it("never reports more than 100% when Docker over-reports current bytes", () => {
    expect(formatPullEvent({ id: "a1", status: "Extracting", progressDetail: { current: 500, total: 400 } }).message).toBe("a1 Extracting 100%");
  });
});

describe("parseProgressLine", () => {
  it("parses a pulling layer line", () => {
    const r = parseProgressLine("a1b2c3d4 Pulling fs layer");
    expect(r).toMatchObject({ layerId: "a1b2c3d4", status: "Pulling", isComplete: false, isSpinner: false });
  });

  it("parses a downloading layer line", () => {
    const r = parseProgressLine("a1b2c3d4 Downloading [==>   ]  10MB/100MB");
    expect(r.layerId).toBe("a1b2c3d4");
    expect(r.status).toBe("Downloading");
    expect(r.isComplete).toBe(false);
  });

  it("marks Pull complete / Download complete / Already exists as terminal", () => {
    expect(parseProgressLine("a1b2c3d4 Pull complete").isComplete).toBe(true);
    expect(parseProgressLine("a1b2c3d4 Download complete").isComplete).toBe(true);
    expect(parseProgressLine("a1b2c3d4 Already exists").isComplete).toBe(true);
  });

  it("strips ANSI escape sequences and carriage returns", () => {
    const r = parseProgressLine("[1A[2K\ra1b2c3d4 Extracting [====>]\r");
    expect(r.message).toBe("a1b2c3d4 Extracting [====>]");
    expect(r.layerId).toBe("a1b2c3d4");
  });

  it("detects a Braille spinner frame", () => {
    expect(parseProgressLine("⠋ Starting simnibs_container...").isSpinner).toBe(true);
  });

  it("returns no layer fields for a plain log line", () => {
    const r = parseProgressLine("Network ti_network  Creating");
    expect(r.layerId).toBeUndefined();
    expect(r.isSpinner).toBe(false);
    expect(r.message).toBe("Network ti_network  Creating");
  });
});
