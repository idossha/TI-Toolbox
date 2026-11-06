/**
 * Pure config builders for the 3D Visual Exporter panel, split out of `index.tsx` so a defaults
 * test can validate every mode against `contracts/generated/config.schema.json` without rendering React — the same
 * split as `pages/panels/nilearn-visuals/config.ts`.
 *
 * Byte-identity rule (the reason this file is so literal): every field below is set to exactly
 * what the v2.5.0 `tit/gui/extensions/visual_exporter.py`'s `_run` passed to the same dataclass,
 * including the ones the Qt widget hardcoded and never showed (`keep_meshes: true`,
 * `vector_scale`/`vector_length` of 1.0). Change one and this panel stops producing the files the
 * Qt extension produced.
 */
import { samePairSet } from "../../_shared/roi/networkChoice";
import type { MontageConfig, RegionConfig, SubcorticalConfig, TractConfig, TractVisualConfig, VectorConfig } from "./api";

/**
 * What `readExportMontage` (previewModel.ts) says of a simulation placed by coordinates, and the
 * sentence `tit/blender/montage_publication.py` refuses its montage export with.
 */
export const NO_RECORDED_NET = "This simulation has no recorded EEG net.";

/** `VectorConfig` (tit/blender/config.py) refuses magnitude-scale thresholds that do not rise. */
export const PERCENTILE_ORDER = "Magnitude-scale percentiles must rise: blue ≤ green ≤ red.";

export const CHOOSE_A_FILE = "Load a file, or choose one already loaded.";
export const CHOOSE_A_NETWORK = "Choose a network.";
export const NAME_THE_NETWORK = "Name the network: letters, digits, _ and -.";
/** `all.trx` is the whole tractogram's file, which an assess of a network must not replace. */
export const NAME_IS_RESERVED = "A network cannot be called all: that is the whole tractogram's file.";

export type Mode = "regions" | "vectors" | "montage" | "subcortical" | "networks";

export interface RegionsForm {
  subjectId: string;
  simulationName: string;
  atlas: string;
  fieldName: string;
  /** `lh.insula`-style atlas keys. Empty means "whole GM only" — Qt's `skip_regions` rule. */
  regions: string[];
}

/**
 * Qt ran the region export **twice**, once per format, from one Run click (`_run`'s
 * `commands.append` pair) — so the panel submits two jobs, in the same order.
 */
export function buildRegionConfigs(form: RegionsForm): RegionConfig[] {
  const base = {
    subject_id: form.subjectId,
    simulation_name: form.simulationName,
    atlas: form.atlas,
    field_name: form.fieldName || "TI_max",
    skip_regions: form.regions.length === 0,
    regions: form.regions,
    keep_meshes: true,
    _type: "RegionConfig",
  } as const;
  return [
    { ...base, format: "stl" } as RegionConfig,
    { ...base, format: "ply" } as RegionConfig,
  ];
}

export interface VectorsForm {
  subjectId: string;
  simulationName: string;
  exportCh1Ch2: boolean;
  exportSum: boolean;
  exportTiNormal: boolean;
  count: number;
  allNodes: boolean;
  seed: number;
  lengthScale: number;
  vectorWidth: number;
  anchor: "tail" | "head";
  color: "rgb" | "magscale";
  bluePercentile: number;
  greenPercentile: number;
  redPercentile: number;
}

export function buildVectorConfig(form: VectorsForm): VectorConfig {
  return {
    subject_id: form.subjectId,
    simulation_name: form.simulationName,
    export_ch1_ch2: form.exportCh1Ch2,
    export_sum: form.exportSum,
    export_ti_normal: form.exportTiNormal,
    count: form.count,
    all_nodes: form.allNodes,
    seed: form.seed,
    length_scale: form.lengthScale,
    vector_scale: 1.0,
    vector_width: form.vectorWidth,
    vector_length: 1.0,
    anchor: form.anchor,
    color: form.color,
    blue_percentile: form.bluePercentile,
    green_percentile: form.greenPercentile,
    red_percentile: form.redPercentile,
    _type: "VectorConfig",
  } as VectorConfig;
}

