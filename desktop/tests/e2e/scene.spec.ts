/**
 * The slim scene renderer, offscreen (lane SCB, plan S4/S6).
 *
 * There is not a screenshot in this file. Every assertion is a number, and the load-bearing one is
 * a cross-check between two independent implementations of the same geometry:
 *
 *   - the **CPU** side, `scene/camera.ts`, imported directly into this spec, computes where a
 *     marker's world position lands in canvas pixels;
 *   - the **GPU** side, `scene/glScene.ts`, rasterises that marker into an off-screen buffer with
 *     a colour id and reads the pixel under the cursor back.
 *
 * The spec clicks where the CPU says the marker is and asserts the GPU selected that marker. If the
 * matrices, the viewport, the device-pixel ratio or the y-flip disagreed anywhere in the chain, the
 * click would land on empty space or on a neighbour, and the test would say so. That is the whole
 * reason the camera is a pure module.
 *
 * It runs against the mock server (the `default` project) because the scene needs no server at all:
 * the gallery builds its own fixtures, encodes them to TVSC1 and parses them back. This is the one
 * spec that needs **both** build flags: `VITE_INCLUDE_GALLERY=1` for the gallery page it mounts the
 * scene inside, and `VITE_SCENE_HOOKS=1` for the `window.__scene` handle it reads (package.json's
 * `pree2e` sets both). Every `--project=real` scene spec needs only the latter.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp } from "./_helpers";
import {
  ORBIT_RAD_PER_PX,
  cameraBasis,
  projectToCanvas,
  screenRay,
  type OrbitCamera,
} from "../../src/renderer/scene/camera";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

/** The fixture's own counts, from `src/renderer/dev/sceneFixtures.ts`: a 64x32 grid is
 *  `2 * 64 * 32 = 4096` triangles and `65 * 33 = 2145` vertices per surface, and
 *  `fixtureMarkers` places 3 rings of 12. */
const SMALL_TRIANGLES = 4096;
const SMALL_VERTICES = 2145;
const MARKER_COUNT = 36;
/** The 400x190 grid the "150k tri" fixture uses: 2 * 400 * 190. */
const BUDGET_TRIANGLES = 152_000;

let app: ElectronApplication;
let page: Page;

interface SceneState {
  camera: OrbitCamera & { settled: boolean };
  canvas: { widthCss: number; heightCss: number; dpr: number };
  markers: Array<{ index: number; id: string; world: [number, number, number] }>;
  parts: Array<{ id: string; triangles: number; vertices: number; opacity: number }>;
  stats: { triangles: number; vertices: number; markers: number; drawCalls: number; lastFrameMs: number };
  selection: { markers: number[]; regions: number[] };
  lastPick: {
    target: { kind: string; index: number } | null;
    xCss: number;
    yCss: number;
    world: [number, number, number] | null;
    ray: { origin: [number, number, number]; direction: [number, number, number] };
  } | null;
  fps: number;
  frames: number;
}

async function readScene(target: Page): Promise<SceneState> {
  return target.evaluate(() => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — was out/ built with VITE_SCENE_HOOKS=1?");
    return {
      camera: scene.camera,
      canvas: scene.canvas,
      markers: scene.markers as SceneState["markers"],
      parts: scene.parts,
      stats: scene.stats,
      selection: scene.selection,
      lastPick: scene.lastPick as SceneState["lastPick"],
      fps: scene.fps,
      frames: scene.frames,
    };
  });
}

