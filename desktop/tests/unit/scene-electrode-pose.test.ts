/**
 * Electrodes stand ON the scalp at their configured size, bent onto it (2026-10-28).
 *
 * `electrodePose.ts` turns each net position into the base point, axis, tangent and the fitted
 * skin quadric the renderer instances the electrode at; `placeOnScalp` is the CPU twin of the
 * shader's bend. The expectations come from geometry, not from the code:
 *   - on a sphere the outward normal at p is p / |p| and the surface is |x| = R;
 *   - on an ellipsoid (two different curvatures under one pad) the surface is sum((x_i / r_i)^2) = 1,
 *     and the distance to it is approximated by (F - 1) / |grad F| (first order, exact enough at
 *     the sub-millimetre level asserted).
 * Meshes are UV grids at ~2 mm spacing, like the served skin, with every other vertex normal
 * flipped — what an inconsistently wound surface hands the renderer. Nets are given off the
 * surface on both sides, as a net sits up to 1.81 mm off the decimated skin.
 *
 * The config mapping is checked against the toolbox's own defaults as the generated schema states
 * them (`contracts/generated/config.schema.json`, written from `tit/sim/config.py`), and the
 * generated model (`electrodeModel.ts`, from `dev/export_electrode_model.py`) for the frame and the
 * budget the shader assumes.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ELECTRODE_MODEL } from "../../src/renderer/scene/electrodeModel";
import {
  DEFAULT_ELECTRODE_PAD,
  electrodePad,
  electrodePoses,
  frameTangent,
  placeOnScalp,
  type ElectrodePad,
} from "../../src/renderer/scene/electrodePose";
import type { Vec3 } from "../../src/renderer/scene/camera";

const R = 90;

/** A UV grid over the ellipsoid `radii`, normals analytic (gradient), every other one flipped. */
function shell(radii: Vec3): { positions: Float32Array; normals: Float32Array } {
  const rows = 140;
  const cols = 280;
  const positions: number[] = [];
  const normals: number[] = [];
  for (let i = 1; i < rows; i += 1) {
    const theta = (Math.PI * i) / rows;
    for (let j = 0; j < cols; j += 1) {
      const phi = (2 * Math.PI * j) / cols;
      const u = [Math.sin(theta) * Math.cos(phi), Math.sin(theta) * Math.sin(phi), Math.cos(theta)];
      const p = [u[0]! * radii[0], u[1]! * radii[1], u[2]! * radii[2]];
      const g = [p[0]! / radii[0] ** 2, p[1]! / radii[1] ** 2, p[2]! / radii[2] ** 2];
      const gl = Math.hypot(g[0]!, g[1]!, g[2]!);
      const sign = (i + j) % 2 === 0 ? 1 : -1;
      positions.push(...p);
      normals.push((g[0]! / gl) * sign, (g[1]! / gl) * sign, (g[2]! / gl) * sign);
    }
  }
  return { positions: new Float32Array(positions), normals: new Float32Array(normals) };
}

const unit = (v: Vec3): Vec3 => {
  const l = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / l, v[1] / l, v[2] / l];
};
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** Signed distance from p to the ellipsoid surface, to first order. */
function offSurface(p: Vec3, radii: Vec3): number {
  const f = (p[0] / radii[0]) ** 2 + (p[1] / radii[1]) ** 2 + (p[2] / radii[2]) ** 2;
  const g = Math.hypot((2 * p[0]) / radii[0] ** 2, (2 * p[1]) / radii[1] ** 2, (2 * p[2]) / radii[2] ** 2);
  return (f - 1) / g;
}

const DIRS: Vec3[] = [
  [0, 0, 1],
  [1, 0, 0],
  [0.3, -0.8, 0.52],
  [-0.6, 0.6, -0.53],
];

