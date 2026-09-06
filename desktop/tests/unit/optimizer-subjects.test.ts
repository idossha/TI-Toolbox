import { describe, expect, it } from "vitest";
import { atlasTarget, defaultExFormState, defaultMExFormState, exSubmissions, savedTargets } from "../../src/renderer/pages/optimizer/exConfig";
import { defaultFlexFormState, flexSubmissions } from "../../src/renderer/pages/optimizer/flexConfig";
import type { RoiConfig } from "../../src/renderer/pages/_shared/roi";
import type { ExConfigBody, MExConfigBody } from "../../src/renderer/pages/optimizer/api";

/**
 * U16 for the Optimizer: the page owns its subject set, so a run for N subjects has to expand into
 * N (or N × targets) submissions that each carry **that subject's own** paths. U11 removed the
 * shell's batch control, which left `useSubject().batch` with no writer and this page able to run
 * one subject only; these are the derivations the page's Run button drives.
 *
 * The trap these tests exist for: every per-subject path in an optimizer config points into that
 * subject's derivatives — `leadfield_hdf` at `sub-<id>/leadfields/`, an atlas target's
 * `atlas_path` at `derivatives/freesurfer/sub-<id>/mri/`. Resolving either once (for the primary
 * subject) and reusing it across the batch produces jobs that silently optimise every subject
 * against the first subject's anatomy.
 */
const leadfields: Record<string, string | null> = {
  ernie: "/mnt/000/derivatives/SimNIBS/sub-ernie/leadfields/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
  "101": "/mnt/000/derivatives/SimNIBS/sub-101/leadfields/101_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
  MNI152: null,
};
const atlasPath = (subject: string) => `/mnt/000/derivatives/freesurfer/sub-${subject}/mri/aparc.DKTatlas+aseg.mgz`;

const exForm = { ...defaultExFormState(), buckets: { e1_plus: ["Fp1"], e1_minus: ["Fp2"], e2_plus: ["F3"], e2_minus: ["F4"] } };
const mexForm = {
  ...defaultMExFormState(),
  buckets: {
    e1_plus: ["Fp1"], e1_minus: ["Fp2"], e2_plus: ["F3"], e2_minus: ["F4"],
    e3_plus: ["C3"], e3_minus: ["C4"], e4_plus: ["P3"], e4_minus: ["P4"],
  },
};

describe("exSubmissions — one Ex/mEx job per (subject × target)", () => {
  it("carries every selected subject's id, and each subject's own leadfield", () => {
    const runs = exSubmissions(
      "ex",
      ["ernie", "101"],
      (s) => ({ leadfieldHdf: leadfields[s] ?? null, targets: savedTargets(["L_Insula_MNI.csv"], false) }),
      { ex: exForm, mex: mexForm },
      "smoke-ui-ex",
    );
    expect(runs.map((r) => r.subject)).toEqual(["ernie", "101"]);
    expect(runs.map((r) => (r.config as ExConfigBody).subject_id)).toEqual(["ernie", "101"]);
    expect(runs.map((r) => (r.config as ExConfigBody).leadfield_hdf)).toEqual([leadfields.ernie, leadfields["101"]]);
    // The run name is the user's and is shared: the outputs are per subject
    // (`derivatives/SimNIBS/sub-<id>/ex-search/<run>`), so they cannot collide.
    expect(new Set(runs.map((r) => (r.config as ExConfigBody).run_name))).toEqual(new Set(["smoke-ui-ex"]));
  });

  it("resolves a subcortical target's atlas_path per subject, never the primary's for all", () => {
    const runs = exSubmissions(
      "ex",
      ["ernie", "101"],
      (s) => ({
        leadfieldHdf: leadfields[s] ?? null,
        targets: [atlasTarget("aparc.DKTatlas+aseg.mgz", atlasPath(s), [17])],
      }),
      { ex: exForm, mex: mexForm },
      "",
    );
    expect(runs.map((r) => (r.config as ExConfigBody).roi_atlas?.[0]?.atlas_path)).toEqual([atlasPath("ernie"), atlasPath("101")]);
    // The target's *name* is subject-independent — which is why the plan grid can use one column
    // per target across every subject row.
    expect(new Set(runs.map((r) => (r.config as ExConfigBody).roi_name))).toEqual(new Set(["aparc.DKTatlas+aseg.mgz_1region"]));
  });

  it("multiplies subjects by targets, in subject-major order", () => {
    const runs = exSubmissions(
      "ex",
      ["ernie", "101"],
      (s) => ({ leadfieldHdf: leadfields[s] ?? null, targets: savedTargets(["A.csv", "B.csv"], false) }),
      { ex: exForm, mex: mexForm },
      "",
    );
    expect(runs.map((r) => `${r.subject}:${(r.config as ExConfigBody).roi_name}`)).toEqual([
      "ernie:A.csv",
      "ernie:B.csv",
      "101:A.csv",
      "101:B.csv",
    ]);
  });

  it("skips a subject with no leadfield rather than submitting it with another subject's matrix", () => {
    const runs = exSubmissions(
      "ex",
      ["ernie", "MNI152"],
      (s) => ({ leadfieldHdf: leadfields[s] ?? null, targets: savedTargets(["L_Insula_MNI.csv"], false) }),
      { ex: exForm, mex: mexForm },
      "",
    );
    expect(runs.map((r) => r.subject)).toEqual(["ernie"]);
  });

  it("builds mEx configs (eight buckets) for every subject when the method is mex", () => {
    const runs = exSubmissions(
      "mex",
      ["ernie", "101"],
      (s) => ({ leadfieldHdf: leadfields[s] ?? null, targets: savedTargets(["L_Insula_MNI.csv"], false) }),
      { ex: exForm, mex: mexForm },
      "smoke-ui-mex",
    );
    expect(runs).toHaveLength(2);
    for (const run of runs) {
      const config = run.config as MExConfigBody;
      expect((config.electrodes as { e4_minus: string[] }).e4_minus).toEqual(["P4"]);
      expect(config.subject_id).toBe(run.subject);
    }
  });
});

describe("flexSubmissions — one flex job per subject", () => {
  const roiFor = (subject: string): RoiConfig => ({
    _type: "AtlasROI",
    atlas_path: [`/mnt/000/derivatives/freesurfer/sub-${subject}/label/lh.aparc.annot`],
    label: [1],
    hemisphere: ["lh"],
  });

  it("carries each subject's id and its own resolved ROI paths", () => {
    const runs = flexSubmissions(["ernie", "101"], defaultFlexFormState(), (s) => ({ roi: roiFor(s), nonRoi: undefined }));
    expect(runs.map((r) => r.subject)).toEqual(["ernie", "101"]);
    expect(runs.map((r) => r.config.subject_id)).toEqual(["ernie", "101"]);
    expect(runs.map((r) => (r.config.roi as RoiConfig & { atlas_path: string[] }).atlas_path[0])).toEqual([
      "/mnt/000/derivatives/freesurfer/sub-ernie/label/lh.aparc.annot",
      "/mnt/000/derivatives/freesurfer/sub-101/label/lh.aparc.annot",
    ]);
  });

  it("skips a subject whose ROI has not resolved yet", () => {
    const runs = flexSubmissions(["ernie", "101"], defaultFlexFormState(), (s) => ({
      roi: s === "ernie" ? roiFor(s) : undefined,
      nonRoi: undefined,
    }));
    expect(runs.map((r) => r.subject)).toEqual(["ernie"]);
  });
});
