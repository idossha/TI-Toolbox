/**
 * Framing: how much of the pane the head actually occupies when the scene first appears
 * (lane FIX-A, defect 3 — reported by lane SCC, `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §6.4:
 * "at 1192 x 544 the whole head occupies ~230 px of the 544 px height").
 *
 * Every number here is measured, not judged. For each pane size and camera preset the test builds
 * the camera the component would build, projects the geometry with `projectToCanvas` and asks two
 * questions of the resulting pixels:
 *
 *   1. **is anything cut off?** — every projected point must be inside the canvas, and in front of
 *      the eye. A framing that fills the pane by cropping the scalp is not a fix.
 *   2. **how much of the pane does the geometry span?** — `max(extentX / width, extentY / height)`,
 *      i.e. how close the silhouette comes to touching the frame along whichever axis constrains
 *      it. This is the number SCC measured at 0.42; the floor asserted below is 0.85.
 *
 * The geometry is the real thing, not a stand-in: `tests/fixtures/scene/ernie-support-points.json`
 * holds the extreme vertices of sub-ernie's *served* skin and grey-matter surfaces (its provenance
 * and its 1.12 mm support-function error are recorded in the file). The projected extent of a point
 * set is decided entirely by its support function, so those 422 points frame exactly as the 109 538
 * they were reduced from. A synthetic ellipsoid is checked alongside them, because for an ellipsoid
 * every expected value is closed form.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_FOV_Y,
  PRESET_ANGLES,
  boundsCentre,
  presetCamera,
  projectToCanvas,
  type Bounds,
  type CameraPreset,
  type Vec3,
} from "../../src/renderer/scene/camera";

/** The fraction of the constraining pane dimension the geometry must span. 0.85 leaves room for
 *  the fit's own gutter (`FIT_FILL`) and for the perspective asymmetry of an off-centre head, and
 *  is still twice what the enclosing-sphere fit managed (0.41-0.59, measured below). */
const MIN_FILL = 0.85;

const FIXTURE = fileURLToPath(new URL("../fixtures/scene/ernie-support-points.json", import.meta.url));
/** The same reduction over the HEAD half only — every served vertex at or above the grey matter's
 *  floor, which is what `GET /api/scene/manifest` calls `focus_bbox` (lane CL1). */
const FOCUS_FIXTURE = fileURLToPath(new URL("../fixtures/scene/ernie-focus-support-points.json", import.meta.url));

interface SupportFixture {
  bbox: Bounds;
  points: [number, number, number][];
}

const ernie = JSON.parse(readFileSync(FIXTURE, "utf8")) as SupportFixture;
const ernieHead = JSON.parse(readFileSync(FOCUS_FIXTURE, "utf8")) as SupportFixture & {
  focus_bbox: Bounds;
  floor_z: number;
};

/** The panes the scene actually gets: SCC measured the right pane at 348 px wide and 1192 px
 *  expanded, both 544 px tall, at a 1280 x 800 window. */
const PANES = [
  { label: "348x544 right pane (default)", width: 348, height: 544 },
  { label: "1192x544 expanded pane", width: 1192, height: 544 },
  { label: "1280x800 full window", width: 1280, height: 800 },
  { label: "420x420 square", width: 420, height: 420 },
];

const PRESETS: CameraPreset[] = ["reset", "front", "left", "top"];

/** A closed-form ellipsoid point cloud: `theta`/`phi` grid, so the support in any direction is
 *  `sqrt(sum (r_i n_i)^2)` and nothing about the expectation depends on the module under test. */
function ellipsoid(radii: [number, number, number], centre: Vec3, u = 96, v = 48): Float32Array {
  const out = new Float32Array((u + 1) * (v + 1) * 3);
  let k = 0;
  for (let i = 0; i <= v; i += 1) {
    const theta = (Math.PI * i) / v;
    for (let j = 0; j <= u; j += 1) {
      const phi = (2 * Math.PI * j) / u;
      out[k] = centre[0] + radii[0] * Math.sin(theta) * Math.cos(phi);
      out[k + 1] = centre[1] + radii[1] * Math.sin(theta) * Math.sin(phi);
      out[k + 2] = centre[2] + radii[2] * Math.cos(theta);
      k += 3;
    }
  }
  return out;
}