export interface MontageForm {
  subjectId: string;
  simulationName: string;
  /** The Qt checkbox is "show only montage electrodes"; the config field is its negation. */
  montageOnly: boolean;
  electrodeDiameterMm: number;
  electrodeHeightMm: number;
}

export function buildMontageConfig(form: MontageForm): MontageConfig {
  return {
    subject_id: form.subjectId,
    simulation_name: form.simulationName,
    show_full_net: !form.montageOnly,
    electrode_diameter_mm: form.electrodeDiameterMm,
    electrode_height_mm: form.electrodeHeightMm,
    _type: "MontageConfig",
  } as MontageConfig;
}

export interface SubcorticalForm {
  subjectId: string;
  /** Optional — no simulation means geometry only, no field-coloured PLY. */
  simulationName: string;
  niftiPath: string;
  /** Label values to extract; empty means the whole volume. */
  labels: number[];
  cleanComponents: boolean;
  fieldName: string;
}

/**
 * `"10, 49"` → `[10, 49]`; `""` → `[]`. Throws the way Qt's `int(l.strip())` did, for a caller
 * that wants to say "Invalid label format" before submitting.
 *
 * Still here after the label browser landed, because the browser can fail to answer — a subject
 * with no segmentation volume, or a path typed by hand that the server will not read — and typing
 * the numbers is then the only way through, exactly as it was in 2.5.0.
 */
export function parseLabels(text: string): number[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed.split(",").map((part) => {
    const n = Number(part.trim());
    if (!Number.isInteger(n)) throw new Error(`Invalid label format: ${part.trim()}`);
    return n;
  });
}

export function buildSubcorticalConfig(form: SubcorticalForm): SubcorticalConfig {
  return {
    subject_id: form.subjectId,
    simulation_name: form.simulationName,
    nifti_path: form.niftiPath,
    labels: [...form.labels],
    clean_components: form.cleanComponents,
    field_name: form.fieldName || "TI_max",
    _type: "SubcorticalConfig",
  } as SubcorticalConfig;
}

/** `tit.tract`'s `Selection` of kind `edges`, the one definition a network has. */
export interface NetworkSelection {
  name: string;
  kind: "edges";
  regions: string[];
  pairs: [string, string][];
}

export interface NetworksForm {
  subjectId: string;
  simulationName: string;
  /** The network chosen by preset, region, connection or a top-N. */
  selection?: NetworkSelection | null;
  /** A file the user loaded for this head model (`tit/tract/own.py`); replaces `selection`. */
  ownNetwork?: string;
  /** The preset it came from, so the render can state what a same-side preset left out. */
  preset?: string;
  /** `tit.blender.network_setup.OVERRIDABLE` keys the user set; the rest are automatic. */
  overrides?: Record<string, unknown>;
  metric: "direction" | "ti_max";
  /** One figure of four fixed panels. */
  stills: boolean;
  turntable: boolean;
  exportBlend: boolean;
  quality: "preview" | "final";
}

/** The figure's size (each panel a quarter of it) and video length of each quality; `quality` itself sets samples and video size. */
const NETWORK_QUALITY = {
  // 96: a crossfade alone takes 48 frames (tract_scene.CROSSFADE_FRAMES).
  preview: { width: 1600, height: 1600, turntable_frames: 96 },
  final: { width: 4000, height: 4000, turntable_frames: 120 },
} as const;

/**
 * The tab draws PNG and MP4 renders only, so the web viewer and connectome figures stay off.
 */
export function buildNetworkConfig(form: NetworksForm): TractVisualConfig {
  const { width, height, turntable_frames } = NETWORK_QUALITY[form.quality];
  const base = {
    subject_id: form.subjectId,
    simulation_name: form.simulationName,
    quality: form.quality,
    web: false,
    connectome: false,
    _type: "TractVisualConfig",
  };
  const outputs = {
    metric: form.metric,
    stills: form.stills,
    turntable: form.turntable,
    export_blend: form.exportBlend,
    // The reference video: fibre directions first, then a scalar metric.
    turntable_crossfade: form.turntable && form.metric !== "direction",
    width,
    height,
    turntable_frames,
  };
  const overrides = form.overrides ?? {};
  if (form.ownNetwork) return { ...base, ...outputs, own_network: form.ownNetwork, overrides } as TractVisualConfig;
  return { ...base, ...outputs, selection: form.selection, preset: form.preset ?? "", overrides } as unknown as TractVisualConfig;
}

