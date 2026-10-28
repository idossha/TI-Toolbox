/**
 * Where each EEG electrode stands on the scalp, how big it is, and how it bends onto the scalp.
 *
 * **Pose.** The axis is the scalp's outward normal at the electrode — the area-weighted vertex
 * normals of the skin within `ELECTRODE_PATCH_MM`, each turned outward first (our surfaces are not
 * reliably wound) — and the base is the electrode projected onto the plane through those vertices.
 *
 * **Bend.** A configured pad is up to ~50 mm across; laid flat on a head of ~90 mm radius its rim
 * would float ~3.5 mm off the scalp. So the skin around each electrode (on the same side) is fitted,
 * in the electrode's own frame (t, b, n), by the least-squares quadric
 * h(x, y) = c0 + c1 x + c2 y + c3 x² + c4 xy + c5 y², and every vertex of the electrode is lifted by
 * h at its footprint position (`placeOnScalp`, and its GPU twin in `glScene.ts`). A quadric is the
 * simplest surface that has the head's two principal curvatures and a tilt, so the gel lies on the
 * scalp across the footprint without a per-vertex search; it is exact on a sphere to the sphere's own
 * departure from a paraboloid (sub-0.1 mm at 25 mm from the axis on a 90 mm head).
 *
 * Two fits per electrode, both from the same pass over the skin: `fit` over `CAP_FIT_MM` for the
 * small cap marker, `fitWide` over `PAD_FIT_MM` for a configured pad. Neither depends on the pad's
 * size, which is what lets a size or gel edit redraw without re-posing anything: everything here is
 * computed once per net and skin, never per edit or per frame. Pure, so it is tested against an
 * analytic sphere and ellipsoid.
 */
import type { Vec3 } from "./camera";

/** Radius of the skin patch an electrode's normal and contact plane are averaged over. */
export const ELECTRODE_PATCH_MM = 5;
/** The cap marker's fit: its own 3 mm radius plus a margin. */
const CAP_FIT_MM = 8;
/** A pad's fit: the half-diagonal of a 50 x 30 mm pad (29 mm) plus a margin. A larger pad's rim
 *  extrapolates the quadric, which on a head stays within a millimetre for another ~10 mm. */
export const PAD_FIT_MM = 32;

/**
 * An electrode's physical size, from the simulation config (`SimulationConfig`): footprint
 * `width` x `height` mm (SimNIBS `dimensions`), `gel` then `rubber` thickness in mm (SimNIBS
 * `thickness`, skin outward). `gel` 0 means no gel layer.
 */
export interface ElectrodePad {
  shape: "ellipse" | "rect";
  width: number;
  height: number;
  gel: number;
  rubber: number;
}

/** The toolbox's own defaults (`tit/sim/config.py` `SimulationConfig`). */
export const DEFAULT_ELECTRODE_PAD: ElectrodePad = { shape: "ellipse", width: 8, height: 8, gel: 4, rubber: 2 };

/**
 * A pad from the config's own field values, falling back field by field to the defaults for a
 * value that is missing or not a usable number (a half-typed width must not collapse the pad).
 */
export function electrodePad(config: {
  electrode_shape?: unknown;
  electrode_dimensions?: unknown;
  gel_thickness?: unknown;
  rubber_thickness?: unknown;
}): ElectrodePad {
  const d = DEFAULT_ELECTRODE_PAD;
  const positive = (v: unknown, fallback: number) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : fallback);
  const dims = Array.isArray(config.electrode_dimensions) ? config.electrode_dimensions : [];
  const gel = config.gel_thickness;
  return {
    shape: config.electrode_shape === "rect" ? "rect" : "ellipse",
    width: positive(dims[0], d.width),
    height: positive(dims[1], d.height),
    gel: typeof gel === "number" && Number.isFinite(gel) && gel >= 0 ? gel : d.gel,
    rubber: positive(config.rubber_thickness, d.rubber),
  };
}