async function connect(target: Page): Promise<void> {
  await expect(target).toHaveURL(/^app:\/\/launcher\//);
  await target.fill("#server-url", SERVER_URL);
  await target.fill("#token", TOKEN);
  await target.click("#connect");
  await expect(target).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  // `nav-rail`, not the old `subjects-table`: the Overview's subject table was replaced during
  // the 2026-09 UI work, and this helper only needs to know the shell is up.
  await expect(target.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
}

async function openGalleryScene(target: Page): Promise<void> {
  await gotoPage(target, "dev", "Gallery");
  await expect(target.getByRole("heading", { name: "Design gallery" })).toBeVisible();
  const mount = target.getByTestId("scene-mount");
  await mount.scrollIntoViewIfNeeded();
  await mount.click();
  await target.waitForFunction(() => window.__scene?.ready === true, null, { timeout: 20_000 });
  await target.getByTestId("scene-canvas").scrollIntoViewIfNeeded();
  await target.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
}

/** The canvas's position in the page, re-read after any scroll — `boundingBox` is viewport-relative
 *  and a stale one puts every synthetic click somewhere else entirely. */
async function canvasBox(target: Page): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await target.getByTestId("scene-canvas").boundingBox();
  if (!box) throw new Error("the scene canvas has no bounding box");
  return box;
}

/** The skin fixture's semi-axes (`FIXTURE_SKIN`). The 36 markers sit on 1.03x this ellipsoid, so
 *  this shell is what has to hide the ones on the far side of the head. */
const SKIN_R = [78, 98, 88] as const;

/**
 * How far along a ray the scalp shell is first met, or `null` when the ray misses it.
 *
 * Scaling the ray into the unit-sphere frame leaves the parameter `t` untouched — the scaling is
 * per-axis and linear, so `o + t d` scales componentwise — which is why the root that comes out is
 * already a distance in the ray's own (unit-direction, therefore millimetre) units.
 */
function skinEntry(origin: readonly number[], direction: readonly number[]): number | null {
  const o = [0, 1, 2].map((i) => (origin[i] as number) / (SKIN_R[i] as number));
  const d = [0, 1, 2].map((i) => (direction[i] as number) / (SKIN_R[i] as number));
  const dot = (a: number[], b: number[]) => (a[0] as number) * (b[0] as number) + (a[1] as number) * (b[1] as number) + (a[2] as number) * (b[2] as number);
  const a = dot(d, d);
  const b = 2 * dot(o, d);
  const c = dot(o, o) - 1;
  const disc = b * b - 4 * a * c;
  if (disc <= 0) return null;
  const near = (-b - Math.sqrt(disc)) / (2 * a);
  const far = (-b + Math.sqrt(disc)) / (2 * a);
  const t = near > 0 ? near : far;
  return t > 0 ? t : null;
}

interface MarkerView {
  index: number;
  x: number;
  y: number;
  inFront: boolean;
  /** Distance from the eye to the marker, mm. */
  distance: number;
  /**
   * Millimetres of scalp the marker is behind: positive means the ray through it crosses the skin
   * shell *before* reaching it, so a head that occludes must hide it. Negative means the marker is
   * the nearer of the two, so it must be drawn. `null` when the ray misses the shell entirely.
   */
  behindMm: number | null;
  /** Distance in canvas pixels to the nearest OTHER marker's projection. */
  nearestOtherPx: number;
}

/**
 * Every marker's projection and its analytic occlusion by the scalp — computed from the pure camera
 * module and the closed-form fixture, never read back from the renderer.
 */
function markerViews(state: SceneState): MarkerView[] {
  const { widthCss, heightCss } = state.canvas;
  const { eye } = cameraBasis(state.camera);
  const projected = state.markers.map((marker) => ({
    index: marker.index,
    world: marker.world,
    ...projectToCanvas(state.camera, marker.world, widthCss, heightCss),
  }));
  return projected.map((p) => {
    const delta = [0, 1, 2].map((i) => (p.world[i] as number) - (eye[i] as number));
    const distance = Math.hypot(delta[0] as number, delta[1] as number, delta[2] as number);
    const direction = delta.map((v) => (v as number) / distance);
    const entry = skinEntry(eye, direction);
    return {
      index: p.index,
      x: p.x,
      y: p.y,
      inFront: p.inFront,
      distance,
      behindMm: entry === null ? null : distance - entry,
      nearestOtherPx: Math.min(
        ...projected.filter((q) => q.index !== p.index).map((q) => Math.hypot(q.x - p.x, q.y - p.y)),
      ),
    };
  });
}

/**
 * Picks the marker to click: the one nearest the canvas centre that is in front of the camera, at
 * least 30 px from every edge, and at least 18 px from every OTHER marker's projection. The
 * separation matters because a marker on the far side of the head can project within a few pixels
 * of a near one, and then "the pick returned the other one" would be correct behaviour reported as
 * a failure.
 *
 * It also has to be a marker the eye can SEE: since 2026-09-04 the renderer occludes a marker
 * behind the scalp and the pick pass follows it, so an electrode on the far side is no longer
 * clickable — aiming at one would be this spec asserting the defect back.
 */
function chooseMarker(state: SceneState): { index: number; x: number; y: number } {
  const { widthCss, heightCss } = state.canvas;
  const candidates = markerViews(state)
    .filter((p) => p.inFront && p.x > 30 && p.y > 30 && p.x < widthCss - 30 && p.y < heightCss - 30)
    .filter((p) => p.nearestOtherPx > 18)
    .filter((p) => p.behindMm === null || p.behindMm < -1)
    .sort(
      (a, b) =>
        Math.hypot(a.x - widthCss / 2, a.y - heightCss / 2) - Math.hypot(b.x - widthCss / 2, b.y - heightCss / 2),
    );
  const best = candidates[0];
  if (!best) throw new Error("no well-separated visible marker in view — the fixture or the framing changed");
  return { index: best.index, x: best.x, y: best.y };
}


/** The GM fixture's semi-axes and grid, from `src/renderer/dev/sceneFixtures.ts` (FIXTURE_GM). */
const GM = { r: [64, 82, 70] as const, u: 64, v: 32, thetaBands: 4, phiBands: 8 };

/**
 * Where the ray through a canvas pixel first meets the grey-matter ellipsoid, and which region the
 * fixture's own banding formula puts there — the closed-form answer the GPU's region pick has to
 * agree with. Also returns the hit point itself, which is what `onPickAt`'s world position has to
 * agree with.
 *
 * The root taken is the first one in front of the eye, so the answer is right whether the camera is
 * outside the shell (two positive roots, the near one wins) or inside it (the roots straddle zero
 * and the far one is the wall the user is looking at).
 *
 * Returns `null` when the ray misses, or when the hit is closer than two grid cells to a band
 * boundary in either direction. That margin is what makes the expectation exact rather than
 * probable: a triangle spans one cell, so two cells of clearance guarantees all three of its
 * vertices carry the same label, whichever one the `flat` qualifier's provoking-vertex rule picks.
 */
function expectedHitAt(
  camera: OrbitCamera,
  xCss: number,
  yCss: number,
  widthCss: number,
  heightCss: number,
): { label: number; world: [number, number, number] } | null {
  const { origin, direction } = screenRay(camera, xCss, yCss, widthCss, heightCss);
  // Scale into the unit-sphere frame, where the intersection is a plain quadratic.
  const scale = (v: readonly [number, number, number]): [number, number, number] => [
    v[0] / GM.r[0],
    v[1] / GM.r[1],
    v[2] / GM.r[2],
  ];
  const o = scale(origin);
  const d = scale(direction);
  const dot = (a: [number, number, number], b: [number, number, number]) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const a = dot(d, d);
  const b = 2 * dot(o, d);
  const c = dot(o, o) - 1;
  const disc = b * b - 4 * a * c;
  if (disc <= 0) return null;
  const near = (-b - Math.sqrt(disc)) / (2 * a);
  const far = (-b + Math.sqrt(disc)) / (2 * a);
  const t = near > 0 ? near : far;
  if (t <= 0) return null;
  const hit = [0, 1, 2].map((i) => (o[i] as number) + t * (d[i] as number)); // already unit-sphere
  const theta = Math.acos(Math.min(1, Math.max(-1, hit[2] as number)));
  let phi = Math.atan2(hit[1] as number, hit[0] as number);
  if (phi < 0) phi += 2 * Math.PI;
  const i = (theta / Math.PI) * GM.v;
  const j = (phi / (2 * Math.PI)) * GM.u;
  const rows = GM.v + 1;
  const cols = GM.u + 1;
  // Clear of the poles and of the phi seam, where neighbouring vertices straddle two bands.
  if (i < 2 || i > GM.v - 2 || j < 2 || j > GM.u - 2) return null;
  const clearance = (value: number, span: number, bands: number) => {
    const scaled = (value * bands) / span;
    return Math.min(scaled - Math.floor(scaled), Math.ceil(scaled) - scaled) * (span / bands);
  };
  if (clearance(i, rows, GM.thetaBands) < 2 || clearance(j, cols, GM.phiBands) < 2) return null;
  const tBand = Math.min(GM.thetaBands - 1, Math.floor((i * GM.thetaBands) / rows));
  const pBand = Math.min(GM.phiBands - 1, Math.floor((j * GM.phiBands) / cols));
  return {
    label: 1 + tBand * GM.phiBands + pBand,
    // Back out of the unit-sphere frame: this is the world point on the ellipsoid, in mm.
    world: [(hit[0] as number) * GM.r[0], (hit[1] as number) * GM.r[1], (hit[2] as number) * GM.r[2]],
  };
}

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-scene-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
});

