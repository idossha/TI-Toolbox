/**
 * Two jobs of one Run press never write one folder (p19, 2026-10-22).
 *
 * What it pins:
 *  - `collidingOutputs` / `collisionReason` (`_shared/run/planModel.ts`): a folder claimed twice
 *    blocks Run with a sentence naming the jobs and the folder; one montage name under two
 *    subjects is two folders; pre-processing stages sharing `m2m_<id>` are not a collision; a
 *    blank Ex run name's timestamp preview is never compared.
 *  - the Simulator's per-row plans (`simPlanBlockedReason`): the Dataset 000 repro — sub-101 has
 *    an `L_Insula` montage under both GSN-HydroCel-185 and EEG10-10_UI_Jurak_2007
 *    (`code/ti-toolbox/config/montage_list.json`), and the server plans both to
 *    `sub-101/Simulations/L_Insula` (`plan.py::_plan_sim`, `pm.simulation(sid, montage.name)`).
 *  - the Optimizer (`jobsForRow`, `optimizerOutputClaims`): an uncombined two-ROI Ex row named
 *    "insula" gave both targets `run_name: "insula"`, so both wrote `ex-search/insula`.
 *
 * Where the folders come from: the server's derivatives layout (`tit/paths.py`:
 * `sub-<id>/Simulations/<montage>`, `sub-<id>/ex-search/<run>`, `sub-<id>/m-ex-search/<run>`),
 * written out by hand in `serverFolder` below — never read back from the code under test. The
 * Python side (the server refusing such a group with 422) is `tests/test_jobs_group_output_collision.py`.
 * Reproduce: `cd desktop && npx vitest run tests/unit/run-output-collision.test.ts`.
 */
import { describe, expect, it } from "vitest";
import { collidingOutputs, collisionReason, type OutputClaim } from "../../src/renderer/pages/_shared/run/planModel";
import { simPlanBlockedReason } from "../../src/renderer/pages/simulator/RunControls";
import { exRunName, jobsForRow, optimizerOutputClaims, type OptimizerJobSpec } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow, type OptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi";

const ROOT = "/data/000/derivatives/SimNIBS";
/** The timestamp the server previews for a blank Ex/mEx run name (`time.strftime`), the same for
 *  every job planned within one second. */
const PREVIEW = "20261022_120000";

/** `tit/paths.py`'s layout, typed from its docstrings: what `plan.py` returns as `output_dir`. */
function serverFolder(kind: "sim" | "ex" | "mex", subject: string, name: string | null): string {
  const family = kind === "sim" ? "Simulations" : kind === "ex" ? "ex-search" : "m-ex-search";
  return `${ROOT}/sub-${subject}/${family}/${name ?? PREVIEW}`;
}

const plan = (outputDir: string) => ({ jobs: [{ output_dir: outputDir }] });

