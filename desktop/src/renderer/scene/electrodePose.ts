/**
 * Where each EEG electrode model stands on the scalp: its base point and its axis.
 *
 * The axis is the scalp's outward normal at the electrode — the area-weighted vertex normals of the
 * skin within `ELECTRODE_PATCH_MM`, each turned outward first (our surfaces are not reliably wound)
 * — and the base is the electrode projected onto the plane through those vertices, so a net whose
 * positions sit a millimetre or two off the served (decimated) skin still stands ON it. Computed
 * once per net and skin, never per frame. Pure, so it is tested against an analytic sphere.
 */
import type { Vec3 } from "./camera";

/** Radius of the skin patch an electrode's normal and contact plane are averaged over. About an
 *  electrode's own radius: wide enough to smooth single-triangle facets, narrow enough to follow
 *  the head's curvature. */
export const ELECTRODE_PATCH_MM = 5;

export interface ElectrodePoses {
  /** xyz per electrode: the contact point on the skin. */
  base: Float32Array;
  /** xyz per electrode: the unit outward normal there. */
  axis: Float32Array;
}

export function electrodePoses(
  points: readonly Vec3[],
  positions: Float32Array,
  normals: Float32Array,
  centre: Vec3,
  patchMm = ELECTRODE_PATCH_MM,
): ElectrodePoses {
  const base = new Float32Array(points.length * 3);
  const axis = new Float32Array(points.length * 3);
  const r2 = patchMm * patchMm;
  points.forEach((p, e) => {
    let n = [0, 0, 0];
    let c = [0, 0, 0];
    let count = 0;
    let nearest = -1;
    let nearestD2 = Infinity;
    // ponytail: brute force over the skin (185 electrodes x ~40 k vertices, ~10 ms once per net);
    // a grid bucket if a pane ever re-poses per frame.
    for (let v = 0; v < positions.length; v += 3) {
      const dx = (positions[v] as number) - p[0];
      const dy = (positions[v + 1] as number) - p[1];
      const dz = (positions[v + 2] as number) - p[2];
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < nearestD2) {
        nearestD2 = d2;
        nearest = v;
      }
      if (d2 > r2) continue;
      accumulate(v);
    }
    if (count === 0 && nearest >= 0) accumulate(nearest);
    function accumulate(v: number): void {
      let nx = normals[v] as number;
      let ny = normals[v + 1] as number;
      let nz = normals[v + 2] as number;
      const ox = (positions[v] as number) - centre[0];
      const oy = (positions[v + 1] as number) - centre[1];
      const oz = (positions[v + 2] as number) - centre[2];
      if (nx * ox + ny * oy + nz * oz < 0) {
        nx = -nx;
        ny = -ny;
        nz = -nz;
      }
      n = [n[0]! + nx, n[1]! + ny, n[2]! + nz];
      c = [c[0]! + (positions[v] as number), c[1]! + (positions[v + 1] as number), c[2]! + (positions[v + 2] as number)];
      count += 1;
    }
    let len = Math.hypot(n[0]!, n[1]!, n[2]!);
    if (len === 0) {
      n = [p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]];
      len = Math.hypot(n[0]!, n[1]!, n[2]!) || 1;
    }
    const a = [n[0]! / len, n[1]! / len, n[2]! / len];
    const k = count > 0 ? 1 / count : 0;
    const plane = count > 0 ? [c[0]! * k, c[1]! * k, c[2]! * k] : [p[0], p[1], p[2]];
    const off = (p[0] - plane[0]!) * a[0]! + (p[1] - plane[1]!) * a[1]! + (p[2] - plane[2]!) * a[2]!;
    for (let i = 0; i < 3; i += 1) {
      base[e * 3 + i] = (p[i] as number) - a[i]! * off;
      axis[e * 3 + i] = a[i]!;
    }
  });
  return { base, axis };
}