test.afterEach(async () => {
  await app?.close();
});

test("uploads the fixture's triangles and selects the marker the camera module aimed at", async () => {
  await connect(page);
  await openGalleryScene(page);
  const state = await readScene(page);

  // What the component says it was handed...
  expect(state.parts.map((p) => p.id).sort()).toEqual(["gm", "skin"]);
  for (const part of state.parts) {
    expect(part.triangles).toBe(SMALL_TRIANGLES);
    expect(part.vertices).toBe(SMALL_VERTICES);
  }
  // ...and what the renderer actually uploaded to the GPU.
  expect(state.stats.triangles).toBe(2 * SMALL_TRIANGLES);
  expect(state.stats.vertices).toBe(2 * SMALL_VERTICES);
  expect(state.stats.markers).toBe(MARKER_COUNT);
  // Per surface, per frame (`glScene.ts` §"Resolving sheets"): the far phase resolves two depth
  // sheets and draws one colour pass (3), the near phase resolves one and draws one (2) — 5 each.
  // Then the marker-occlusion depth pre-pass over each surface (2) and one instanced marker draw:
  // 5 + 5 + 2 + 1 = 13.
  //
  // It was 7 while the transparent pass was a back-face draw and a front-face draw per surface.
  // The extra six are the price of deciding which sheet a pixel shows from DEPTH rather than from
  // winding, which is what stopped the folded grey matter from showing its buried triangles; the
  // fps test below is the one that says the price is affordable, and it measured no change.
  expect(state.stats.drawCalls).toBe(13);
  expect(state.frames).toBeGreaterThan(0);

  const target = chooseMarker(state);
  // The app's own projection and this spec's must be the same arithmetic to the last bit; if they
  // were not, the click below would be aimed by a formula the renderer does not use.
  const appProjection = await page.evaluate(
    (world) => window.__scene?.project(world as [number, number, number]),
    state.markers[target.index]?.world,
  );
  expect(appProjection?.x).toBeCloseTo(target.x, 9);
  expect(appProjection?.y).toBeCloseTo(target.y, 9);

  const box = await canvasBox(page);
  await page.mouse.click(box.x + target.x, box.y + target.y);
  await expect
    .poll(async () => (await readScene(page)).selection.markers, { timeout: 5000 })
    .toEqual([target.index]);

  // The legend is DOM, so what the pane claims is selected is readable without a screenshot.
  await expect(page.getByTestId("scene-legend")).toContainText(`1 of ${MARKER_COUNT} selected`);

  // A second click on the same marker toggles it off (montage mode, `selection.ts`).
  await page.mouse.click(box.x + target.x, box.y + target.y);
  await expect.poll(async () => (await readScene(page)).selection.markers, { timeout: 5000 }).toEqual([]);
});

test("a drag orbits the camera by the documented radians per pixel, and the projection follows", async () => {
  await connect(page);
  await openGalleryScene(page);
  const before = await readScene(page);
  const box = await canvasBox(page);

  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  const dragPx = 120;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  for (let i = 1; i <= 20; i += 1) await page.mouse.move(startX + (dragPx / 20) * i, startY);
  await page.mouse.up();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });

  const after = await readScene(page);
  // orbitBy's contract: yaw += dx * ORBIT_RAD_PER_PX. 120 px * 0.008 = 0.96 rad.
  expect(after.camera.yaw - before.camera.yaw).toBeCloseTo(dragPx * ORBIT_RAD_PER_PX, 6);
  expect(after.camera.distance).toBeCloseTo(before.camera.distance, 6);
  expect(after.camera.target).toEqual(before.camera.target);

  // The projection has to follow the camera, not the other way round: recompute with the NEW
  // camera, click there, and the GPU must agree. Aiming with the OLD camera would now miss.
  const target = chooseMarker(after);
  const stale = projectToCanvas(before.camera, after.markers[target.index]?.world ?? [0, 0, 0], after.canvas.widthCss, after.canvas.heightCss);
  expect(Math.hypot(stale.x - target.x, stale.y - target.y)).toBeGreaterThan(18);

  await page.mouse.click(box.x + target.x, box.y + target.y);
  await expect
    .poll(async () => (await readScene(page)).selection.markers, { timeout: 5000 })
    .toEqual([target.index]);
});