/** The tract job that samples this simulation's fields along a loaded file's streamlines. */
export function buildOwnAssessConfig(subjectId: string, simulationName: string, ownNetwork: string): TractConfig {
  return {
    _type: "TractConfig",
    subject_id: subjectId,
    stages: ["assess"],
    assess: { simulations: [simulationName], selections: [], own_network: ownNetwork },
  } as unknown as TractConfig;
}

/** The tract job that writes one network's bundle: fields along every streamline, one `.trx`. */
export function buildNetworkAssessConfig(subjectId: string, simulationName: string, selection: NetworkSelection): TractConfig {
  return {
    _type: "TractConfig",
    subject_id: subjectId,
    stages: ["assess"],
    assess: { simulations: [simulationName], selections: [selection] },
  } as unknown as TractConfig;
}

/** The assess stage with no bundle: `edges.json` and the rest, which a top-N list is read from. */
export function buildConnectionsAssessConfig(subjectId: string, simulationName: string): TractConfig {
  return {
    _type: "TractConfig",
    subject_id: subjectId,
    stages: ["assess"],
    assess: { simulations: [simulationName], selections: [] },
  } as unknown as TractConfig;
}

/**
 * Whether this simulation can draw the network yet: its own bundle holds exactly these edges, or
 * `all.trx` can be cut to them. A bundle of this name holding anything else would be replaced.
 */
export function assessState(selection: NetworkSelection, nStreamlines: number, outputs: { networks: string[]; assessed: { name: string; pairs: string[][]; n_streamlines: number }[] }): "ready" | "assess" | "replace" {
  const own = outputs.assessed.find((bundle) => bundle.name === selection.name);
  if (own && own.n_streamlines === nStreamlines && samePairSet(own.pairs, selection.pairs)) return "ready";
  if (outputs.networks.includes(selection.name)) return "replace";
  return outputs.networks.includes("all") ? "ready" : "assess";
}

/** The Plan as one line: what Run queues, what it draws, and what it replaces. */
export function networkPlanLine(plan: { jobs: number; memGb?: number; network?: string; streamlines?: number; blendMb?: number; replaced: readonly string[] }): string {
  const parts = [`${plan.jobs} job${plan.jobs === 1 ? "" : "s"}`];
  if (plan.memGb !== undefined) parts.push(`${plan.memGb} GB`);
  if (plan.network) parts.push(plan.network);
  if (plan.streamlines !== undefined) parts.push(`${plan.streamlines.toLocaleString("en-US")} streamlines`);
  if (plan.blendMb !== undefined) parts.push(`network.blend about ${plan.blendMb} MB`);
  parts.push(plan.replaced.length ? `will overwrite ${plan.replaced.length} file${plan.replaced.length === 1 ? "" : "s"}` : "replaces nothing");
  return parts.join(" · ");
}

/** The one-line "what this Run writes" the action bar and the toast both say. */
export function outputHint(mode: Mode, subjectId: string, simulationName: string, network = "all"): string {
  const sub = `sub-${subjectId}`;
  switch (mode) {
    case "regions":
      // One Run queues an STL and a PLY job (buildRegionConfigs); each writes under its format.
      return `visual_exports/${sub}/${simulationName}/{stl|ply}/cortical_{stls|plys}/regions`;
    case "vectors":
      return `visual_exports/${sub}/${simulationName}/vectors`;
    case "montage":
      return `visual_exports/${sub}/montage_publication`;
    case "subcortical":
      return `visual_exports/${sub}/sub-cortical`;
    case "networks":
      return `visual_exports/${sub}/${simulationName}/networks/${network}`;
  }
}
