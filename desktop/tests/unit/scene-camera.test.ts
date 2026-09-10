/**
 * `scene/camera.ts` — every expected value below is derived from the geometry by hand, in the test,
 * because this module is what a Playwright spec uses to decide *where to click*. A camera checked
 * only against its own renderer would agree with itself while both were wrong, and the pick test
 * built on it would still pass.
 *
 * The worked case throughout is a front (anterior) view with `fovY = pi/2`, so `tan(fovY/2) = 1`
 * and the projection arithmetic is exact rather than approximate.
 */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_FOV_Y,
  PITCH_LIMIT,
  boundsCentre,
  boundsRadius,
  cameraBasis,
  cameraPosition,
  dampCamera,
  FIT_FILL,
  fitDistance,
  fitDistanceToPoints,
  orbitBy,
  panBy,
  presetCamera,
  projectPoint,
  projectToCanvas,
  screenRay,
  viewMatrix,
  viewProjection,
  zoomBy,
  type Bounds,
  type OrbitCamera,
} from "../../src/renderer/scene/camera";

/** Distance 100 mm in front of the origin, 90-degree vertical field, so tan(fovY/2) = 1. */
const FRONT: OrbitCamera = { target: [0, 0, 0], distance: 100, yaw: 0, pitch: 0, fovY: Math.PI / 2 };

describe("cameraPosition", () => {
  it("puts yaw 0 on the anterior axis and yaw +90 degrees on the subject's right", () => {
    // World is RAS: +Y anterior, +X right. Yaw is measured from +Y towards +X.
    expect(cameraPosition(FRONT)).toEqual([0, 100, 0]);
    const right = cameraPosition({ ...FRONT, yaw: Math.PI / 2 });
    expect(right[0]).toBeCloseTo(100, 10);
    expect(right[1]).toBeCloseTo(0, 10);
    const left = cameraPosition({ ...FRONT, yaw: -Math.PI / 2 });
    expect(left[0]).toBeCloseTo(-100, 10);
  });

  it("puts pitch +90 degrees straight above the target", () => {
    const top = cameraPosition({ ...FRONT, pitch: Math.PI / 2 });
    expect(top[2]).toBeCloseTo(100, 10);
    expect(Math.hypot(top[0], top[1])).toBeCloseTo(0, 10);
  });

  it("orbits about the target, not the origin", () => {
    expect(cameraPosition({ ...FRONT, target: [10, -20, 30] })).toEqual([10, 80, 30]);
  });
});

describe("cameraBasis", () => {
  it("puts the subject's right on the viewer's left in a face-on view", () => {
    // Looking at a face from in front, their right hand is on your left. Anything else would put
    // the pane in radiological convention while the rest of the toolbox is not.
    const { right, up, forward } = cameraBasis(FRONT);
    expect(right[0]).toBeCloseTo(-1, 12);
    expect(up[2]).toBeCloseTo(1, 12);
    expect(forward[1]).toBeCloseTo(-1, 12);
  });
});

describe("viewMatrix", () => {
  it("maps the target onto the view axis at -distance", () => {
    const view = viewMatrix(FRONT);
    // Column-major: the translation column is m[12..14], which is where the origin lands.
    expect(view[12]).toBeCloseTo(0, 12);
    expect(view[13]).toBeCloseTo(0, 12);
    expect(view[14]).toBeCloseTo(-100, 12);
  });
});

describe("projectPoint", () => {
  const W = 800;
  const H = 400; // aspect 2

  it("puts the target at the centre of the canvas", () => {
    const projected = projectToCanvas(FRONT, [0, 0, 0], W, H);
    expect(projected.x).toBeCloseTo(W / 2, 9);
    expect(projected.y).toBeCloseTo(H / 2, 9);
    expect(projected.inFront).toBe(true);
  });

  it("projects a 10 mm lateral offset to the pixel the perspective divide predicts", () => {
    // Derived by hand: view-space x = dot(right, p - eye) = -10 (right is -X here); w = 100;
    // clip.x = (1/tan(fovY/2) / aspect) * x_view = 0.5 * -10 = -5; ndc = -0.05;
    // screen = (1 - 0.05) / 2 * 800 = 380.
    const projected = projectToCanvas(FRONT, [10, 0, 0], W, H);
    expect(projected.x).toBeCloseTo(380, 6);
    expect(projected.y).toBeCloseTo(200, 6);
  });

  it("projects a vertical offset with the aspect ratio applied only horizontally", () => {
    // z is up on screen; clip.y = 1 * 10 = 10, w = 100, ndc = 0.1, screen y = (1 - 0.1)/2 * 400
    // = 180 (y grows downwards).
    const projected = projectToCanvas(FRONT, [0, 0, 10], W, H);
    expect(projected.y).toBeCloseTo(180, 6);
    expect(projected.x).toBeCloseTo(400, 6);
  });

  it("reports a point behind the eye rather than folding it back onto the canvas", () => {
    // 200 mm anterior of the target is 100 mm BEHIND a camera sitting at y = 100.
    const behind = projectToCanvas(FRONT, [0, 200, 0], W, H);
    expect(behind.inFront).toBe(false);
    expect(Number.isNaN(behind.x)).toBe(true);
  });

  it("agrees with the matrix path", () => {
    const vp = viewProjection(FRONT, W / H);
    expect(projectPoint(vp, [10, 0, 0], W, H).x).toBeCloseTo(380, 6);
  });
});

