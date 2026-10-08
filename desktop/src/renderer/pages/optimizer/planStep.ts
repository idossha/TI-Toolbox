/**
 * A plan step on the Optimizer (`app/proposals/stepForm.tsx`): a flex / ex / mEx step's config as
 * the jobs table's rows — the inverse of `buildFlexConfig` / `buildExConfig` / `buildMExConfig` and
 * `roiToConfig` — and the rows back through `jobsForRow` as the step's one config. A step runs ONE
 * config on every subject and keeps its kind (the PATCH route edits config and subjects only).
 */
import type { StepEdit } from "../../app/proposals/api";
import { kindLabel } from "../../app/proposals/model";
import type { PlanStepTarget } from "../../app/proposals/stepForm";
import { emptyRoi, type RoiValue, type SphereRow } from "../_shared/roi";
import { defaultExFormState, defaultMExFormState, MEX_BUCKET_KEYS, type ExFormState, type MExFormState } from "./exConfig";
import { defaultFlexFormState, type FlexFormState } from "./flexConfig";
import { netKey } from "./nets";
import { jobsForRow, rowFormReason } from "./plan";
import { emptyOptimizerRow, type OptimizerRow } from "./rows";

type Config = Record<string, unknown>;
/** A catalog atlas: `GET /api/catalog/atlases`'s id and (lh) path. */
export interface CatalogAtlas {
  id: string;
  path: string;
}

const object = (v: unknown): v is Config => !!v && typeof v === "object" && !Array.isArray(v);
const num = <T>(v: unknown, fallback: T): number | T => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
const bool = (v: unknown, fallback: boolean): boolean => (typeof v === "boolean" ? v : fallback);
const str = <T>(v: unknown, fallback: T): string | T => (typeof v === "string" ? v : fallback);
/** ROI fields broadcast: a scalar is one value, a list is per entry. */
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]);
const space = (v: unknown): "subject" | "mni" => (v === "mni" ? "mni" : "subject");
const tissues = (v: unknown): "GM" | "WM" | "both" => (v === "WM" || v === "both" ? v : "GM");

/** `FlexConfig` → the flex form, over the page's defaults; *kind* says which focality mode it is. */
export function flexFormFromConfig(c: Config, kind: string): FlexFormState {
  const d = defaultFlexFormState();
  const e = object(c.electrode) ? c.electrode : {};
  const dims = list(e.dimensions);
  const mutation = typeof c.mutation === "string" ? c.mutation.split(",").map(Number) : [];
  const adaptive = object(c.adaptive) ? c.adaptive : {};
  const pareto = object(c.pareto) ? c.pareto : {};
  const goal = (["mean", "max", "focality", "focality_tf"] as const).find((g) => g === c.goal) ?? d.goal;
  return {
    ...d,
    goal,
    postproc: (["max_TI", "dir_TI_normal", "dir_TI_tangential"] as const).find((p) => p === c.postproc) ?? d.postproc,
    anisotropyType: c.anisotropy_type === "vn" ? "vn" : c.anisotropy_type === "scalar" ? "scalar" : d.anisotropyType,
    anisoMaxratio: num(c.aniso_maxratio, d.anisoMaxratio),
    anisoMaxcond: num(c.aniso_maxcond, d.anisoMaxcond),
    currentMA: num(c.current_mA, d.currentMA),
    electrodeShape: e.shape === "rect" ? "rect" : e.shape === "ellipse" ? "ellipse" : d.electrodeShape,
    dimensionWidth: num(dims[0], d.dimensionWidth),
    dimensionHeight: num(dims[1] ?? dims[0], d.dimensionHeight),
    gelThickness: num(e.gel_thickness, d.gelThickness),
    minElectrodeDistance: num(c.min_electrode_distance, d.minElectrodeDistance),
    optimizeCurrentRatio: bool(c.optimize_current_ratio, d.optimizeCurrentRatio),
    ratioLevels: num(c.ratio_levels, d.ratioLevels),
    ratioTotalMA: num(c.ratio_total_mA, d.ratioTotalMA),
    nonRoiMethod: c.non_roi_method === "specific" ? "specific" : "everything_else",
    intensityWeight: goal === "focality_tf" ? num(c.intensity_weight, d.intensityWeight) : d.intensityWeight,
    focalityMode: kind === "flex_adaptive" ? "adaptive" : kind === "flex_pareto" ? "pareto" : goal === "focality" ? "manual" : d.focalityMode,
    manualThresholds: str(c.thresholds, d.manualThresholds),
    adaptiveNonRoiPct: num(adaptive.nonroi_percentage, d.adaptiveNonRoiPct),
    adaptiveRoiPct: num(adaptive.roi_percentage, d.adaptiveRoiPct),
    paretoRoiPcts: Array.isArray(pareto.roi_pcts) ? pareto.roi_pcts.join(",") : d.paretoRoiPcts,
    paretoNonRoiPcts: Array.isArray(pareto.nonroi_pcts) ? pareto.nonroi_pcts.join(",") : d.paretoNonRoiPcts,
    nMultistart: num(c.n_multistart, d.nMultistart),
    maxIterations: num(c.max_iterations, d.maxIterations),
    populationSize: num(c.population_size, d.populationSize),
    tolerance: num(c.tolerance, d.tolerance),
    mutationMin: num(mutation[0], d.mutationMin),
    mutationMax: num(mutation[1], d.mutationMax),
    recombination: num(c.recombination, d.recombination),
    skinRegionMarginMm: num(c.skin_region_margin_mm, d.skinRegionMarginMm),
    avoidLandmarkRegions: bool(c.avoid_landmark_regions, d.avoidLandmarkRegions),
    visualizeSkinElectrodes: typeof c.skin_visualization_net === "string",
    skinVisualizationNet: str(c.skin_visualization_net, undefined),
    runFinalElectrodeSimulation: bool(c.run_final_electrode_simulation, d.runFinalElectrodeSimulation),
    enableMapping: bool(c.enable_mapping, d.enableMapping),
    eegNet: str(c.eeg_net, undefined),
  };
}