describe("electrodePoses — where an electrode stands", () => {
  const sphere = shell([R, R, R]);
  for (const offMm of [-1.8, 0, 1.8]) {
    it(`puts the base on the skin and the axis along the outward normal (net ${offMm} mm off the skin)`, () => {
      const points = DIRS.map((d) => {
        const u = unit(d);
        return [u[0] * (R + offMm), u[1] * (R + offMm), u[2] * (R + offMm)] as Vec3;
      });
      const poses = electrodePoses(points, sphere.positions, sphere.normals, [0, 0, 0]);
      DIRS.forEach((d, e) => {
        const n = unit(d);
        const a: Vec3 = [poses.axis[e * 3]!, poses.axis[e * 3 + 1]!, poses.axis[e * 3 + 2]!];
        expect(dot(a, n)).toBeGreaterThan(Math.cos((0.5 * Math.PI) / 180));
        // The contact point (bend included) is on the sphere and under the electrode.
        const contact = placeOnScalp(poses, e, 0, 0, 0);
        expect(Math.abs(Math.hypot(...contact) - R)).toBeLessThan(0.05);
        expect(dot(unit(contact), n)).toBeGreaterThan(Math.cos((0.1 * Math.PI) / 180));
        // The tangent is the one the shader would derive: unit, perpendicular to the axis.
        const t: Vec3 = [poses.tangent[e * 3]!, poses.tangent[e * 3 + 1]!, poses.tangent[e * 3 + 2]!];
        expect(t).toEqual(frameTangent(a).map((v) => expect.closeTo(v, 6)));
        expect(Math.abs(dot(t, a))).toBeLessThan(1e-6);
      });
    });
  }

  it("falls back to the direction from the centre when there is no skin", () => {
    const { base, axis } = electrodePoses([[0, 30, 40]], new Float32Array(0), new Float32Array(0), [0, 0, 0]);
    expect(Array.from(axis)).toEqual([0, expect.closeTo(0.6, 6), expect.closeTo(0.8, 6)]);
    expect(Array.from(base)).toEqual([0, 30, 40]);
  });
});

describe("the bend — a large pad's gel lies on the scalp across its whole footprint", () => {
  const big: ElectrodePad = { shape: "rect", width: 50, height: 30, gel: 5, rubber: 2 };
  const footprint = (pad: ElectrodePad): Array<[number, number]> => {
    const out: Array<[number, number]> = [];
    for (let i = -5; i <= 5; i += 1) for (let j = -5; j <= 5; j += 1) out.push([(i / 5) * (pad.width / 2), (j / 5) * (pad.height / 2)]);
    return out;
  };

  it("on a sphere, every bent base point is within 0.1 mm of the surface (flat, the rim would be ~4.7 mm off)", () => {
    const sphere = shell([R, R, R]);
    const points = DIRS.map((d) => unit(d).map((v) => v * R) as Vec3);
    const poses = electrodePoses(points, sphere.positions, sphere.normals, [0, 0, 0]);
    DIRS.forEach((_, e) => {
      for (const [x, y] of footprint(big)) {
        expect(Math.abs(Math.hypot(...placeOnScalp(poses, e, x, y, 0, true)) - R), `electrode ${e} at (${x}, ${y})`).toBeLessThan(0.1);
      }
      // ...and the gel's top is the gel thickness above it, along the scalp's normal there.
      const top = placeOnScalp(poses, e, 20, 10, big.gel, true);
      expect(Math.hypot(...top) - R).toBeCloseTo(big.gel, 0);
    });
    // The control: the sagitta of the corner of a flat 50 x 30 pad on this sphere.
    expect(R - Math.sqrt(R * R - (25 ** 2 + 15 ** 2))).toBeGreaterThan(4.5);
  });

  it("on an ellipsoid (two curvatures under one pad), every bent base point is within 0.3 mm", () => {
    const radii: Vec3 = [78, 98, 88];
    const head = shell(radii);
    const points = DIRS.map((d) => {
      const u = unit(d);
      const s = 1 / Math.hypot(u[0] / radii[0], u[1] / radii[1], u[2] / radii[2]);
      return [u[0] * s, u[1] * s, u[2] * s] as Vec3;
    });
    const poses = electrodePoses(points, head.positions, head.normals, [0, 0, 0]);
    DIRS.forEach((_, e) => {
      for (const [x, y] of footprint(big)) {
        expect(Math.abs(offSurface(placeOnScalp(poses, e, x, y, 0, true), radii)), `electrode ${e} at (${x}, ${y})`).toBeLessThan(0.3);
      }
    });
  });
});

