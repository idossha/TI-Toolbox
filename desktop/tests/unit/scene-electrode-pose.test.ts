/**
 * Electrode models stand ON the scalp, axis along its outward normal (2026-10-28).
 *
 * `electrodePose.ts` turns each net position into the base point and axis the renderer instances
 * the electrode model at. The expectations come from a sphere, not from the code: the outward
 * normal of a sphere at p is p / |p|, and the surface is |x| = R. The mesh here is a UV sphere whose
 * vertex normals are the analytic ones with every other vertex's flipped, which is what an
 * inconsistently wound surface hands the renderer; nets are given off the surface on both sides,
 * the way a net sits up to 1.81 mm off the served (decimated) skin.
 *
 * The generated model (`electrodeModel.ts`, from `dev/export_electrode_model.py`) is checked for
 * the frame the shader assumes — base at z = 0, axis +Z, radius 1 — and for its budget.
 */
import { describe, expect, it } from "vitest";
import { ELECTRODE_MODEL } from "../../src/renderer/scene/electrodeModel";
import { electrodePoses } from "../../src/renderer/scene/electrodePose";
import type { Vec3 } from "../../src/renderer/scene/camera";

const R = 90;

/** A UV sphere: 2 mm-ish vertex spacing, like the served skin. */
function sphere(): { positions: Float32Array; normals: Float32Array } {
  const rows = 140;
  const cols = 280;
  const positions: number[] = [];
  const normals: number[] = [];
  for (let i = 1; i < rows; i += 1) {
    const theta = (Math.PI * i) / rows;
    for (let j = 0; j < cols; j += 1) {
      const phi = (2 * Math.PI * j) / cols;
      const n = [Math.sin(theta) * Math.cos(phi), Math.sin(theta) * Math.sin(phi), Math.cos(theta)];
      positions.push(n[0]! * R, n[1]! * R, n[2]! * R);
      const sign = (i + j) % 2 === 0 ? 1 : -1; // inconsistent winding
      normals.push(n[0]! * sign, n[1]! * sign, n[2]! * sign);
    }
  }
  return { positions: new Float32Array(positions), normals: new Float32Array(normals) };
}

describe("electrodePoses", () => {
  const { positions, normals } = sphere();
  const dirs: Vec3[] = [
    [0, 0, 1],
    [1, 0, 0],
    [0.3, -0.8, 0.52],
    [-0.6, 0.6, -0.53],
  ];
  const unit = (v: Vec3): Vec3 => {
    const l = Math.hypot(v[0], v[1], v[2]);
    return [v[0] / l, v[1] / l, v[2] / l];
  };

  for (const offMm of [-1.8, 0, 1.8]) {
    it(`puts the base on the skin and the axis along the outward normal (net ${offMm} mm off the skin)`, () => {
      const points = dirs.map((d) => {
        const u = unit(d);
        return [u[0] * (R + offMm), u[1] * (R + offMm), u[2] * (R + offMm)] as Vec3;
      });
      const { base, axis } = electrodePoses(points, positions, normals, [0, 0, 0]);
      dirs.forEach((d, e) => {
        const n = unit(d);
        const a: Vec3 = [axis[e * 3]!, axis[e * 3 + 1]!, axis[e * 3 + 2]!];
        const b: Vec3 = [base[e * 3]!, base[e * 3 + 1]!, base[e * 3 + 2]!];
        // Outward, and within half a degree of the sphere's normal.
        expect(a[0] * n[0] + a[1] * n[1] + a[2] * n[2]).toBeGreaterThan(Math.cos((0.5 * Math.PI) / 180));
        // On the surface: a 5 mm patch's chord plane sits at most r^2 / (2R) = 0.14 mm inside it.
        expect(Math.abs(Math.hypot(b[0], b[1], b[2]) - R)).toBeLessThan(0.15);
        // ...and under the electrode, not slid along the scalp.
        const bu = unit(b);
        expect(bu[0] * n[0] + bu[1] * n[1] + bu[2] * n[2]).toBeGreaterThan(Math.cos((0.1 * Math.PI) / 180));
      });
    });
  }

  it("falls back to the direction from the centre when there is no skin", () => {
    const { base, axis } = electrodePoses([[0, 30, 40]], new Float32Array(0), new Float32Array(0), [0, 0, 0]);
    expect(Array.from(axis)).toEqual([0, expect.closeTo(0.6, 6), expect.closeTo(0.8, 6)]);
    expect(Array.from(base)).toEqual([0, 30, 40]);
  });
});

describe("ELECTRODE_MODEL", () => {
  const { positions, normals, indices, height } = ELECTRODE_MODEL;
  it("is light enough to draw once per electrode", () => {
    expect(indices.length % 3).toBe(0);
    expect(indices.length / 3).toBeGreaterThanOrEqual(100);
    expect(indices.length / 3).toBeLessThanOrEqual(300);
    expect(Math.max(...indices)).toBeLessThan(positions.length / 3);
  });
  it("stands on z = 0 along +Z with radius 1, as the shader assumes", () => {
    let minZ = Infinity;
    let maxZ = -Infinity;
    let maxR = 0;
    for (let v = 0; v < positions.length; v += 3) {
      minZ = Math.min(minZ, positions[v + 2]!);
      maxZ = Math.max(maxZ, positions[v + 2]!);
      maxR = Math.max(maxR, Math.hypot(positions[v]!, positions[v + 1]!));
    }
    expect(minZ).toBeCloseTo(0, 3);
    expect(maxR).toBeCloseTo(1, 3);
    expect(maxZ).toBeCloseTo(height, 3);
    for (let v = 0; v < normals.length; v += 3) {
      expect(Math.hypot(normals[v]!, normals[v + 1]!, normals[v + 2]!)).toBeCloseTo(1, 2);
    }
  });
});
