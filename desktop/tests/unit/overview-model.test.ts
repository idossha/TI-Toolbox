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
  COLUMN_LABEL,
  COLUMN_TITLE,
  PRESENCE_COLUMNS,
  PRESENCE_LEGEND,
  STAGES,
  blockedReason,
  isReady,
  notConverted,
  overviewStatusValue,
  presenceCells,
  readyFor,
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

  it("gives every column a one-word head and a long form for its tooltip", () => {
    // No head wraps and none repeats: `fs`/`fsr` used to differ by a letter and `lf` used to read
    // as a second line of the neighbouring Leadfield column.
    const heads = PRESENCE_COLUMNS.map((k) => COLUMN_LABEL[k]);
    expect(heads).toEqual(["raw", "fast", "free", "m2m", "dwi", "ct", "lf", "net"]);
    expect(new Set(heads).size).toBe(heads.length);
    for (const head of heads) expect(head).not.toContain(" ");
    for (const key of PRESENCE_COLUMNS) expect(COLUMN_TITLE[key].length).toBeGreaterThan(COLUMN_LABEL[key].length);
  });

  it("spells the five dot colours out in one legend line", () => {
    expect(PRESENCE_LEGEND.map((l) => l.state)).toEqual(["present", "partial", "pending", "failed", "absent"]);
    expect(new Set(PRESENCE_LEGEND.map((l) => l.kind)).size).toBe(5);
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

  it("names the four workflows a selected subject can be sent into", () => {
    expect(STAGES.map((s) => s.id)).toEqual(["preprocess", "simulator", "optimizer", "analyzer"]);
    expect(STAGES.map((s) => s.verb)).toEqual(["Pre-process", "Simulate", "Optimize", "Analyze"]);
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
