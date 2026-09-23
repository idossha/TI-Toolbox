/**
 * "Explode" — an MNI atlas pulled apart so deep regions can be reached (`ScenePane`'s toggle).
 *
 * Purely visual: every region is TRANSLATED (never scaled) outward from the atlas centre along
 * its own centroid, by a per-vertex offset the vertex shader adds at `offset * progress`. Pick ids
 * are the labels, which do not move, so hover, click and the selection keep working exploded and
 * the selection is untouched by the toggle.
 */

/**
 * Per-axis weight on the displacement: mostly lateral, as asked ("expand towards laterality"),
 * so the two hemispheres of a lateralised atlas separate first and most.
 * ponytail: tuned by eye on CIT168 and Harvard-Oxford; a calibration knob, not a derived value.
 */
export const EXPLODE_AXIS_WEIGHT: readonly [number, number, number] = [1, 0.55, 0.55];
/** Growth per mm of centroid distance: a region twice as far from the centre moves twice as far. */
export const EXPLODE_SPREAD = 0.9;
/** Constant push (mm) along the centroid direction, so a region sitting at the centre still moves. */
export const EXPLODE_PUSH_MM = 12;
/** Whole animation, both stages. */
export const EXPLODE_DURATION_MS = 800;
/** The share of the timeline the skin fade takes; the regions then move for the rest. */
const VEIL_SHARE = 0.35;

/**
 * One offset per vertex (xyz, mm), constant across each label: `W ⊙ (A·d + B·d̂)` with `d` the
 * label centroid minus the centre of the surface's bounding box (the midline for a symmetric MNI
 * atlas). A region whose centroid IS the centre is pushed straight up, the only direction left.
 */
export function regionOffsets(positions: Float32Array, labels: ArrayLike<number>): Float32Array {
  const count = labels.length;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const sums = new Map<number, Float64Array>();
  for (let v = 0; v < count; v += 1) {
    const label = labels[v] as number;
    let sum = sums.get(label);
    if (!sum) sums.set(label, (sum = new Float64Array(4)));
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[v * 3 + axis] as number;
      sum[axis]! += value;
      if (value < min[axis]!) min[axis] = value;
      if (value > max[axis]!) max[axis] = value;
    }
    sum[3]! += 1;
  }
  const centre = [0, 1, 2].map((axis) => (min[axis]! + max[axis]!) / 2);
  const byLabel = new Map<number, [number, number, number]>();
  for (const [label, sum] of sums) {
    const d = [0, 1, 2].map((axis) => sum[axis]! / sum[3]! - centre[axis]!);
    const length = Math.hypot(d[0]!, d[1]!, d[2]!);
    const unit = length > 1e-6 ? d.map((value) => value / length) : [0, 0, 1];
    byLabel.set(
      label,
      [0, 1, 2].map(
        (axis) => EXPLODE_AXIS_WEIGHT[axis]! * (EXPLODE_SPREAD * d[axis]! + EXPLODE_PUSH_MM * unit[axis]!),
      ) as [number, number, number],
    );
  }
  const out = new Float32Array(count * 3);
  for (let v = 0; v < count; v += 1) out.set(byLabel.get(labels[v] as number)!, v * 3);
  return out;
}

/** The positions the shader draws at offset scale `t` — what the camera frames when exploded. */
export function explodedPositions(positions: Float32Array, offsets: Float32Array, t: number): Float32Array {
  if (t === 0) return positions;
  const out = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 1) out[i] = (positions[i] as number) + (offsets[i] as number) * t;
  return out;
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));
const easeInOut = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/**
 * Timeline progress 0..1 -> what is drawn. Opening runs it forwards (the skin fades, then the
 * regions move out); closing runs the SAME timeline backwards, so the regions collapse first and
 * the skin fades back in last. `veil` is the fraction of the skin's opacity removed.
 */
export function explodeStage(progress: number): { veil: number; offset: number } {
  const p = clamp01(progress);
  return { veil: clamp01(p / VEIL_SHARE), offset: easeInOut(clamp01((p - VEIL_SHARE) / (1 - VEIL_SHARE))) };
}
