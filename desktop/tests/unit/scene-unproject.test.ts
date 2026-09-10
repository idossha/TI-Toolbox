/**
 * Unprojection: canvas pixel + depth -> the world point under the cursor (lane FIX-A, defect 2 —
 * lane SCC's request in `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §6.1: `onPick` says *which* marker or
 * region was hit but not *where*, so "click anywhere on the cortex to place the sphere centre"
 * cannot be built).
 *
 * The renderer answers the "where" by reading the depth its own pick pass rasterised and turning it
 * back into millimetres. That inverse is what this file proves, and it is proved against geometry —
 * a ray/ellipsoid intersection solved here, and the projection's own z row retyped from the
 * documented matrix — rather than against the code under test:
 *
 *   - the depth of a point at eye-space distance `d` is `ndc = -(m10 * ze + m14) / ze` with
 *     `ze = -d`, and `m10`/`m14` come from `perspective()`'s definition written out by hand below;
 *   - a point on an ellipsoid found by solving the quadratic must unproject to itself, to the
 *     micron, from the pixel it projects into.
 */
import { describe, expect, it } from "vitest";
import {
  cameraBasis,
  depthRange,
  projectToCanvas,
  screenRay,
  unprojectDepth,
  viewDepthFromNdc,
  type OrbitCamera,
  type Vec3,
} from "../../src/renderer/scene/camera";

/** Eye 200 mm anterior of the origin, looking at it. fovY = 90 degrees, so tan(fovY/2) = 1. */
const FRONT: OrbitCamera = { target: [0, 0, 0], distance: 200, yaw: 0, pitch: 0, fovY: Math.PI / 2 };
/** A three-quarter view of an off-centre scene, at the default 35-degree field. */
const OBLIQUE: OrbitCamera = {
  target: [8, -14, 22],
  distance: 430,
  yaw: -0.62,
  pitch: 0.3,
  fovY: (35 * Math.PI) / 180,
};

const W = 800;
const H = 400;

/** The normalised device depth of a fragment `d` mm in front of the eye, from the perspective
 *  matrix's definition (`camera.ts`: `m10 = (far + near) / (near - far)`,
 *  `m14 = 2 * far * near / (near - far)`, `w_clip = -z_eye`), retyped rather than imported. */
function ndcDepthAt(camera: OrbitCamera, mmInFront: number): number {
  const { near, far } = depthRange(camera);
  const m10 = (far + near) / (near - far);
  const m14 = (2 * far * near) / (near - far);
  const zEye = -mmInFront;
  return -(m10 * zEye + m14) / zEye;
}

const distance = (a: Vec3, b: Vec3): number => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

describe("viewDepthFromNdc", () => {
  it("inverts the projection's z row exactly, at both plane limits and in between", () => {
    for (const camera of [FRONT, OBLIQUE]) {
      const { near, far } = depthRange(camera);
      for (const mm of [near, near * 3, camera.distance / 2, camera.distance, camera.distance * 2, far]) {
        expect(viewDepthFromNdc(camera, ndcDepthAt(camera, mm))).toBeCloseTo(mm, 6);
      }
    }
  });

  it("maps the near plane to -1 and the far plane to +1, the depth range GL clips against", () => {
    const { near, far } = depthRange(FRONT);
    expect(ndcDepthAt(FRONT, near)).toBeCloseTo(-1, 12);
    expect(ndcDepthAt(FRONT, far)).toBeCloseTo(1, 12);
  });
});

