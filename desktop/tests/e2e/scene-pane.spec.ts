/**
 * The run-page scene pane, on the native WebGL2 renderer (plan
 * `dev/notes/v3-native-panes-external-viewer-plan.md`, N1-N4; NR's mock gate).
 *
 * There is not a screenshot in this file. The two claims it exists to pin are the two directions of
 * one selection:
 *
 *  - **a click in the scene reaches the form** — the electrode the CPU-side projection says is
 *    under the cursor is the electrode that lands in the montage, and the region the pane reports
 *    picking is the region the ROI picker then lists;
 *  - **an edit in the form reaches the scene** — a region chosen in the ROI picker is highlighted
 *    by the pane, by its wire label, without the pane holding a second copy of the list.
 *
 * The aiming is arithmetic, not a guess: the spec imports `scene/camera.ts` and computes where a
 * marker's world position lands in canvas pixels, then clicks there. If the matrices, the viewport,
 * the device-pixel ratio or the y-flip disagreed anywhere in the chain, the click would land on a
 * neighbour and this would say so.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";
import { cameraPosition, type OrbitCamera } from "../../src/renderer/scene/camera";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const NET = "GSN-HydroCel-185";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

interface PaneScene {
  camera: OrbitCamera & { settled: boolean };
  canvas: { widthCss: number; heightCss: number; dpr: number };
  markers: Array<{ index: number; id: string; world: [number, number, number] }>;
}

async function readScene(): Promise<PaneScene> {
  return page.evaluate(() => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — was out/ built with VITE_SCENE_HOOKS=1?");
    return { camera: scene.camera, canvas: scene.canvas, markers: scene.markers as PaneScene["markers"] };
  });
}

/**
 * The ACTIVE page's canvas box, re-read after any scroll.
 *
 * Scoped to `[data-page-active="true"]` because the app retains a mounted panel per page: three
 * panes are alive at once, and an unscoped `getByTestId("scene-canvas")` resolves to the hidden
 * 1x1 one as readily as to the one on screen. `boundingBox` is viewport-relative, so a stale one
 * puts every synthetic click somewhere else entirely.
 */
async function canvasBox(): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await page.locator('[data-page-active="true"]').getByTestId("scene-canvas").boundingBox();
  if (!box) throw new Error("the active page has no scene canvas");
  return box;
}

/**
 * The marker to click: the one NEAREST the eye that is comfortably inside the canvas and has no
 * other marker within 18 CSS px of it.
 *
 * Nearest the eye rather than "any visible one" because electrodes lie ON the scalp and the pane
 * draws them occluded — an electrode round the back is behind the head by design, and clicking
 * where it projects would select nothing. Well-separated because a 185-electrode net puts
 * neighbours ~20 px apart at the default framing, and a click 3 px off would still be a pass for
 * the wrong reason.
 */
async function chooseMarker(scene: PaneScene): Promise<{ index: number; id: string; x: number; y: number }> {
  const projections = await page.evaluate(
    (worlds) => worlds.map((world) => window.__scene?.project(world as [number, number, number]) ?? null),
    scene.markers.map((m) => m.world),
  );
  const eye = cameraPosition(scene.camera);
  const { widthCss, heightCss } = scene.canvas;
  const candidates = scene.markers
    .map((marker, i) => ({
      index: i,
      id: marker.id,
      projection: projections[i],
      eyeDistance: Math.hypot(marker.world[0] - eye[0], marker.world[1] - eye[1], marker.world[2] - eye[2]),
    }))
    .filter((c) => c.projection?.inFront)
    .map((c) => ({ ...c, x: c.projection!.x, y: c.projection!.y }))
    .filter((c) => c.x > 40 && c.y > 40 && c.x < widthCss - 40 && c.y < heightCss - 40)
    .filter((c) =>
      projections.every((other, j) => j === c.index || !other?.inFront || Math.hypot(other.x - c.x, other.y - c.y) > 18),
    )
    .sort((a, b) => a.eyeDistance - b.eyeDistance);
  const best = candidates[0];
  if (!best) throw new Error("no well-separated marker in front of the camera — the fixture or the framing changed");
  return { index: best.index, id: best.id, x: best.x, y: best.y };
}

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-scene-pane-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  // The net is the montage table's first column: setting it on a row is also what tells the scene
  // pane which net's electrodes to draw.
  // Addressed by the CELL, not by a combobox index: the montage table gained a Subject column on
  // 2026-09-06 and `nth(0)` silently became the subject picker.
  await page.locator("tr[data-montage-row]").first().locator('td[data-cell="net"]').getByRole("combobox").click();
  await page.getByRole("option", { name: NET, exact: true }).click();
});

test.afterAll(async () => {
  await app?.close();
});

