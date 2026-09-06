/**
 * Which way round the subject is on screen (lane N1, second half of the maintainer's report:
 * *"the EEG net visualisation looks wrong; the electrode positions look wrong"*).
 *
 * The occlusion half of that report is a rendering defect and is proved offscreen with pixels
 * (`tests/e2e/scene.spec.ts`). This half is pure arithmetic and belongs here: for every camera
 * preset, where do known anatomical landmarks land on screen, and does the pane's own caption say
 * the same thing? A swapped `left`/`right` preset, a mirrored projection, or an axial view that is
 * upside down would all read to a user exactly as "the positions look wrong", and none of them can
 * survive this file.
 *
 * Two landmark sets, deliberately:
 *
 *  1. **`AXIS_LANDMARKS`** — points defined by nothing but their anatomical role (a point 90 mm to
 *     the subject's left, and so on). The expectation is derived from the definition, so this set
 *     cannot be wrong; it pins the convention itself.
 *  2. **`ERNIE_10_20`** — the real electrode positions the container serves for sub-ernie's
 *     `EEG10-20_Okamoto_2004.csv` (`GET /api/scene/electrodes`), the net the Simulator's own real
 *     spec drives. Nothing here is a recorded *expectation*: the coordinates are input, and the
 *     first test checks that each name's coordinates match the anatomy its name asserts (Fp1 left
 *     and anterior, T8 the rightmost, and so on) before any of them is projected. The 10-20 net has
 *     no Oz; O1/O2 are its posterior pair and are used in its place.
 */
import { describe, expect, it } from "vitest";
import {
  PRESET_ANGLES,
  cameraBasis,
  dominantAxis,
  orientationCaption,
  orientationTitle,
  presetCamera,
  projectToCanvas,
  screenAnatomy,
  type AnatomicalAxis,
  type Bounds,
  type CameraPreset,
  type Vec3,
} from "../../src/renderer/scene/camera";

/** Subject RAS millimetres: +x the subject's right, +y anterior, +z superior. */
const AXIS_LANDMARKS: Record<string, Vec3> = {
  left: [-90, 0, 0],
  right: [90, 0, 0],
  anterior: [0, 110, 0],
  posterior: [0, -100, 0],
  superior: [0, 0, 95],
};

/** sub-ernie, `EEG10-20_Okamoto_2004.csv`, as the scene service serves it. */
const ERNIE_10_20: Record<string, Vec3> = {
  Fp1: [-22.08, 112.51, 26.41],
  Fp2: [31.63, 112.84, 26.09],
  Fz: [2.54, 74.77, 85.13],
  T7: [-77.99, 5.94, 2.29],
  T8: [81.58, 4.06, 3.52],
  O1: [-28.77, -87.06, 12.68],
  O2: [26.13, -85.56, 14.19],
};

const WIDTH = 400;
const HEIGHT = 320;

function boundsOf(points: Record<string, Vec3>): Bounds {
  const all = Object.values(points);
  const axis = (i: number) => all.map((p) => p[i] as number);
  return [
    Math.min(...axis(0)),
    Math.min(...axis(1)),
    Math.min(...axis(2)),
    Math.max(...axis(0)),
    Math.max(...axis(1)),
    Math.max(...axis(2)),
  ];
}

/** Canvas position and eye-space depth of every landmark, for one preset. */
function screenOf(points: Record<string, Vec3>, preset: CameraPreset) {
  const camera = presetCamera(preset, boundsOf(points), WIDTH / HEIGHT);
  const { eye, forward } = cameraBasis(camera);
  const out: Record<string, { x: number; y: number; depth: number; inFront: boolean }> = {};
  for (const [name, world] of Object.entries(points)) {
    const p = projectToCanvas(camera, world, WIDTH, HEIGHT);
    out[name] = {
      x: p.x,
      y: p.y,
      inFront: p.inFront,
      depth: [0, 1, 2].reduce((sum, i) => sum + ((world[i] as number) - (eye[i] as number)) * (forward[i] as number), 0),
    };
  }
  return { camera, at: out };
}

