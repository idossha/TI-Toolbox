import { emptyRoi, type AtlasLookup, type RoiValue } from "../_shared/roi";
import { buildExConfig, buildMExConfig, defaultExFormState, defaultMExFormState, exTargets, type ExFormState, type MExFormState } from "../optimizer/exConfig";

export interface ExNodeEditor {
  kind: "ex" | "mex";
  ex: ExFormState;
  mex: MExFormState;
  roi: RoiValue;
  leadfieldHdf: string;
  net: string;
  runName: string;
}
export function defaultExNodeEditor(kind: "ex" | "mex"): ExNodeEditor {
  return { kind, ex: defaultExFormState(), mex: defaultMExFormState(), roi: emptyRoi("saved"), leadfieldHdf: "", net: "", runName: "" };
}
function object(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.map(String) : []; }
export function editorFromExNode(node: { kind: "ex" | "mex"; config?: Record<string, unknown> }): ExNodeEditor {
  const editor = defaultExNodeEditor(node.kind), config = node.config ?? {}, electrodes = object(config.electrodes);
  for (const key of Object.keys(editor.mex.buckets)) {
    editor.mex.buckets[key] = strings(electrodes[key]);
    if (key in editor.ex.buckets) editor.ex.buckets[key] = strings(electrodes[key]);
  }
  editor.ex.electrodeMode = electrodes._type === "PoolElectrodes" ? "all" : "bucketed";
  editor.ex.pool = strings(electrodes.electrodes);
  if (typeof config.total_current === "number") editor.ex.totalCurrent = config.total_current;
  if (typeof config.current_step === "number") editor.ex.currentStep = config.current_step;
  if (typeof config.channel_limit === "number" || config.channel_limit === null) editor.ex.channelLimit = config.channel_limit;
  if (typeof config.current_mA === "number") editor.mex.currentMa = config.current_mA;
  editor.mex.symmetricBucket = config.symmetric_bucket === true;
  editor.mex.symmetryPairing = config.symmetry_pairing === "cross_pairs" ? "cross_pairs" : "within_pairs";
  editor.leadfieldHdf = String(config.leadfield_hdf ?? ""); editor.runName = String(config.run_name ?? "");
  const space = config.roi_coordinate_space === "mni" ? "mni" : "subject";
  const entries = Array.isArray(config.roi_atlas) ? config.roi_atlas.map(object) : [];
  const first = entries[0];
  if (first?.label === null && typeof first.atlas_path === "string") {
    editor.roi = { mode: "mask", path: first.atlas_path, space: first.atlas_space === "mni" ? "mni" : "subject", tissues: "GM" };
  } else if (first) {
    editor.roi = { mode: "subcortical", atlas: String(first.atlas_path ?? ""), atlasSpace: space, tissues: "GM", regions: entries.map((entry) => ({ id: Number(entry.label), name: String(entry.label) })) };
  } else {
    const names = strings(config.roi_names);
    editor.roi = { mode: "saved", selected: names.length ? names : config.roi_name ? [String(config.roi_name)] : [], combine: names.length > 1, radius: typeof config.roi_radius === "number" ? config.roi_radius : 3, space };
  }
  return editor;
}
export function exNodeError(editor: ExNodeEditor): string | null {
  if (editor.roi.mode === "saved" && editor.roi.selected.length > 1 && (editor.kind === "mex" || !editor.roi.combine)) return "Use one node per target, or combine the saved ROIs for Ex-search.";
  return null;
}
export function buildExNodeConfig(editor: ExNodeEditor, atlasLookup: (atlas: string) => AtlasLookup | undefined, cohort: string[] = []): Record<string, unknown> {
  const lookup = (atlas: string) => atlasLookup(atlas) ?? (atlas.startsWith("/") ? { path: atlas } : undefined);
  const target = exTargets(editor.roi, lookup, editor.kind === "ex")[0] ?? { roiName: "", roiNames: [], roiAtlas: null, radius: 3, space: "subject" as const };
  return (editor.kind === "ex" ? buildExConfig(cohort[0] ?? "", editor.leadfieldHdf, editor.ex, target, editor.runName) : buildMExConfig(cohort[0] ?? "", editor.leadfieldHdf, editor.mex, target, editor.runName)) as unknown as Record<string, unknown>;
}