const byPath = (atlases: CatalogAtlas[], path: unknown) => atlases.find((a) => a.path === path)?.id;

/**
 * A `FlexConfig` ROI as the picker's value: the inverse of `roiToConfig`. An atlas is found in
 * *atlases* by its path (a cortical one by its `lh.` file); `null` when it is not in the catalog
 * or the ROI is not one the picker draws.
 */
export function roiFromConfig(roi: unknown, atlases: CatalogAtlas[]): RoiValue | null {
  if (!object(roi)) return null;
  if (roi._type === "SphericalROI") {
    const [x, y, z, r] = [list(roi.x), list(roi.y), list(roi.z), list(roi.radius)];
    const n = Math.max(x.length, y.length, z.length, r.length);
    const at = (v: unknown[], i: number) => num(v.length === 1 ? v[0] : v[i], undefined);
    const spheres: SphereRow[] = Array.from({ length: n }, (_, i) => ({ x: at(x, i), y: at(y, i), z: at(z, i), radius: at(r, i) }));
    return { mode: "spherical", spheres, space: roi.use_mni === true ? "mni" : "subject", volumetric: roi.volumetric === true, tissues: tissues(roi.tissues) };
  }
  if (roi._type === "AtlasROI") {
    const paths = list(roi.atlas_path);
    const labels = list(roi.label);
    const hemis = list(roi.hemisphere);
    const hemiAt = (i: number): "lh" | "rh" => ((hemis.length === 1 ? hemis[0] : hemis[i]) === "rh" ? "rh" : "lh");
    const lh = String(paths[0] ?? "").replace(/(^|\/)rh\./, "$1lh.");
    const atlas = byPath(atlases, lh);
    if (!atlas || labels.length === 0) return null;
    return { mode: "cortical", space: "subject", atlas, regions: labels.map((id, i) => ({ id: Number(id), name: String(id), hemi: hemiAt(i) })) };
  }
  if (roi._type === "SubcorticalROI") {
    const path = list(roi.atlas_path)[0];
    if (roi.label === null || roi.label === undefined) return typeof path === "string" ? { mode: "mask", path, space: space(roi.atlas_space), tissues: tissues(roi.tissues) } : null;
    const atlas = byPath(atlases, path);
    if (!atlas) return null;
    return { mode: "subcortical", space: space(roi.atlas_space), atlas, regions: list(roi.label).map((id) => ({ id: Number(id), name: String(id) })), tissues: tissues(roi.tissues) };
  }
  return null;
}

/** An `ExConfig`/`MExConfig` target as the picker's value (the inverse of `exTargets`). */
export function exRoiFromConfig(c: Config, atlases: CatalogAtlas[]): RoiValue | null {
  const names = c.roi_names;
  const s = space(c.roi_coordinate_space);
  const radius = num(c.roi_radius, 3);
  if (Array.isArray(names) && names.length > 0) return { mode: "saved", selected: names.map(String), combine: true, radius, space: s };
  const atlasRois = Array.isArray(c.roi_atlas) ? c.roi_atlas.filter(object) : [];
  if (atlasRois.length > 0) {
    const first = atlasRois[0]!;
    const roiSpace = space(first.atlas_space ?? s);
    if (first.label === null || first.label === undefined) return { mode: "mask", path: String(first.atlas_path ?? ""), space: roiSpace, tissues: "GM" };
    const atlas = byPath(atlases, first.atlas_path);
    if (!atlas) return null;
    return { mode: "subcortical", space: roiSpace, atlas, regions: atlasRois.map((r) => ({ id: Number(r.label), name: String(r.label) })), tissues: "GM" };
  }
  if (typeof c.roi_name === "string" && c.roi_name) return { mode: "saved", selected: [c.roi_name], combine: false, radius, space: s };
  return null;
}

function bucketsFrom(electrodes: Config, keys: readonly string[]): Record<string, string[]> {
  return Object.fromEntries(keys.map((k) => [k, list(electrodes[k]).map(String)]));
}

