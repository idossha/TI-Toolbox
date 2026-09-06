/**
 * `pages/_shared/run/planModel.ts` — the object the plan grid, the stats strip and the action-bar
 * digest all read (DESIGN.md v3 §4.5). These are the rules stated as numbers: chip precedence,
 * stage-column derivation, the per-job cost the tiles must not multiply, and the digest.
 */
import { describe, expect, it } from "vitest";
import {
  chipFor,
  countChip,
  mergePlanResults,
  normalizeStageId,
  planDigest,
  planModelFrom,
  stageIdOf,
  type PlanJob,
  type PlanResult,
} from "../../src/renderer/pages/_shared/run/planModel";

function job(over: Partial<PlanJob> & { subject: string; output_dir: string }): PlanJob {
  return { kind: "pre", exists: false, will_overwrite: false, ...over };
}

function result(jobs: PlanJob[], over: Partial<PlanResult> = {}): PlanResult {
  return { jobs, lock_conflicts: [], cost: { cpus: 8, mem_gb: 16 }, warnings: [], resolved: null, ...over };
}

const CONFLICT = {
  key: "pre:101",
  held_by: "job_12",
  kind: "pre" as const,
  subject: "101",
  started_at: "2026-09-03T10:00:00Z",
};

describe("chipFor — the five-word vocabulary and its precedence", () => {
  const j = job({ subject: "ernie", output_dir: "/p/m2m_ernie" });

  it("new when nothing exists", () => {
    expect(chipFor(j, [], [], "charm")).toBe("new");
  });

  it("skip when the output exists and the config keeps it", () => {
    expect(chipFor({ ...j, exists: true }, [], [], "charm")).toBe("skip");
  });

  it("overwrite when the output exists and will be replaced", () => {
    expect(chipFor({ ...j, exists: true, will_overwrite: true }, [], [], "charm")).toBe("overwrite");
  });

  it("wait beats overwrite when a lock conflict names the subject", () => {
    const blocked = { ...j, subject: "101", exists: true, will_overwrite: true };
    expect(chipFor(blocked, [CONFLICT], [], "charm")).toBe("wait");
  });

  it("blocked beats everything when a warning names both the subject and the stage", () => {
    const warnings = ["101 — charm cannot run: no T1w image"];
    expect(chipFor({ ...j, subject: "101" }, [CONFLICT], warnings, "charm")).toBe("blocked");
  });

  it("a warning naming only one of the two does not block (Q2: string matching, word boundaries)", () => {
    expect(chipFor({ ...j, subject: "101" }, [], ["charm output already exists"], "charm")).toBe("new");
    expect(chipFor({ ...j, subject: "101" }, [], ["101 has no DWI"], "charm")).toBe("new");
    // "1010" must not match "101".
    expect(chipFor({ ...j, subject: "101" }, [], ["1010 — charm failed"], "charm")).toBe("new");
  });
});

describe("stage columns", () => {
  it("prefers resolved.stages[i].tags[0] for kind=pre, aligned by index", () => {
    const r = result(
      [job({ subject: "ernie", output_dir: "/p/m2m_ernie" }), job({ subject: "ernie", output_dir: "/p/fastsurfer" })],
      { resolved: { stages: [{ tags: ["G2a"] }, { tags: ["G2b"] }] } },
    );
    expect(stageIdOf("pre", r, 0)).toBe("G2a");
    expect(stageIdOf("pre", r, 1)).toBe("G2b");
    // …and those tags get the readable column headings the wireframe asks for.
    expect(planModelFrom("pre", r, ["ernie"]).stages.map((s) => s.label)).toEqual(["charm", "fastsurfer"]);
  });

  it("falls through when the stages array is not aligned with jobs (a different backend)", () => {
    const r = result([job({ subject: "ernie", output_dir: "/p/m2m_ernie" })], { resolved: { stages: [] } });
    expect(stageIdOf("pre", r, 0)).toBe("m2m");
  });

  it("normalizes the subject id out of a per-subject directory, so one stage is one column", () => {
    expect(normalizeStageId("m2m_ernie", "ernie")).toBe("m2m");
    expect(normalizeStageId("m2m_101", "101")).toBe("m2m");
    // A directory that is not named after the subject is left alone.
    expect(normalizeStageId("Thalamus", "ernie")).toBe("Thalamus");
  });

  it("kind=sim columns are the montage names, one column per distinct value in first-seen order", () => {
    const r = result([
      job({ kind: "sim", subject: "ernie", output_dir: "/p/sub-ernie/Simulations/Thalamus" }),
      job({ kind: "sim", subject: "101", output_dir: "/p/sub-101/Simulations/Thalamus", exists: true, will_overwrite: true }),
      job({ kind: "sim", subject: "ernie", output_dir: "/p/sub-ernie/Simulations/L_Insula" }),
    ]);
    const model = planModelFrom("sim", r, ["ernie", "101"]);
    expect(model.stages.map((s) => s.id)).toEqual(["Thalamus", "L_Insula"]);
    expect(model.subjects.map((s) => s.subject)).toEqual(["ernie", "101"]);
    expect(model.subjects[0]?.cells.map((c) => c.chip)).toEqual(["new", "new"]);
    // 101 has no L_Insula job: the cell is null, which the grid draws as "·" — visibly not part
    // of this run rather than an empty box that reads as a bug.
    expect(model.subjects[1]?.cells.map((c) => c.chip)).toEqual(["overwrite", null]);
  });

  it("gives every selected subject a row, in the page's display order, even with no job", () => {
    const model = planModelFrom("pre", result([job({ subject: "ernie", output_dir: "/p/m2m_ernie" })]), ["101", "ernie", "MNI152"]);
    expect(model.subjects.map((s) => s.subject)).toEqual(["101", "ernie", "MNI152"]);
    expect(model.subjects[0]?.cells.every((c) => c.chip === null)).toBe(true);
  });
});

