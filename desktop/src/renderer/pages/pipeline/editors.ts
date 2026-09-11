import { defaultExNodeEditor, editorFromExNode, buildExNodeConfig, exNodeError, type ExNodeEditor } from "./exNodeEditor";
/** Node configs stay authoritative; shared page builders apply only explicitly edited fields. */
import { defaultConfig as defaultPreConfig } from "../preprocess/config";
import type { PreprocessConfig } from "../preprocess/api";
import { defaultFlexFormState, buildFlexConfig, type FlexFormState } from "../optimizer/flexConfig";
import { buildSimulationConfig, type GlobalParams } from "../simulator/buildConfig";
import { buildConfig as buildAnalyzerConfig, rowTargets, type AnalysisType, type Space } from "../analyzer/buildConfig";
import { emptyRoi, roiToConfig, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { EMPTY_SPHERE, type Sphere } from "../analyzer/SphereRows";
import type { SelectedRow } from "../simulator/types";
import type { NodeKind } from "./graph";

/** Every stage flag a `pre` node can turn on, in the order the page shows them. */
export const PRE_STAGES: { key: string; label: string }[] = [
  { key: "convert_dicom", label: "Convert DICOM" },
  { key: "run_fastsurfer", label: "FastSurfer segmentation" },
  { key: "run_freesurfer", label: "FreeSurfer" },
  { key: "create_m2m", label: "SimNIBS head model (charm)" },
  { key: "run_tissue_analysis", label: "Tissue analysis" },
  { key: "run_qsiprep", label: "QSIPrep" },
  { key: "run_qsirecon", label: "QSIRecon" },
  { key: "extract_dti", label: "Extract DTI tensors" },
];

/** The cohort. The one node that *owns* a subject list; every other node is handed one. */
export interface SubjectsEditor {
  kind: "subjects";
  subjects: string[];
}

export interface PreEditor {
  kind: "pre";
  stages: Record<string, boolean>;
  settings?: PreprocessConfig;
}

export interface FlexEditor {
  kind: "flex";
  form: FlexFormState;
  roi: RoiValue;
  nonRoi?: RoiValue;
}

export interface SimEditor {
  kind: "sim";
  montages: string;
  definitions?: Record<string, unknown>[];
  eegNet: string;
  currents: string;
  params: GlobalParams;
}

export interface AnalyzerEditor {
  kind: "analyzer";
  mode?: "single" | "group";
  simulation: string;
  space: Space;
  analysisType: AnalysisType;
  combine?: boolean;
  field: string;
  tissueType: string;
  coordinateSpace: "subject" | "mni";
  sphere: Sphere;
  roi: RoiValue;
}

/**
 * Kinds whose page form does not lift out of its page (the ex/mEx builders take a resolved
 * leadfield path, a target and a run name that only that page computes; `leadfield`, `source` and
 * `stats` have no v3 form at all). Their config is edited as JSON here, labelled as such rather
 * than faked with a half-form that would build a config their runner rejects.
 */
export interface JsonEditor {
  kind: "json";
  nodeKind: NodeKind;
  text: string;
}

export type NodeEditor = SubjectsEditor | PreEditor | FlexEditor | SimEditor | AnalyzerEditor | JsonEditor | ExNodeEditor;

const SIM_PARAMS: GlobalParams = {
  conductivity: "scalar",
  electrodeShape: "ellipse",
  dimensions: [8, 8],
  gelThickness: 4,
  outputFields: ["TI_max"],
  customConductivities: {},
};

export function defaultEditor(kind: NodeKind): NodeEditor {
  switch (kind) {
    case "ex":
    case "mex": return defaultExNodeEditor(kind);
    case "subjects":
      return { kind: "subjects", subjects: [] };
    case "pre":
      return { kind: "pre", stages: Object.fromEntries(PRE_STAGES.map(({key}) => [key, defaultPreConfig()[key as keyof PreprocessConfig] === true])), settings: defaultPreConfig() };
    case "flex":
      return { kind: "flex", form: defaultFlexFormState(), roi: emptyRoi("subcortical") };
    case "sim":
      return { kind: "sim", montages: "", eegNet: "", currents: "1.0, 1.0", params: { ...SIM_PARAMS } };
    case "analyzer":
      return {
        kind: "analyzer",
        simulation: "",
        space: "mesh",
        analysisType: "spherical",
        field: "__auto__",
        tissueType: "GM",
        coordinateSpace: "subject",
        sphere: { ...EMPTY_SPHERE },
        roi: emptyRoi("spherical"),
      };
    default:
      return { kind: "json", nodeKind: kind, text: "{}" };
  }
}

/** Restore visible fields; raw config remains authoritative for everything not edited. */
export function editorFromNode(node: { kind: NodeKind; config?: Record<string, unknown> }): NodeEditor {
  if (node.kind === "ex" || node.kind === "mex") return editorFromExNode({kind:node.kind,config:node.config});
  const config = node.config ?? {};
  const base = defaultEditor(node.kind);
  switch (base.kind) {
    case "subjects": return { ...base, subjects: Array.isArray(config.subject_ids) ? config.subject_ids.map(String) : [] };
    case "pre": return { ...base, settings: { ...defaultPreConfig(), ...config } as PreprocessConfig, stages: Object.fromEntries(PRE_STAGES.map(({ key }) => [key, config[key] === true])) };
    case "flex": {
      const form = { ...base.form };
      const fields: Partial<Record<keyof FlexFormState, string>> = {
        goal: "goal", postproc: "postproc", anisotropyType: "anisotropy_type", anisoMaxratio: "aniso_maxratio", anisoMaxcond: "aniso_maxcond", currentMA: "current_mA", minElectrodeDistance: "min_electrode_distance",
        optimizeCurrentRatio: "optimize_current_ratio", ratioLevels: "ratio_levels", ratioTotalMA: "ratio_total_mA", nonRoiMethod: "non_roi_method", intensityWeight: "intensity_weight", manualThresholds: "thresholds", nMultistart: "n_multistart", maxIterations: "max_iterations", populationSize: "population_size", tolerance: "tolerance", recombination: "recombination", skinRegionMarginMm: "skin_region_margin_mm", avoidLandmarkRegions: "avoid_landmark_regions", runFinalElectrodeSimulation: "run_final_electrode_simulation", enableMapping: "enable_mapping", eegNet: "eeg_net", skinVisualizationNet: "skin_visualization_net",
      };
      for (const [field, key] of Object.entries(fields)) if (config[key] !== undefined && config[key] !== null) Object.assign(form, { [field]: config[key] });
      form.visualizeSkinElectrodes = typeof config.skin_visualization_net === "string" && !!config.skin_visualization_net;
      const electrode = object(config.electrode);
      if (typeof electrode.shape === "string") form.electrodeShape = electrode.shape as FlexFormState["electrodeShape"];
      if (Array.isArray(electrode.dimensions)) [form.dimensionWidth, form.dimensionHeight] = electrode.dimensions as [number, number];
      if (typeof electrode.gel_thickness === "number") form.gelThickness = electrode.gel_thickness;
      if (typeof config.mutation === "string") [form.mutationMin, form.mutationMax] = config.mutation.split(",").map(Number) as [number, number];
      form.focalityMode = config.pareto ? "pareto" : config.adaptive ? "adaptive" : "manual";
      const adaptive = object(config.adaptive), pareto = object(config.pareto);
      if (typeof adaptive.non_roi_pct === "number") form.adaptiveNonRoiPct = adaptive.non_roi_pct;
      if (typeof adaptive.roi_pct === "number") form.adaptiveRoiPct = adaptive.roi_pct;
      if (Array.isArray(pareto.roi_pcts)) form.paretoRoiPcts = pareto.roi_pcts.join(",");
      if (Array.isArray(pareto.nonroi_pcts)) form.paretoNonRoiPcts = pareto.nonroi_pcts.join(",");
      return { ...base, form, roi: restoreRoi(config.roi) ?? base.roi, nonRoi: restoreRoi(config.non_roi) };
    }
    case "sim": {
      const montages = Array.isArray(config.montages) ? config.montages.map(object) : [];
      const params = { ...base.params };
      const map = { conductivity: "conductivity", electrodeShape: "electrode_shape", dimensions: "electrode_dimensions", gelThickness: "gel_thickness", outputFields: "output_fields", anisoMaxratio: "aniso_maxratio", anisoMaxcond: "aniso_maxcond", mapToFsavg: "map_to_fsavg", customConductivities: "tissue_conductivities" };
      for (const [field, key] of Object.entries(map)) if (config[key] !== undefined && config[key] !== null) Object.assign(params, { [field]: config[key] });
      const nets = [...new Set(montages.map((m) => m.eeg_net).filter((n): n is string => typeof n === "string"))];
      return { ...base, definitions: montages, montages: montages.map((m) => String(m.name ?? "")).join(", "), eegNet: nets.length === 1 ? nets[0]! : "", currents: Array.isArray(config.intensities) ? config.intensities.join(", ") : base.currents, params };
    }
    case "analyzer": {
      const analysisType = ["spherical", "cortical", "subcortical", "mask", "nifti_mask"].includes(String(config.analysis_type)) ? (config.analysis_type === "nifti_mask" ? "mask" : config.analysis_type) as AnalysisType : base.analysisType;
      const center = Array.isArray(config.center) ? config.center : [];
      const roi = analysisType === "mask" ? { mode: "mask" as const, path: String(config.mask_path ?? ""), space: config.coordinate_space === "mni" ? "mni" as const : "subject" as const, tissues: "GM" as const }
        : analysisType === "cortical" || analysisType === "subcortical" ? { ...emptyRoi(analysisType), atlas: typeof config.atlas === "string" ? config.atlas : undefined, regions: (Array.isArray(config.region) ? config.region : config.region ? [config.region] : []).map((name, index) => ({ id: -index - 1, name: String(name) })) } as RoiValue : {mode:"spherical",spheres:[{x:center[0],y:center[1],z:center[2],radius:config.radius}],space:config.coordinate_space === "mni" ? "mni" : "subject",volumetric:false,tissues:"GM"} as RoiValue;
      return { ...base, mode: config.mode === "group" ? "group" : "single", simulation: String(config.simulation ?? ""), space: config.space === "voxel" ? "voxel" : "mesh", analysisType, field: typeof config.field === "string" ? config.field : "__auto__", tissueType: String(config.tissue_type ?? "GM"), coordinateSpace: config.coordinate_space === "mni" ? "mni" : "subject", sphere: { x: center[0] as number | undefined, y: center[1] as number | undefined, z: center[2] as number | undefined, radius: typeof config.radius === "number" ? config.radius : undefined }, roi };
    }
    case "ex":
    case "mex": return editorFromExNode({kind:base.kind,config});
    case "json": return { ...base, text: JSON.stringify(config, null, 2) };
  }
}

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function restoreRoi(value: unknown): RoiValue | undefined {
  const roi = object(value);
  const list = (v: unknown): unknown[] => Array.isArray(v) ? v : v === undefined ? [] : [v];
  const tissues = roi.tissues === "WM" || roi.tissues === "both" ? roi.tissues : "GM";
  if (roi._type === "SphericalROI" || roi.x !== undefined) {
    const ys = list(roi.y), zs = list(roi.z), radii = list(roi.radius);
    return { mode: "spherical", spheres: list(roi.x).map((x, i) => ({ x: Number(x), y: Number(ys[i] ?? ys[0]), z: Number(zs[i] ?? zs[0]), radius: Number(radii[i] ?? radii[0]) })), space: roi.use_mni ? "mni" : "subject", volumetric: roi.volumetric === true, tissues };
  }
  if (roi._type === "SubcorticalROI" && roi.label === null && typeof roi.atlas_path === "string") return { mode: "mask", path: roi.atlas_path, space: roi.atlas_space === "mni" ? "mni" : "subject", tissues };
  if (roi._type === "AtlasROI" || roi._type === "SubcorticalROI") {
    const atlas = String(list(roi.atlas_path)[0] ?? "");
    const hemis = list(roi.hemisphere);
    const regions = list(roi.label).map((id, i) => ({ id: Number(id), name: String(id), ...(roi._type === "AtlasROI" ? { hemi: (hemis[i] ?? hemis[0] ?? "lh") as "lh" | "rh" } : {}) }));
    return roi._type === "AtlasROI" ? { mode: "cortical", atlas, regions } : { mode: "subcortical", atlas, regions, atlasSpace: roi.atlas_space === "mni" ? "mni" : "subject", tissues };
  }
  return undefined;
}

export function parseSubjects(text: string): string[] {
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function simRow(subjectId: string, name: string, editor: SimEditor): SelectedRow {
  return {
    id: `${subjectId}:${name}`,
    subjectId,
    source: "montage",
    name,
    pairs: [],
    eegNet: editor.eegNet || undefined,
    currents: editor.currents,
  };
}

/**
 * The node's config, built by the same function its page uses.
 *
 * **A node's config is its own.** Nothing here is copied from the node upstream of it: an edge
 * carries one named port and nothing else. The cohort is the exception that proves it — it is not
 * copied into the config at all, it stays on the `subjects` node and reaches this one over the
 * wire, so a document has exactly one place that says who takes part.
 */
function buildEditorConfig(
  editor: NodeEditor,
  atlasLookup: (atlas: string) => AtlasLookup | undefined,
  previous?: Record<string, unknown>,
  /**
   * The subjects that reach this node over the graph's `subjects` wire. Only a *representative*
   * is used, and only where a page's builder insists on one: the server fans a node out to one
   * job per subject and forces each generated config's `subject_id` to its own subject
   * (`tit.pipeline.plan`), so the id embedded here never decides which anatomy a job reads.
   */
  cohort: string[] = [],
): Record<string, unknown> {
  const representative = cohort[0] ?? "";

  switch (editor.kind) {
    case "ex":
    case "mex": return buildExNodeConfig(editor,atlasLookup,cohort);
    case "subjects":
      // The one node that owns a subject list. Nothing else about it is configurable.
      return { subject_ids: [...editor.subjects] };
    case "pre": {
      const flags: Record<string, unknown> = { ...editor.settings };
      delete flags.subject_ids;
      for (const stage of PRE_STAGES) flags[stage.key] = editor.stages[stage.key] === true;
      return flags;
    }
    case "flex": {
      const roi = roiToConfig(editor.roi, atlasLookup);
      const config = buildFlexConfig(representative, editor.form, roi ?? ({} as never), editor.nonRoi ? roiToConfig(editor.nonRoi, atlasLookup) ?? undefined : undefined) as unknown as Record<string, unknown>;
      return config;
    }
    case "sim": {
      const names = editor.montages.split(",").map((s) => s.trim()).filter(Boolean);
      // One `SimulationConfig` carrying every montage the node runs: the server's plan fans this
      // out per subject, and each montage becomes one simulation name a downstream Analyzer binds.
      const montages = names.map((name) => {
        const row = simRow(representative, name, editor);
        return editor.definitions?.find((m) => m.name === name) ?? (buildSimulationConfig(row, editor.params).montages as unknown[])[0];
      });
      const base = buildSimulationConfig(simRow(representative, names[0] ?? "", editor), editor.params);
      return { ...base, montages };
    }
    case "analyzer": {
      const config = buildAnalyzerConfig({
        mode: editor.mode ?? "single",
        subjectId: editor.mode === "group" ? null : representative,
        subjectIds: cohort,
        simulation: editor.simulation,
        space: editor.space,
        tissueType: editor.tissueType,
        field: editor.field,
        analysisType: editor.analysisType,
        coordinateSpace: editor.coordinateSpace,
        sphere: editor.sphere,
        roiValue: editor.roi,
      }) as unknown as Record<string, unknown>;
      // The cohort is the graph's, not this node's: `subject_ids` is deliberately not written
      // back into the config, so the document has exactly one place that says who takes part.
      delete config.subject_ids;
      return config;
    }
    case "json": {
      // `previous` is the config the node already carries. Mid-edit the textarea is *always*
      // briefly unparseable, and returning `{}` for it — which this used to do — wiped the node's
      // real config on the first mistyped brace and never said so. Keeping the last config that
      // parsed means a half-typed edit costs nothing, and the inspector shows the parse error
      // while it lasts.
      try {
        const parsed: unknown = JSON.parse(editor.text);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
      } catch {
        /* fall through to the last good config */
      }
      return previous ?? {};
    }
  }
}


/** Apply changes generated by the shared page builder, retaining every untouched saved field. */
export function configFor(editor: NodeEditor, atlasLookup: (atlas: string) => AtlasLookup | undefined, previous?: Record<string, unknown>, cohort: string[] = [], previousEditor?: NodeEditor): Record<string, unknown> {
  if (!previous || editor.kind === "json") return buildEditorConfig(editor, atlasLookup, previous, cohort);
  const before = previousEditor ?? editorFromNode({ kind: editor.kind, config: previous });
  const lookup = (atlas: string) => atlasLookup(atlas) ?? (atlas.startsWith("/") ? { path: atlas } : undefined);
  const oldBuilt = buildEditorConfig(before, lookup, previous, cohort);
  const newBuilt = buildEditorConfig(editor, lookup, previous, cohort);
  const merged = applyChangedFields(previous, oldBuilt, newBuilt);
  if (editor.kind === "sim" && before.kind === "sim" && (editor.montages !== before.montages || editor.eegNet !== before.eegNet || editor.definitions !== before.definitions)) {
    const saved = Array.isArray(previous.montages) ? previous.montages.map(object) : [];
    merged.montages = (newBuilt.montages as Record<string, unknown>[]).map((m) => {
      const original = saved.find((entry) => entry.name === m.name);
      return original && editor.definitions === before.definitions ? original : m;
    });
  }
  return merged;
}

function applyChangedFields(saved: Record<string, unknown>, before: Record<string, unknown>, after: Record<string, unknown>): Record<string, unknown> {
  const result = { ...saved };
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (JSON.stringify(before[key]) === JSON.stringify(after[key])) continue;
    if (!(key in after)) { delete result[key]; continue; }
    const oldObject = object(before[key]), newObject = object(after[key]);
    result[key] = Object.keys(oldObject).length && Object.keys(newObject).length && oldObject._type === newObject._type && object(saved[key])._type === oldObject._type
      ? applyChangedFields(object(saved[key]), oldObject, newObject) : after[key];
  }
  return result;
}

/** Invalid drafts must not masquerade as the last valid document. */
export function editorError(editor: NodeEditor): string | null {
  if (editor.kind === "ex" || editor.kind === "mex") return exNodeError(editor);
  if (editor.kind !== "json") return null;
  try { const value: unknown = JSON.parse(editor.text); return value && typeof value === "object" && !Array.isArray(value) ? null : "Config must be a JSON object."; }
  catch { return "Config contains invalid JSON. Reopen the step to correct it."; }
}

/** Expand targets with the Analyzer page's own one-job-per-target rules. */
export function analyzerNodeTargets(editor: AnalyzerEditor): AnalyzerEditor[] {
  return rowTargets({roi:editor.roi,combine:editor.combine ?? true}).map((roi)=>analyzerEditorTarget(editor,roi,true));
}
export function analyzerEditorTarget(editor: AnalyzerEditor, roi: RoiValue, combine = editor.combine ?? true): AnalyzerEditor {
  return {...editor,roi,combine,analysisType:roi.mode as AnalysisType, sphere:roi.mode === "spherical" ? roi.spheres[0] ?? {...EMPTY_SPHERE} : editor.sphere,coordinateSpace:roi.mode === "spherical" || roi.mode === "mask" ? roi.space : roi.mode === "subcortical" ? roi.atlasSpace : "subject"};
}