test("target mode picks the region the ray/ellipsoid intersection says is under the cursor", async () => {
  await connect(page);
  await openGalleryScene(page);
  await page.getByRole("radiogroup", { name: "Scene mode" }).getByRole("radio", { name: "target" }).click();
  await expect(page.getByTestId("scene-pane")).toHaveAttribute("data-mode", "target");

  const state = await readScene(page);
  const { widthCss, heightCss } = state.canvas;
  // Sweep a coarse grid for a pixel whose hit is comfortably inside one band in both directions.
  let aimed: { x: number; y: number; label: number } | null = null;
  for (let y = heightCss * 0.25; y < heightCss * 0.8 && !aimed; y += 6) {
    for (let x = widthCss * 0.25; x < widthCss * 0.8; x += 6) {
      const hit = expectedHitAt(state.camera, x, y, widthCss, heightCss);
      if (hit !== null) {
        aimed = { x, y, label: hit.label };
        break;
      }
    }
  }
  if (!aimed) throw new Error("no pixel lands well inside a region band — the fixture or the framing changed");
  expect(aimed.label).toBeGreaterThanOrEqual(1);
  expect(aimed.label).toBeLessThanOrEqual(GM.thetaBands * GM.phiBands);

  const box = await canvasBox(page);
  await page.mouse.click(box.x + aimed.x, box.y + aimed.y);
  await expect
    .poll(async () => (await readScene(page)).selection.regions, { timeout: 5000 })
    .toEqual([aimed.label]);
  // Markers are not pickable in target mode (plan 2.4), even though 36 of them are drawn.
  expect((await readScene(page)).selection.markers).toEqual([]);
  await expect(page.getByTestId("scene-legend")).toContainText("Highlighted regions");

  // A second click on the same region takes it out again.
  await page.mouse.click(box.x + aimed.x, box.y + aimed.y);
  await expect.poll(async () => (await readScene(page)).selection.regions, { timeout: 5000 }).toEqual([]);
});

test("a camera preset re-frames the scene and the keyboard reaches the same presets", async () => {
  await connect(page);
  await openGalleryScene(page);

  await page.getByRole("radiogroup", { name: "Camera preset" }).getByRole("radio", { name: "L", exact: true }).click();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
  const left = await readScene(page);
  expect(left.camera.yaw).toBeCloseTo(-Math.PI / 2, 6);
  expect(left.camera.pitch).toBeCloseTo(0, 6);

  // The same preset from the keyboard (key "3" is right), on the focused canvas.
  await page.getByTestId("scene-canvas").click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("3");
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
  expect((await readScene(page)).camera.yaw).toBeCloseTo(Math.PI / 2, 6);
});

test("the pane's chrome sits in its corners and every opacity row is one line", async () => {
  await connect(page);
  await openGalleryScene(page);
  const pane = page.getByTestId("scene-pane");
  const paneBox = (await pane.boundingBox())!;

  // (1) The view cluster is flush in the TOP-RIGHT corner: 8 px in from both edges, not floating
  // a gap in from the corner. Measured on the cluster's own box, not its CSS.
  const cluster = pane.locator(".scene-chrome-top");
  const clusterBox = (await cluster.boundingBox())!;
  expect(Math.abs(paneBox.x + paneBox.width - (clusterBox.x + clusterBox.width))).toBeLessThanOrEqual(8);
  expect(Math.abs(clusterBox.y - paneBox.y)).toBeLessThanOrEqual(8);

  // (2) "GM", not "Grey matter": on a 2-row card the long name wrapped and made its slider row two
  // lines tall. Each row is one line — its height is under one and a half line boxes.
  const rows = pane.locator(".scene-opacity-row");
  const heights = await rows.evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height));
  expect(heights.length).toBe(2);
  for (const h of heights) expect(h).toBeLessThan(28);
  await expect(pane.getByTestId("scene-opacity")).toContainText("GM");
});

test("the Electrode names switch shows a name for every electrode the eye can see", async () => {
  await connect(page);
  await openGalleryScene(page);
  const pane = page.getByTestId("scene-pane");
  const toggle = pane.getByTestId("scene-names-toggle");

  // Default off: no name overlay at all.
  await expect(pane.getByTestId("scene-names")).toHaveCount(0);
  await expect(toggle.getByRole("switch", { name: "Electrode names" })).toHaveAttribute("data-state", "unchecked");

  await toggle.getByRole("switch", { name: "Electrode names" }).click();
  const names = pane.getByTestId("scene-names");
  await expect(names).toHaveCount(1);
  // One span per marker, and the visible ones are the near-side half — the same claim the marker
  // pass makes with the depth buffer, so "all of them" would be the bug (names bleeding through
  // the head).
  const total = (await readScene(page)).markers.length;
  await expect(names.locator(".scene-name")).toHaveCount(total);
  const visible = await names.locator(".scene-name:not([hidden])").count();
  expect(visible).toBeGreaterThan(0);
  expect(visible).toBeLessThan(total);

  await toggle.getByRole("switch", { name: "Electrode names" }).click();
  await expect(pane.getByTestId("scene-names")).toHaveCount(0);
});

test("recovers from a lost context by re-uploading everything", async () => {
  await connect(page);
  await openGalleryScene(page);
  expect((await readScene(page)).stats.triangles).toBe(2 * SMALL_TRIANGLES);

  expect(await page.evaluate(() => window.__scene?.loseContext())).toBe(true);
  await expect(page.getByTestId("scene-context-lost")).toBeVisible({ timeout: 5000 });
  await expect.poll(async () => page.evaluate(() => window.__scene?.contextLost), { timeout: 5000 }).toBe(true);

  expect(await page.evaluate(() => window.__scene?.restoreContext())).toBe(true);
  await expect(page.getByTestId("scene-context-lost")).toHaveCount(0, { timeout: 10_000 });
  // The GPU-side counts come back, which is the part that proves the CPU-side data was retained
  // and re-uploaded rather than the canvas merely being blank and quiet.
  await expect
    .poll(async () => (await readScene(page)).stats.triangles, { timeout: 10_000 })
    .toBe(2 * SMALL_TRIANGLES);
  const restored = await readScene(page);
  expect(restored.stats.markers).toBe(MARKER_COUNT);
  expect(restored.frames).toBeGreaterThan(0);
});