describe("screenRay", () => {
  it("shoots the view direction through the centre of the canvas", () => {
    const ray = screenRay(FRONT, 400, 200, 800, 400);
    expect(ray.origin).toEqual([0, 100, 0]);
    expect(ray.direction[1]).toBeCloseTo(-1, 12);
  });

  it("round-trips a projected point: the ray through its pixel passes through it", () => {
    const point: [number, number, number] = [23, -14, 37];
    const projected = projectToCanvas(FRONT, point, 800, 400);
    const ray = screenRay(FRONT, projected.x, projected.y, 800, 400);
    const eye = cameraPosition(FRONT);
    const toPoint = [point[0] - eye[0], point[1] - eye[1], point[2] - eye[2]];
    const length = Math.hypot(toPoint[0] as number, toPoint[1] as number, toPoint[2] as number);
    for (let i = 0; i < 3; i += 1) {
      expect(ray.direction[i] as number).toBeCloseTo((toPoint[i] as number) / length, 9);
    }
  });
});

describe("framing", () => {
  const cube: Bounds = [-50, -50, -50, 50, 50, 50];

  it("takes the centre and the enclosing sphere of the bounds", () => {
    expect(boundsCentre([0, 10, 20, 10, 30, 20])).toEqual([5, 20, 20]);
    expect(boundsRadius(cube)).toBeCloseTo(0.5 * Math.sqrt(3 * 100 * 100), 9);
  });

  it("fits the bounding box's own corners, at the fill the constant states", () => {
    // Front view of the cube, 90-degree field, so tan(halfY) = 1 and every number is exact.
    // The constraining corner is the NEAR one on the constraining axis: it is 50 mm across the view
    // axis and 50 mm towards the eye, so d = 50 / (tan(halfX) * FIT_FILL) + 50.
    const front = { yaw: 0, pitch: 0 };
    expect(fitDistance(cube, Math.PI / 2, 1, front)).toBeCloseTo(50 / FIT_FILL + 50, 9);
    // A wide viewport must not use the wider horizontal angle, or the head is cropped top and
    // bottom: the vertical half-angle still decides, so the answer does not change.
    expect(fitDistance(cube, Math.PI / 2, 3, front)).toBeCloseTo(50 / FIT_FILL + 50, 9);
    // A tall viewport is the mirror image: the horizontal half-angle is now the narrow one, and
    // tan(halfX) = tan(45 deg) * 0.5 = 0.5.
    expect(fitDistance(cube, Math.PI / 2, 0.5, front)).toBeCloseTo(50 / (0.5 * FIT_FILL) + 50, 9);
    // A sphere's radius is not what is framed any more — framing the sphere around this box would
    // stand 1.5x further back and spend the difference on empty space.
    expect(fitDistance(cube, Math.PI / 2, 1, front)).toBeLessThan((boundsRadius(cube) / Math.SQRT1_2) * 1.08);
  });

  it("frames the points it is given, not the box around them", () => {
    // A ball of radius 50 inside the same cube: its corners are empty air, so the fit is closer.
    const ball: number[] = [];
    for (let i = 0; i <= 24; i += 1) {
      const theta = (Math.PI * i) / 24;
      for (let j = 0; j < 48; j += 1) {
        const phi = (2 * Math.PI * j) / 48;
        ball.push(50 * Math.sin(theta) * Math.cos(phi), 50 * Math.sin(theta) * Math.sin(phi), 50 * Math.cos(theta));
      }
    }
    const front = { yaw: 0, pitch: 0 };
    const fitted = fitDistanceToPoints([Float64Array.from(ball)], [0, 0, 0], Math.PI / 2, 1, front);
    // Closed form for a ball: the constraining point is not the equator but the one tilted towards
    // the eye, and maximising (r sin t)/tanHalf + r cos t over t gives r * sqrt(1 + tanHalf^2) /
    // tanHalf — which is the same thing as r / sin(atan(tanHalf)), the classic sphere fit taken at
    // the reduced half-angle. The grid samples it to within 0.05 %.
    const tanHalf = Math.tan(Math.PI / 4) * FIT_FILL;
    const exact = (50 * Math.sqrt(1 + tanHalf * tanHalf)) / tanHalf;
    expect(Math.abs(fitted - exact) / exact).toBeLessThan(0.002);
    expect(fitted).toBeLessThan(fitDistance(cube, Math.PI / 2, 1, front));
  });

  it("keeps the frontmost point clear of the near plane", () => {
    // A flat wall facing the camera: nothing constrains the fit laterally, so the only thing left
    // to stop the camera from standing inside it is the near-plane rule.
    const wall = Float64Array.from([-1, 60, -1, 1, 60, -1, -1, 60, 1, 1, 60, 1]);
    const distance = fitDistanceToPoints([wall], [0, 0, 0], Math.PI / 2, 1, { yaw: 0, pitch: 0 });
    expect(distance).toBeGreaterThan(60);
    // depthRange puts the near plane at 1 % of the distance; the wall is 60 mm in front of the
    // target, i.e. `distance - 60` in front of the eye, and that has to clear it.
    expect(distance - 60).toBeGreaterThan(distance * 0.01);
  });

  it("gives each preset the axis its name says", () => {
    const front = presetCamera("front", cube, 1);
    expect(cameraPosition(front)[1]).toBeGreaterThan(0); // anterior
    expect(cameraPosition(presetCamera("left", cube, 1))[0]).toBeLessThan(0);
    expect(cameraPosition(presetCamera("right", cube, 1))[0]).toBeGreaterThan(0);
    expect(cameraPosition(presetCamera("top", cube, 1))[2]).toBeGreaterThan(0);
    expect(front.fovY).toBe(DEFAULT_FOV_Y);
    // Reset is a three-quarter view, so neither of the two lateral axes is zero.
    const reset = presetCamera("reset", cube, 1);
    expect(Math.abs(reset.yaw)).toBeGreaterThan(0.1);
    expect(reset.pitch).toBeGreaterThan(0.1);
  });
});