describe("electrodePad — the configured electrode", () => {
  it("maps the simulation config's own fields", () => {
    expect(electrodePad({ electrode_shape: "rect", electrode_dimensions: [50, 30], gel_thickness: 5, rubber_thickness: 3 })).toEqual({
      shape: "rect",
      width: 50,
      height: 30,
      gel: 5,
      rubber: 3,
    });
    expect(electrodePad({ electrode_shape: "ellipse", electrode_dimensions: [10, 10], gel_thickness: 0 })).toEqual({
      shape: "ellipse",
      width: 10,
      height: 10,
      gel: 0, // no gel layer
      rubber: DEFAULT_ELECTRODE_PAD.rubber,
    });
  });

  it("falls back field by field to the defaults for a missing or half-typed value", () => {
    expect(electrodePad({ electrode_dimensions: [Number.NaN, -1], gel_thickness: -2, rubber_thickness: 0 })).toEqual(DEFAULT_ELECTRODE_PAD);
    expect(electrodePad({})).toEqual(DEFAULT_ELECTRODE_PAD);
  });

  it("defaults to what the toolbox's generated schema says SimulationConfig defaults to", () => {
    const schema = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json"), "utf8"));
    const props = schema.$defs.SimulationConfig.properties;
    const dims = schema["x-app-defaults"].sim.electrode_dimensions;
    expect(DEFAULT_ELECTRODE_PAD).toEqual({
      shape: props.electrode_shape.default,
      width: dims[0],
      height: dims[1],
      gel: props.gel_thickness.default,
      rubber: props.rubber_thickness.default,
    });
  });
});

describe("ELECTRODE_MODEL", () => {
  const { positions, normals, layers, indices, height } = ELECTRODE_MODEL;
  it("is light enough to draw once per electrode", () => {
    expect(indices.length % 3).toBe(0);
    expect(indices.length / 3).toBeLessThanOrEqual(400);
    expect(Math.max(...indices)).toBeLessThan(positions.length / 3);
    expect(layers.length).toBe(positions.length / 3);
  });
  it("has a pad standing on z = 0 along +Z with radius 1, and a unit gel slab under it", () => {
    const span = (layer: number) => {
      let minZ = Infinity;
      let maxZ = -Infinity;
      let maxR = 0;
      for (let v = 0; v < layers.length; v += 1) {
        if (layers[v] !== layer) continue;
        minZ = Math.min(minZ, positions[v * 3 + 2]!);
        maxZ = Math.max(maxZ, positions[v * 3 + 2]!);
        maxR = Math.max(maxR, Math.hypot(positions[v * 3]!, positions[v * 3 + 1]!));
      }
      return { minZ, maxZ, maxR };
    };
    const pad = span(1);
    expect(pad.minZ).toBeCloseTo(0, 3);
    expect(pad.maxR).toBeCloseTo(1, 3);
    expect(pad.maxZ).toBeCloseTo(height, 3);
    const gel = span(0);
    expect(gel).toEqual({ minZ: 0, maxZ: 1, maxR: expect.closeTo(1, 3) });
    for (let v = 0; v < normals.length; v += 3) {
      expect(Math.hypot(normals[v]!, normals[v + 1]!, normals[v + 2]!)).toBeCloseTo(1, 2);
    }
  });
  it("has every normal pointing out of its layer (a flipped one shades black when stretched)", () => {
    for (let v = 0; v < layers.length; v += 1) {
      const mid = layers[v] === 1 ? height / 2 : 0.5;
      const out = normals[v * 3]! * positions[v * 3]! + normals[v * 3 + 1]! * positions[v * 3 + 1]! + normals[v * 3 + 2]! * (positions[v * 3 + 2]! - mid);
      expect(out, `vertex ${v}`).toBeGreaterThan(0);
    }
  });
});
