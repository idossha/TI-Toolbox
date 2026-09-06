/**
 * `scene/normals.ts` — shading correctness as arithmetic.
 *
 * Every expected normal here is a cross product worked out in the comment above the assertion, and
 * the last case reads the real fixture and checks that the computed normal points *outwards* on an
 * ellipsoid whose outward direction is known in closed form (the gradient of x^2/a^2 + y^2/b^2 +
 * z^2/c^2). That single test covers the two things a picture would otherwise be needed for: the
 * winding convention of the fixture generator, and the sign convention of the accumulator.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { computeBounds, computeVertexNormals, unionBounds } from "../../src/renderer/scene/normals";
import { parseTvsc1 } from "../../src/renderer/scene/tvsc";

const FIXTURES = join(__dirname, "..", "fixtures", "scene");

describe("computeVertexNormals", () => {
  it("gives a counter-clockwise triangle in the XY plane the +Z normal", () => {
    const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
    const normals = computeVertexNormals(positions, new Uint32Array([0, 1, 2]));
    expect(Array.from(normals)).toEqual([0, 0, 1, 0, 0, 1, 0, 0, 1]);
  });

  it("flips with the winding", () => {
    const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
    const normals = computeVertexNormals(positions, new Uint32Array([0, 2, 1]));
    expect(Array.from(normals)).toEqual([0, 0, -1, 0, 0, -1, 0, 0, -1]);
  });

  it("weights a shared vertex by triangle area, not by triangle count", () => {
    // Triangle A: (0,0,0) (4,0,0) (0,4,0) -> cross = (0,0,16), i.e. twice its area of 8.
    // Triangle B: (0,0,0) (0,0,1) (1,0,0) -> cross = (0,1,0), twice its area of 0.5.
    // Vertex 0 accumulates (0,1,16); |(0,1,16)| = sqrt(257).
    const positions = new Float32Array([0, 0, 0, 4, 0, 0, 0, 4, 0, 0, 0, 1, 1, 0, 0]);
    const normals = computeVertexNormals(positions, new Uint32Array([0, 1, 2, 0, 3, 4]));
    const length = Math.sqrt(257);
    expect(normals[0]).toBeCloseTo(0, 6);
    expect(normals[1]).toBeCloseTo(1 / length, 6);
    expect(normals[2]).toBeCloseTo(16 / length, 6);
    // A count-weighted average would be (0, 0.5, 0.5)/|..| = (0, 0.707, 0.707) — nowhere near.
    expect(normals[2] as number).toBeGreaterThan(0.99);
  });

  it("falls back to +Z on a vertex whose triangles cancel exactly", () => {
    // A zero-area triangle contributes a zero cross product; a zero normal shades pure black,
    // which reads as a hole in the surface rather than as bad data.
    const positions = new Float32Array([0, 0, 0, 1, 0, 0, 2, 0, 0]);
    const normals = computeVertexNormals(positions, new Uint32Array([0, 1, 2]));
    expect(Array.from(normals.subarray(0, 3))).toEqual([0, 0, 1]);
  });

  it("points outwards everywhere on the skin fixture", () => {
    // Outward on x^2/a^2 + y^2/b^2 + z^2/c^2 = 1 is the gradient (x/a^2, y/b^2, z/c^2). If the
    // fixture's winding or the accumulator's sign were reversed, every one of these dot products
    // would be negative, and the lit side of the head would be the far side.
    const file = readFileSync(join(FIXTURES, "skin.tvsc"));
    const parsed = parseTvsc1(file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer);
    const normals = computeVertexNormals(parsed.positions, parsed.indices ?? new Uint32Array());
    const [a2, b2, c2] = [78 * 78, 98 * 98, 88 * 88];
    let checked = 0;
    let minCos = 1;
    // Skip the two pole rows, whose triangles are degenerate by construction.
    for (let i = 66; i < parsed.vertexCount - 66; i += 37) {
      const x = parsed.positions[i * 3] as number;
      const y = parsed.positions[i * 3 + 1] as number;
      const z = parsed.positions[i * 3 + 2] as number;
      const gx = x / a2;
      const gy = y / b2;
      const gz = z / c2;
      const glen = Math.hypot(gx, gy, gz);
      const cos =
        ((normals[i * 3] as number) * gx + (normals[i * 3 + 1] as number) * gy + (normals[i * 3 + 2] as number) * gz) /
        glen;
      minCos = Math.min(minCos, cos);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(50);
    // A 64x32 grid on this ellipsoid is faceted enough that a vertex normal is a few degrees off
    // the true surface normal; 0.999 is cos(2.6 degrees) and comfortably excludes "inwards".
    expect(minCos).toBeGreaterThan(0.999);
  });
});

describe("computeBounds", () => {
  it("is the axis-aligned box of the positions", () => {
    const positions = new Float32Array([1, -2, 3, -4, 5, -6, 0, 0, 0]);
    expect(Array.from(computeBounds(positions))).toEqual([-4, -2, -6, 1, 5, 3]);
  });

  it("returns a zero box for no positions rather than an inverted infinite one", () => {
    // An inverted box makes every downstream fitDistance NaN and the pane blank with no error.
    expect(Array.from(computeBounds(new Float32Array()))).toEqual([0, 0, 0, 0, 0, 0]);
  });
});

describe("unionBounds", () => {
  it("takes the extremes of every non-empty box", () => {
    expect(
      unionBounds([
        [0, 0, 0, 1, 1, 1],
        [-5, 2, -1, -1, 9, 0],
      ]),
    ).toEqual([-5, 0, -1, 1, 9, 1]);
  });

  it("ignores an empty list", () => {
    expect(unionBounds([])).toEqual([0, 0, 0, 0, 0, 0]);
  });
});
