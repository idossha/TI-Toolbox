/**
 * Pure config builders for the 3D Visual Exporter panel, split out of `index.tsx` so a defaults
 * test can validate every mode against `contracts/schema.json` without rendering React — the same
 * split as `pages/panels/nilearn-visuals/config.ts`.
 *
 * Byte-identity rule (the reason this file is so literal): every field below is set to exactly
 * what `tit/gui/extensions/visual_exporter.py`'s `_run` passed to the same dataclass in 2.5.0,
 * including the ones the Qt widget hardcoded and never showed (`keep_meshes: true`,
 * `vector_scale`/`vector_length` of 1.0). Change one and this panel stops producing the files the
 * Qt extension produced.
 */
import type { MontageConfig, RegionConfig, SubcorticalConfig, VectorConfig } from "./api";

export type Mode = "regions" | "vectors" | "montage" | "subcortical";

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

/** The one-line "what this Run writes" the action bar and the toast both say. */
export function outputHint(mode: Mode, subjectId: string, simulationName: string): string {
  const sub = `sub-${subjectId}`;
  switch (mode) {
    case "regions":
      return `visual_exports/${sub}/${simulationName}/cortical_stls`;
    case "vectors":
      return `visual_exports/${sub}/${simulationName}`;
    case "montage":
      return `visual_exports/${sub}/montage_publication`;
    case "subcortical":
      return `visual_exports/${sub}/sub-cortical`;
  }
}