describe("interaction", () => {
  it("orbits by a fixed number of radians per pixel and clamps the pole", () => {
    const orbited = orbitBy(FRONT, 100, 0);
    expect(orbited.yaw).toBeCloseTo(0.8, 12); // 100 px * 0.008 rad/px
    // Straight up is excluded: at exactly 90 degrees the up vector is parallel to the view
    // direction and lookAt divides by zero.
    expect(orbitBy(FRONT, 0, 10_000).pitch).toBe(PITCH_LIMIT);
    expect(orbitBy(FRONT, 0, -10_000).pitch).toBe(-PITCH_LIMIT);
  });

  it("zooms by a constant proportion, so one notch feels the same at every distance", () => {
    const inOnce = zoomBy(FRONT, -100, 100);
    expect(inOnce.distance).toBeCloseTo(100 * Math.exp(-0.15), 9);
    // Out and back in is the identity, which a linear step would not be.
    expect(zoomBy(zoomBy(FRONT, 200, 100), -200, 100).distance).toBeCloseTo(100, 9);
  });

  it("clamps zoom to a quarter and twenty times the scene radius", () => {
    expect(zoomBy(FRONT, -100_000, 80).distance).toBe(20);
    expect(zoomBy(FRONT, 100_000, 80).distance).toBe(1600);
  });

  it("pans the target in the camera's screen plane, by the world size of a pixel", () => {
    // worldPerPx = 2 * d * tan(fovY/2) / heightPx = 2 * 100 * 1 / 400 = 0.5 mm.
    // Dragging 40 px right moves the target 20 mm along -right, and right is -X in a front view,
    // so the target moves +20 in X.
    const panned = panBy(FRONT, 40, 0, 400);
    expect(panned.target[0]).toBeCloseTo(20, 9);
    expect(panned.target[1]).toBeCloseTo(0, 9);
    // Dragging down moves the target down: up is +Z here.
    expect(panBy(FRONT, 0, 40, 400).target[2]).toBeCloseTo(20, 9);
  });
});

describe("dampCamera", () => {
  const goal: OrbitCamera = { target: [0, 0, 0], distance: 400, yaw: 1, pitch: 0, fovY: Math.PI / 2 };
  const start: OrbitCamera = { target: [0, 0, 0], distance: 100, yaw: 0, pitch: 0, fovY: Math.PI / 2 };
  /** lambda * dt = ln 2, so the blend factor 1 - exp(-lambda dt) is exactly 1/2. */
  const HALF_MS = (1000 * Math.LN2) / 18;

  it("moves exactly halfway when the step is one half-life", () => {
    const { camera, settled } = dampCamera(start, goal, HALF_MS);
    expect(settled).toBe(false);
    expect(camera.yaw).toBeCloseTo(0.5, 9);
    // Distance is interpolated in log space, so half a step is the geometric mean, not the
    // arithmetic one: sqrt(100 * 400) = 200, where a linear lerp would give 250.
    expect(camera.distance).toBeCloseTo(200, 6);
  });

  it("is frame-rate independent: two 8 ms steps land where one 16 ms step does", () => {
    const twice = dampCamera(dampCamera(start, goal, 8).camera, goal, 8).camera;
    const once = dampCamera(start, goal, 16).camera;
    expect(twice.yaw).toBeCloseTo(once.yaw, 12);
    expect(twice.distance).toBeCloseTo(once.distance, 9);
  });

  it("snaps onto the goal and reports settled once the residual is below the threshold", () => {
    const { camera, settled } = dampCamera(start, goal, 10_000);
    expect(settled).toBe(true);
    expect(camera).toEqual(goal);
  });

  it("reports settled immediately when it is already there", () => {
    expect(dampCamera(goal, goal, 16).settled).toBe(true);
  });
});