describe("the landmark set says what its names claim", () => {
  it("ernie's 10-20 coordinates match the anatomy each electrode name asserts", () => {
    // Input data, checked before it is used as input: if the served coordinates did not have these
    // signs, every projection assertion below would be testing the wrong thing.
    expect(ERNIE_10_20.Fp1?.[0], "Fp1 is on the subject's left").toBeLessThan(0);
    expect(ERNIE_10_20.Fp2?.[0], "Fp2 is on the subject's right").toBeGreaterThan(0);
    expect(ERNIE_10_20.T7?.[0], "T7 is on the subject's left").toBeLessThan(0);
    expect(ERNIE_10_20.T8?.[0], "T8 is on the subject's right").toBeGreaterThan(0);

    const names = Object.keys(ERNIE_10_20);
    const most = (i: number, sign: 1 | -1) =>
      names.reduce((best, n) =>
        sign * ((ERNIE_10_20[n] as Vec3)[i] as number) > sign * ((ERNIE_10_20[best] as Vec3)[i] as number) ? n : best,
      );
    expect(most(1, 1), "the most anterior electrode").toBe("Fp2");
    expect(most(1, -1), "the most posterior electrode").toBe("O1");
    expect(most(2, 1), "the most superior electrode").toBe("Fz");
    expect(most(0, 1), "the rightmost electrode").toBe("T8");
    expect(most(0, -1), "the leftmost electrode").toBe("T7");
  });
});

describe("screenAnatomy names the axes the projection actually uses", () => {
  /**
   * The convention, stated once, in one table. Every other assertion in this file is a consequence
   * of a row of it.
   *
   * The **front** row is the one worth reading twice: the eye is in front of the face, so you are
   * FACING the subject and their left hand is on your right — the same way round as a photograph
   * of a person, and the mirror image of a radiological axial slice. The **top** row is the other
   * way round because you are behind the vertex looking down, and both are correct; that is exactly
   * why the pane states its convention rather than assuming the user shares one.
   */
  const EXPECTED: Record<CameraPreset, { right: AnatomicalAxis; up: AnatomicalAxis; toward: AnatomicalAxis }> = {
    front: { right: "left", up: "superior", toward: "anterior" },
    left: { right: "posterior", up: "superior", toward: "left" },
    right: { right: "anterior", up: "superior", toward: "right" },
    top: { right: "right", up: "anterior", toward: "superior" },
    reset: { right: "left", up: "superior", toward: "anterior" },
  };

  for (const preset of Object.keys(EXPECTED) as CameraPreset[]) {
    it(`${preset}`, () => {
      const camera = presetCamera(preset, boundsOf(ERNIE_10_20), WIDTH / HEIGHT);
      expect(screenAnatomy(camera)).toEqual(EXPECTED[preset]);
    });
  }

  it("dominantAxis reads each RAS direction back", () => {
    expect(dominantAxis([1, 0, 0])).toBe("right");
    expect(dominantAxis([-1, 0, 0])).toBe("left");
    expect(dominantAxis([0, 1, 0])).toBe("anterior");
    expect(dominantAxis([0, -1, 0])).toBe("posterior");
    expect(dominantAxis([0, 0, 1])).toBe("superior");
    expect(dominantAxis([0, 0, -1])).toBe("inferior");
    // A mostly-lateral three-quarter direction is lateral, not a coin toss.
    expect(dominantAxis([-0.814, -0.581, 0])).toBe("left");
  });
});

