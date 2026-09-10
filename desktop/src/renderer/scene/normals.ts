/**
 * Per-vertex normals, computed in the browser because `TVSC1` deliberately does not carry them
 * (`tvsc.ts`). Pure and array-in/array-out, so the shading can be checked with arithmetic instead
 * of by looking at a picture.
 */

/**
 * Area-weighted vertex normals.
 *
 * Each triangle contributes its *unnormalised* cross product to its three vertices, so a large
 * triangle counts more than a sliver. That is the standard choice and the one that matters on a
 * decimated cortical surface: with equal weighting, the many tiny triangles in a sulcus outvote the
 * few large ones on the neighbouring gyrus and the shading develops a visible seam along the
 * decimation boundary.
 *
 * Winding is counter-clockwise-is-front, matching `gl.frontFace(gl.CCW)` (WebGL's default) and the
 * meshes SimNIBS writes. A vertex whose triangles cancel exactly (a degenerate fan) gets `+Z`
 * rather than a zero vector: a zero normal shades pure black, which reads as a hole in the surface.
 */
export function computeVertexNormals(positions: Float32Array, indices: Uint32Array): Float32Array {
  const normals = new Float32Array(positions.length);
  for (let t = 0; t < indices.length; t += 3) {
    const ia = (indices[t] as number) * 3;
    const ib = (indices[t + 1] as number) * 3;
    const ic = (indices[t + 2] as number) * 3;
    const ax = positions[ia] as number;
    const ay = positions[ia + 1] as number;
    const az = positions[ia + 2] as number;
    const e1x = (positions[ib] as number) - ax;
    const e1y = (positions[ib + 1] as number) - ay;
    const e1z = (positions[ib + 2] as number) - az;
    const e2x = (positions[ic] as number) - ax;
    const e2y = (positions[ic + 1] as number) - ay;
    const e2z = (positions[ic + 2] as number) - az;
    // |e1 x e2| is twice the triangle's area, which is the weight.
    const nx = e1y * e2z - e1z * e2y;
    const ny = e1z * e2x - e1x * e2z;
    const nz = e1x * e2y - e1y * e2x;
    normals[ia] = (normals[ia] as number) + nx;
    normals[ia + 1] = (normals[ia + 1] as number) + ny;
    normals[ia + 2] = (normals[ia + 2] as number) + nz;
    normals[ib] = (normals[ib] as number) + nx;
    normals[ib + 1] = (normals[ib + 1] as number) + ny;
    normals[ib + 2] = (normals[ib + 2] as number) + nz;
    normals[ic] = (normals[ic] as number) + nx;
    normals[ic + 1] = (normals[ic + 1] as number) + ny;
    normals[ic + 2] = (normals[ic + 2] as number) + nz;
  }
  for (let i = 0; i < normals.length; i += 3) {
    const x = normals[i] as number;
    const y = normals[i + 1] as number;
    const z = normals[i + 2] as number;
    const len = Math.hypot(x, y, z);
    if (len === 0) {
      normals[i + 2] = 1;
    } else {
      normals[i] = x / len;
      normals[i + 1] = y / len;
      normals[i + 2] = z / len;
    }
  }
  return normals;
}

/** Axis-aligned bounds of a position array, as the `[x0,y0,z0,x1,y1,z1]` the manifest uses.
 *  Returns a zero box for an empty array rather than `[+inf, ..., -inf]`, which would make every
 *  downstream `fitDistance` produce `NaN` and a blank pane with no error anywhere. */
export function computeBounds(positions: Float32Array): [number, number, number, number, number, number] {
  if (positions.length === 0) return [0, 0, 0, 0, 0, 0];
  let x0 = Infinity;
  let y0 = Infinity;
  let z0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  let z1 = -Infinity;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i] as number;
    const y = positions[i + 1] as number;
    const z = positions[i + 2] as number;
    if (x < x0) x0 = x;
    if (y < y0) y0 = y;
    if (z < z0) z0 = z;
    if (x > x1) x1 = x;
    if (y > y1) y1 = y;
    if (z > z1) z1 = z;
  }
  return [x0, y0, z0, x1, y1, z1];
}

/** The union of several bounds, used to frame a scene made of more than one surface. */
export function unionBounds(
  boxes: Array<[number, number, number, number, number, number]>,
): [number, number, number, number, number, number] {
  const nonEmpty = boxes.filter((b) => b[3] >= b[0]);
  const first = nonEmpty[0];
  if (!first) return [0, 0, 0, 0, 0, 0];
  const out: [number, number, number, number, number, number] = [...first];
  for (const b of nonEmpty.slice(1)) {
    for (let i = 0; i < 3; i += 1) {
      if ((b[i] as number) < (out[i] as number)) out[i] = b[i] as number;
      if ((b[i + 3] as number) > (out[i + 3] as number)) out[i + 3] = b[i + 3] as number;
    }
  }
  return out;
}