test("holds the interaction budget while orbiting a 150 k-triangle surface", async () => {
  await connect(page);
  await openGalleryScene(page);
  await page.getByRole("radiogroup", { name: "Fixture size" }).getByRole("radio", { name: "150k tri" }).click();
  await page.waitForFunction(
    (expected) => window.__scene?.parts.some((part) => part.triangles === expected) === true,
    BUDGET_TRIANGLES,
    { timeout: 30_000 },
  );
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });

  const loaded = await readScene(page);
  expect(loaded.stats.triangles).toBe(BUDGET_TRIANGLES + SMALL_TRIANGLES);

  // S8's budget is stated at 1280x800, and the gallery's own frame is 880x420. Resizing the pane
  // through CSS drives the component's real ResizeObserver path, so the backing store — and the
  // fragment cost — is the budget's, not the gallery's. Only the top-left of it is visible inside
  // the gallery's clipped frame, which is where the synthetic drag has to stay.
  // A never-shown Electron window belongs to no display and reports devicePixelRatio 1, so an
  // uncorrected measurement here would be a quarter of the fragment work a Retina user's pane does.
  // Forcing 2 (the component's own cap) before the resize makes the backing store 2560x1600.
  await page.evaluate(() => Object.defineProperty(window, "devicePixelRatio", { value: 2, configurable: true }));
  await page.addStyleTag({ content: ".scene-pane { width: 1280px !important; height: 800px !important; }" });
  await page.waitForFunction(
    () =>
      Math.round(window.__scene?.canvas.widthCss ?? 0) === 1280 &&
      Math.round(window.__scene?.canvas.heightCss ?? 0) === 800 &&
      window.__scene?.canvas.dpr === 2,
    null,
    { timeout: 10_000 },
  );

  // Orbit for two seconds of real frames, the way a hand would, and read the renderer's own frame
  // counter.
  const box = await canvasBox(page);
  const cx = box.x + 300;
  const cy = box.y + 180;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  for (let i = 0; i < 80; i += 1) {
    await page.mouse.move(cx + 60 * Math.sin(i / 6), cy + 30 * Math.cos(i / 9));
    await page.waitForTimeout(25);
  }
  const orbiting = await readScene(page);
  await page.mouse.up();

  console.log(
    `SCENE-FPS triangles=${orbiting.stats.triangles} fps=${orbiting.fps.toFixed(1)} ` +
      `frames=${orbiting.frames} lastFrameMs=${orbiting.stats.lastFrameMs.toFixed(3)} ` +
      `canvas=${Math.round(orbiting.canvas.widthCss)}x${Math.round(orbiting.canvas.heightCss)}@${orbiting.canvas.dpr}`,
  );
  // The camera must actually have moved: an fps figure from a still scene measures nothing.
  expect(orbiting.camera.yaw).not.toBe(loaded.camera.yaw);
  expect(orbiting.fps).toBeGreaterThanOrEqual(30);
});

test("falls back to one readable line when the display has no WebGL2", async () => {
  // Forced by stubbing getContext before the app navigates to the server, which is the only way to
  // exercise S6's path on a machine that does have WebGL2.
  await page.addInitScript(() => {
    // Narrowed to one call signature rather than the DOM's overload set, which cannot be expressed
    // as a single assignable function type.
    const proto = HTMLCanvasElement.prototype as unknown as {
      getContext: (this: HTMLCanvasElement, type: string, options?: unknown) => unknown;
    };
    const original = proto.getContext;
    proto.getContext = function (type: string, options?: unknown) {
      if (type === "webgl2" || type === "webgl") return null;
      return original.call(this, type, options);
    };
  });
  await connect(page);
  await gotoPage(page, "dev", "Gallery");
  const mount = page.getByTestId("scene-mount");
  await mount.scrollIntoViewIfNeeded();
  await mount.click();

  const fallback = page.getByTestId("scene-fallback");
  await expect(fallback).toBeVisible({ timeout: 10_000 });
  await expect(fallback).toContainText("3D preview unavailable");
  await expect(fallback).toContainText("also in the form beside it");
  // No canvas, no debug handle, and the legend still says what the pane would have drawn — the
  // page keeps working without it (S6).
  await expect(page.getByTestId("scene-canvas")).toHaveCount(0);
  await expect(fallback.getByTestId("scene-legend")).toContainText("GM");
  // The handle still exists (it is mounted by the component, not by the GL context) and says so:
  // no WebGL2, never ready, nothing uploaded.
  expect(await page.evaluate(() => ({ webgl2: window.__scene?.webgl2, ready: window.__scene?.ready }))).toEqual({
    webgl2: false,
    ready: false,
  });
});

test("picks the surface the eye can see, not the one behind it (both faces are pickable)", async () => {
  // Lane FIX-A, defect 1 — reported by lane SCC (`scc-notes.md` §6.2) with a measurement on real
  // geometry: the pick pass culled back faces while the visible pass drew both, so at canvas pixel
  // (588, 264) on sub-ernie it named region 12 at 908.2 mm where the surface under the cursor was
  // region 27 at 887.5 mm — a different gyrus, 20.7 mm nearer, with nothing on screen to say so.
  //
  // The fixture reproduces the same disagreement without needing a misoriented triangle: zoom in
  // past the shell. Every triangle of a closed surface seen from inside presents its BACK face, so
  // a pick that culls back faces can see nothing at all while the renderer is drawing the wall the
  // user is clicking on. Before the fix this click selected nothing.
  await connect(page);
  await openGalleryScene(page);
  await page.getByRole("radiogroup", { name: "Scene mode" }).getByRole("radio", { name: "target" }).click();

  const box = await canvasBox(page);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -3000); // clamped at radius * 0.25 by zoomBy
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });

  const state = await readScene(page);
  // The eye really is inside the grey-matter shell: (x/rx)^2 + (y/ry)^2 + (z/rz)^2 < 1.
  const eye: [number, number, number] = [
    state.camera.target[0] + state.camera.distance * Math.cos(state.camera.pitch) * Math.sin(state.camera.yaw),
    state.camera.target[1] + state.camera.distance * Math.cos(state.camera.pitch) * Math.cos(state.camera.yaw),
    state.camera.target[2] + state.camera.distance * Math.sin(state.camera.pitch),
  ];
  const inside = (eye[0] / GM.r[0]) ** 2 + (eye[1] / GM.r[1]) ** 2 + (eye[2] / GM.r[2]) ** 2;
  expect(inside).toBeLessThan(1);

  const { widthCss, heightCss } = state.canvas;
  let aimed: { x: number; y: number; label: number } | null = null;
  for (let y = heightCss * 0.3; y < heightCss * 0.7 && !aimed; y += 5) {
    for (let x = widthCss * 0.3; x < widthCss * 0.7; x += 5) {
      const hit = expectedHitAt(state.camera, x, y, widthCss, heightCss);
      if (hit !== null) {
        aimed = { x, y, label: hit.label };
        break;
      }
    }
  }
  if (!aimed) throw new Error("no pixel lands well inside a region band from inside the shell");

  await page.mouse.click(box.x + aimed.x, box.y + aimed.y);
  await expect
    .poll(async () => (await readScene(page)).selection.regions, { timeout: 5000 })
    .toEqual([aimed.label]);
});

