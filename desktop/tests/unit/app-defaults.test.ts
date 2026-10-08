/**
 * The run pages start where they did before their defaults moved to the server (2026-10-08).
 *
 * What this pins: `defaultConfig()` (Pre-processing), `defaultJobSettings()` (Simulator),
 * `defaultFlexFormState()` / `defaultExFormState()` / `defaultMExFormState()` (Optimizer), built
 * from `x-app-defaults` + the schema's own defaults in the committed
 * `contracts/generated/config.schema.json` (tests/unit/setup-app-defaults.ts loads it).
 * Where the numbers come from: the literal default objects these functions returned at 07ee0ac0
 * (`git show 07ee0ac0:desktop/src/renderer/pages/{preprocess/config.ts,simulator/types.ts,
 * optimizer/flexConfig.ts,optimizer/exConfig.ts}`), copied verbatim — groundTruth: authored by the
 * pages, not derived from the table under test.
 * Reproduce: cd desktop && npx vitest run tests/unit/app-defaults.test.ts
 * Deliberately elsewhere: the server filling the same table into an agent's config
 * (tests/test_jobs_routes.py, tests/test_agent_plugin_jobs.py).
 */
import { describe, expect, it } from "vitest";
import { defaultConfig } from "../../src/renderer/pages/preprocess/config";
import { defaultJobSettings } from "../../src/renderer/pages/simulator/types";
import { defaultFlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";
import { defaultExFormState, defaultMExFormState } from "../../src/renderer/pages/optimizer/exConfig";

describe("run-page defaults come from the server's table unchanged", () => {
  it("Pre-processing", () => {
    expect(defaultConfig()).toStrictEqual({
      subject_ids: [],
      convert_dicom: true,
      run_fastsurfer: true,
      run_freesurfer: false,
      freesurfer_recon_all: true,
      freesurfer_subregions: ["thalamus", "hippo-amygdala"],
      freesurfer_threads: null,
      charm_options: null,
      charm_threads: null,
      fastsurfer_threads: null,
      create_m2m: true,
      run_tissue_analysis: false,
      run_qsiprep: false,
      run_qsirecon: false,
      qsiprep_config: null,
      qsi_recon_config: null,
      extract_dti: false,
      skip_existing_outputs: true,
      replace_existing_outputs: false,
    });
  });

  it("Simulator", () => {
    expect(defaultJobSettings()).toStrictEqual({
      conductivity: "scalar",
      anisoMaxratio: 10,
      anisoMaxcond: 2,
      electrodeShape: "ellipse",
      dimensions: [8, 8],
      gelThickness: 4,
      outputFields: ["TI_max"],
      mapToMni: false,
      mapToFsavg: false,
      carrierOnly: false,
      customConductivities: {},
    });
  });

  it("Optimizer flex", () => {
    expect(defaultFlexFormState()).toStrictEqual({
      goal: "mean",
      postproc: "max_TI",
      anisotropyType: "scalar",
      anisoMaxratio: 10.0,
      anisoMaxcond: 2.0,
      currentMA: 1.0,
      electrodeShape: "ellipse",
      dimensionWidth: 8,
      dimensionHeight: 8,
      gelThickness: 4,
      minElectrodeDistance: 5.0,
      optimizeCurrentRatio: false,
      ratioLevels: 21,
      ratioTotalMA: undefined,
      nonRoiMethod: "everything_else",
      intensityWeight: 0.0,
      focalityMode: "adaptive",
      manualThresholds: "",
      adaptiveNonRoiPct: 20,
      adaptiveRoiPct: 80,
      paretoRoiPcts: "80",
      paretoNonRoiPcts: "20,30,40",
      nMultistart: 1,
      maxIterations: 500,
      populationSize: 13,
      tolerance: 0.1,
      mutationMin: 0.01,
      mutationMax: 0.5,
      recombination: 0.7,
      skinRegionMarginMm: 0.0,
      avoidLandmarkRegions: true,
      visualizeSkinElectrodes: false,
      skinVisualizationNet: undefined,
      runFinalElectrodeSimulation: false,
      enableMapping: false,
      eegNet: undefined,
    });
  });

  it("Optimizer ex and mEx", () => {
    expect(defaultExFormState()).toStrictEqual({
      electrodeMode: "bucketed",
      buckets: { e1_plus: [], e1_minus: [], e2_plus: [], e2_minus: [] },
      pool: [],
      totalCurrent: 2.0,
      currentStep: 0.2,
      channelLimit: 1.6,
    });
    expect(defaultMExFormState()).toStrictEqual({
      buckets: { e1_plus: [], e1_minus: [], e2_plus: [], e2_minus: [], e3_plus: [], e3_minus: [], e4_plus: [], e4_minus: [] },
      currentMa: 2.0,
      symmetricBucket: false,
      symmetryPairing: "within_pairs",
    });
  });

  it("each call is a fresh copy, so editing one form never changes the next", () => {
    defaultJobSettings().dimensions[0] = 99;
    expect(defaultJobSettings().dimensions).toEqual([8, 8]);
  });
});
