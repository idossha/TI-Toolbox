/**
 * Pure `AnalyzerConfig` construction, split out of `AnalyzerPage.tsx` (mirrors
 * `simulator/buildConfig.ts`) so it is unit-testable against `contracts/generated/config.schema.json` without
 * mounting the page component.
 */
import type { RoiValue } from "../_shared/roi";
import type { Sphere } from "./SphereRows";
import type { AnalyzerConfig } from "./api";

export type Mode = "single" | "group";
export type Space = "mesh" | "voxel";
export type AnalysisType = "spherical" | "cortical" | "subcortical" | "mask";

/** Sentinel for the Field select's "Auto" option — Radix Select reserves `value=""` to mean "show
 *  the placeholder, nothing selected", so the wire meaning (`field: null`) needs a real string. */
export const AUTO_FIELD = "__auto__";

/** Extracts AnalyzerConfig's plain `atlas`/`region` fields from a cortical/subcortical RoiValue. */
export function roiToAnalyzerFields(value: RoiValue): {
  atlas: string | null;
  region: string | string[] | null;
} {
  // `spherical` has no atlas/region, and `saved` (the ex/mEx mode B3 added to the shared
  // picker) is not an analyzer target at all — both resolve to "no atlas, no region".
  if (value.mode !== "cortical" && value.mode !== "subcortical") return { atlas: null, region: null };
  const names = value.regions.map((r) => r.name);
  return {
    atlas: value.atlas ?? null,
    region: names.length <= 1 ? (names[0] ?? null) : names,
  };
}

export function buildConfig(opts: {
  mode: Mode;
  subjectId: string | null;
  subjectIds: string[];
  simulation: string;
  space: Space;
  tissueType: string;
  field: string;
  analysisType: AnalysisType;
  coordinateSpace: "subject" | "mni";
  sphere: Sphere;
  roiValue: RoiValue;
}): AnalyzerConfig {
  const {
    mode,
    subjectId,
    subjectIds,
    simulation,
    space,
    tissueType,
    field,
    analysisType,
    coordinateSpace,
    sphere,
    roiValue,
  } = opts;
  const { atlas, region } = roiToAnalyzerFields(roiValue);
  return {
    mode,
    subject_id: mode === "single" ? subjectId : null,
    subject_ids: mode === "group" ? subjectIds : [],
    simulation,
    space,
    tissue_type: space === "voxel" ? tissueType : "GM",
    analysis_type: analysisType,
    field: field === AUTO_FIELD ? null : field,
    center:
      analysisType === "spherical"
        ? [sphere.x ?? 0, sphere.y ?? 0, sphere.z ?? 0]
        : null,
    radius: analysisType === "spherical" ? (sphere.radius ?? 0) : null,
    coordinate_space: roiValue.mode === "mask" ? roiValue.space : coordinateSpace,
    mask_path: roiValue.mode === "mask" ? roiValue.path.trim() : null,
    atlas,
    region,
    output_dir: null,
    visualize: true,
  };
}

export function sphereComplete(s: Sphere): boolean {
  return (
    s.x !== undefined &&
    s.y !== undefined &&
    s.z !== undefined &&
    s.radius !== undefined &&
    s.radius > 0
  );
}

export function rowTargets(row: {roi: RoiValue; combine: boolean}): RoiValue[] {
  const roi = row.roi;
  if (roi.mode === "spherical") return roi.spheres.map((s) => ({ ...roi, spheres: [s] }));
  if (roi.mode === "cortical" || roi.mode === "subcortical") {
    if (row.combine || roi.regions.length <= 1) return [roi];
    return roi.regions.map((r) => ({ ...roi, regions: [r] }));
  }
  return [roi];
}
