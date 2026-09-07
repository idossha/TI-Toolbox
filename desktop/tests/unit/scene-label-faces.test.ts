/**
 * Per-face region labels — `scene/labelFaces.ts`.
 *
 * What this pins
 *     The maintainer reported, on 2026-09-06, that atlas borders in the run-page pane are a ragged
 *     saw-tooth: triangle-sized spikes of one region poking into the next. The surface shaders read
 *     the region from a `flat` varying, so a triangle is one region — decided by WebGL 2's provoking
 *     vertex, which is the triangle's LAST index and has nothing to do with the anatomy. On the
 *     packaged ernie guide with DK40 that leaves 15 289 border triangles whose colour is a coin
 *     toss, roughly a third of them landing on the region only ONE of their three corners is in.
 *
 * Where the numbers come from
 *     Hand-authored triangles whose majority is stated in the test. No golden image and no GL
 *     context is involved: this is an index-permutation property, checkable exactly.
 */
import { describe, expect, it } from "vitest";

import { countMinorityFaces, orientFacesToMajorityLabel } from "../../src/renderer/scene/labelFaces";

const winding = (indices: Uint32Array, face: number): string => {
  // A rotation of [a,b,c] and nothing else: canonicalise by rotating the smallest index to front.
  const t = [indices[face * 3]!, indices[face * 3 + 1]!, indices[face * 3 + 2]!];
  const at = t.indexOf(Math.min(...t));
  return [t[at]!, t[(at + 1) % 3]!, t[(at + 2) % 3]!].join(",");
};

describe("orientFacesToMajorityLabel", () => {
  it("rotates a two-to-one triangle so the majority corner provokes", () => {
    // Corners 0 and 1 are region 7; corner 2 is region 9. Unrotated, the flat varying would paint
    // and pick the whole triangle as 9 — a spike of the neighbour across the border.
    const labels = new Uint16Array([7, 7, 9]);
    const out = orientFacesToMajorityLabel(new Uint32Array([0, 1, 2]), labels);
    expect(labels[out[2]!]).toBe(7);
  });

  it("preserves winding, so normals and culling are untouched", () => {
    const labels = new Uint16Array([7, 7, 9]);
    const before = new Uint32Array([0, 1, 2]);
    const after = orientFacesToMajorityLabel(before, labels);
    expect(winding(after, 0)).toBe(winding(before, 0));
    expect([...after].sort()).toEqual([0, 1, 2]);
  });

  it("leaves a genuine triple junction exactly as it came", () => {
    const before = new Uint32Array([0, 1, 2]);
    const after = orientFacesToMajorityLabel(before, new Uint16Array([1, 2, 3]));
    expect(after).toBe(before); // the same array: nothing to decide, nothing copied
  });

  it("never mutates the caller's index buffer", () => {
    const before = new Uint32Array([0, 1, 2]);
    const copy = Uint32Array.from(before);
    orientFacesToMajorityLabel(before, new Uint16Array([7, 7, 9]));
    expect([...before]).toEqual([...copy]);
  });

  it("leaves no minority-labelled face on a two-region strip", () => {
    // A 16x2 strip of quads split down the middle: rows 0..7 are region 1, 8..15 region 2. Every
    // triangle that straddles the split has a 2:1 majority, and none of them may take the minority.
    const w = 16;
    const positions = w * 2;
    const labels = new Uint16Array(positions);
    for (let i = 0; i < positions; i += 1) labels[i] = i % w < 8 ? 1 : 2;
    const faces: number[] = [];
    for (let c = 0; c < w - 1; c += 1) {
      const a = c;
      const b = c + 1;
      const d = w + c;
      const e = w + c + 1;
      faces.push(a, b, d, b, e, d);
    }
    const before = new Uint32Array(faces);
    expect(countMinorityFaces(before, labels)).toBeGreaterThan(0);
    expect(countMinorityFaces(orientFacesToMajorityLabel(before, labels), labels)).toBe(0);
  });

  it("is idempotent", () => {
    const labels = new Uint16Array([7, 7, 9, 9, 4, 4]);
    const once = orientFacesToMajorityLabel(new Uint32Array([0, 1, 2, 3, 4, 5]), labels);
    const twice = orientFacesToMajorityLabel(once, labels);
    expect(twice).toBe(once);
  });
});
