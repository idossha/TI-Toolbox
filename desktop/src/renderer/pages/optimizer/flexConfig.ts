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

/** A number field's accepted range. One table feeds the input's min/max attributes, its invalid
 *  mark and the row gate (`flexFormReason`), so the three cannot disagree. `exclusiveMin` /
 *  `exclusiveMax`: the value must be strictly inside (a current or a size of 0 is not a value). */
export interface FlexBound {
  label: string;
  unit?: string;
  min: number;
  max?: number;
  exclusiveMin?: boolean;
  exclusiveMax?: boolean;
  integer?: boolean;
}

/** Lower ends from `FlexConfig.__post_init__` (tit/opt/config.py) and physics (a current, a size,
 *  a distance is > 0); upper ends from FlexConfig (intensity weight in [0, 1], a percentage below
 *  100) or the bound the input already declared (51 ratio levels, 20 runs). */
export const FLEX_BOUNDS = {
  currentMA: { label: "Current", unit: "mA", min: 0, exclusiveMin: true },
  dimensionWidth: { label: "Electrode width", unit: "mm", min: 0, exclusiveMin: true },
  dimensionHeight: { label: "Electrode height", unit: "mm", min: 0, exclusiveMin: true },
  gelThickness: { label: "Gel thickness", unit: "mm", min: 0, exclusiveMin: true },
  minElectrodeDistance: { label: "Min distance", unit: "mm", min: 0, exclusiveMin: true },
  intensityWeight: { label: "Intensity preference", min: 0, max: 1 },
  ratioLevels: { label: "Ratio levels", min: 2, max: 51, integer: true },
  ratioTotalMA: { label: "Ratio total current", unit: "mA", min: 0, exclusiveMin: true },
  adaptiveNonRoiPct: { label: "Non-ROI share", unit: "%", min: 0, max: 100, exclusiveMin: true, exclusiveMax: true },
  adaptiveRoiPct: { label: "ROI share", unit: "%", min: 0, max: 100, exclusiveMin: true, exclusiveMax: true },
  nMultistart: { label: "Optimization runs", min: 1, max: 20, integer: true },
} as const satisfies Record<string, FlexBound>;

export type FlexBoundKey = keyof typeof FLEX_BOUNDS;

/** Why *value* is outside *key*'s bound — a sentence naming the field — or null. A cleared
 *  optional field (undefined/null) is in bounds. */
export function boundReason(key: FlexBoundKey, value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const b: FlexBound = FLEX_BOUNDS[key];
  const unit = b.unit === undefined ? "" : b.unit === "%" ? "%" : ` ${b.unit}`;
  if (!Number.isFinite(value)) return `${b.label} must be a number.`;
  if (b.integer && !Number.isInteger(value)) return `${b.label} must be a whole number.`;
  if (b.exclusiveMin ? value <= b.min : value < b.min) return `${b.label} must be ${b.exclusiveMin ? "greater than" : "at least"} ${b.min}${unit}.`;
  if (b.max !== undefined && (b.exclusiveMax ? value >= b.max : value > b.max)) return `${b.label} must be ${b.exclusiveMax ? "less than" : "at most"} ${b.max}${unit}.`;
  return null;
}

/** The bounded fields this form sends, in on-screen order. A field the form does not send (the
 *  intensity weight outside threshold-free focality, the ratio settings with the ratio search off,
 *  the adaptive shares in another mode) cannot block it. */
function activeBoundFields(form: FlexFormState): FlexBoundKey[] {
  const keys: FlexBoundKey[] = [];
  if (form.goal === "focality_tf") keys.push("intensityWeight");
  if (form.goal === "focality" && form.focalityMode === "adaptive") keys.push("adaptiveNonRoiPct", "adaptiveRoiPct");
  keys.push("currentMA", "dimensionWidth", "dimensionHeight", "gelThickness", "minElectrodeDistance");
  if (form.optimizeCurrentRatio) keys.push("ratioLevels", "ratioTotalMA");
  keys.push("nMultistart");
  return keys;
}

/** The inline error for one bounded field, or undefined when it is in bounds. */
export function flexFieldError(form: FlexFormState, key: FlexBoundKey): string | undefined {
  return boundReason(key, form[key]) ?? undefined;
}

const THRESHOLD_PLACEHOLDERS = new Set(["", "dynamic", "auto"]);

/**
 * `FlexConfig`'s rule for a fixed-threshold focality run (tit/opt/config.py `_parse_thresholds`;
 * SimNIBS `measures.ROC`): one value (non-ROI max = ROI min) or two (non-ROI max, ROI min), each
 * a finite field strength > 0 V/m, the first not above the second. A single run has no default —
 * SimNIBS refuses a focality run without a threshold — so a blank box is an error.
 */
export function thresholdsReason(text: string): string | null {
  const raw = text.trim();
  if (THRESHOLD_PLACEHOLDERS.has(raw.toLowerCase())) {
    return "Enter the E-field thresholds: one value (non-ROI max = ROI min) or two (non-ROI max, ROI min) in V/m.";
  }
  const parts = raw.split(",").map((s) => s.trim());
  if (parts.length > 2) return `Give one or two thresholds, not ${parts.length}.`;
  const values = parts.map((p) => (p === "" ? Number.NaN : Number(p)));
  if (values.some((v) => !Number.isFinite(v) || v <= 0)) return "Each threshold must be a number greater than 0 V/m.";
  if (values.length === 2 && values[0]! > values[1]!) return "The non-ROI maximum (first value) may not exceed the ROI minimum (second value).";
  return null;
}

/** `FlexConfig.ParetoSweepConfig`: both lists non-empty, every value in (0, 100), every non-ROI
 *  percentage below every ROI percentage. A token that is not a number is an error, never dropped. */
export function paretoReason(form: FlexFormState): string | null {
  for (const [label, text] of [["ROI thresholds", form.paretoRoiPcts], ["Non-ROI thresholds", form.paretoNonRoiPcts]] as const) {
    const tokens = text.split(",").map((s) => s.trim()).filter((s) => s.length > 0);
    if (tokens.length === 0) return `${label}: enter at least one percentage.`;
    const bad = tokens.find((t) => !(Number(t) > 0 && Number(t) < 100));
    if (bad !== undefined) return `${label}: '${bad}' is not a percentage between 0 and 100.`;
  }
  if (Math.max(...parsePctList(form.paretoNonRoiPcts)) >= Math.min(...parsePctList(form.paretoRoiPcts))) {
    return "Every non-ROI threshold must be below every ROI threshold.";
  }
  return null;
}

/** Why this flex form cannot run as it stands, or null: the bounds table, then the cross-field
 *  rules `FlexConfig` enforces, in on-screen order. */
export function flexFormReason(form: FlexFormState): string | null {
  for (const key of activeBoundFields(form)) {
    const reason = boundReason(key, form[key]);
    if (reason) return reason;
  }
  if (form.electrodeShape === "ellipse" && form.dimensionWidth !== form.dimensionHeight) return "Unequal ellipse dimensions are unsupported. Use equal dimensions or a rectangle.";
  if (form.goal !== "focality") return null;
  if (form.focalityMode === "manual") return thresholdsReason(form.manualThresholds);
  if (form.focalityMode === "adaptive" && form.adaptiveNonRoiPct >= form.adaptiveRoiPct) return "The non-ROI share must be below the ROI share.";
  if (form.focalityMode === "pareto") return paretoReason(form);
  return null;
}
