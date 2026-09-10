/**
 * Orbit-camera maths — pure, DOM-free, GPU-free (plan `docs/dev/HISTORY.md § 2026-09-04 (scene service)`, S4).
 *
 * Everything the scene needs to turn "the user dragged 40 px right" into a matrix lives here, and
 * nothing here touches a canvas. That split is the whole reason the renderer is testable without a
 * GPU: a Playwright spec computes where a marker *should* land on screen with these functions and
 * then clicks there, so the colour-ID pick (GPU) and the projection (CPU) have to agree. A camera
 * folded into the WebGL class could only ever be checked against itself.
 *
 * ## Conventions, stated once
 *
 * - **World space is subject RAS, millimetres**: +X right, +Y anterior, +Z superior. That is what
 *   `GET /api/scene/*` promises (`space:"subject-ras"`, plan §2.1), so the camera speaks it too and
 *   nothing in the pipeline needs a swap matrix.
 * - **Matrices are column-major `Mat4`**, the order `gl.uniformMatrix4fv` wants with `transpose =
 *   false`; `m[col * 4 + row]`. A row-major copy uploaded verbatim renders a plausible-looking but
 *   wrong scene, which is why the convention is written down rather than inferred.
 * - **Screen coordinates are CSS pixels with y down**, the same space as `MouseEvent.offsetX/Y` and
 *   `page.mouse.click()`. Device-pixel-ratio scaling belongs to the GL viewport, not here.
 * - Angles are radians.
 */

export type Vec3 = [number, number, number];

/** Column-major 4x4. A tuple, not `Float32Array`, so a literal index is typed `number` under
 *  `noUncheckedIndexedAccess`, and still assignable to `number[]` for `uniformMatrix4fv`. */
export type Mat4 = [
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
];

/** `[x0, y0, z0, x1, y1, z1]` — the axis-aligned bounds the manifest reports (plan §2.1). */
export type Bounds = [number, number, number, number, number, number];

/**
 * The camera, as five numbers the UI can actually reason about.
 *
 * `yaw` is measured from the anterior axis (+Y) towards the subject's right (+X), so yaw 0 is the
 * face-on view and yaw +pi/2 looks in from the right ear. `pitch` is elevation above the axial
 * plane. Both stay unwrapped (never reduced mod 2pi): damping a wrapped angle makes the camera spin
 * the long way round when a drag crosses the seam.
 */
export interface OrbitCamera {
  /** World point the camera looks at. */
  target: Vec3;
  /** Eye-to-target distance, mm. */
  distance: number;
  /** Radians, from +Y towards +X. */
  yaw: number;
  /** Radians above the axial plane, clamped to +/-`PITCH_LIMIT`. */
  pitch: number;
  /** Vertical field of view, radians. */
  fovY: number;
}

/** Poles are excluded: at exactly +/-90 degrees the up vector is parallel to the view direction and
 *  `lookAt` divides by zero — the view flips to a garbage orientation for one frame. */
export const PITCH_LIMIT = Math.PI / 2 - 0.02;

/** Drag sensitivity, radians per CSS pixel. 0.008 puts a full turn at ~785 px, about one wide
 *  pane's width, which is the sensitivity a hand expects from a trackpad drag. */
export const ORBIT_RAD_PER_PX = 0.008;

/** Wheel/pinch sensitivity, natural-log units of distance per wheel pixel. */
export const ZOOM_PER_PX = 0.0015;

/** The world +Z axis is up on screen for every non-polar pitch. */
const WORLD_UP: Vec3 = [0, 0, 1];

const clamp = (v: number, lo: number, hi: number): number => (v < lo ? lo : v > hi ? hi : v);

/** `noUncheckedIndexedAccess` types every array read as `T | undefined`; a `Mat4` always has its
 *  16 entries, so the assertion lives here once instead of at sixty call sites. */
const m4 = (m: Mat4, i: number): number => m[i] as number;

export function normalize(v: Vec3): Vec3 {
  const len = Math.hypot(v[0], v[1], v[2]);
  return len === 0 ? [0, 0, 0] : [v[0] / len, v[1] / len, v[2] / len];
}

export function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