test("the pane draws the packaged guide with our own renderer — no iframe anywhere", async () => {
  await expectRunPaneTab(page, "scene");
  const host = page.locator('[data-page-panel="simulator"]').getByTestId("scene-pane-host");
  await expect(host).toHaveAttribute("data-renderer", "native");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(page.locator('[data-page-active="true"]').getByTestId("scene-canvas")).toBeVisible();
  // N4: the pane is our code end to end. An iframe here is the embed coming back.
  await expect(page.locator("iframe")).toHaveCount(0);

  const debug = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return JSON.parse(JSON.stringify(handle)) as {
      mode: string;
      gesture: string;
      markers: number;
      guide: string | null;
      space: string | null;
      subject: string | null;
      parts: { id: string; triangles: number; labelled: boolean }[];
      firstPaintMs: number | null;
    };
  });
  expect(debug).toMatchObject({ mode: "montage", gesture: "electrode", markers: 185, subject: null });
  // The guide, named — and its space said out loud, because a consumer that mistakes `guide-ras`
  // for a research subject's RAS writes a silently wrong coordinate.
  expect(debug.guide).toBe("ernie");
  expect(debug.space).toBe("guide-ras");
  expect(debug.parts.map((part) => part.id).sort()).toEqual(["gm", "skin"]);
  expect(debug.firstPaintMs).not.toBeNull();
});

test("clicking the electrode the projection aims at is the electrode the montage gets", async () => {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const scene = await readScene();
  expect(scene.markers.length).toBe(185);
  const target = await chooseMarker(scene);
  const box = await canvasBox();
  await page.mouse.click(box.x + target.x, box.y + target.y);

  // The form is the source of truth, so the assertion is on the FORM, not on the pane's own state.
  await expect(page.locator(".electrode-pair-row").first().getByRole("combobox").first()).toContainText(target.id, {
    timeout: 10_000,
  });
  // ...and the pane mirrors it back: that marker, and only that marker, is selected.
  await expect
    .poll(() => page.evaluate(() => window.__scenePane?.selection.markers ?? []))
    .toEqual([target.index]);
  // Colour is the whole state signal: the marker now belongs to channel 0, the first pair.
  await expect(page.getByTestId("scene-pane-host")).toHaveAttribute("data-active-channel", /^\d$/);
});

test("a region picked in the scene is the region the ROI picker lists", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "Flex", exact: true }).click();
  await page.getByTestId("page-work").getByRole("radio", { name: "Cortical", exact: true }).click();
  await field("Atlas").getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: /DK40/i }).first().click();

  const host = page.locator('[data-page-panel="optimizer"]').getByTestId("scene-pane-host");
  await expectRunPaneTab(page, "scene");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(host).toHaveAttribute("data-gesture", "region");
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });

  // The middle of the canvas is cortex: the camera frames the head, so a click there hits the
  // grey matter and the pick pass names whichever region is under it. Which one it is is the
  // renderer's answer, not this spec's guess — what is asserted is that the FORM then holds it.
  const box = await canvasBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const picked = await page
    .evaluate(() => window.__scenePane?.selectedRegions ?? [])
    .then((regions) => regions[0]);
  expect(picked, "a click in the middle of the framed head hit no region").toBeTruthy();

  const hemi = picked!.hemi === "rh" ? "R" : "L";
  await expect(field("Region(s)").getByRole("combobox")).toHaveText(`${hemi} · ${picked!.name}`);
});

test("a region chosen in the ROI picker is highlighted by the pane", async () => {
  const before = await page.evaluate(() => window.__scenePane?.selection.regions ?? []);
  await field("Region(s)").getByRole("combobox").click();
  // A second region, addressed by its own value — no punctuation, no label guessing.
  const option = page.locator('[role="option"][data-option-value]').first();
  const value = await option.getAttribute("data-option-value");
  await option.click();
  await page.getByTestId("roi-region-done").click();

  await expect
    .poll(() => page.evaluate(() => (window.__scenePane?.selection.regions ?? []).length))
    .toBe(before.length + 1);
  // The pane's list is the FORM's list, resolved through the guide legend — same ids, same order.
  const [selected, legend] = await page.evaluate(() => [
    window.__scenePane?.selectedRegions ?? [],
    window.__scenePane?.legend ?? [],
  ]);
  const added = selected[selected.length - 1]!;
  expect(`${added.hemi}:${added.id}`).toBe(value);
  const row = legend.find((entry) => entry.id === added.id && entry.hemi === added.hemi);
  expect(row, "the pane highlighted a region its own legend does not contain").toBeTruthy();
  const regions = await page.evaluate(() => window.__scenePane?.selection.regions ?? []);
  expect(regions).toContain(row!.label);
});