function boundsOf(points: Float32Array): Bounds {
  const b: Bounds = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let i = 0; i + 2 < points.length; i += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = points[i + axis] as number;
      if (value < (b[axis] as number)) b[axis] = value;
      if (value > (b[axis + 3] as number)) b[axis + 3] = value;
    }
  }
  return b;
}

interface Framed {
  /** Span of the projection as a fraction of the pane, along whichever axis constrains it. */
  fill: number;
  /** How many projected points fall outside the canvas, or behind the eye. */
  outside: number;
  extentXpx: number;
  extentYpx: number;
}

function frame(points: Float32Array, camera: Parameters<typeof projectToCanvas>[0], width: number, height: number): Framed {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let outside = 0;
  for (let i = 0; i + 2 < points.length; i += 3) {
    const p = projectToCanvas(camera, [points[i] as number, points[i + 1] as number, points[i + 2] as number], width, height);
    if (!p.inFront) {
      outside += 1;
      continue;
    }
    if (p.x < 0 || p.x > width || p.y < 0 || p.y > height) outside += 1;
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  const extentXpx = maxX - minX;
  const extentYpx = maxY - minY;
  return { fill: Math.max(extentXpx / width, extentYpx / height), outside, extentXpx, extentYpx };
}

const erniePoints = new Float32Array(ernie.points.flat());

describe("framing — the head fills the pane", () => {
  it.each(PANES)("fills $label on the real ernie surfaces at every preset", ({ width, height }) => {
    for (const preset of PRESETS) {
      const camera = presetCamera(preset, ernie.bbox, width / height, DEFAULT_FOV_Y, [erniePoints]);
      const framed = frame(erniePoints, camera, width, height);
      expect(
        framed.fill,
        `${preset} @ ${width}x${height}: ${framed.extentXpx.toFixed(0)}x${framed.extentYpx.toFixed(0)} px`,
      ).toBeGreaterThanOrEqual(MIN_FILL);
      expect(framed.outside, `${preset} @ ${width}x${height}: points off-canvas`).toBe(0);
      // And it must not overshoot into a crop: the fit reserves a gutter on purpose.
      expect(framed.fill).toBeLessThanOrEqual(1);
    }
  });

  it.each(PANES)("fills $label on a synthetic ellipsoid at every preset", ({ width, height }) => {
    // Skin-sized, and deliberately off-centre so an implementation that assumes the geometry is
    // centred on its bounding box has to earn the number rather than inherit it.
    const points = ellipsoid([78, 98, 88], [12, -20, 30]);
    const bounds = boundsOf(points);
    for (const preset of PRESETS) {
      const camera = presetCamera(preset, bounds, width / height, DEFAULT_FOV_Y, [points]);
      const framed = frame(points, camera, width, height);
      expect(framed.fill, `${preset} @ ${width}x${height}`).toBeGreaterThanOrEqual(MIN_FILL);
      expect(framed.outside, `${preset} @ ${width}x${height}: points off-canvas`).toBe(0);
    }
  });

  it("frames the bounding box when the caller has no positions to give", () => {
    // The empty-pane path (`SceneCanvas`'s EMPTY_BOUNDS) still has to produce a usable view: the
    // box's own corners are the geometry then. The floor is lower here for a reason that is
    // perspective, not slack: with only eight points the constraining one is a NEAR corner, which
    // projects larger than the far corner opposite it, so the span cannot reach twice the
    // half-frame fill. Measured at 0.79 on this box; a real surface's points fill the gap.
    const MIN_BOX_FILL = 0.75;
    const bounds: Bounds = [-80, -105, -70, 80, 90, 95];
    const centre = boundsCentre(bounds);
    const corners = new Float32Array(
      [0, 1, 2, 3, 4, 5, 6, 7]
        .map((mask) => [
          mask & 1 ? bounds[3] : bounds[0],
          mask & 2 ? bounds[4] : bounds[1],
          mask & 4 ? bounds[5] : bounds[2],
        ])
        .flat(),
    );
    for (const preset of PRESETS) {
      const camera = presetCamera(preset, bounds, 1192 / 544, DEFAULT_FOV_Y);
      expect(camera.target).toEqual(centre);
      const framed = frame(corners, camera, 1192, 544);
      expect(framed.fill, `${preset}`).toBeGreaterThanOrEqual(MIN_BOX_FILL);
      expect(framed.outside, `${preset}: corners off-canvas`).toBe(0);
    }
  });

  it("keeps the whole head in view at a pane far narrower than it is tall", () => {
    // The pane can be dragged narrow; the geometry must shrink to fit rather than be cropped.
    const camera = presetCamera("front", ernie.bbox, 220 / 700, DEFAULT_FOV_Y, [erniePoints]);
    const framed = frame(erniePoints, camera, 220, 700);
    expect(framed.outside).toBe(0);
    expect(framed.extentXpx / 220).toBeGreaterThanOrEqual(MIN_FILL);
  });

  it("does not depend on the preset's own angles being the ones framed", () => {
    // presetCamera frames for the angles it is about to use, so a lateral view of a head that is
    // deeper than it is wide gets its own distance rather than the front view's.
    const front = presetCamera("front", ernie.bbox, 1, DEFAULT_FOV_Y, [erniePoints]);
    const left = presetCamera("left", ernie.bbox, 1, DEFAULT_FOV_Y, [erniePoints]);
    expect(front.yaw).toBe(PRESET_ANGLES.front.yaw);
    expect(left.yaw).toBe(PRESET_ANGLES.left.yaw);
    // ernie is 228 mm front-to-back and 168 mm ear-to-ear, so the left view — which looks along
    // the narrow axis at the wide one — has to stand further back than the front view.
    expect(left.distance).toBeGreaterThan(front.distance);
  });
});

/**
 * The neck (lane CL1, closing FIX-A's §5.4 and SCC's §6.4).
 *
 * FIX-A made the fit exact for the geometry it is *given*, then said what was left: sub-ernie's
 * skin runs to z = −128.9 mm (neck and shoulders) while the grey matter starts at −50.7, so an
 * exact fit to everything still frames a head-and-neck. The remaining gain had to come from what
 * is *served*, and it now does: `GET /api/scene/manifest` carries `focus_bbox` — the box above the
 * grey matter's floor (`tit/scene/build.py::focus_bbox`) — and `SceneCanvas` aims at that box and
 * fits to the points at or above its floor, while still drawing, picking and depth-testing
 * everything.
 *
 * The number measured here is the one a user cares about: **how much of the pane the head
 * occupies**. The head is the same 357 support points in both cases; only the camera changes.
 * `fill` (FIX-A's metric, the larger of the two axis ratios) is reported alongside the **area**
 * fraction, because on a portrait pane the head is already width-constrained and the neck costs
 * nothing along the axis `fill` reads — which is exactly why one number is not enough here.
 */
describe("framing — the neck is not what the pane is for", () => {
  const headPoints = new Float32Array(ernieHead.points.flat());
  const allPoints = new Float32Array(ernie.points.flat());

  /** Fraction of the pane the projected silhouette's bounding box covers. */
  const area = (f: Framed, width: number, height: number): number =>
    (f.extentXpx * f.extentYpx) / (width * height);

  it("the fixture's head really is the geometry above the grey matter's floor", () => {
    // Guards the fixture, not the code: a regenerated file with the wrong subset would make every
    // number below meaningless.
    expect(ernieHead.floor_z).toBeCloseTo(ernieHead.focus_bbox[2] as number, 3);
    expect(ernieHead.bbox[2]).toBeLessThan(ernieHead.floor_z);
    for (let i = 2; i < headPoints.length; i += 3) {
      expect(headPoints[i] as number).toBeGreaterThanOrEqual(ernieHead.floor_z - 1e-3);
    }
    // And the neck really is a third of the box that used to be framed: 228.8 mm of z becomes
    // 150.7 mm.
    const full = (ernieHead.bbox[5] as number) - (ernieHead.bbox[2] as number);
    const head = (ernieHead.focus_bbox[5] as number) - (ernieHead.focus_bbox[2] as number);
    expect(1 - head / full).toBeGreaterThan(0.3);
  });

  it.each(PANES)("never gives the head less of $label, and never crops it", ({ label, width, height }) => {
    for (const preset of PRESETS) {
      const before = presetCamera(preset, ernie.bbox, width / height, DEFAULT_FOV_Y, [allPoints]);
      const after = presetCamera(preset, ernieHead.focus_bbox, width / height, DEFAULT_FOV_Y, [headPoints]);
      const b = frame(headPoints, before, width, height);
      const a = frame(headPoints, after, width, height);
      console.log(
        `HEAD-FILL ${width}x${height} ${preset.padEnd(5)} area ${area(b, width, height).toFixed(3)} -> ` +
          `${area(a, width, height).toFixed(3)}  fill ${b.fill.toFixed(3)} -> ${a.fill.toFixed(3)}  ` +
          `height ${(b.extentYpx / height).toFixed(3)} -> ${(a.extentYpx / height).toFixed(3)}`,
      );
      // Never worse, except in the one view where there is nothing to win: seen from directly
      // above, the neck is behind the head and the focus box only moves the target a few
      // millimetres closer. The slack was 0.002 while `top` looked down from a fraction of a degree
      // ANTERIOR of the vertex, where the neck fell just outside the head's silhouette and the
      // focus framing gained 0.004 to 0.008 of the pane. Lane N1 turned `top` round (yaw pi, so the
      // axial view is not upside down — `camera.ts` PRESET_ANGLES), and from a fraction of a degree
      // posterior the same near-tie lands on the other side: measured on this fixture, the focus
      // framing *loses* 0.0040 at 1192x544, 0.0055 at 1280x800 and 0.0089 at 420x420. That is under
      // 1 % of the pane, and it buys an axial view with the nose at the top; the presets where the
      // neck actually costs something are asserted with real gains in the test below.
      expect(area(a, width, height), `${preset} @ ${label}`).toBeGreaterThan(area(b, width, height) - 0.010);
      expect(a.outside, `${preset} @ ${label}: head points off-canvas`).toBe(0);
      expect(a.fill).toBeLessThanOrEqual(1);
    }
  });

  it("wins where the neck actually costs: the expanded pane's oblique and lateral views", () => {
    // 1192 x 544 is S7's expand control — the pane a user inspects in, and the one where the
    // height is the constraint the neck was spending.
    const [width, height] = [1192, 544];
    const gains: Record<string, number> = {};
    for (const preset of ["reset", "front", "left"] as CameraPreset[]) {
      const before = frame(headPoints, presetCamera(preset, ernie.bbox, width / height, DEFAULT_FOV_Y, [allPoints]), width, height);
      const after = frame(headPoints, presetCamera(preset, ernieHead.focus_bbox, width / height, DEFAULT_FOV_Y, [headPoints]), width, height);
      gains[preset] = area(after, width, height) / area(before, width, height) - 1;
    }
    console.log(`HEAD-FILL 1192x544 area gain: ${Object.entries(gains).map(([k, v]) => `${k} +${(v * 100).toFixed(0)}%`).join("  ")}`);
    expect(gains.reset).toBeGreaterThan(0.1);
    expect(gains.front).toBeGreaterThan(0.3);
    expect(gains.left).toBeGreaterThan(0.8);
  });

  it("crops the neck rather than the head — that is the whole trade", () => {
    // If nothing leaves the canvas, the focus box changed nothing.
    const camera = presetCamera("front", ernieHead.focus_bbox, 348 / 544, DEFAULT_FOV_Y, [headPoints]);
    expect(frame(headPoints, camera, 348, 544).outside).toBe(0);
    expect(frame(allPoints, camera, 348, 544).outside).toBeGreaterThan(0);
  });

  it("falls back to the whole scene when the server sends no focus box", () => {
    // An older server, or a 202: `manifest.focus_bbox` is null and the pane frames `bbox`, which
    // is exactly FIX-A's behaviour and is asserted by the suite above.
    const width = 1192;
    const height = 544;
    const fallback = presetCamera("reset", ernie.bbox, width / height, DEFAULT_FOV_Y, [allPoints]);
    expect(frame(allPoints, fallback, width, height).outside).toBe(0);
    expect(frame(allPoints, fallback, width, height).fill).toBeGreaterThanOrEqual(MIN_FILL);
  });
});