export function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/** Where the eye is, in world mm. */
export function cameraPosition(cam: OrbitCamera): Vec3 {
  const cp = Math.cos(cam.pitch);
  return [
    cam.target[0] + cam.distance * cp * Math.sin(cam.yaw),
    cam.target[1] + cam.distance * cp * Math.cos(cam.yaw),
    cam.target[2] + cam.distance * Math.sin(cam.pitch),
  ];
}

/** The orthonormal camera basis: `right`, `up`, `forward` (eye -> target), all unit length. */
export function cameraBasis(cam: OrbitCamera): { right: Vec3; up: Vec3; forward: Vec3; eye: Vec3 } {
  const eye = cameraPosition(cam);
  const forward = normalize([cam.target[0] - eye[0], cam.target[1] - eye[1], cam.target[2] - eye[2]]);
  const right = normalize(cross(forward, WORLD_UP));
  const up = cross(right, forward);
  return { right, up, forward, eye };
}

/** Standard `lookAt`, column-major. */
export function lookAt(eye: Vec3, target: Vec3, up: Vec3 = WORLD_UP): Mat4 {
  const f = normalize([target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]]);
  const s = normalize(cross(f, up));
  const u = cross(s, f);
  return [
    s[0], u[0], -f[0], 0,
    s[1], u[1], -f[1], 0,
    s[2], u[2], -f[2], 0,
    -dot(s, eye), -dot(u, eye), dot(f, eye), 1,
  ];
}

/** The view matrix of an orbit camera. */
export function viewMatrix(cam: OrbitCamera): Mat4 {
  return lookAt(cameraPosition(cam), cam.target, WORLD_UP);
}

export function perspective(fovY: number, aspect: number, near: number, far: number): Mat4 {
  const f = 1 / Math.tan(fovY / 2);
  const nf = 1 / (near - far);
  return [
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ];
}

/** `out = a * b`, column-major (apply `b` first, then `a`). */
export function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Array<number>(16).fill(0) as unknown as Mat4;
  for (let col = 0; col < 4; col += 1) {
    for (let row = 0; row < 4; row += 1) {
      let sum = 0;
      for (let k = 0; k < 4; k += 1) sum += m4(a, k * 4 + row) * m4(b, col * 4 + k);
      out[col * 4 + row] = sum;
    }
  }
  return out;
}

/**
 * Near and far planes derived from the orbit distance rather than fixed.
 *
 * A fixed `near = 0.1` on a head 180 mm across throws away most of the depth buffer's precision and
 * the two nested translucent shells z-fight; a fixed `far` clips the skin away as soon as the user
 * zooms out. Both scale with the distance, so the ratio (and therefore the precision) is constant
 * at every zoom level.
 */
export function depthRange(cam: OrbitCamera): { near: number; far: number } {
  return { near: Math.max(cam.distance * 0.01, 0.1), far: cam.distance * 10 + 1000 };
}

/** `projection * view` for a viewport of the given aspect ratio (width / height). */
export function viewProjection(cam: OrbitCamera, aspect: number): Mat4 {
  const { near, far } = depthRange(cam);
  return multiply(perspective(cam.fovY, aspect, near, far), viewMatrix(cam));
}

export interface Projected {
  /** CSS pixels from the canvas's left edge. */
  x: number;
  /** CSS pixels from the canvas's top edge (y grows downwards, like a mouse event). */
  y: number;
  /** Normalised device depth in [-1, 1]; smaller is nearer. */
  depth: number;
  /** False when the point is behind the eye, where the perspective divide has no meaning. */
  inFront: boolean;
}

/** World point -> canvas pixel. The e2e spec's click target. */
export function projectPoint(vp: Mat4, p: Vec3, widthCss: number, heightCss: number): Projected {
  const x = m4(vp, 0) * p[0] + m4(vp, 4) * p[1] + m4(vp, 8) * p[2] + m4(vp, 12);
  const y = m4(vp, 1) * p[0] + m4(vp, 5) * p[1] + m4(vp, 9) * p[2] + m4(vp, 13);
  const z = m4(vp, 2) * p[0] + m4(vp, 6) * p[1] + m4(vp, 10) * p[2] + m4(vp, 14);
  const w = m4(vp, 3) * p[0] + m4(vp, 7) * p[1] + m4(vp, 11) * p[2] + m4(vp, 15);
  if (w <= 0) return { x: NaN, y: NaN, depth: NaN, inFront: false };
  const ndcX = x / w;
  const ndcY = y / w;
  return {
    x: (ndcX * 0.5 + 0.5) * widthCss,
    y: (1 - (ndcY * 0.5 + 0.5)) * heightCss,
    depth: z / w,
    inFront: true,
  };
}