export interface ElectrodePoses {
  /** xyz per electrode: the contact point on the skin. */
  base: Float32Array;
  /** xyz per electrode: the unit outward normal there. */
  axis: Float32Array;
  /** xyz per electrode: the unit tangent the footprint's width runs along (`frameTangent`). */
  tangent: Float32Array;
  /** c0..c5 per electrode: the skin under a cap marker, h(x, y) along the axis (see header). */
  fit: Float32Array;
  /** c0..c5 per electrode: the skin under a pad of up to ~50 x 30 mm. */
  fitWide: Float32Array;
}

/** The tangent the shader also derives from the axis: horizontal (perpendicular to world +Z)
 *  unless the axis is nearly vertical. A rect pad's width runs along it. */
export function frameTangent(n: Vec3): Vec3 {
  const a: Vec3 = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  const t: Vec3 = [n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0]];
  const l = Math.hypot(t[0], t[1], t[2]) || 1;
  return [t[0] / l, t[1] / l, t[2] / l];
}

export function electrodePoses(
  points: readonly Vec3[],
  positions: Float32Array,
  normals: Float32Array,
  centre: Vec3,
  patchMm = ELECTRODE_PATCH_MM,
): ElectrodePoses {
  const count = points.length;
  const base = new Float32Array(count * 3);
  const axis = new Float32Array(count * 3);
  const tangent = new Float32Array(count * 3);
  const fit = new Float32Array(count * 6);
  const fitWide = new Float32Array(count * 6);
  const outward = (v: number): Vec3 => {
    const n: Vec3 = [normals[v] as number, normals[v + 1] as number, normals[v + 2] as number];
    const o = (positions[v] as number) - centre[0];
    const p = (positions[v + 1] as number) - centre[1];
    const q = (positions[v + 2] as number) - centre[2];
    return n[0] * o + n[1] * p + n[2] * q < 0 ? [-n[0], -n[1], -n[2]] : n;
  };
  points.forEach((p, e) => {
    const reach2 = PAD_FIT_MM * PAD_FIT_MM;
    const patch2 = patchMm * patchMm;
    let n: Vec3 = [0, 0, 0];
    let c: Vec3 = [0, 0, 0];
    let inPatch = 0;
    let nearest = -1;
    let nearestD2 = Infinity;
    const near: number[] = [];
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
      if (d2 > reach2) continue;
      near.push(v, d2);
      if (d2 > patch2) continue;
      const vn = outward(v);
      n = [n[0] + vn[0], n[1] + vn[1], n[2] + vn[2]];
      c = [c[0] + (positions[v] as number), c[1] + (positions[v + 1] as number), c[2] + (positions[v + 2] as number)];
      inPatch += 1;
    }
    if (inPatch === 0 && nearest >= 0) {
      n = outward(nearest);
      c = [positions[nearest] as number, positions[nearest + 1] as number, positions[nearest + 2] as number];
      inPatch = 1;
    }
    let len = Math.hypot(n[0], n[1], n[2]);
    if (len === 0) {
      n = [p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]];
      len = Math.hypot(n[0], n[1], n[2]) || 1;
    }
    const a: Vec3 = [n[0] / len, n[1] / len, n[2] / len];
    const plane: Vec3 = inPatch > 0 ? [c[0] / inPatch, c[1] / inPatch, c[2] / inPatch] : [p[0], p[1], p[2]];
    const off = (p[0] - plane[0]) * a[0] + (p[1] - plane[1]) * a[1] + (p[2] - plane[2]) * a[2];
    const b0: Vec3 = [p[0] - a[0] * off, p[1] - a[1] * off, p[2] - a[2] * off];
    const t = frameTangent(a);
    const bt: Vec3 = [a[1] * t[2] - a[2] * t[1], a[2] * t[0] - a[0] * t[2], a[0] * t[1] - a[1] * t[0]];
    const facing = (v: number) => {
      const vn = outward(v);
      return vn[0] * a[0] + vn[1] * a[1] + vn[2] * a[2];
    };
    for (let i = 0; i < 3; i += 1) {
      base[e * 3 + i] = b0[i]!;
      axis[e * 3 + i] = a[i]!;
      tangent[e * 3 + i] = t[i]!;
    }
    fit.set(fitQuadric(near, CAP_FIT_MM, positions, b0, t, bt, a, facing), e * 6);
    fitWide.set(fitQuadric(near, PAD_FIT_MM, positions, b0, t, bt, a, facing), e * 6);
  });
  return { base, axis, tangent, fit, fitWide };
}

