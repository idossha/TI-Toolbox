/**
 * The Terminal's three-source rule and the plan grid's legend, as pure functions (fix lane FXU1).
 * No browser, no socket: the rules are the thing under test, not React.
 */
import { describe, expect, it } from "vitest";
import {
  durationLabel,
  estimateMinutes,
  logBasename,
  parseLogText,
  pickLogFile,
  RUN_STEPS,
  stepsFor,
  type LogFileEntry,
} from "../../src/renderer/pages/_shared/run/terminalSources";
import { chipsPresent } from "../../src/renderer/pages/_shared/run/PlanGrid";
import { planModelFrom, type PlanResult } from "../../src/renderer/pages/_shared/run/planModel";

const file = (name: string, kind: string, modified: string): LogFileEntry => ({
  path: `/mnt/example/derivatives/ti-toolbox/logs/sub-ernie/${name}`,
  name,
  kind,
  modified,
});

describe("parseLogText", () => {
  it("maps the level word onto the console's four levels", () => {
    const lines = parseLogText(
      [
        "2026-08-27 08:41:02 INFO  tit.pre start",
        "2026-08-27 08:48:02 WARNING tit.pre low contrast",
        "2026-08-27 08:49:02 ERROR tit.pre boom",
        "2026-08-27 08:49:03 DEBUG tit.pre noise",
      ].join("\n"),
    );
    expect(lines.map((l) => l.level)).toEqual(["info", "warning", "error", "debug"]);
    expect(lines.map((l) => l.seq)).toEqual([0, 1, 2, 3]);
  });

  it("treats a line with no level word as info, not debug", () => {
    // A traceback's continuation lines must not be greyed out into invisibility.
    expect(parseLogText("    File \"x.py\", line 3").map((l) => l.level)).toEqual(["info"]);
  });

  it("drops only the trailing newline, so a blank line inside a log survives", () => {
    expect(parseLogText("a\n\nb\n").map((l) => l.text)).toEqual(["a", "", "b"]);
  });
});

describe("pickLogFile", () => {
  const files = [
    file("preprocess_20260827_084102.log", "pre", "2026-08-27T09:16:33Z"),
    file("Simulator_20260828_140211.log", "sim", "2026-08-28T14:12:05Z"),
    file("preprocess_20260901_101500.log", "pre", "2026-09-01T10:40:00Z"),
  ];

  it("takes the newest file of one of the page's kinds, not the first the server sent", () => {
    expect(pickLogFile(files, ["pre"])?.name).toBe("preprocess_20260901_101500.log");
  });

  it("is null when no file matches the kind, so the caller falls through to the preview", () => {
    expect(pickLogFile(files, ["flex"])).toBeNull();
    expect(pickLogFile([], ["pre"])).toBeNull();
  });

  it("accepts several kinds (the Optimizer follows flex, ex and mex)", () => {
    const opt = [file("ex_search_a.log", "ex", "2026-08-30T09:22:40Z"), file("flex_search_a.log", "flex", "2026-08-29T10:44:31Z")];
    expect(pickLogFile(opt, ["flex", "ex", "mex"])?.kind).toBe("ex");
  });
});

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

describe("logBasename", () => {
  it("keeps the file name only", () => {
    expect(logBasename("/mnt/example/derivatives/ti-toolbox/logs/sub-ernie/preprocess_1.log")).toBe("preprocess_1.log");
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
