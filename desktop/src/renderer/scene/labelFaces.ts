/**
 * Per-face region labels, spelled as a triangle winding.
 *
 * The surface shaders read the region id from a `flat`-qualified `uint` varying (`glScene.ts`,
 * §"Picking"), so a triangle is painted, and picked, entirely as ONE region. Which one is decided
 * by the *provoking vertex*, and WebGL 2 fixes that to the triangle's **last** index — an arbitrary
 * corner as far as the anatomy is concerned.
 *
 * That arbitrariness is what the maintainer saw on 2026-09-06: *"the label borderlines between
 * regions should be much smoother"*. Measured on the packaged ernie guide with DK40, after the
 * service-side mode filter, **15 289 of 145 402** grey-matter triangles (10.5 %) still straddle a
 * region border, as any border on a real parcellation must. Of those, 14 965 have two corners in
 * one region and one in the other — an unambiguous majority — and with the last corner deciding,
 * roughly a third of them take the *minority* label. Each one is a triangle-sized spike of the
 * neighbour's colour poking across the border, which is exactly the reported saw-tooth.
 *
 * This module rotates each such triangle so a majority corner is last. Rotation is not a reordering:
 * `[a,b,c] -> [b,c,a] -> [c,a,b]` preserves the winding, so normals, culling and the outward
 * orientation the service guarantees are all untouched, and no vertex data changes — only which of
 * three existing corners the rasteriser asks for the label. The border then follows the mesh edges
 * between the two regions instead of wandering a triangle either side of it.
 *
 * A triangle whose three corners are three different regions is a genuine triple junction (324 of
 * them on ernie/DK40, 0.22 %). There is no majority to rotate to, so it is left exactly as it came.
 */

/**
 * Rotates every triangle so its last corner carries the majority region label.
 *
 * Returns the input array itself when nothing needs moving, and otherwise a new array — the caller's
 * buffer is never mutated, because `ScenePart.indices` is shared with the decoded payload cache.
 */
export function orientFacesToMajorityLabel(
  indices: Uint32Array,
  labels: Uint16Array,
): Uint32Array {
  const faces = Math.floor(indices.length / 3);
  let out: Uint32Array | null = null;
  for (let f = 0; f < faces; f += 1) {
    const i = f * 3;
    const a = indices[i];
    const b = indices[i + 1];
    const c = indices[i + 2];
    const la = labels[a];
    const lb = labels[b];
    const lc = labels[c];
    if (lc === la || lc === lb) continue; // the last corner is already a majority one
    // `lc` is the odd one out, so a majority exists only if the other two agree.
    if (la !== lb) continue; // genuine triple junction — nothing to rotate to
    if (out === null) out = Uint32Array.from(indices);
    // [a,b,c] -> [c,a,b]: same winding, and `b` (label `la === lb`) provokes.
    out[i] = c;
    out[i + 1] = a;
    out[i + 2] = b;
  }
  return out ?? indices;
}

/**
 * How many triangles of a labelled surface take a label a majority of their own corners disagree
 * with. 0 after {@link orientFacesToMajorityLabel}, except at triple junctions, where no corner is
 * in a majority and none is counted. Exists for the tests and for the pane's diagnostics.
 */
export function countMinorityFaces(indices: Uint32Array, labels: Uint16Array): number {
  const faces = Math.floor(indices.length / 3);
  let n = 0;
  for (let f = 0; f < faces; f += 1) {
    const i = f * 3;
    const la = labels[indices[i]];
    const lb = labels[indices[i + 1]];
    const lc = labels[indices[i + 2]];
    if (lc !== la && lc !== lb && la === lb) n += 1;
  }
  return n;
}