test("reports where the click landed: the world point on the surface the ray hits", async () => {
  // Lane FIX-A, defect 2 — SCC's §6.1 request. `onPick` names the region; `onPickAt` also says
  // where, which is what "click anywhere on the cortex to put the sphere centre there" needs.
  await connect(page);
  await openGalleryScene(page);
  await page.getByRole("radiogroup", { name: "Scene mode" }).getByRole("radio", { name: "target" }).click();

  const state = await readScene(page);
  const { widthCss, heightCss } = state.canvas;
  let aimed: { x: number; y: number; label: number; world: [number, number, number] } | null = null;
  for (let y = heightCss * 0.25; y < heightCss * 0.8 && !aimed; y += 6) {
    for (let x = widthCss * 0.25; x < widthCss * 0.8; x += 6) {
      const hit = expectedHitAt(state.camera, x, y, widthCss, heightCss);
      if (hit !== null) {
        aimed = { x, y, ...hit };
        break;
      }
    }
  }
  if (!aimed) throw new Error("no pixel lands well inside a region band — the fixture or the framing changed");

  const box = await canvasBox(page);
  await page.mouse.click(box.x + aimed.x, box.y + aimed.y);
  await expect.poll(async () => (await readScene(page)).lastPick?.target?.index, { timeout: 5000 }).toBe(aimed.label);

  const pick = (await readScene(page)).lastPick;
  if (!pick || !pick.world) throw new Error("the pick reported no world position");
  expect(pick.xCss).toBeCloseTo(aimed.x, 3);
  expect(pick.yCss).toBeCloseTo(aimed.y, 3);

  // 1. It is where the ray meets the ellipsoid, solved independently in this spec.
  //
  //    The tolerance is derived, not chosen. The renderer samples the depth at the centre of the
  //    device pixel under the cursor, this spec's ray goes through the exact CSS coordinate, and on
  //    a surface seen at an angle a sub-pixel difference along the screen slides the hit point down
  //    the surface by `worldPerPx / cos(incidence)`. Add the fixture's own faceting — a 64x32 grid
  //    chords the ellipsoid by ~0.1 mm — and that is the whole budget. It is still two orders of
  //    magnitude tighter than the 20.7 mm the culled pick was wrong by.
  const normal = [
    aimed.world[0] / GM.r[0] ** 2,
    aimed.world[1] / GM.r[1] ** 2,
    aimed.world[2] / GM.r[2] ** 2,
  ];
  const normalLength = Math.hypot(normal[0] as number, normal[1] as number, normal[2] as number);
  const ray = screenRay(state.camera, aimed.x, aimed.y, widthCss, heightCss);
  const cosIncidence = Math.abs(
    ((normal[0] as number) * ray.direction[0] +
      (normal[1] as number) * ray.direction[1] +
      (normal[2] as number) * ray.direction[2]) /
      normalLength,
  );
  const depthMm = Math.hypot(
    aimed.world[0] - ray.origin[0],
    aimed.world[1] - ray.origin[1],
    aimed.world[2] - ray.origin[2],
  );
  const worldPerPx = (2 * depthMm * Math.tan(state.camera.fovY / 2)) / heightCss;
  const tolerance = worldPerPx / Math.max(cosIncidence, 0.1) + 0.2;
  const error = Math.hypot(
    pick.world[0] - aimed.world[0],
    pick.world[1] - aimed.world[1],
    pick.world[2] - aimed.world[2],
  );
  console.log(
    `SCENE-PICKAT error=${error.toFixed(3)}mm tolerance=${tolerance.toFixed(3)}mm ` +
      `worldPerPx=${worldPerPx.toFixed(3)} cosIncidence=${cosIncidence.toFixed(3)}`,
  );
  expect(error).toBeLessThan(tolerance);

  // 2. It is ON the surface, checked against the ellipsoid equation rather than against a distance:
  //    the quadratic form gives the point's radius as a fraction of the surface's in that
  //    direction, so `|p| * |1 - 1/sqrt(form)|` is how far off the surface it is, in mm. The bound
  //    is the same sub-pixel budget as above projected onto the normal, plus faceting: a chord lies
  //    inside the ellipsoid it spans.
  const onSurface =
    (pick.world[0] / GM.r[0]) ** 2 + (pick.world[1] / GM.r[1]) ** 2 + (pick.world[2] / GM.r[2]) ** 2;
  const radius = Math.hypot(pick.world[0], pick.world[1], pick.world[2]);
  const radialError = radius * Math.abs(1 - 1 / Math.sqrt(onSurface));
  console.log(`SCENE-PICKAT radial=${radialError.toFixed(3)}mm form=${onSurface.toFixed(5)}`);
  expect(radialError).toBeLessThan(tolerance * cosIncidence + 0.2);

  // 3. It is on the ray the pane reports, and that ray starts at the eye this spec computes.
  for (let i = 0; i < 3; i += 1) {
    expect(pick.ray.origin[i] as number).toBeCloseTo(ray.origin[i] as number, 6);
    expect(pick.ray.direction[i] as number).toBeCloseTo(ray.direction[i] as number, 9);
  }
  const along =
    (pick.world[0] - pick.ray.origin[0]) * pick.ray.direction[0] +
    (pick.world[1] - pick.ray.origin[1]) * pick.ray.direction[1] +
    (pick.world[2] - pick.ray.origin[2]) * pick.ray.direction[2];
  const perpendicular = Math.hypot(
    pick.world[0] - pick.ray.origin[0] - along * pick.ray.direction[0],
    pick.world[1] - pick.ray.origin[1] - along * pick.ray.direction[1],
    pick.world[2] - pick.ray.origin[2] - along * pick.ray.direction[2],
  );
  expect(perpendicular).toBeLessThan(1e-6);

  // 4. A click on empty space reports the ray but no point, rather than a point at infinity.
  await page.mouse.click(box.x + 3, box.y + 3);
  await expect.poll(async () => (await readScene(page)).lastPick?.world, { timeout: 5000 }).toBeNull();
});

