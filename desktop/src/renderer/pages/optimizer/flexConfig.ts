/**
 * Form state -> `FlexConfig` wire shape. Parity source: `tit/gui/flex_search_tab.py`
 * `_build_flex_config` (field-for-field defaults and mapping), `tit/gui/components/
 * electrode_config.py` (`ElectrodeConfigWidget`), `tit/gui/components/solver_params.py`
 * (`SolverParamsWidget`). See PARITY.md for the full checklist this was built against.
 */
import type { RoiConfig } from "../_shared/roi/types";
import type { FlexConfigWire } from "./api";

export type OptGoal = "mean" | "max" | "focality" | "focality_tf";
export type FieldPostproc = "max_TI" | "dir_TI_normal" | "dir_TI_tangential";
export type NonRoiMethod = "everything_else" | "specific";
export type FocalityMode = "manual" | "adaptive" | "pareto";
export type ElectrodeShape = "ellipse" | "rect";

export interface FlexFormState {
  goal: OptGoal;
  postproc: FieldPostproc;
  anisotropyType: "scalar" | "vn";
  anisoMaxratio: number;
  anisoMaxcond: number;

  // Electrode Parameters (kept apart from Hyper Parameters — DESIGN.md / memory
  // feedback_gui_param_placement.md).
  currentMA: number;
  electrodeShape: ElectrodeShape;
  dimensionWidth: number;
  dimensionHeight: number;
  gelThickness: number;
  minElectrodeDistance: number;

  // Current-ratio search (applies to every goal).
  optimizeCurrentRatio: boolean;
  ratioLevels: number;
  ratioTotalMA: number | undefined;

  // Focality (goal === "focality" | "focality_tf").
  nonRoiMethod: NonRoiMethod;
  intensityWeight: number;
  focalityMode: FocalityMode;
  manualThresholds: string;
  adaptiveNonRoiPct: number;
  adaptiveRoiPct: number;
  paretoRoiPcts: string;
  paretoNonRoiPcts: string;

  // Hyper Parameters.
  nMultistart: number;
  maxIterations: number;
  populationSize: number;
  tolerance: number;
  mutationMin: number;
  mutationMax: number;
  recombination: number;
  cpus: number | undefined;
  skinRegionMarginMm: number;
  avoidLandmarkRegions: boolean;
  visualizeSkinElectrodes: boolean;
  skinVisualizationNet: string | undefined;

  // Automatic Simulations.
  runFinalElectrodeSimulation: boolean;
  enableMapping: boolean;
  eegNet: string | undefined;
}

export function defaultFlexFormState(): FlexFormState {
  return {
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
    cpus: undefined,
    skinRegionMarginMm: 0.0,
    avoidLandmarkRegions: true,
    visualizeSkinElectrodes: false,
    skinVisualizationNet: undefined,

    runFinalElectrodeSimulation: false,
    enableMapping: false,
    eegNet: undefined,
  };
}

/** "flex" (mean/max/focality_tf, and focality with manual thresholds), or the two orchestration
 *  job kinds for the ROC-focality Manual-alternative modes (see PARITY.md "adaptive/pareto" note
 *  for the open contract gap these two kinds carry). */
export function jobKindFor(form: FlexFormState): "flex" | "flex_adaptive" | "flex_pareto" {
  if (form.goal !== "focality") return "flex";
  if (form.focalityMode === "adaptive") return "flex_adaptive";
  if (form.focalityMode === "pareto") return "flex_pareto";
  return "flex";
}

export function parsePctList(text: string): number[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map(Number)
    .filter((n) => Number.isFinite(n));
}

export function sweepCombinationCount(form: FlexFormState): number {
  return parsePctList(form.paretoRoiPcts).length * parsePctList(form.paretoNonRoiPcts).length;
}

/**
 * Build the `FlexConfig`-shaped request body. `flex_adaptive`/`flex_pareto` jobs additionally
 * carry an `adaptive`/`pareto` block — a provisional shape (no `AdaptiveFocalityConfig`/
 * `ParetoSweepConfig` exists in `contracts/generated/config.schema.json` yet; see PARITY.md and the final report)
 * proposed for B4/F1b to formalise once those runners exist.
 */
export function buildFlexConfig(subjectId: string, form: FlexFormState, roi: RoiConfig, nonRoi: RoiConfig | undefined): FlexConfigWire {
  const isFocality = form.goal === "focality" || form.goal === "focality_tf";
  const kind = jobKindFor(form);

  const base: FlexConfigWire = {
    subject_id: subjectId,
    goal: form.goal,
    postproc: form.postproc,
    anisotropy_type: form.anisotropyType,
    aniso_maxratio: form.anisoMaxratio,
    aniso_maxcond: form.anisoMaxcond,
    current_mA: form.currentMA,
    electrode: {
      shape: form.electrodeShape,
      dimensions: [form.dimensionWidth, form.dimensionHeight],
      gel_thickness: form.gelThickness,
    },
    roi,
    non_roi_method: isFocality ? form.nonRoiMethod : null,
    non_roi: isFocality && form.nonRoiMethod === "specific" ? (nonRoi ?? null) : null,
    thresholds: form.goal === "focality" && form.focalityMode === "manual" ? form.manualThresholds : null,
    intensity_weight: form.goal === "focality_tf" ? form.intensityWeight : 0.0,
    optimize_current_ratio: form.optimizeCurrentRatio,
    ratio_total_mA: form.optimizeCurrentRatio ? (form.ratioTotalMA ?? null) : null,
    ratio_levels: form.ratioLevels,
    eeg_net: form.enableMapping ? (form.eegNet ?? null) : null,
    enable_mapping: form.enableMapping,
    disable_mapping_simulation: false,
    output_folder: null,
    run_final_electrode_simulation: form.runFinalElectrodeSimulation,
    n_multistart: form.nMultistart,
    max_iterations: form.maxIterations,
    population_size: form.populationSize,
    tolerance: form.tolerance,
    mutation: `${form.mutationMin},${form.mutationMax}`,
    recombination: form.recombination,
    cpus: form.cpus ?? null,
    min_electrode_distance: form.minElectrodeDistance,
    detailed_results: false,
    visualize_valid_skin_region: true,
    skin_visualization_net: form.visualizeSkinElectrodes ? (form.skinVisualizationNet ?? null) : null,
    skin_region_margin_mm: form.skinRegionMarginMm,
    avoid_landmark_regions: form.avoidLandmarkRegions,
  };

  if (kind === "flex_adaptive") {
    base.adaptive = { non_roi_pct: form.adaptiveNonRoiPct, roi_pct: form.adaptiveRoiPct };
  }
  if (kind === "flex_pareto") {
    base.pareto = { roi_pcts: parsePctList(form.paretoRoiPcts), nonroi_pcts: parsePctList(form.paretoNonRoiPcts) };
  }
  return base;
}
