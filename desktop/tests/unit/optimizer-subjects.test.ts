import { describe, expect, it } from "vitest";
import { jobsForRow, rowFormReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow, type OptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import type { AtlasLookup, RoiValue } from "../../src/renderer/pages/_shared/roi";
import type { ExConfigBody, MExConfigBody } from "../../src/renderer/pages/optimizer/api";

/**
 * The Optimizer's Run button, from a jobs-table row to the wire (lane OJ, 2026-09-06).
 *
 * The trap these tests exist for is U16's, now per row rather than per page: every per-subject path
 * in an optimizer config points into that subject's own derivatives — `leadfield_hdf` at
 * `sub-<id>/leadfields/`, an atlas target's `atlas_path` at `derivatives/freesurfer/sub-<id>/`.
 * Resolving either once and reusing it across the table produces jobs that silently optimise every
 * subject against the first row's anatomy. Since the rework a row names its OWN subject, so the
 * defect is one row away rather than one batch away, and `jobsForRow` takes both facts through
 * `resolve` for exactly that reason.
 */
const leadfields: Record<string, string | null> = {
  ernie: "/mnt/000/derivatives/SimNIBS/sub-ernie/leadfields/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
  "101": "/mnt/000/derivatives/SimNIBS/sub-101/leadfields/101_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
  MNI152: null,
};
const atlasPath = (subject: string) => `/mnt/000/derivatives/freesurfer/sub-${subject}/mri/aparc.DKTatlas+aseg.mgz`;
const corticalPath = (subject: string) => `/mnt/000/derivatives/freesurfer/sub-${subject}/label/lh.DK40.annot`;

/** The resolvers the page hands `jobsForRow`, answering per subject as the real ones do. */
const resolve = {
  atlas: (subject: string, roi: RoiValue) => (): AtlasLookup | undefined =>
    roi.mode === "cortical" ? { path: corticalPath(subject) } : { path: atlasPath(subject) },
  leadfield: (subject: string) => leadfields[subject] ?? null,
};

const EX_BUCKETS = { e1_plus: ["Fp1"], e1_minus: ["Fp2"], e2_plus: ["F3"], e2_minus: ["F4"] };
const MEX_BUCKETS = {
  ...EX_BUCKETS,
  e3_plus: ["C3"], e3_minus: ["C4"], e4_plus: ["P3"], e4_minus: ["P4"],
};

function flexRow(subject: string, extra: Partial<OptimizerRow> = {}): OptimizerRow {
  return {
    ...emptyOptimizerRow({ subjectId: subject, method: "flex" }),
    roi: { mode: "cortical", atlas: "DK40", regions: [{ id: 1, name: "bankssts", hemi: "lh" }] },
    ...extra,
  };
}

function savedRoi(names: string[], combine = false): RoiValue {
  return { mode: "saved", selected: names, combine, radius: 3.0, space: "subject" };
}

function exRow(subject: string, roi: RoiValue, pairs: 2 | 4 = 2): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: subject, method: "ex", exPairs: pairs });
  return {
    ...row,
    roi,
    net: "EEG10-10_UI_Jurak_2007",
    ex: { ...row.ex, buckets: EX_BUCKETS },
    mex: { ...row.mex, buckets: MEX_BUCKETS },
  };
}