/** Convenience for callers that hold a camera and a canvas size rather than a matrix. */
export function projectToCanvas(cam: OrbitCamera, p: Vec3, widthCss: number, heightCss: number): Projected {
  return projectPoint(viewProjection(cam, widthCss / heightCss), p, widthCss, heightCss);
}

export interface Ray {
  origin: Vec3;
  /** Unit length. */
  direction: Vec3;
}

/**
 * Canvas pixel -> world ray, built from the camera basis rather than by inverting the
 * view-projection. Inverting a near-singular matrix is where a picking ray quietly goes wrong at
 * extreme zoom; the basis is exact at every distance and needs no inverse at all.
 */
export function screenRay(cam: OrbitCamera, xCss: number, yCss: number, widthCss: number, heightCss: number): Ray {
  const { right, up, forward, eye } = cameraBasis(cam);
  const aspect = widthCss / heightCss;
  const tanY = Math.tan(cam.fovY / 2);
  const ndcX = (2 * xCss) / widthCss - 1;
  const ndcY = 1 - (2 * yCss) / heightCss;
  const dx = ndcX * tanY * aspect;
  const dy = ndcY * tanY;
  return {
    origin: eye,
    direction: normalize([
      right[0] * dx + up[0] * dy + forward[0],
      right[1] * dx + up[1] * dy + forward[1],
      right[2] * dx + up[2] * dy + forward[2],
    ]),
  };
}

/**
 * Normalised device depth -> how far in front of the eye that fragment is, in mm.
 *
 * The inverse of the projection's z row. `perspective` writes `m10 = (far + near) / (near - far)`
 * and `m14 = 2 * far * near / (near - far)` with `w_clip = -z_eye`, so
 * `ndc = -(m10 * z_eye + m14) / z_eye` and therefore `-z_eye = m14 / (ndc + m10)`. Inverting the
 * whole 4x4 would give the same answer with none of that legible.
 *
 * This is what turns "the pick pass says the winning fragment is at depth z" into "the cortex is
 * 312.4 mm in front of the eye there", which is the first half of answering *where* a user clicked.
 */
export function viewDepthFromNdc(cam: OrbitCamera, ndcDepth: number): number {
  const { near, far } = depthRange(cam);
  const nf = 1 / (near - far);
  const m10 = (far + near) * nf;
  const m14 = 2 * far * near * nf;
  const denominator = ndcDepth + m10;
  if (denominator === 0) return Infinity;
  return m14 / denominator;
}

/**
 * Canvas pixel + the depth rasterised there -> the world point under the cursor.
 *
 * The point is on `screenRay`'s ray by construction, at the distance that puts its *eye-space
 * depth* (not its distance from the eye — those differ everywhere but the centre pixel) at what the
 * depth buffer says. That is the whole "click anywhere on the cortex and put the sphere centre
 * there" gesture, and it is pure: the renderer supplies one number, the depth.
 */
export function unprojectDepth(
  cam: OrbitCamera,
  xCss: number,
  yCss: number,
  widthCss: number,
  heightCss: number,
  ndcDepth: number,
): Vec3 {
  const ray = screenRay(cam, xCss, yCss, widthCss, heightCss);
  const { forward } = cameraBasis(cam);
  const cosine = dot(ray.direction, forward);
  const t = viewDepthFromNdc(cam, ndcDepth) / (cosine === 0 ? 1 : cosine);
  return [
    ray.origin[0] + ray.direction[0] * t,
    ray.origin[1] + ray.direction[1] * t,
    ray.origin[2] + ray.direction[2] * t,
  ];
}

// ---------------------------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------------------------

