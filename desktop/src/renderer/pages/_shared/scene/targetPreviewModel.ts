import type { RoiValue } from "../roi";

export type TargetPreviewRoi =
  | { kind: "saved"; names: string[]; radius: number; space: "subject" | "mni" }
  | { kind: "mask"; path: string; space: "subject" | "mni" }
  | { kind: "subcortical"; atlas: string; labels: number[]; space: "subject" | "mni" }
  | { kind: "spherical"; spheres: { center: [number, number, number]; radius: number }[]; space: "subject" | "mni" };

/** Only complete form values can request geometry; preview events never write back to the ROI. */
export function targetPreviewRoi(roi: RoiValue | undefined): TargetPreviewRoi | null {
  if (roi?.mode === "saved")
    return roi.selected.length && roi.selected.every((name) => name.trim()) && Number.isFinite(roi.radius) && roi.radius > 0
      ? { kind: "saved", names: [...roi.selected], radius: roi.radius, space: roi.space } : null;
  if (roi?.mode === "mask")
    return /\.nii(\.gz)?$/i.test(roi.path.trim()) ? { kind: "mask", path: roi.path.trim(), space: roi.space } : null;
  if (roi?.mode === "subcortical")
    return roi.atlas && roi.regions.length ? { kind: "subcortical", atlas: roi.atlas, labels: roi.regions.map((region) => region.id), space: roi.atlasSpace } : null;
  if (roi?.mode === "spherical" && roi.spheres.length && roi.spheres.every((sphere) =>
    [sphere.x, sphere.y, sphere.z, sphere.radius].every((value) => typeof value === "number" && Number.isFinite(value)) && sphere.radius! > 0,
  )) return { kind: "spherical", space: roi.space, spheres: roi.spheres.map((sphere) => ({ center: [sphere.x!, sphere.y!, sphere.z!], radius: sphere.radius! })) };
  return null;
}