describe("collidingOutputs / collisionReason", () => {
  it("blocks two jobs claiming one folder, naming both jobs and the folder from sub-<id> on", () => {
    const dir = serverFolder("sim", "101", "L_Insula");
    const claims: OutputClaim[] = [
      { label: "Job 1", outputDir: dir },
      { label: "Job 3", outputDir: serverFolder("sim", "101", "M1") },
      { label: "Job 2", outputDir: dir },
    ];
    expect(collidingOutputs(claims)).toEqual([{ outputDir: dir, labels: ["Job 1", "Job 2"] }]);
    const reason = collisionReason(claims);
    expect(reason).toMatch(/^Job 1 and Job 2 both write sub-101\/Simulations\/L_Insula;/);
  });

  it("says 'all write' and lists every job when three claim one folder", () => {
    const dir = serverFolder("ex", "ernie", "r");
    const claims = ["Job 1", "Job 2", "Job 4"].map((label) => ({ label, outputDir: dir }));
    expect(collisionReason(claims)).toMatch(/^Job 1, Job 2 and Job 4 all write sub-ernie\/ex-search\/r;/);
  });

  it("counts the jobs when one label claims a folder twice (one row, two identical targets)", () => {
    const dir = serverFolder("sim", "ernie", "M");
    expect(collisionReason([{ label: "ernie · M", outputDir: dir }, { label: "ernie · M", outputDir: dir }])).toMatch(
      /^2 jobs of ernie · M both write sub-ernie\/Simulations\/M;/,
    );
  });

  it("allows one montage name for two subjects — two folders", () => {
    const claims = ["ernie", "101"].map((sid) => ({ label: sid, outputDir: serverFolder("sim", sid, "L_Insula") }));
    expect(collidingOutputs(claims)).toEqual([]);
    expect(collisionReason(claims)).toBeNull();
  });

  it("never compares pre-processing stages, which all write into m2m_<id> by design", () => {
    const m2m = `${ROOT}/sub-ernie/m2m_ernie`;
    const claims: OutputClaim[] = ["charm", "tissue", "dti"].map((label) => ({ label, outputDir: m2m, kind: "pre" }));
    expect(collisionReason(claims)).toBeNull();
    // The same claims from any other kind ARE a collision: the exclusion is the kind, not the path.
    expect(collisionReason(claims.map((c) => ({ ...c, kind: "sim" as const })))).not.toBeNull();
  });

  it("never compares a timestamp preview (outputDir null)", () => {
    expect(collisionReason([{ label: "Job 1", outputDir: null }, { label: "Job 2", outputDir: null }])).toBeNull();
  });
});

describe("Simulator: rows whose plans land in one folder", () => {
  it("blocks the Dataset 000 repro: sub-101 L_Insula under two nets", () => {
    // Both rows carry the montage NAME; the net is not part of the folder (plan.py::_plan_sim).
    const rows = [
      { subjectId: "101", name: "L_Insula" },
      { subjectId: "101", name: "L_Insula" },
    ];
    const outcomes = rows.map((r) => ({ data: plan(serverFolder("sim", r.subjectId, r.name)) }));
    const reason = simPlanBlockedReason(rows, outcomes);
    expect(reason).toContain("sub-101/Simulations/L_Insula");
    expect(reason).toContain("101 · L_Insula");
  });

  it("lets a duplicated row re-pointed at another subject run", () => {
    const rows = [
      { subjectId: "ernie", name: "L_Insula" },
      { subjectId: "101", name: "L_Insula" },
    ];
    expect(simPlanBlockedReason(rows, rows.map((r) => ({ data: plan(serverFolder("sim", r.subjectId, r.name)) })))).toBeNull();
  });
});

/** An Ex (2 pairs) or mEx (4 pairs) row targeting saved ROIs. */
function exRow(over: { subject?: string; pairs?: 2 | 4; selected: string[]; combine: boolean; runName: string }): OptimizerRow {
  const roi: RoiValue = { mode: "saved", selected: over.selected, combine: over.combine, radius: 3, space: "subject" };
  return emptyOptimizerRow({ subjectId: over.subject ?? "ernie", method: "ex", exPairs: over.pairs ?? 2, net: "GSN-HydroCel-185", roi, runName: over.runName });
}

const resolve = { atlas: () => () => undefined, leadfield: (s: string) => `${ROOT}/sub-${s}/leadfields/GSN-HydroCel-185_leadfield.hdf5` };

function runNames(row: OptimizerRow): (string | null)[] {
  return jobsForRow(row, resolve).map((j) => (j.config as { run_name: string | null }).run_name);
}

/** The plan the server returns for each job, by its own path rule. */
function serverPlans(jobs: OptimizerJobSpec[]) {
  return jobs.map((j) => plan(serverFolder(j.kind as "ex" | "mex", j.subject, (j.config as { run_name: string | null }).run_name)));
}