test("frames the head to fill the pane at every pane size", async () => {
  // Lane FIX-A, defect 3 — SCC's §6.4: "at 1192 x 544 the whole head occupies ~230 px of 544".
  // The unit test proves the maths; this proves the component actually frames on the geometry it
  // uploaded, and re-frames when the pane is resized (S7's expand control).
  await connect(page);
  await openGalleryScene(page);

  // The fixture's own surfaces, sampled here from the formula in `dev/sceneFixtures.ts` — the same
  // closed form the gallery builds them from, retyped rather than imported.
  const SKIN = [78, 98, 88] as const;
  const surfacePoints: Array<[number, number, number]> = [];
  for (const r of [SKIN, GM.r]) {
    for (let i = 0; i <= 32; i += 1) {
      const theta = (Math.PI * i) / 32;
      for (let j = 0; j < 64; j += 1) {
        const phi = (2 * Math.PI * j) / 64;
        surfacePoints.push([
          r[0] * Math.sin(theta) * Math.cos(phi),
          r[1] * Math.sin(theta) * Math.sin(phi),
          r[2] * Math.cos(theta),
        ]);
      }
    }
  }

  for (const size of [
    { width: 880, height: 420 },
    { width: 348, height: 544 },
    { width: 1192, height: 544 },
    { width: 420, height: 420 },
  ]) {
    await page.addStyleTag({
      content: `.scene-pane { width: ${size.width}px !important; height: ${size.height}px !important; }`,
    });
    await page.waitForFunction(
      (expected) =>
        Math.round(window.__scene?.canvas.widthCss ?? 0) === expected.width &&
        Math.round(window.__scene?.canvas.heightCss ?? 0) === expected.height,
      size,
      { timeout: 10_000 },
    );
    await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
    const state = await readScene(page);
    const width = state.canvas.widthCss;
    const height = state.canvas.heightCss;
    const points = [...surfacePoints, ...state.markers.map((m) => m.world)];
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    let outside = 0;
    for (const world of points) {
      const p = projectToCanvas(state.camera, world, width, height);
      if (!p.inFront || p.x < 0 || p.x > width || p.y < 0 || p.y > height) outside += 1;
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    const fill = Math.max((maxX - minX) / width, (maxY - minY) / height);
    console.log(
      `SCENE-FRAMING ${Math.round(width)}x${Math.round(height)} fill=${fill.toFixed(3)} ` +
        `span=${Math.round(maxX - minX)}x${Math.round(maxY - minY)}px distance=${state.camera.distance.toFixed(1)}`,
    );
    // Nothing cropped, and the geometry spans at least 85 % of whichever axis constrains it.
    expect(outside, `${size.width}x${size.height}: points off-canvas`).toBe(0);
    expect(fill, `${size.width}x${size.height}`).toBeGreaterThanOrEqual(0.85);
  }
});

/* -------------------------------------------------------------------------------------------- */
/* Occlusion: an electrode behind the scalp (lane N1)                                             */
/* -------------------------------------------------------------------------------------------- */

/**
 * Reads the drawing buffer at `points` twice — once with the marker pass on, once with it
 * suppressed — and reports, per point, the largest per-channel difference between the two frames.
 *
 * That difference is the whole discriminator, and it is exact rather than a colour model: the two
 * frames draw identical surfaces, so a pixel where **no** marker fragment won is byte-identical in
 * both and the difference is 0. Anything above 0 means a marker painted there. No threshold, no
 * luminance heuristic, no screenshot.
 */
async function markerContribution(
  target: Page,
  points: Array<[number, number]>,
  options: { occluded?: boolean } = {},
): Promise<number[]> {
  const occluded = options.occluded ?? true;
  const withMarkers = await target.evaluate(
    ({ pts, occ }) => {
      window.__scene?.setMarkerOcclusion(occ);
      const read = window.__scene?.samplePixels(pts, true) ?? null;
      window.__scene?.setMarkerOcclusion(true);
      return read;
    },
    { pts: points, occ: occluded },
  );
  const without = await target.evaluate((pts) => window.__scene?.samplePixels(pts, false) ?? null, points);
  if (!withMarkers || !without) throw new Error("samplePixels returned null — no renderer or no camera");
  return points.map((_, i) => {
    const a = withMarkers[i] as number[];
    const b = without[i] as number[];
    return Math.max(...[0, 1, 2].map((c) => Math.abs((a[c] as number) - (b[c] as number))));
  });
}

test("an electrode on the far side of the head is hidden by the scalp", async () => {
  // The maintainer's report, in the Simulator's montage pane: *"the EEG net visualisation looks
  // wrong; the electrode positions look wrong"*. The data was proved correct first (lane SCA: every
  // electrode of every net within 1.81 mm of the served skin, Fp1 left, Fp2 right). What was wrong
  // was the draw order — the markers were drawn FIRST, opaque and depth-writing, and the surfaces
  // afterwards with `depthMask(false)` — so every electrode was painted over the head whichever
  // side of it it was on, and the user saw all of them at once, front and back superimposed.
  await connect(page);
  await openGalleryScene(page);
  await page
    .getByRole("radiogroup", { name: "Camera preset" })
    .getByRole("radio", { name: "F", exact: true })
    .click();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });

  const state = await readScene(page);
  expect(state.camera.yaw).toBeCloseTo(0, 6);
  expect(state.camera.pitch).toBeCloseTo(0, 6);

  const { widthCss, heightCss } = state.canvas;
  const views = markerViews(state).filter(
    (m) => m.inFront && m.x > 24 && m.y > 24 && m.x < widthCss - 24 && m.y < heightCss - 24 && m.nearestOtherPx > 16,
  );
  // Behind by far more than any tolerance the renderer could reasonably allow: the head is 196 mm
  // deep, so a rear electrode is ~190 mm behind the scalp the ray crossed first.
  const hidden = views.filter((m) => m.behindMm !== null && m.behindMm > 60);
  // In front of the scalp on its own ray — these must still be drawn, and they are the control that
  // stops the assertion below from passing because the sampler reads nothing at all.
  const shown = views.filter((m) => m.behindMm !== null && m.behindMm < -1);
  expect(hidden.length, "far-side electrodes to test").toBeGreaterThanOrEqual(4);
  expect(shown.length, "near-side electrodes as the control").toBeGreaterThanOrEqual(4);

  const points: Array<[number, number]> = [...hidden, ...shown].map((m) => [m.x, m.y]);
  const contribution = await markerContribution(page, points);
  const hiddenDelta = contribution.slice(0, hidden.length);
  const shownDelta = contribution.slice(hidden.length);

  // The defect itself, on this build: with occlusion switched off the markers meet an empty depth
  // buffer, which is the draw order this renderer had until 2026-09-04, and every one of the same
  // far-side electrodes is painted over the head. A number recorded from a build that no longer
  // exists is a claim; a number measured either side of one switch is a test.
  const unoccluded = (await markerContribution(page, points, { occluded: false })).slice(0, hidden.length);

  console.log(
    `SCENE-OCCLUSION hidden=${hidden.length} drawn=${hiddenDelta.filter((d) => d > 0).length} ` +
      `maxDelta=${Math.max(...hiddenDelta)} | occlusion OFF drawn=${unoccluded.filter((d) => d > 0).length} ` +
      `maxDelta=${Math.max(...unoccluded)} | control near=${shown.length} ` +
      `drawn=${shownDelta.filter((d) => d > 0).length} minDelta=${Math.min(...shownDelta)}`,
  );

  expect(
    unoccluded.filter((d) => d > 0).length,
    "with occlusion off, every far-side electrode is painted — the defect, on this build",
  ).toBe(hidden.length);

  // The control first: if the near-side electrodes were not painted either, the sampler is broken
  // and the assertion under it would pass for the wrong reason.
  for (let i = 0; i < shown.length; i += 1) {
    const m = shown[i] as MarkerView;
    expect(
      shownDelta[i],
      `marker ${m.index} is ${(-(m.behindMm as number)).toFixed(0)} mm in FRONT of the scalp and must be drawn`,
    ).toBeGreaterThan(0);
  }

  // The defect: a marker the scalp is in front of must contribute nothing to the frame.
  for (let i = 0; i < hidden.length; i += 1) {
    const m = hidden[i] as MarkerView;
    expect(
      hiddenDelta[i],
      `marker ${m.index} is ${(m.behindMm as number).toFixed(0)} mm behind the scalp at (${m.x.toFixed(0)}, ${m.y.toFixed(0)}) and must be hidden by it`,
    ).toBe(0);
  }
});