/** Drag-to-orbit. Dragging right turns the subject's right towards the viewer. */
export function orbitBy(cam: OrbitCamera, dxPx: number, dyPx: number): OrbitCamera {
  return {
    ...cam,
    yaw: cam.yaw + dxPx * ORBIT_RAD_PER_PX,
    pitch: clamp(cam.pitch + dyPx * ORBIT_RAD_PER_PX, -PITCH_LIMIT, PITCH_LIMIT),
  };
}

/**
 * Wheel-to-zoom, exponential so that one notch changes the view by the same *proportion* at every
 * distance — a linear step either crawls when zoomed out or slams into the target when zoomed in.
 * Bounds come from the scene radius so the user can neither end up inside a vertex nor lose the
 * head to a dot.
 */
export function zoomBy(cam: OrbitCamera, deltaPx: number, radius: number): OrbitCamera {
  const next = cam.distance * Math.exp(deltaPx * ZOOM_PER_PX);
  return { ...cam, distance: clamp(next, radius * 0.25, radius * 20) };
}

/** Drag-to-pan: the target slides in the camera's own screen plane, so the point under the cursor
 *  stays under the cursor (to first order) whatever the current orientation. */
export function panBy(cam: OrbitCamera, dxPx: number, dyPx: number, heightCss: number): OrbitCamera {
  const { right, up } = cameraBasis(cam);
  const worldPerPx = (2 * cam.distance * Math.tan(cam.fovY / 2)) / heightCss;
  const sx = -dxPx * worldPerPx;
  const sy = dyPx * worldPerPx;
  return {
    ...cam,
    target: [
      cam.target[0] + right[0] * sx + up[0] * sy,
      cam.target[1] + right[1] * sx + up[1] * sy,
      cam.target[2] + right[2] * sx + up[2] * sy,
    ],
  };
}

// ---------------------------------------------------------------------------------------------
// Framing and presets
// ---------------------------------------------------------------------------------------------

export function boundsCentre(b: Bounds): Vec3 {
  return [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
}

/** Radius of the sphere that encloses the bounds. */
export function boundsRadius(b: Bounds): number {
  return 0.5 * Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]);
}

/** Yaw and pitch, the two angles a fit depends on: framing is orientation-dependent, because a
 *  head 228 mm deep and 168 mm wide needs a different distance from the side than from the front. */
export interface ViewAngles {
  yaw: number;
  pitch: number;
}

/**
 * How much of the constraining pane dimension the framed geometry spans — the gutter, stated as a
 * number rather than as a magic multiplier.
 *
 * 0.94 leaves 3 % of the frame on each side, which is enough that the silhouette does not touch the
 * edge and little enough that the head is the pane's subject. The previous rule — fit the sphere
 * that encloses the bounding *box*, then add 8 % — spent the difference between a head and the
 * sphere around its box on empty space: measured on sub-ernie's served surfaces, the head spanned
 * 0.48 of a 348 x 544 pane and 0.59 of a 1192 x 544 one (`tests/unit/scene-framing.test.ts`).
 */
export const FIT_FILL = 0.94;

/** The eye must stay outside the near plane's slab: `depthRange` puts near at 1 % of the distance,
 *  so the frontmost point has to sit beyond that or the fit hands back a view with the nose sliced
 *  off. The 0.98 (rather than 0.99) is one per cent of headroom on the same rule. */
const NEAR_CLEARANCE = 0.98;

/**
 * The exact framing distance for a set of world points: the smallest distance at which every one of
 * them projects inside `fill` of the frame, in both axes.
 *
 * It is closed form, not a search. For a point at camera-space offset `(u, v, w)` from the target
 * (right, up, forward), the eye sits `d` behind the target, so the point's depth is `d + w` and it
 * lands at `u / ((d + w) * tan(halfX))` of the half-frame. Requiring that to be at most `fill`
 * gives `d >= |u| / (tan(halfX) * fill) - w`, and the same for `v`; the fit is the maximum over
 * every point and both axes.
 *
 * Points, not a bounding box, because the box of a head is much bigger than the head: its corners
 * are empty air, and framing them is how a 230 px head ends up in a 544 px pane. The pass is linear
 * in the vertex count (~110 k for a real subject, under a millisecond) and runs only when the
 * geometry, the preset or the pane size changes — never per frame.
 */
