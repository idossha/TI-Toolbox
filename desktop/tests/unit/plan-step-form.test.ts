/**
 * "Open in form" (ARCHITECTURE §6, app/proposals/stepForm.tsx): a plan step's config becomes each
 * run page's own form state and comes back as the step's config. Pins:
 *  - the Optimizer's inverse mappings undo its builders: `flexFormFromConfig(buildFlexConfig(f))`
 *    is `f`, `roiFromConfig(roiToConfig(v))` is `v`, and the ex/mEx forms survive their builders;
 *  - a step saved from the forms keeps fields the form does not show, keeps its kind, and refuses
 *    what one step cannot say (different settings per subject, a changed kind, two searches);
 *  - the Simulator turns a sim step into subject × montage rows and back, and a sim_from_flex step
 *    into one flex row per subject that keeps its flex step unless another run is picked;
 *  - Pre-processing saves the form's stages over the step's config for the chosen subjects.
 * Expected values are the hand-written forms and configs below (authored in the contract's
 * shapes), never the code's own output. Reproduce: cd desktop && npx vitest run tests/unit/plan-step-form.test.ts
 */
import { describe, expect, it } from "vitest";
import type { PlanStepTarget } from "../../src/renderer/app/proposals/stepForm";
import { planStepTarget, stepRoute } from "../../src/renderer/app/proposals/stepForm";
import type { Proposal } from "../../src/renderer/app/proposals/model";
import { roiToConfig, type RoiValue } from "../../src/renderer/pages/_shared/roi";
import { buildFlexConfig, defaultFlexFormState, type FlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";
import { buildExConfig, buildMExConfig, defaultExFormState, defaultMExFormState, exTargets } from "../../src/renderer/pages/optimizer/exConfig";
import { exFormFromConfig, flexFormFromConfig, mexFormFromConfig, netFromLeadfield, optStepEdit, optStepRows, roiFromConfig } from "../../src/renderer/pages/optimizer/planStep";
import { simStepEdit, simStepRows } from "../../src/renderer/pages/simulator/planStep";
import { defaultJobSettings } from "../../src/renderer/pages/simulator/types";
import type { GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { defaultConfig, preStepEdit, preStepValues } from "../../src/renderer/pages/preprocess/index";

const DK40 = { id: "DK40", path: "/p/sub-101/m2m_101/segmentation/lh.DK40.annot" };
const ASEG = { id: "aseg", path: "/p/freesurfer/sub-101/mri/aseg.mgz" };
const ATLASES = [DK40, ASEG];
const lookup = (id: string) => ATLASES.find((a) => a.id === id);

const target = (kind: string, config: Record<string, unknown>, subjectIds = ["101"], extra: Partial<PlanStepTarget> = {}): PlanStepTarget => ({
  proposalId: "abcdef0123456789",
  stepId: "s1",
  number: 1,
  title: "A plan",
  kind,
  config,
  subjectIds,
  overwrite: false,
  ...extra,
});

describe("Optimizer", () => {
  const form: FlexFormState = {
    ...defaultFlexFormState(),
    goal: "focality_tf",
    postproc: "dir_TI_normal",
    currentMA: 1.5,
    electrodeShape: "rect",
    dimensionWidth: 10,
    dimensionHeight: 20,
    gelThickness: 3,
    intensityWeight: 0.7,
    nonRoiMethod: "specific",
    nMultistart: 4,
    mutationMin: 0.2,
    mutationMax: 0.9,
    enableMapping: true,
    eegNet: "GSN-HydroCel-185.csv",
  };
  const cortical: RoiValue = { mode: "cortical", space: "subject", atlas: "DK40", regions: [{ id: 17, name: "17", hemi: "lh" }, { id: 17, name: "17", hemi: "rh" }] };
  const sphere: RoiValue = { mode: "spherical", space: "mni", volumetric: true, tissues: "WM", spheres: [{ x: -10, y: -60, z: 40, radius: 8 }, { x: 10, y: -60, z: 40, radius: 8 }] };
  const sub: RoiValue = { mode: "subcortical", space: "subject", atlas: "aseg", regions: [{ id: 10, name: "10" }, { id: 49, name: "49" }], tissues: "both" };
  const mask: RoiValue = { mode: "mask", path: "/p/masks/target.nii.gz", space: "mni", tissues: "GM" };

  it("undoes buildFlexConfig, including the focality mode the kind encodes", () => {
    expect(flexFormFromConfig(buildFlexConfig("101", form, roiToConfig(cortical, lookup)!, roiToConfig(sphere, lookup)), "flex")).toEqual(form);
    // intensity_weight travels only for focality_tf (0.0 otherwise), so other goals read the default.
    const adaptive = { ...form, intensityWeight: defaultFlexFormState().intensityWeight, goal: "focality" as const, focalityMode: "adaptive" as const, adaptiveNonRoiPct: 40, adaptiveRoiPct: 60 };
    expect(flexFormFromConfig(buildFlexConfig("101", adaptive, roiToConfig(sub, lookup)!, undefined), "flex_adaptive")).toEqual(adaptive);
    const manual = { ...form, intensityWeight: defaultFlexFormState().intensityWeight, goal: "focality" as const, focalityMode: "manual" as const, manualThresholds: "0.2,0.5" };
    expect(flexFormFromConfig(buildFlexConfig("101", manual, roiToConfig(sub, lookup)!, undefined), "flex")).toEqual(manual);
  });

  it("undoes roiToConfig for every mode the flex picker builds, finding the atlas by path", () => {
    for (const roi of [cortical, sphere, sub, mask]) expect(roiFromConfig(roiToConfig(roi, lookup), ATLASES)).toEqual(roi);
    // An agent's scalar sphere (SphericalROI broadcasts) is one sphere.
    expect(roiFromConfig({ _type: "SphericalROI", x: -10, y: -60, z: 40, radius: 10, use_mni: true }, [])).toMatchObject({ spheres: [{ x: -10, y: -60, z: 40, radius: 10 }], space: "mni" });
    expect(roiFromConfig({ _type: "SubcorticalROI", atlas_path: "/elsewhere.nii.gz", label: [1] }, ATLASES)).toBeNull(); // not in the catalog
  });

  it("undoes the ex and mEx builders", () => {
    const ex = { ...defaultExFormState(), buckets: { e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4", "E5"] }, totalCurrent: 2, currentStep: 0.25, channelLimit: 1.5 };
    const [t] = exTargets({ mode: "saved", selected: ["a", "b"], combine: true, radius: 5, space: "mni" }, () => undefined);
    expect(exFormFromConfig(buildExConfig("101", "/p/sub-101/leadfields/GSN/leadfield.hdf5", ex, t!, "run1") as Record<string, unknown>)).toEqual(ex);
    const pool = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["E1", "E2", "E3", "E4"] };
    expect(exFormFromConfig(buildExConfig("101", "/x.hdf5", pool, t!, "") as Record<string, unknown>)).toMatchObject({ electrodeMode: "all", pool: pool.pool });
    const mex = { ...defaultMExFormState(), currentMa: 3, symmetricBucket: true, symmetryPairing: "cross_pairs" as const, buckets: Object.fromEntries(Object.keys(defaultMExFormState().buckets).map((k, i) => [k, [`E${i}`]])) };
    expect(mexFormFromConfig(buildMExConfig("101", "/x.hdf5", mex, t!, "") as Record<string, unknown>)).toEqual(mex);
    expect(netFromLeadfield("/p/sub-101/leadfields/GSN-HydroCel-185/leadfield.hdf5")).toBe("GSN-HydroCel-185");
    expect(netFromLeadfield("/p/leadfields/101_leadfield_EEG10-10.csv.hdf5")).toBe("EEG10-10");
  });

  const agentFlex = {
    goal: "mean",
    current_mA: 1,
    output_folder: "thalamus_mean",
    electrode: { shape: "ellipse", dimensions: [8, 8], gel_thickness: 4 },
    roi: { _type: "SubcorticalROI", atlas_path: [ASEG.path, ASEG.path], label: [10, 49], tissues: "GM", atlas_space: "subject" },
    agent_note: "kept",
  };
  const resolve = { atlas: () => lookup, leadfield: () => "/p/lf.hdf5" };

  it("opens a flex step as one row per subject and saves it back with the form's change", () => {
    const step = target("flex", agentFlex, ["101", "ernie"]);
    const rows = optStepRows(step, ATLASES);
    expect(rows.map((r) => [r.subjectId, r.method, r.runName, r.flex.goal, r.flex.currentMA])).toEqual([
      ["101", "flex", "thalamus_mean", "mean", 1],
      ["ernie", "flex", "thalamus_mean", "mean", 1],
    ]);
    expect(rows[0]!.roi).toEqual({ mode: "subcortical", space: "subject", atlas: "aseg", regions: [{ id: 10, name: "10" }, { id: 49, name: "49" }], tissues: "GM" });
    const edited = rows.map((r) => ({ ...r, flex: { ...r.flex, goal: "max" as const } }));
    const edit = optStepEdit(step, edited, resolve);
    expect(edit.subject_ids).toEqual(["101", "ernie"]);
    expect(edit.config).toMatchObject({ goal: "max", output_folder: "thalamus_mean", agent_note: "kept", roi: agentFlex.roi });
    expect(edit.config).not.toHaveProperty("subject_id");
  });

  it("refuses what one step cannot say", () => {
    const step = target("flex", agentFlex, ["101", "ernie"]);
    const rows = optStepRows(step, ATLASES);
    expect(() => optStepEdit(step, [rows[0]!, { ...rows[1]!, flex: { ...rows[1]!.flex, currentMA: 2 } }], resolve)).toThrow(/same settings/);
    const adaptive = rows.map((r) => ({ ...r, flex: { ...r.flex, goal: "focality" as const, focalityMode: "adaptive" as const } }));
    expect(() => optStepEdit(step, adaptive, resolve)).toThrow(/This step is a Flex-search; the form now describes a Flex-search \(adaptive focality\)/);
  });
});

describe("Simulator", () => {
  const params = defaultJobSettings() as GlobalParams;
  const sim = {
    montages: [
      { _type: "Montage", name: "F3_F4", mode: "net", electrode_pairs: [["F3", "F4"], ["C3", "C4"]], eeg_net: "GSN-HydroCel-185.csv" },
      { _type: "Montage", name: "P3_P4", mode: "net", electrode_pairs: [["P3", "P4"], ["O1", "O2"]], eeg_net: "GSN-HydroCel-185.csv" },
    ],
    intensities: [2, 2],
    conductivity: "dir",
    agent_note: "kept",
  };

  it("opens a sim step as subject × montage rows and saves the edited currents back", () => {
    const step = target("sim", sim, ["101", "ernie"]);
    const rows = simStepRows(step);
    expect(rows.map((r) => [r.subjectId, r.source, r.name, r.eegNet, r.currents, r.settings?.conductivity])).toEqual([
      ["101", "montage", "F3_F4", "GSN-HydroCel-185.csv", "2,2", "dir"],
      ["101", "montage", "P3_P4", "GSN-HydroCel-185.csv", "2,2", "dir"],
      ["ernie", "montage", "F3_F4", "GSN-HydroCel-185.csv", "2,2", "dir"],
      ["ernie", "montage", "P3_P4", "GSN-HydroCel-185.csv", "2,2", "dir"],
    ]);
    const edit = simStepEdit(step, rows.map((r) => ({ ...r, currents: "1.5,1.5" })), params);
    expect(edit.subject_ids).toEqual(["101", "ernie"]);
    expect(edit.config).toMatchObject({ intensities: [1.5, 1.5], conductivity: "dir", agent_note: "kept" });
    expect((edit.config!.montages as { name: string; electrode_pairs: string[][] }[]).map((m) => [m.name, m.electrode_pairs])).toEqual([
      ["F3_F4", [["F3", "F4"], ["C3", "C4"]]],
      ["P3_P4", [["P3", "P4"], ["O1", "O2"]]],
    ]);
    expect(edit.config).not.toHaveProperty("subject_id");
  });

  it("refuses rows one step cannot run: different per subject, or per montage", () => {
    const step = target("sim", sim, ["101", "ernie"]);
    const rows = simStepRows(step);
    expect(() => simStepEdit(step, rows.slice(0, 3), params)).toThrow(/same jobs on every subject/);
    const perMontage = rows.map((r) => (r.name === "P3_P4" ? { ...r, currents: "1,1" } : r));
    expect(() => simStepEdit(step, perMontage, params)).toThrow(/same currents and settings/);
  });

  it("opens a sim_from_flex step as the flex step's run, and keeps the step unless another run is picked", () => {
    const step = target("sim_from_flex", { flex_step: "opt", conductivity: "scalar" }, ["101"], { flexRun: "thalamus_mean" });
    const [row] = simStepRows(step);
    expect(row).toMatchObject({ subjectId: "101", source: "flex", name: "thalamus_mean", planFlexStep: "opt", currents: "" });
    const kept = simStepEdit(step, [{ ...row!, eegNet: "GSN-HydroCel-185.csv" }], params);
    expect(kept.config).toMatchObject({ flex_step: "opt", eeg_net: "GSN-HydroCel-185.csv", conductivity: "scalar" });
    expect(kept.config).not.toHaveProperty("intensities"); // still the run's own
    expect(kept.config).not.toHaveProperty("flex_run");
    const other = simStepEdit(step, [{ ...row!, name: "older_run", planFlexStep: undefined, currents: "1,2" }], params);
    expect(other.config).toMatchObject({ flex_run: "older_run", intensities: [1, 2] });
    expect(other.config).not.toHaveProperty("flex_step");
  });
});

describe("Pre-processing and routing", () => {
  it("saves the form's stages over the step's config for the chosen subjects", () => {
    const step = target("pre", { create_m2m: true, run_freesurfer: false, agent_note: "kept" }, ["101"]);
    const values = preStepValues(step);
    expect(values).toMatchObject({ ...defaultConfig(), create_m2m: true, run_freesurfer: false, subject_ids: [] });
    const edit = preStepEdit(step, { ...values, run_freesurfer: true }, ["101", "ernie"]);
    expect(edit).toMatchObject({ config: { create_m2m: true, run_freesurfer: true, agent_note: "kept" }, subject_ids: ["101", "ernie"] });
    expect(edit.config).not.toHaveProperty("subject_ids");
    expect(() => preStepEdit(step, values, [])).toThrow(/at least one subject/);
  });

  it("sends each kind to the page that builds it", () => {
    expect(["pre", "sim", "sim_from_flex", "flex", "flex_adaptive", "flex_pareto", "ex", "mex", "leadfield"].map(stepRoute)).toEqual([
      "/preprocess", "/simulator", "/simulator", "/optimizer", "/optimizer", "/optimizer", "/optimizer", "/optimizer", null,
    ]);
    const p = { id: "p1", title: "T", steps: [{ id: "opt", kind: "flex", config: { output_folder: "/abs/runs/r1" }, subject_ids: ["101"], overwrite: false }, { id: "sim", kind: "sim_from_flex", config: { flex_step: "opt" }, subject_ids: ["101"], overwrite: true }] } as unknown as Proposal;
    expect(planStepTarget(p, p.steps[1]!)).toMatchObject({ number: 2, flexRun: "r1", overwrite: true, subjectIds: ["101"] });
  });
});
