/**
 * `pages/overview/model.ts` — how the one `/api/catalog/overview` response reads on screen: the
 * five presence states, the readiness board, and the `counts` status cell (U6/U8, R1).
 *
 * Built from `tests/fixtures/overview.json`, the same body the mock server serves, so the numbers
 * asserted here are the numbers on screen. The arithmetic itself (coverage, counts, readiness) is
 * the server's now and is tested in `tests/test_server_overview.py`; what is tested here is the
 * presentation that used to silently disagree with it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Overview, OverviewSubject } from "../../src/renderer/pages/overview/api";
import {
  PRESENCE_COLUMNS,
  blockedReason,
  isReady,
  notConverted,
  overviewStatusValue,
  presenceCells,
  readyFor,
  stages,
} from "../../src/renderer/pages/overview/model";

const data = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "overview.json"), "utf8"),
) as Overview;
const row = (id: string): OverviewSubject => data.subjects.find((s) => s.id === id)!;

describe("presence", () => {
  it("draws every defined column, in order, for every subject", () => {
    for (const subject of data.subjects) {
      expect(presenceCells(subject).map((c) => c.key)).toEqual([...PRESENCE_COLUMNS]);
    }
  });

  it("gives the five states five distinguishable readings", () => {
    const seen = (subject: OverviewSubject, key: string) => presenceCells(subject).find((c) => c.key === key)!;
    expect(seen(row("ernie"), "m2m")).toMatchObject({ state: "present", kind: "success", pulse: false });
    expect(seen(row("ernie"), "ct")).toMatchObject({ state: "absent", kind: "neutral" });
    expect(seen(row("ernie"), "leadfield")).toMatchObject({ state: "partial", kind: "warning" });
    // Synthetic rows for the two job-derived states: the fixture project has no running job.
    const running = { ...row("101"), m2m: "pending" } as OverviewSubject;
    expect(seen(running, "m2m")).toMatchObject({ state: "pending", kind: "accent", pulse: true });
    const broken = { ...row("101"), m2m: "failed" } as OverviewSubject;
    expect(seen(broken, "m2m")).toMatchObject({ state: "failed", kind: "danger" });
    // Four distinct colours across the four non-absent states — the point of the change.
    const kinds = new Set([
      seen(row("ernie"), "m2m").kind,
      seen(row("ernie"), "leadfield").kind,
      seen(running, "m2m").kind,
      seen(broken, "m2m").kind,
    ]);
    expect(kinds.size).toBe(4);
  });

  it("titles every dot with its column and its state", () => {
    expect(presenceCells(row("MNI152")).find((c) => c.key === "raw")!.title).toBe("raw missing");
    expect(presenceCells(row("ernie")).find((c) => c.key === "leadfield")!.title).toBe("leadfield partial");
  });
});

describe("readiness", () => {
  it("reads the server's own per-stage answer, reason included", () => {
    expect(readyFor(row("101"), "optimizer")).toBe(false);
    expect(blockedReason(row("101"), "optimizer")).toBe("no leadfield");
    expect(blockedReason(row("ernie"), "optimizer")).toBeUndefined();
  });

  it("builds the four stage cards from the response's totals", () => {
    const board = stages(data);
    expect(board.map((s) => s.id)).toEqual(["preprocess", "simulator", "optimizer", "analyzer"]);
    const optimizer = board.find((s) => s.id === "optimizer")!;
    expect(optimizer.ready).toEqual(["ernie"]);
    expect(optimizer.blocked).toEqual([
      { subject: "101", reason: "no leadfield" },
      { subject: "MNI152", reason: "no leadfield" },
    ]);
    expect(optimizer.summary).toBe("2 search runs so far");
    expect(board.find((s) => s.id === "preprocess")!.summary).toBe("3 head models built");
    expect(board.find((s) => s.id === "analyzer")!.summary).toBe("4 analyses so far");
  });
});

describe("filters and the status cell", () => {
  it("Ready means a head model and converted raw data", () => {
    expect(isReady(row("ernie"))).toBe(true);
    expect(isReady(row("MNI152"))).toBe(false); // m2m, but no raw
  });

  it("partial raw is 'staged, not converted', not 'missing'", () => {
    expect(notConverted({ ...row("101"), raw: "partial" } as OverviewSubject)).toBe(true);
    expect(notConverted(row("MNI152"))).toBe(false);
  });

  it("prints the project's counts, dropping the zeroes", () => {
    expect(overviewStatusValue(data)).toBe("3 subjects · 3 m2m · 1 leadfield");
    expect(overviewStatusValue(undefined)).toBeUndefined();
    expect(
      overviewStatusValue({ subjects: [], totals: { subjects: 0, simulations: 0, optimizations: 0, analyses: 0, coverage: [] } }),
    ).toBeUndefined();
  });
});
