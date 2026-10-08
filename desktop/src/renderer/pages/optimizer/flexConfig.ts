/**
 * Form state -> `FlexConfig` wire shape. Parity source: `tit/gui/flex_search_tab.py`
 * `_build_flex_config` (field-for-field defaults and mapping), `tit/gui/components/
 * electrode_config.py` (`ElectrodeConfigWidget`), `tit/gui/components/solver_params.py`
 * (`SolverParamsWidget`). See PARITY.md for the full checklist this was built against.
 */
import { appDefaults } from "../../forms/appDefaults";
import type { RoiConfig } from "../_shared/roi/types";
import type { components } from "../../api/schema";
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
  skinRegionMarginMm: number;
  avoidLandmarkRegions: boolean;
  visualizeSkinElectrodes: boolean;
  skinVisualizationNet: string | undefined;

  // Automatic Simulations.
  runFinalElectrodeSimulation: boolean;
  enableMapping: boolean;
  eegNet: string | undefined;
}

type FlexDefaults = components["schemas"]["FlexConfig"];

/** The form's starting values: `x-app-defaults.flex` (and the adaptive / multi-threshold kinds'
 *  own settings) over `FlexConfig`'s; the choices with no config field of their own are below. */
export function defaultFlexFormState(): FlexFormState {
  const d = appDefaults("flex", "FlexConfig") as FlexDefaults;
  const adaptive = (appDefaults("flex_adaptive", "FlexConfig") as FlexDefaults).adaptive!;
  const pareto = (appDefaults("flex_pareto", "FlexConfig") as FlexDefaults).pareto as { roi_pcts: number[]; nonroi_pcts: number[] };
  const [mutationMin, mutationMax] = (d.mutation as string).split(",").map(Number) as [number, number];
  const [dimensionWidth, dimensionHeight] = d.electrode.dimensions as [number, number];
  return {
    goal: d.goal,
    postproc: d.postproc,
    anisotropyType: d.anisotropy_type as FlexFormState["anisotropyType"],
    anisoMaxratio: d.aniso_maxratio,
    anisoMaxcond: d.aniso_maxcond,

    currentMA: d.current_mA,
    electrodeShape: d.electrode.shape as ElectrodeShape,
    dimensionWidth,
    dimensionHeight,
    gelThickness: d.electrode.gel_thickness,
    minElectrodeDistance: d.min_electrode_distance,

    optimizeCurrentRatio: d.optimize_current_ratio,
    ratioLevels: d.ratio_levels,
    ratioTotalMA: d.ratio_total_mA ?? undefined,

    // A focality search's non-ROI and threshold mode: what FlexConfig's own None amounts to.
    nonRoiMethod: "everything_else",
    intensityWeight: d.intensity_weight,
    focalityMode: "adaptive",
    manualThresholds: "",
    adaptiveNonRoiPct: adaptive.nonroi_percentage,
    adaptiveRoiPct: adaptive.roi_percentage,
    paretoRoiPcts: pareto.roi_pcts.join(","),
    paretoNonRoiPcts: pareto.nonroi_pcts.join(","),

    nMultistart: d.n_multistart,
    maxIterations: d.max_iterations as number,
    populationSize: d.population_size as number,
    tolerance: d.tolerance as number,
    mutationMin,
    mutationMax,
    recombination: d.recombination as number,
    skinRegionMarginMm: d.skin_region_margin_mm,
    avoidLandmarkRegions: d.avoid_landmark_regions,
    visualizeSkinElectrodes: d.skin_visualization_net != null,
    skinVisualizationNet: d.skin_visualization_net ?? undefined,

    runFinalElectrodeSimulation: d.run_final_electrode_simulation,
    enableMapping: d.enable_mapping,
    eegNet: d.eeg_net ?? undefined,
  };
}

/** Threshold modes dispatch to the existing adaptive and multi-threshold drivers. */
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

/** Build the existing FlexConfig shape, including its threshold driver settings. */
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
    min_electrode_distance: form.minElectrodeDistance,
    detailed_results: false,
    visualize_valid_skin_region: true,
    skin_visualization_net: form.visualizeSkinElectrodes ? (form.skinVisualizationNet ?? null) : null,
    skin_region_margin_mm: form.skinRegionMarginMm,
    avoid_landmark_regions: form.avoidLandmarkRegions,
  };

  if (kind === "flex_adaptive") {
    base.adaptive = { nonroi_percentage: form.adaptiveNonRoiPct, roi_percentage: form.adaptiveRoiPct };
  }
  if (kind === "flex_pareto") {
    base.pareto = { roi_pcts: parsePctList(form.paretoRoiPcts), nonroi_pcts: parsePctList(form.paretoNonRoiPcts) };
  }
  return base;
}