export function fitDistanceToPoints(
  sets: ReadonlyArray<ArrayLike<number>>,
  target: Vec3,
  fovY: number,
  aspect: number,
  angles: ViewAngles,
  fill: number = FIT_FILL,
): number {
  const { right, up, forward } = cameraBasis({ target, distance: 1, fovY, ...angles });
  const halfY = fovY / 2;
  const halfX = Math.atan(Math.tan(halfY) * aspect);
  const tx = Math.tan(halfX) * fill;
  const ty = Math.tan(halfY) * fill;
  let distance = 0;
  let frontmost = 0;
  let seen = 0;
  for (const set of sets) {
    for (let i = 0; i + 2 < set.length; i += 3) {
      const dx = (set[i] as number) - target[0];
      const dy = (set[i + 1] as number) - target[1];
      const dz = (set[i + 2] as number) - target[2];
      const w = dx * forward[0] + dy * forward[1] + dz * forward[2];
      const u = Math.abs(dx * right[0] + dy * right[1] + dz * right[2]);
      const v = Math.abs(dx * up[0] + dy * up[1] + dz * up[2]);
      const need = Math.max(u / tx, v / ty) - w;
      if (need > distance) distance = need;
      if (-w > frontmost) frontmost = -w;
      seen += 1;
    }
  }
  if (seen === 0) return 0;
  return Math.max(distance, frontmost / NEAR_CLEARANCE);
}

/** The eight corners of a bounding box, as one flat `x, y, z` array. */
function boundsCorners(b: Bounds): Float64Array {
  const corners = new Float64Array(24);
  for (let mask = 0; mask < 8; mask += 1) {
    corners[mask * 3] = mask & 1 ? b[3] : b[0];
    corners[mask * 3 + 1] = mask & 2 ? b[4] : b[1];
    corners[mask * 3 + 2] = mask & 4 ? b[5] : b[2];
  }
  return corners;
}

/** The same fit over the eight corners of a bounding box — the fallback for a caller that has
 *  bounds but no positions (an empty pane, or a manifest that arrived before its geometry). */
export function fitDistance(
  b: Bounds,
  fovY: number,
  aspect: number,
  angles: ViewAngles,
  fill: number = FIT_FILL,
): number {
  return fitDistanceToPoints([boundsCorners(b)], boundsCentre(b), fovY, aspect, angles, fill);
}

export type CameraPreset = "front" | "left" | "right" | "top" | "reset";

/**
 * Yaw/pitch of each preset. `reset` is a three-quarter view from the left-anterior-superior
 * octant — the angle at which both hemispheres and the vertex are visible at once, which is what a
 * user placing electrodes needs to see first.
 *
 * `top`'s yaw is `pi`, not 0, and the difference is the whole orientation of the frame. At a pitch
 * of ~90 degrees the yaw no longer chooses a side of the head, only how the head is *rotated* on
 * screen: it decides which way the nose points. With yaw 0 the eye sits a degree anterior of the
 * vertex, `up` collapses onto -Y, and the axial view comes out with the nose at the BOTTOM —
 * measured on ernie's 10-20 net at 400x320: Fp1/Fp2 at y = 289 and O1/O2 at y = 38-39, upside down
 * against every convention a neuroimaging user has. With yaw `pi` the eye sits a degree posterior,
 * `up` is +Y and `right` is +X: nose at the top, subject's left on the viewer's left. The other
 * three are unambiguous — the eye is on the side the preset is named after.
 */
export const PRESET_ANGLES: Record<CameraPreset, { yaw: number; pitch: number }> = {
  front: { yaw: 0, pitch: 0 },
  left: { yaw: -Math.PI / 2, pitch: 0 },
  right: { yaw: Math.PI / 2, pitch: 0 },
  top: { yaw: Math.PI, pitch: PITCH_LIMIT },
  reset: { yaw: -0.62, pitch: 0.3 },
};

// ---------------------------------------------------------------------------------------------
// Which way round the subject is on screen
// ---------------------------------------------------------------------------------------------

/** A direction in the subject's own RAS frame. */
export type AnatomicalAxis = "left" | "right" | "anterior" | "posterior" | "superior" | "inferior";