/**
 * Least-squares h = c0 + c1 x + c2 y + c3 x² + c4 xy + c5 y² over the skin vertices in `near`
 * (vertex offset, squared distance pairs) within `reach` mm, facing the same way as the axis — the
 * other side of an ear is not this scalp. Returns all zeros — a flat electrode on the contact plane
 * — when there are too few vertices to fit.
 */
function fitQuadric(
  near: number[],
  reach: number,
  positions: Float32Array,
  origin: Vec3,
  t: Vec3,
  b: Vec3,
  n: Vec3,
  facing: (v: number) => number,
): number[] {
  const m = Array.from({ length: 6 }, () => new Array<number>(7).fill(0));
  let used = 0;
  const reach2 = reach * reach;
  for (let i = 0; i < near.length; i += 2) {
    const v = near[i] as number;
    if ((near[i + 1] as number) > reach2 || facing(v) < 0.3) continue;
    const d: Vec3 = [(positions[v] as number) - origin[0], (positions[v + 1] as number) - origin[1], (positions[v + 2] as number) - origin[2]];
    const x = d[0] * t[0] + d[1] * t[1] + d[2] * t[2];
    const y = d[0] * b[0] + d[1] * b[1] + d[2] * b[2];
    const h = d[0] * n[0] + d[1] * n[1] + d[2] * n[2];
    const row = [1, x, y, x * x, x * y, y * y];
    for (let i = 0; i < 6; i += 1) {
      for (let j = 0; j < 6; j += 1) m[i]![j]! += row[i]! * row[j]!;
      m[i]![6]! += row[i]! * h;
    }
    used += 1;
  }
  if (used < 12) return [0, 0, 0, 0, 0, 0];
  // Gaussian elimination with partial pivoting on the 6x6 normal equations.
  for (let col = 0; col < 6; col += 1) {
    let pivot = col;
    for (let r = col + 1; r < 6; r += 1) if (Math.abs(m[r]![col]!) > Math.abs(m[pivot]![col]!)) pivot = r;
    if (Math.abs(m[pivot]![col]!) < 1e-9) return [0, 0, 0, 0, 0, 0];
    [m[col], m[pivot]] = [m[pivot]!, m[col]!];
    for (let r = 0; r < 6; r += 1) {
      if (r === col) continue;
      const f = m[r]![col]! / m[col]![col]!;
      for (let k = col; k < 7; k += 1) m[r]![k]! -= f * m[col]![k]!;
    }
  }
  return m.map((row, i) => row[6]! / row[i]!);
}

/**
 * The world position of the point (x, y) mm across the footprint and z mm up the axis, for
 * electrode `e`: the CPU twin of the electrode vertex shader's bend, used for the name labels
 * and the tests.
 */
export function placeOnScalp(poses: ElectrodePoses, e: number, x: number, y: number, z: number, wide = false): Vec3 {
  const { base, axis, tangent } = poses;
  const fit = wide ? poses.fitWide : poses.fit;
  const at = (arr: Float32Array, i: number) => arr[e * 3 + i] as number;
  const n: Vec3 = [at(axis, 0), at(axis, 1), at(axis, 2)];
  const t: Vec3 = [at(tangent, 0), at(tangent, 1), at(tangent, 2)];
  const b: Vec3 = [n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2], n[0] * t[1] - n[1] * t[0]];
  const c = Array.from(fit.subarray(e * 6, e * 6 + 6));
  const h = c[0]! + c[1]! * x + c[2]! * y + c[3]! * x * x + c[4]! * x * y + c[5]! * y * y;
  return [0, 1, 2].map((i) => at(base, i) + t[i]! * x + b[i]! * y + n[i]! * (h + z)) as Vec3;
}