describe("landmarks land on the side of the screen the convention says", () => {
  it("front: the subject's left is on the viewer's RIGHT, superior is up, posterior is behind", () => {
    const { at } = screenOf(ERNIE_10_20, "front");
    // Laterality — the assertion a mirrored projection cannot survive.
    expect(at.Fp1?.x, "Fp1 (left) right of Fp2 (right)").toBeGreaterThan(at.Fp2?.x as number);
    expect(at.T7?.x, "T7 (left) right of T8 (right)").toBeGreaterThan(at.T8?.x as number);
    expect(at.T7?.x, "T7 is the rightmost landmark").toBe(Math.max(...Object.values(at).map((p) => p.x)));
    expect(at.T8?.x, "T8 is the leftmost landmark").toBe(Math.min(...Object.values(at).map((p) => p.x)));
    // Superior is up: canvas y grows downwards.
    expect(at.Fz?.y, "Fz is the highest landmark on screen").toBe(Math.min(...Object.values(at).map((p) => p.y)));
    // Anterior/posterior is depth from this view, not a screen direction.
    expect(at.O1?.depth, "O1 (posterior) is further from the eye than Fp1").toBeGreaterThan(at.Fp1?.depth as number);
    // Everything is in front of the eye, so no landmark's projection is meaningless.
    expect(Object.values(at).every((p) => p.inFront)).toBe(true);
  });

  it("left: the eye is on the subject's left, so anterior is on the viewer's LEFT", () => {
    const { at } = screenOf(ERNIE_10_20, "left");
    expect(at.O1?.x, "O1 (posterior) right of Fp1 (anterior)").toBeGreaterThan(at.Fp1?.x as number);
    expect(at.T7?.depth, "T7 (left) is the nearest landmark").toBeLessThan(at.T8?.depth as number);
    expect(at.Fz?.y).toBe(Math.min(...Object.values(at).map((p) => p.y)));
  });

  it("right: the mirror of left — anterior is on the viewer's RIGHT", () => {
    const { at } = screenOf(ERNIE_10_20, "right");
    expect(at.Fp1?.x, "Fp1 (anterior) right of O1 (posterior)").toBeGreaterThan(at.O1?.x as number);
    expect(at.T8?.depth, "T8 (right) is the nearest landmark").toBeLessThan(at.T7?.depth as number);
    expect(at.Fz?.y).toBe(Math.min(...Object.values(at).map((p) => p.y)));
  });

  it("top: looking down, anterior is UP and the subject's left is on the viewer's LEFT", () => {
    const { at } = screenOf(ERNIE_10_20, "top");
    // The defect this pins: with `top`'s yaw at 0 the eye sat a degree ANTERIOR of the vertex, so
    // `up` collapsed onto -y and the axial view came out with the nose at the bottom — Fp1/Fp2 at
    // y = 289 and O1/O2 at y = 38 on a 400x320 pane, upside down. Yaw pi puts the eye a degree
    // posterior instead, and the frame is the right way up.
    expect(at.Fp1?.y, "Fp1 (anterior) above O1 (posterior)").toBeLessThan(at.O1?.y as number);
    expect(at.Fp2?.y, "Fp2 (anterior) above O2 (posterior)").toBeLessThan(at.O2?.y as number);
    expect(at.T8?.x, "T8 (right) right of T7 (left)").toBeGreaterThan(at.T7?.x as number);
    expect(at.Fz?.depth, "Fz (superior) is the nearest landmark from above").toBeLessThan(at.O1?.depth as number);
  });

  it("reset: the three-quarter view keeps the front view's laterality", () => {
    const { at } = screenOf(ERNIE_10_20, "reset");
    expect(at.Fp1?.x, "Fp1 (left) right of Fp2 (right)").toBeGreaterThan(at.Fp2?.x as number);
    expect(at.Fz?.y).toBe(Math.min(...Object.values(at).map((p) => p.y)));
  });

  it("the same holds for landmarks that are nothing but their anatomical role", () => {
    // The subject-independent version: no electrode names, no head, only the six directions.
    const front = screenOf(AXIS_LANDMARKS, "front").at;
    expect(front.left?.x).toBeGreaterThan(front.right?.x as number);
    expect(front.superior?.y).toBeLessThan(front.left?.y as number);
    expect(front.posterior?.depth).toBeGreaterThan(front.anterior?.depth as number);

    const top = screenOf(AXIS_LANDMARKS, "top").at;
    expect(top.right?.x).toBeGreaterThan(top.left?.x as number);
    expect(top.anterior?.y).toBeLessThan(top.posterior?.y as number);

    const leftView = screenOf(AXIS_LANDMARKS, "left").at;
    expect(leftView.posterior?.x).toBeGreaterThan(leftView.anterior?.x as number);
    expect(leftView.left?.depth).toBeLessThan(leftView.right?.depth as number);
  });
});

describe("the pane says which convention it is using", () => {
  const captions: Record<CameraPreset, string> = {
    front: "Anterior view · right = subject's L",
    left: "Left view · right = posterior",
    right: "Right view · right = anterior",
    top: "Superior view · right = subject's R",
    reset: "Anterior view · right = subject's L",
  };

  for (const preset of Object.keys(captions) as CameraPreset[]) {
    it(`${preset}`, () => {
      const camera = presetCamera(preset, boundsOf(ERNIE_10_20), WIDTH / HEIGHT);
      expect(orientationCaption(camera)).toBe(captions[preset]);
    });
  }

  it("the long form names both screen axes and the side facing the viewer", () => {
    const camera = presetCamera("front", boundsOf(ERNIE_10_20), WIDTH / HEIGHT);
    expect(orientationTitle(camera)).toBe(
      "Looking at anterior of the head. The right of the screen is the subject's left; the top of the screen is superior.",
    );
  });

  it("the caption follows the camera, not the preset button", () => {
    // Orbiting 180 degrees from the front lands behind the head, and the caption has to say so —
    // it is derived from `cameraBasis`, the same function the view matrix comes from.
    const front = presetCamera("front", boundsOf(ERNIE_10_20), WIDTH / HEIGHT);
    const behind = { ...front, yaw: front.yaw + Math.PI };
    expect(orientationCaption(behind)).toBe("Posterior view · right = subject's R");
    expect(PRESET_ANGLES.front.yaw).toBe(0);
  });
});