describe("jobsForRow — one row, its own subject's paths", () => {
  it("gives a Flex row one job carrying its subject's own resolved ROI path", () => {
    const jobs = ["ernie", "101"].flatMap((s) => jobsForRow(flexRow(s), resolve));
    expect(jobs.map((j) => j.subject)).toEqual(["ernie", "101"]);
    expect(jobs.map((j) => j.kind)).toEqual(["flex", "flex"]);
    expect(jobs.map((j) => j.stage)).toEqual(["flex", "flex"]);
    expect(jobs.map((j) => (j.config as { subject_id: string }).subject_id)).toEqual(["ernie", "101"]);
    expect(jobs.map((j) => (j.config as { roi: { atlas_path: string[] } }).roi.atlas_path[0])).toEqual([
      corticalPath("ernie"),
      corticalPath("101"),
    ]);
  });

  it("derives the adaptive and Pareto job kinds from the row's own focality mode", () => {
    const base = flexRow("ernie");
    const focal = (mode: "adaptive" | "pareto") => ({ ...base, flex: { ...base.flex, goal: "focality" as const, focalityMode: mode } });
    expect(jobsForRow(focal("adaptive"), resolve)[0]?.kind).toBe("flex_adaptive");
    expect(jobsForRow(focal("pareto"), resolve)[0]?.kind).toBe("flex_pareto");
    // The kind and the config are read off ONE fact, so they cannot disagree.
    const config = jobsForRow(focal("adaptive"), resolve)[0]?.config as { goal: string; adaptive: unknown };
    expect(config.goal).toBe("focality");
    expect(config.adaptive).toBeDefined();
  });

  it("derives ex from mEx by the electrode count the row configured", () => {
    const four = jobsForRow(exRow("ernie", savedRoi(["A.csv"]), 2), resolve)[0];
    const eight = jobsForRow(exRow("ernie", savedRoi(["A.csv"]), 4), resolve)[0];
    expect(four?.kind).toBe("ex");
    expect(four?.stage).toBe("ex");
    expect(eight?.kind).toBe("mex");
    expect(eight?.stage).toBe("mex");
    // …and each builds its own config shape: four buckets against eight.
    expect(Object.keys((four?.config as { electrodes: Record<string, unknown> }).electrodes)).toContain("e2_minus");
    expect(Object.keys((eight?.config as { electrodes: Record<string, unknown> }).electrodes)).toContain("e4_minus");
  });

  it("carries the row's run name into the flex output folder", () => {
    const job = jobsForRow(flexRow("ernie", { runName: " smoke-ui-flex " }), resolve)[0];
    expect((job?.config as { output_folder: string }).output_folder).toBe("smoke-ui-flex");
  });

  it("gives an Ex row one job per uncombined target, with that subject's leadfield", () => {
    const jobs = ["ernie", "101"].flatMap((s) => jobsForRow(exRow(s, savedRoi(["A.csv", "B.csv"])), resolve));
    expect(jobs.map((j) => `${j.subject}:${(j.config as ExConfigBody).roi_name}`)).toEqual([
      "ernie:A.csv",
      "ernie:B.csv",
      "101:A.csv",
      "101:B.csv",
    ]);
    expect(jobs.map((j) => (j.config as ExConfigBody).leadfield_hdf)).toEqual([
      leadfields.ernie,
      leadfields.ernie,
      leadfields["101"],
      leadfields["101"],
    ]);
  });

  it("combines saved ROIs into one target when the row asks for it", () => {
    const jobs = jobsForRow(exRow("ernie", savedRoi(["A.csv", "B.csv"], true)), resolve);
    expect(jobs).toHaveLength(1);
    expect((jobs[0]!.config as ExConfigBody).roi_names).toEqual(["A.csv", "B.csv"]);
  });

  it("resolves a subcortical target's atlas_path per subject, never one subject's for all", () => {
    const roi: RoiValue = {
      mode: "subcortical",
      atlasSpace: "subject",
      atlas: "aparc.DKTatlas+aseg.mgz",
      regions: [{ id: 17, name: "Left-Hippocampus" }],
      tissues: "GM",
    };
    const jobs = ["ernie", "101"].flatMap((s) => jobsForRow(exRow(s, roi), resolve));
    expect(jobs.map((j) => (j.config as ExConfigBody).roi_atlas?.[0]?.atlas_path)).toEqual([atlasPath("ernie"), atlasPath("101")]);
    // The target's *name* is subject-independent, which is why one plan column serves every row.
    expect(new Set(jobs.map((j) => (j.config as ExConfigBody).roi_name))).toEqual(new Set(["aparc.DKTatlas+aseg.mgz_1region"]));
  });

  it("yields nothing for a subject with no leadfield rather than another subject's matrix", () => {
    expect(jobsForRow(exRow("MNI152", savedRoi(["A.csv"])), resolve)).toEqual([]);
  });

  it("builds an mEx config with all eight buckets", () => {
    const job = jobsForRow(exRow("ernie", savedRoi(["A.csv"]), 4), resolve)[0];
    expect(job?.kind).toBe("mex");
    expect((job?.config as MExConfigBody).electrodes).toMatchObject({ e4_minus: ["P4"] });
    expect((job?.config as MExConfigBody).subject_id).toBe("ernie");
  });

  it("yields nothing for a row with no subject, or an unresolved target", () => {
    expect(jobsForRow(emptyOptimizerRow(), resolve)).toEqual([]);
    expect(jobsForRow(emptyOptimizerRow({ subjectId: "ernie" }), resolve)).toEqual([]);
  });
});

describe("rowFormReason — the per-row half of the disabled-Run sentence", () => {
  it("names an empty Ex bucket, and is silent once every bucket is filled", () => {
    const empty = emptyOptimizerRow({ subjectId: "ernie", method: "ex" });
    expect(rowFormReason(empty)).toBe("Fill in every electrode bucket.");
    expect(rowFormReason(exRow("ernie", savedRoi(["A.csv"])))).toBeNull();
  });

  it("names all eight buckets for mEx", () => {
    expect(rowFormReason(emptyOptimizerRow({ subjectId: "ernie", method: "ex", exPairs: 4 }))).toBe("Fill in all eight electrode buckets.");
    expect(rowFormReason(exRow("ernie", savedRoi(["A.csv"]), 4))).toBeNull();
  });

  it("asks for a threshold only when focality is in manual mode", () => {
    const row = flexRow("ernie");
    expect(rowFormReason({ ...row, flex: { ...row.flex, goal: "focality", focalityMode: "manual" } })).toBe(
      "Enter at least one E-field threshold.",
    );
    // Adaptive/Pareto derive their thresholds; the manual field is not theirs to fill.
    expect(rowFormReason({ ...row, flex: { ...row.flex, goal: "focality", focalityMode: "adaptive" } })).toBeNull();
    expect(rowFormReason({ ...row, flex: { ...row.flex, goal: "focality", focalityMode: "pareto" } })).toBeNull();
  });

  it("asks for the net a mapped-electrode simulation needs", () => {
    const row = flexRow("ernie");
    expect(rowFormReason({ ...row, flex: { ...row.flex, enableMapping: true, eegNet: undefined } })).toBe(
      "Select an EEG net for the mapped-electrode simulation.",
    );
  });
});