export function exFormFromConfig(c: Config): ExFormState {
  const d = defaultExFormState();
  const e = object(c.electrodes) ? c.electrodes : {};
  const pool = e._type === "PoolElectrodes" || Array.isArray(e.electrodes);
  return {
    ...d,
    electrodeMode: pool ? "all" : "bucketed",
    buckets: pool ? d.buckets : bucketsFrom(e, Object.keys(d.buckets)),
    pool: pool ? list(e.electrodes).map(String) : [],
    totalCurrent: num(c.total_current, d.totalCurrent),
    currentStep: num(c.current_step, d.currentStep),
    channelLimit: c.channel_limit === null ? null : num(c.channel_limit, d.channelLimit),
  };
}

export function mexFormFromConfig(c: Config): MExFormState {
  const d = defaultMExFormState();
  const e = object(c.electrodes) ? c.electrodes : {};
  return {
    buckets: bucketsFrom(e, MEX_BUCKET_KEYS),
    currentMa: num(c.current_mA, d.currentMa),
    symmetricBucket: bool(c.symmetric_bucket, d.symmetricBucket),
    symmetryPairing: c.symmetry_pairing === "cross_pairs" ? "cross_pairs" : c.symmetry_pairing === "within_pairs" ? "within_pairs" : d.symmetryPairing,
  };
}

/** `…_leadfield_<net>.hdf5` or `…/leadfields/<net>/leadfield.hdf5` → the bare net name. */
export function netFromLeadfield(path: unknown): string | null {
  if (typeof path !== "string") return null;
  const m = /_leadfield_(.+)\.hdf5$/.exec(path) ?? /\/leadfields\/([^/]+)\/[^/]+\.hdf5$/.exec(path);
  return m ? netKey(m[1]!) : null;
}

/**
 * The step as jobs-table rows, one per subject. *atlases* is the subject's catalog (cortical and
 * subcortical, both spaces) the ROIs are looked up in; *unresolved* is told when a target could not
 * be drawn and is left for the user to pick again.
 */
export function optStepRows(step: PlanStepTarget, atlases: CatalogAtlas[], unresolved: () => void = () => {}): OptimizerRow[] {
  const c = step.config;
  const flex = step.kind.startsWith("flex");
  const roi = (flex ? roiFromConfig(c.roi, atlases) : exRoiFromConfig(c, atlases)) ?? (unresolved(), emptyRoi(flex ? "cortical" : "subcortical"));
  const nonRoi = (flex && c.non_roi_method === "specific" ? roiFromConfig(c.non_roi, atlases) : null) ?? emptyRoi("cortical");
  return step.subjectIds.map((subjectId) =>
    emptyOptimizerRow({
      subjectId,
      method: flex ? "flex" : "ex",
      exPairs: step.kind === "mex" ? 4 : 2,
      net: flex ? null : netFromLeadfield(c.leadfield_hdf),
      roi,
      nonRoi,
      flex: flex ? flexFormFromConfig(c, step.kind) : undefined,
      ex: step.kind === "ex" ? exFormFromConfig(c) : undefined,
      mex: step.kind === "mex" ? mexFormFromConfig(c) : undefined,
      runName: String((flex ? c.output_folder : c.run_name) ?? ""),
    }),
  );
}

/** "Save to plan": the rows through `jobsForRow` as the step's config; throws when they cannot be one step. */
export function optStepEdit(step: PlanStepTarget, rows: OptimizerRow[], resolve: Parameters<typeof jobsForRow>[1]): StepEdit {
  const subjects = [...new Set(rows.map((r) => r.subjectId).filter(Boolean))];
  if (subjects.length === 0) throw new Error("Add a search job with a subject.");
  const content = (r: OptimizerRow) => JSON.stringify({ ...r, id: undefined, subjectId: undefined });
  if (rows.some((r) => content(r) !== content(rows[0]!)) || rows.length !== subjects.length) {
    throw new Error("A plan step runs one search on every subject: one row per subject, with the same settings.");
  }
  const row = rows.find((r) => r.subjectId === subjects[0])!;
  const reason = rowFormReason(row);
  if (reason) throw new Error(reason);
  const jobs = jobsForRow(row, resolve);
  if (jobs.length === 0) throw new Error("Complete the search: a target, and for Ex/mEx a computed leadfield.");
  if (jobs.length > 1) throw new Error("A plan step is one search: combine the selected ROIs, or keep one.");
  if (jobs[0]!.kind !== step.kind) {
    throw new Error(`This step is a ${kindLabel(step.kind)}; the form now describes a ${kindLabel(jobs[0]!.kind)}. Change it back, or ask the agent for a new plan.`);
  }
  const config: Config = { ...step.config, ...(jobs[0]!.config as Config) };
  delete config.subject_id;
  if (step.kind.startsWith("flex") && !config.output_folder) config.output_folder = step.config.output_folder;
  return { config, subject_ids: subjects };
}