test("what the eye can no longer see, the cursor can no longer hit", async () => {
  // `drawPickSequence` used to clear the depth buffer before the marker pass, on the premise that
  // the visible pass drew markers over everything — "what the eye can see, the cursor can hit". The
  // premise is what changed: the eye no longer sees a marker behind the scalp, so the rule now cuts
  // the other way and the pick pass has to occlude the markers exactly as the visible pass does. A
  // click that selected an electrode the user cannot see would be the same defect wearing a mouse.
  await connect(page);
  await openGalleryScene(page);
  await page
    .getByRole("radiogroup", { name: "Camera preset" })
    .getByRole("radio", { name: "F", exact: true })
    .click();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });

  const state = await readScene(page);
  const { widthCss, heightCss } = state.canvas;
  const views = markerViews(state).filter(
    (m) => m.inFront && m.x > 24 && m.y > 24 && m.x < widthCss - 24 && m.y < heightCss - 24 && m.nearestOtherPx > 16,
  );
  const hidden = views
    .filter((m) => m.behindMm !== null && m.behindMm > 60)
    .sort((a, b) => (b.behindMm as number) - (a.behindMm as number));
  const target = hidden[0];
  if (!target) throw new Error("no far-side marker to click — the fixture or the framing changed");

  const box = await canvasBox(page);
  await page.mouse.click(box.x + target.x, box.y + target.y);
  // Montage mode selects markers and nothing else, so a click on a hidden one must leave the
  // selection empty rather than name it.
  await expect
    .poll(async () => (await readScene(page)).selection.markers, { timeout: 5000 })
    .toEqual([]);
  // Whatever the pick named, it was not that marker. It is not necessarily *nothing*: a click that
  // asks for a depth also rasterises the labelled surfaces, so on this fixture the pixel carries
  // the region id of the scalp the user actually clicked — which is the correct answer, and the one
  // montage mode's reducer then ignores.
  const named = (await readScene(page)).lastPick?.target;
  expect(named?.kind === "marker" ? named.index : null).not.toBe(target.index);

  // ...and the same click on a marker the eye CAN see still selects it, so the pick pass was not
  // simply switched off.
  const visible = chooseMarker(state);
  await page.mouse.click(box.x + visible.x, box.y + visible.y);
  await expect
    .poll(async () => (await readScene(page)).selection.markers, { timeout: 5000 })
    .toEqual([visible.index]);
});
