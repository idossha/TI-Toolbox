/**
 * The run pages' step catalogue, its estimate, and the plan grid's legend, as pure functions. No
 * browser, no socket: the rules are the thing under test, not React.
 *
 * The Terminal's log-FILE source and its "What will run" preview were retired in fix lane FXU2 —
 * the pane shows a running job or an empty console — so `parseLogText`/`pickLogFile`/`logBasename`
 * and their tests went with them. The follow rule itself lives in `run-jobTerminal.test.ts`.
 */
import { describe, expect, it } from "vitest";
import {
  durationLabel,
  estimateMinutes,
  RUN_STEPS,
  stepsFor,
} from "../../src/renderer/pages/_shared/run/terminalSources";
import { chipsPresent } from "../../src/renderer/pages/_shared/run/PlanGrid";
import { planModelFrom, type PlanResult } from "../../src/renderer/pages/_shared/run/planModel";

describe("the estimate", () => {
  it("scales with the plan's subject rows and divides by the parallelism", () => {
    const plan = planModelFrom("pre", { jobs: [], lock_conflicts: [], cost: { cpus: 4, mem_gb: 16 }, warnings: [] } as PlanResult, [
      "ernie",
      "101",
      "MNI152",
    ]);
    const steps = stepsFor("pre", ["G1", "G3"]); // 2 + 3 minutes per subject
    expect(estimateMinutes(steps, plan, 1)).toBe(15);
    expect(estimateMinutes(steps, plan, 3)).toBe(5);
  });

  it("never divides by zero and treats a null plan as one subject", () => {
    expect(estimateMinutes(stepsFor("sim"), null, 0)).toBe(13);
  });

  it("labels hours and minutes, never a bare number", () => {
    expect(durationLabel(0.2)).toBe("< 1 m");
    expect(durationLabel(48)).toBe("48 m");
    expect(durationLabel(60)).toBe("1 h");
    expect(durationLabel(85)).toBe("1 h 25 m");
  });
});

describe("stepsFor", () => {
  it("keeps the catalogue's run order regardless of the order the ids arrive in", () => {
    expect(stepsFor("pre", ["G2b", "G1"]).map((s) => s.id)).toEqual(["G1", "G2b"]);
  });

  it("returns every step of the kind when the page names none", () => {
    expect(stepsFor("analyzer")).toHaveLength(RUN_STEPS.analyzer.length);
  });

  it("gives every kind a non-empty, described step list — the pane is never blank", () => {
    for (const kind of ["pre", "sim", "flex", "ex", "mex", "analyzer"] as const) {
      const steps = RUN_STEPS[kind];
      expect(steps.length, kind).toBeGreaterThan(0);
      for (const s of steps) {
        expect(s.detail.length, `${kind}/${s.id}`).toBeGreaterThan(20);
        expect(s.minutes, `${kind}/${s.id}`).toBeGreaterThan(0);
      }
    }
  });
});

describe("the legend names only the chips the matrix contains", () => {
  const result: PlanResult = {
    jobs: [
      { kind: "pre", subject: "ernie", output_dir: "/p/anat", exists: true, will_overwrite: false, stage: "G1" },
      { kind: "pre", subject: "101", output_dir: "/p/anat", exists: false, will_overwrite: false, stage: "G1" },
    ],
    lock_conflicts: [],
    cost: { cpus: 4, mem_gb: 16 },
    warnings: [],
  };

  it("is the present chips in vocabulary order, not all five", () => {
    const plan = planModelFrom("pre", result, ["ernie", "101"], {
      stages: [
        { id: "G1", label: "dicom" },
        { id: "G2a", label: "charm" },
      ],
    });
    expect(chipsPresent(plan)).toEqual(["new", "skip"]);
  });

  it("declared columns come first and in run order, even with no job for them", () => {
    const plan = planModelFrom("pre", result, ["ernie"], {
      stages: [
        { id: "G1", label: "dicom" },
        { id: "G2a", label: "charm" },
        { id: "report", label: "report" },
      ],
    });
    expect(plan.stages.map((s) => s.id)).toEqual(["G1", "G2a", "report"]);
    expect(plan.subjects[0]?.cells.map((c) => c.chip)).toEqual(["skip", null, null]);
  });

  it("appends a stage the plan returned that the page did not declare", () => {
    const plan = planModelFrom("pre", result, ["ernie"], { stages: [{ id: "G2a", label: "charm" }] });
    expect(plan.stages.map((s) => s.id)).toEqual(["G2a", "G1"]);
  });
});