describe("stats and digest", () => {
  it("reads cost PER JOB — the plan is never multiplied by the job count", () => {
    const r = result([
      job({ subject: "ernie", output_dir: "/p/m2m_ernie" }),
      job({ subject: "101", output_dir: "/p/m2m_101" }),
    ]);
    const model = planModelFrom("pre", r, ["ernie", "101"]);
    expect(model.stats).toEqual({ jobs: 2, cpus: 8, memoryGb: 16, waits: 0 });
  });

  it("counts waits from lock_conflicts and marks every conflicted subject's cells", () => {
    const r = result([job({ subject: "101", output_dir: "/p/m2m_101" })], { lock_conflicts: [CONFLICT] });
    const model = planModelFrom("pre", r, ["101"]);
    expect(model.stats.waits).toBe(1);
    expect(model.subjects[0]?.cells[0]?.chip).toBe("wait");
  });

  it("planDigest states jobs, cost, overwrites and waits — and nothing it has not measured", () => {
    const plain = planModelFrom("pre", result([job({ subject: "ernie", output_dir: "/p/m2m_ernie" })]), ["ernie"]);
    expect(planDigest(plain)).toBe("1 job · 8 CPU · 16 GB");

    const busy = planModelFrom(
      "pre",
      result(
        [
          job({ subject: "ernie", output_dir: "/p/m2m_ernie", exists: true, will_overwrite: true }),
          job({ subject: "108", output_dir: "/p/m2m_108" }),
        ],
        { lock_conflicts: [CONFLICT] },
      ),
      ["ernie", "108", "101"],
    );
    expect(planDigest(busy)).toBe("2 jobs · 8 CPU · 16 GB · 1 overwrite · 1 wait");
    expect(countChip(busy, "overwrite")).toBe(1);
  });

  it("a blocked plan's digest is the reason, verbatim — never a silent disabled button", () => {
    const model = planModelFrom("sim", result([]), [], { blockedReason: "Select at least one montage." });
    expect(planDigest(model)).toBe("Select at least one montage.");
  });
});

describe("mergePlanResults — the per-row plans the Simulator issues", () => {
  it("concatenates jobs, de-duplicates warnings and conflicts, and takes the largest single cost", () => {
    const a = result([job({ kind: "sim", subject: "ernie", output_dir: "/p/a/Thalamus" })], {
      cost: { cpus: 8, mem_gb: 16 },
      warnings: ["output already exists"],
    });
    const b = result([job({ kind: "sim", subject: "101", output_dir: "/p/b/Thalamus" })], {
      cost: { cpus: 4, mem_gb: 32 },
      warnings: ["output already exists"],
      lock_conflicts: [CONFLICT],
    });
    const merged = mergePlanResults([a, b]);
    expect(merged.jobs).toHaveLength(2);
    expect(merged.warnings).toEqual(["output already exists"]);
    expect(merged.lock_conflicts).toHaveLength(1);
    // Not 12 CPU / 48 GB: `_plan_cost` measures one representative job, so the tiles read per job.
    expect(merged.cost).toEqual({ cpus: 8, mem_gb: 32 });
  });
});