describe("Optimizer: an Ex/mEx row with several targets is several run folders", () => {
  it("gives each target of an uncombined two-ROI Ex row its own run name", () => {
    expect(runNames(exRow({ selected: ["L-Insula", "R-Insula"], combine: false, runName: "insula" }))).toEqual([
      "insula_L-Insula",
      "insula_R-Insula",
    ]);
  });

  it("does the same for an mEx row, which never combines", () => {
    expect(runNames(exRow({ pairs: 4, selected: ["L-Insula", "R-Insula"], combine: true, runName: " insula " }))).toEqual([
      "insula_L-Insula",
      "insula_R-Insula",
    ]);
  });

  it("keeps one target's run name exactly as typed (trimmed), and a combined selection is one run", () => {
    expect(runNames(exRow({ selected: ["L-Insula"], combine: false, runName: "insula " }))).toEqual(["insula"]);
    expect(runNames(exRow({ selected: ["L-Insula", "R-Insula"], combine: true, runName: "insula" }))).toEqual(["insula"]);
  });

  it("leaves a blank name blank for every target, so each run takes its own timestamp", () => {
    expect(runNames(exRow({ selected: ["L-Insula", "R-Insula"], combine: false, runName: "" }))).toEqual([null, null]);
    expect(exRunName("  ", { roiName: "x", roiNames: null, roiAtlas: null, radius: 3, space: "subject" }, 2)).toBe("");
  });

  it("blocks two rows that name the same run for the same target, and names both rows", () => {
    const rows = [exRow({ selected: ["L-Insula"], combine: false, runName: "r" }), exRow({ selected: ["L-Insula"], combine: false, runName: "r" })];
    const jobs = rows.flatMap((r) => jobsForRow(r, resolve));
    const claims = optimizerOutputClaims(jobs, serverPlans(jobs), (id) => rows.findIndex((r) => r.id === id) + 1);
    expect(collisionReason(claims)).toMatch(/^Job 1 and Job 2 both write sub-ernie\/ex-search\/r;/);
  });

  it("does not compare blank-name previews even though the server previews one folder for both", () => {
    const rows = [exRow({ selected: ["L-Insula"], combine: false, runName: "" }), exRow({ selected: ["R-Insula"], combine: false, runName: "" })];
    const jobs = rows.flatMap((r) => jobsForRow(r, resolve));
    const plans = serverPlans(jobs);
    expect(plans[0]!.jobs[0]!.output_dir).toBe(plans[1]!.jobs[0]!.output_dir);
    expect(collisionReason(optimizerOutputClaims(jobs, plans, () => 1))).toBeNull();
  });

  it("over random tables: Run is blocked exactly when two jobs share (kind, subject, run name)", () => {
    // mulberry32: a fixed seed, so a failure reproduces.
    let seed = 0x19c0ffee;
    const rand = () => {
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const pick = <T,>(xs: readonly T[]): T => xs[Math.floor(rand() * xs.length)] as T;
    const rois = ["L-Insula", "R-Insula", "M1"];
    let blockedTables = 0;
    for (let n = 0; n < 400; n += 1) {
      const rows = Array.from({ length: 1 + Math.floor(rand() * 3) }, () =>
        exRow({
          subject: pick(["ernie", "101"]),
          pairs: pick([2, 4] as const),
          selected: rois.filter(() => rand() < 0.6),
          combine: rand() < 0.5,
          runName: pick(["", "r", "insula"]),
        }),
      );
      const jobs = rows.flatMap((r) => jobsForRow(r, resolve));
      const named = jobs.filter((j) => (j.config as { run_name: string | null }).run_name);
      const keys = named.map((j) => `${j.kind}|${j.subject}|${(j.config as { run_name: string }).run_name}`);
      const duplicateKey = new Set(keys).size !== keys.length;
      const reason = collisionReason(optimizerOutputClaims(jobs, serverPlans(jobs), (id) => rows.findIndex((r) => r.id === id) + 1));
      expect(reason !== null, JSON.stringify(rows.map((r) => [r.subjectId, r.exPairs, (r.roi as { selected: string[] }).selected, r.runName]))).toBe(duplicateKey);
      // One row alone can never collide with itself any more.
      if (rows.length === 1) expect(reason).toBeNull();
      if (reason) blockedTables += 1;
    }
    // Has something to check: the generator does produce colliding tables.
    expect(blockedTables).toBeGreaterThan(10);
  });
});