/** What each screen axis points along, anatomically. */
export interface ScreenAnatomy {
  /** The anatomical direction that grows towards the RIGHT of the screen. */
  right: AnatomicalAxis;
  /** ...towards the TOP of the screen. */
  up: AnatomicalAxis;
  /** The side of the head facing the viewer — the direction from the target towards the eye. */
  toward: AnatomicalAxis;
}

/** `[negative, positive]` name of each RAS axis. */
const AXIS_NAMES: ReadonlyArray<readonly [AnatomicalAxis, AnatomicalAxis]> = [
  ["left", "right"],
  ["posterior", "anterior"],
  ["inferior", "superior"],
];

/** The anatomical direction a world vector mostly points along. Ties (a perfect 45-degree view)
 *  break towards the earlier axis, deterministically, so the label never flickers. */
export function dominantAxis(v: Vec3): AnatomicalAxis {
  let best = 0;
  for (let i = 1; i < 3; i += 1) if (Math.abs(v[i] as number) > Math.abs(v[best] as number)) best = i;
  const pair = AXIS_NAMES[best] as readonly [AnatomicalAxis, AnatomicalAxis];
  return (v[best] as number) >= 0 ? pair[1] : pair[0];
}

/**
 * Which way round the subject is on screen, for THIS camera.
 *
 * It exists because a 3-D head view has no universal convention and the two plausible ones are
 * mirror images: from the front you are facing the subject, so their left hand is on your right
 * (this renderer, and every "look at the face" view); from above, looking down, their left is on
 * your left. The maintainer's own report on 2026-09-04 was *"the electrode positions look wrong"*,
 * and half of answering it is being able to say, in a test, which convention the projection uses.
 *
 * Derived from `cameraBasis`, the same function the view matrix comes from, so what this reports
 * cannot drift from the projection: change one and the other follows.
 */
export function screenAnatomy(cam: OrbitCamera): ScreenAnatomy {
  const { right, up, forward } = cameraBasis(cam);
  return {
    right: dominantAxis(right),
    up: dominantAxis(up),
    toward: dominantAxis([-forward[0], -forward[1], -forward[2]]),
  };
}

export const DEFAULT_FOV_Y = (35 * Math.PI) / 180;

/**
 * A whole camera for a preset, framed on the geometry. Re-framing (rather than keeping the current
 * distance) is deliberate: a preset is "show me the head from the left", not "spin in place".
 *
 * `points` are the world positions the pane is drawing (each a flat `x, y, z` array — the parts'
 * `positions`, plus any markers). Given them, the fit is the exact one and the head fills the pane;
 * without them it falls back to the bounding box's corners, which is all an empty pane has.
 */
export function presetCamera(
  preset: CameraPreset,
  bounds: Bounds,
  aspect: number,
  fovY: number = DEFAULT_FOV_Y,
  points?: ReadonlyArray<ArrayLike<number>>,
): OrbitCamera {
  const angles = PRESET_ANGLES[preset];
  const target = boundsCentre(bounds);
  return {
    target,
    distance: frameDistance(bounds, target, fovY, aspect, angles, points),
    yaw: angles.yaw,
    pitch: angles.pitch,
    fovY,
  };
}

/**
 * The framing distance for arbitrary angles — what a re-frame after a pane resize uses, where the
 * user's own yaw and pitch have to be kept and only the distance recomputed.
 *
 * Falls back to the bounding box whenever the point sets are empty or produce a distance that is
 * not a usable positive number (a single degenerate point, a NaN in the geometry): a camera at
 * distance 0 makes `log(distance)` in the damping step -Infinity and the pane never renders again.
 */
export function frameDistance(
  bounds: Bounds,
  target: Vec3,
  fovY: number,
  aspect: number,
  angles: ViewAngles,
  points?: ReadonlyArray<ArrayLike<number>>,
): number {
  if (points && points.length > 0) {
    const fitted = fitDistanceToPoints(points, target, fovY, aspect, angles);
    if (Number.isFinite(fitted) && fitted > 0) return fitted;
  }
  // The box, framed around the SAME target the camera is looking at — not around the box's own
  // centre, which is a different view as soon as the user has panned.
  const corners = fitDistanceToPoints([boundsCorners(bounds)], target, fovY, aspect, angles);
  if (Number.isFinite(corners) && corners > 0) return corners;
  // Degenerate bounds (a single point, a NaN): anything positive beats a distance of 0, whose
  // log is -Infinity the first time the damping step touches it.
  return boundsRadius(bounds) * 3 + 1;
}