describe("unprojectDepth", () => {
  it("puts the centre pixel of a face-on view on the view axis at the depth given", () => {
    // Eye at (0, 200, 0) looking down -Y: a fragment 50 mm in front of it is (0, 150, 0), and no
    // arithmetic in the module under test is involved in saying so.
    const point = unprojectDepth(FRONT, W / 2, H / 2, W, H, ndcDepthAt(FRONT, 50));
    expect(point[0]).toBeCloseTo(0, 9);
    expect(point[1]).toBeCloseTo(150, 6);
    expect(point[2]).toBeCloseTo(0, 9);
  });

  it("returns a point that lies on the screen ray through that pixel", () => {
    for (const [x, y] of [
      [W / 2, H / 2],
      [12, 8],
      [W - 3, H - 5],
      [W * 0.31, H * 0.77],
    ]) {
      const ray = screenRay(OBLIQUE, x as number, y as number, W, H);
      const point = unprojectDepth(OBLIQUE, x as number, y as number, W, H, ndcDepthAt(OBLIQUE, 380));
      const toPoint: Vec3 = [point[0] - ray.origin[0], point[1] - ray.origin[1], point[2] - ray.origin[2]];
      const along = toPoint[0] * ray.direction[0] + toPoint[1] * ray.direction[1] + toPoint[2] * ray.direction[2];
      // The residual perpendicular to the ray is zero: the point is ON the ray, not near it.
      const perpendicular = Math.hypot(
        toPoint[0] - along * ray.direction[0],
        toPoint[1] - along * ray.direction[1],
        toPoint[2] - along * ray.direction[2],
      );
      expect(perpendicular).toBeLessThan(1e-6);
      // ...and its eye-space depth is the 380 mm asked for, not its distance along the ray, which
      // is longer everywhere but the centre.
      const { forward } = cameraBasis(OBLIQUE);
      const depth = toPoint[0] * forward[0] + toPoint[1] * forward[1] + toPoint[2] * forward[2];
      expect(depth).toBeCloseTo(380, 6);
      if (x !== W / 2 || y !== H / 2) expect(along).toBeGreaterThan(depth);
    }
  });

  it("round-trips every world point through project -> unproject", () => {
    const points: Vec3[] = [
      [0, 0, 0],
      [64, 0, 0],
      [-33.5, 71.2, 37.5],
      [8, -140, 22],
      [-70, 60, -45],
    ];
    for (const camera of [FRONT, OBLIQUE]) {
      for (const world of points) {
        const projected = projectToCanvas(camera, world, W, H);
        if (!projected.inFront) continue;
        const back = unprojectDepth(camera, projected.x, projected.y, W, H, projected.depth);
        expect(distance(back, world)).toBeLessThan(1e-6);
      }
    }
  });

  it("recovers the ray/ellipsoid hit a region pick would land on", () => {
    // The geometry the expectation comes from: an ellipsoid the size of the gm fixture, solved
    // here as a quadratic. Whatever the renderer's depth buffer says, this is where the surface is.
    const radii: Vec3 = [64, 82, 70];
    const camera: OrbitCamera = { ...OBLIQUE, target: [0, 0, 0], distance: 300 };
    let checked = 0;
    for (const [x, y] of [
      [W / 2, H / 2],
      [W * 0.42, H * 0.38],
      [W * 0.58, H * 0.61],
    ]) {
      const ray = screenRay(camera, x as number, y as number, W, H);
      const o: Vec3 = [ray.origin[0] / radii[0], ray.origin[1] / radii[1], ray.origin[2] / radii[2]];
      const d: Vec3 = [ray.direction[0] / radii[0], ray.direction[1] / radii[1], ray.direction[2] / radii[2]];
      const a = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
      const b = 2 * (o[0] * d[0] + o[1] * d[1] + o[2] * d[2]);
      const c = o[0] * o[0] + o[1] * o[1] + o[2] * o[2] - 1;
      const disc = b * b - 4 * a * c;
      expect(disc).toBeGreaterThan(0);
      const t = (-b - Math.sqrt(disc)) / (2 * a);
      const hit: Vec3 = [
        ray.origin[0] + t * ray.direction[0],
        ray.origin[1] + t * ray.direction[1],
        ray.origin[2] + t * ray.direction[2],
      ];
      // The hit really is on the ellipsoid, to the last bit — the expectation is checked too.
      expect((hit[0] / radii[0]) ** 2 + (hit[1] / radii[1]) ** 2 + (hit[2] / radii[2]) ** 2).toBeCloseTo(1, 9);
      const projected = projectToCanvas(camera, hit, W, H);
      const back = unprojectDepth(camera, x as number, y as number, W, H, projected.depth);
      expect(distance(back, hit)).toBeLessThan(1e-6);
      checked += 1;
    }
    expect(checked).toBe(3);
  });

  it("survives the depth quantisation an 8-bit-per-channel pick buffer imposes", () => {
    // The renderer reads the depth back as four bytes (32-bit fixed point of the window depth), so
    // the pick's world point is only as good as that quantisation. At the distances a head is
    // viewed from, the error has to be far below a voxel — this is the number that says so.
    const camera: OrbitCamera = { ...OBLIQUE, target: [0, 0, 0], distance: 430 };
    const world: Vec3 = [-33.5, 71.2, 37.5];
    const projected = projectToCanvas(camera, world, W, H);
    const windowZ = projected.depth * 0.5 + 0.5;
    const quantised = Math.round(windowZ * 4294967295) / 4294967295;
    const back = unprojectDepth(camera, projected.x, projected.y, W, H, quantised * 2 - 1);
    expect(distance(back, world)).toBeLessThan(0.01);
  });
});
