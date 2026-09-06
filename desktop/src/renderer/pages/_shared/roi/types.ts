/**
 * Value model for `<RoiPicker>` — mirrors `FlexConfig`'s ROI union
 * (`SphericalROI | AtlasROI | SubcorticalROI`, `contracts/schema.json`) but keeps every field
 * editable independently (undefined coordinates while a row is half-typed, empty region lists)
 * rather than forcing a config-shaped value on every keystroke. Build the wire-shaped object with
 * `roiToConfig()` only at submit/plan time.
 *
 * Multiple spheres, or multiple selected regions, are a **union** into one combined target — the
 * same broadcast-to-list semantics `SphericalROI`/`AtlasROI`/`SubcorticalROI` already have
 * server-side (scalar fields become arrays). There is no separate "combine" toggle: selecting more
 * than one row/chip *is* combining, matching flex-search's ROI classes (unlike ex-search's opt-in
 * Combine checkbox for a different config shape).
 */

/**
 * `saved` is the ex/mEx target mechanism (B3 optimizer merge): a named ROI CSV already stored for
 * the subject, picked by name, with a radius and a coordinate space. It is a *fourth* mode of the
 * one picker rather than a second picker, because U7's merged Optimizer must not carry two ROI
 * widgets that disagree about what an ROI is.
 */
export type RoiMode = "spherical" | "cortical" | "subcortical" | "saved";
export type RoiSpace = "subject" | "mni";
export type TissueKind = "GM" | "WM" | "both";

/**
 * One row of a cortical or subcortical region selection. `hemi` is only meaningful for cortical.
 * `id` is the FreeSurfer `.annot` label index (cortical) or the volumetric atlas's voxel label
 * value (subcortical) — `Region.id: integer` per the reconciled `contracts/openapi.v1.yaml`
 * (`AtlasROI.label`/`SubcorticalROI.label` need exactly this integer, not a display string).
 */
export interface RoiRegion {
  id: number;
  name: string;
  hemi?: "lh" | "rh";
}

export interface SphereRow {
  x: number | undefined;
  y: number | undefined;
  z: number | undefined;
  radius: number | undefined;
}

export function emptySphereRow(): SphereRow {
  return { x: undefined, y: undefined, z: undefined, radius: 10 };
}

export interface SphericalRoiValue {
  mode: "spherical";
  spheres: SphereRow[];
  space: RoiSpace;
  volumetric: boolean;
  tissues: TissueKind;
}

export interface CorticalRoiValue {
  mode: "cortical";
  /** Atlas id from `GET /api/catalog/atlases?kind=cortical` (e.g. "DK40"). */
  atlas: string | undefined;
  regions: RoiRegion[];
}

export interface SubcorticalRoiValue {
  mode: "subcortical";
  atlasSpace: RoiSpace;
  /** Atlas id from `GET /api/catalog/atlases?kind=subcortical`. */
  atlas: string | undefined;
  regions: RoiRegion[];
  tissues: TissueKind;
}

/**
 * Ex/mEx target: one or more saved ROI CSV names. `combine` unions the selected names into a
 * single run (`ExConfig.roi_names`); unchecked, each selected name is its own run. `radius` is
 * `ExConfig.roi_radius`; `space` is `roi_coordinate_space`.
 */
export interface SavedRoiValue {
  mode: "saved";
  selected: string[];
  combine: boolean;
  radius: number;
  space: RoiSpace;
}

export type RoiValue = SphericalRoiValue | CorticalRoiValue | SubcorticalRoiValue | SavedRoiValue;

export function emptyRoi(mode: RoiMode, space: RoiSpace = "subject"): RoiValue {
  switch (mode) {
    case "spherical":
      return { mode, spheres: [emptySphereRow()], space, volumetric: false, tissues: "GM" };
    case "cortical":
      return { mode, atlas: undefined, regions: [] };
    case "subcortical":
      return { mode, atlasSpace: space, atlas: undefined, regions: [], tissues: "GM" };
    case "saved":
      return { mode, selected: [], combine: false, radius: 3.0, space };
  }
}

/** True once the value has enough to build a valid ROI config (see `roiToConfig`). */
export function isRoiComplete(value: RoiValue): boolean {
  if (value.mode === "saved") return value.selected.length > 0;
  if (value.mode === "spherical") {
    return (
      value.spheres.length > 0 &&
      value.spheres.every((s) => s.x !== undefined && s.y !== undefined && s.z !== undefined && s.radius !== undefined)
    );
  }
  return value.atlas !== undefined && value.regions.length > 0;
}

/** Wire shape for `FlexConfig.roi` / `.non_roi` — the `_type`-discriminated union in schema.json. */
export type RoiConfig =
  | { _type: "SphericalROI"; x: number[]; y: number[]; z: number[]; radius: number[]; use_mni: boolean; volumetric: boolean; tissues: TissueKind }
  | { _type: "AtlasROI"; atlas_path: string[]; label: number[]; hemisphere: string[] }
  | { _type: "SubcorticalROI"; atlas_path: string[]; label: number[]; tissues: TissueKind; atlas_space: RoiSpace };

/**
 * A cortical/subcortical atlas as returned by the catalog, resolving a region id to the file
 * path(s) `AtlasROI`/`SubcorticalROI` need. Cortical atlases are per-hemisphere `.annot` files —
 * the catalog only advertises the "lh" path (see `RoiPicker.tsx` header comment), so
 * `atlasPathForHemi` derives "rh" from it by convention.
 */
export interface AtlasLookup {
  path: string;
}

export function atlasPathForHemi(atlas: AtlasLookup, hemi: "lh" | "rh"): string {
  return atlas.path.replace(/(^|\/)lh\./, `$1${hemi}.`);
}

/** Build the wire-shaped ROI config, or `undefined` while the value is incomplete. */
export function roiToConfig(value: RoiValue, atlasLookup: (atlas: string) => AtlasLookup | undefined): RoiConfig | undefined {
  if (!isRoiComplete(value)) return undefined;
  // `saved` is not a FlexConfig ROI shape — ex/mEx read it through `exTargets()` instead.
  if (value.mode === "saved") return undefined;
  if (value.mode === "spherical") {
    return {
      _type: "SphericalROI",
      x: value.spheres.map((s) => s.x!),
      y: value.spheres.map((s) => s.y!),
      z: value.spheres.map((s) => s.z!),
      radius: value.spheres.map((s) => s.radius!),
      use_mni: value.space === "mni",
      volumetric: value.volumetric,
      tissues: value.tissues,
    };
  }
  if (value.mode === "cortical") {
    const atlas = value.atlas ? atlasLookup(value.atlas) : undefined;
    if (!atlas) return undefined;
    return {
      _type: "AtlasROI",
      atlas_path: value.regions.map((r) => atlasPathForHemi(atlas, r.hemi ?? "lh")),
      label: value.regions.map((r) => r.id),
      hemisphere: value.regions.map((r) => r.hemi ?? "lh"),
    };
  }
  const atlas = value.atlas ? atlasLookup(value.atlas) : undefined;
  if (!atlas) return undefined;
  return {
    _type: "SubcorticalROI",
    atlas_path: value.regions.map(() => atlas.path),
    label: value.regions.map((r) => r.id),
    tissues: value.tissues,
    atlas_space: value.atlasSpace,
  };
}