// ---------------------------------------------------------------------------------------------
// Damping
// ---------------------------------------------------------------------------------------------

/** Higher is snappier. 18 /s settles a drag in ~200 ms, fast enough not to feel laggy and slow
 *  enough to hide the 8 ms jitter of a wheel event stream. */
export const DAMPING_LAMBDA = 18;

export interface DampResult {
  camera: OrbitCamera;
  /** True once the camera has been snapped exactly onto the goal, so a caller can stop the rAF
   *  loop — and so a test can wait for "the view has stopped moving" rather than sleeping. */
  settled: boolean;
}

/**
 * One damping step towards `goal`, frame-rate independent: the blend factor is `1 - exp(-lambda *
 * dt)`, so the camera follows the same curve at 30 fps and at 120 fps. A plain `lerp(cur, goal, k)`
 * with a constant `k` moves twice as fast on a 120 Hz display, which is how a "smooth" camera ends
 * up feeling different on every machine.
 *
 * Distance is interpolated in log space for the same reason `zoomBy` is exponential.
 */
export function dampCamera(current: OrbitCamera, goal: OrbitCamera, dtMs: number, lambda = DAMPING_LAMBDA): DampResult {
  const k = 1 - Math.exp((-lambda * Math.max(dtMs, 0)) / 1000);
  const yaw = current.yaw + (goal.yaw - current.yaw) * k;
  const pitch = current.pitch + (goal.pitch - current.pitch) * k;
  const distance = Math.exp(Math.log(current.distance) + (Math.log(goal.distance) - Math.log(current.distance)) * k);
  const target: Vec3 = [
    current.target[0] + (goal.target[0] - current.target[0]) * k,
    current.target[1] + (goal.target[1] - current.target[1]) * k,
    current.target[2] + (goal.target[2] - current.target[2]) * k,
  ];
  const done =
    Math.abs(goal.yaw - yaw) < 1e-4 &&
    Math.abs(goal.pitch - pitch) < 1e-4 &&
    Math.abs(Math.log(goal.distance / distance)) < 1e-4 &&
    Math.hypot(goal.target[0] - target[0], goal.target[1] - target[1], goal.target[2] - target[2]) < 1e-3;
  if (done) return { camera: { ...goal }, settled: true };
  return { camera: { target, distance, yaw, pitch, fovY: goal.fovY }, settled: false };
}

// ---------------------------------------------------------------------------------------------
// When a re-frame is honest
// ---------------------------------------------------------------------------------------------

/** The subset of a scene part this signature reads. */
export interface FramingPart {
  id: string;
  positions: ArrayLike<number>;
}

/**
 * A string that changes only when the framing GEOMETRY changes — a different guide or subject, a
 * surface appearing or disappearing — and stays identical across everything else a pane does while
 * a user is working in it: a new EEG net, a montage pair being edited, an electrode toggled, an
 * atlas swapped onto the same cortex, an opacity slider.
 *
 * Framing is re-run on this key rather than on the point arrays themselves because those arrays are
 * rebuilt (new identities, same silhouette) whenever the marker set changes, and re-framing there
 * is the pane snapping back to the default view under a user who had just orbited it
 * (`tests/unit/scene-framing-stability.test.ts`).
 *
 * Markers are deliberately absent: they are framed on at first load, and moving them never re-frames.
 */
export function framingSignature(bounds: Bounds, parts: ReadonlyArray<FramingPart>): string {
  const box = bounds.map((v) => (Number.isFinite(v) ? v.toFixed(3) : "x")).join(",");
  const geometry = parts.map((part) => {
    const n = part.positions.length;
    // Length plus the two extreme vertices: two different heads with identical vertex counts still
    // differ here, and no in-place recolouring of the same surface does.
    const head = n >= 3 ? `${part.positions[0]},${part.positions[1]},${part.positions[2]}` : "";
    const tail = n >= 3 ? `${part.positions[n - 3]},${part.positions[n - 2]},${part.positions[n - 1]}` : "";
    return `${part.id}:${n}:${head}:${tail}`;
  });
  return `${box}|${geometry.join("|")}`;
}
