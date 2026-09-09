/**
 * The run-page scene pane, on the native WebGL2 renderer (plan
 * `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`, N1-N4; NR's mock gate).
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
import { analysisRows, analysisTargetText, closeOptEditor, openOptEditor, optRows } from "./_jobs";
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

test("the pane draws the subject's own head with our own renderer — no iframe anywhere", async () => {
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
  expect(debug).toMatchObject({ mode: "montage", gesture: "electrode", markers: 185, subject: "ernie" });
  // Since 2026-09-06 the Simulator draws the SUBJECT (maintainer: "instead of having our default
  // subject in the simulator, we should just load the selected subject") — a free-hand placement
  // is a millimetre in this head and in no other. `guide` is therefore null here, and the space is
  // said out loud either way, because a consumer that mixes the two writes a silently wrong
  // coordinate. The guide's own gate is `guide.spec.ts`, on the Optimizer.
  expect(debug.guide).toBeNull();
  expect(debug.space).toBe("subject-ras");
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

test("changing the EEG net leaves the camera exactly where the user put it", async () => {
  // The reported defect: "when placing a new net or selecting a new net in the simulator, it
  // should not change the orientation of the 3D visualization. Right now it snaps it to a
  // different orientation." The pane re-framed on its fit points, and those are rebuilt whenever
  // the marker set changes.
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const box = await canvasBox();
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(centre.x, centre.y);
  await page.mouse.down();
  await page.mouse.move(centre.x + 140, centre.y + 50, { steps: 10 });
  await page.mouse.up();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });

  const before = (await readScene()).camera;
  const netCell = page.locator("tr[data-montage-row]").first().locator('td[data-cell="net"]').getByRole("combobox");
  await netCell.click();
  const options = page.getByRole("option");
  const names = await options.allInnerTexts();
  const other = names.map((name) => name.trim()).find((name) => name && name !== NET);
  expect(other, "the guide catalog offers only one net — this spec needs two").toBeTruthy();
  const markersBefore = await page.evaluate(() => window.__scenePane?.markers ?? 0);
  await page.getByRole("option", { name: other!, exact: true }).click();
  // Wait for the pane to have actually redrawn the OTHER net, so the assertion below is about a
  // net change that happened rather than about one that never arrived.
  await expect.poll(() => page.evaluate(() => window.__scenePane?.net ?? null), { timeout: 20_000 }).toBe(other);
  await expect
    .poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0), { timeout: 20_000 })
    .not.toBe(markersBefore);

  const after = (await readScene()).camera;
  expect({ yaw: after.yaw, pitch: after.pitch, distance: after.distance, target: after.target }).toEqual({
    yaw: before.yaw,
    pitch: before.pitch,
    distance: before.distance,
    target: before.target,
  });

  // Put the montage back on the net the rest of the file is written against.
  await netCell.click();
  await page.getByRole("option", { name: NET, exact: true }).click();
});

test("Analyzer accepts a first atlas pick without opening the target editor", async () => {
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
  const row = analysisRows(page).first();
  await expect(analysisTargetText(row)).toContainText("Choose a target");
  const host = page.locator('[data-page-panel="analyzer"]').getByTestId("scene-pane-host");
  await expectRunPaneTab(page, "scene");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(host).toHaveAttribute("data-gesture", "region");
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const box = await canvasBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.selectedRegions.length ?? 0)).toBe(1);
  const picked = await page.evaluate(() => window.__scenePane!.selectedRegions[0]);
  if (!picked) throw new Error("Atlas click did not select a region");
  await expect(analysisTargetText(row)).toContainText("Cortical · DK40");
  await expect(analysisTargetText(row)).toContainText(picked.name);
  // Toggling remains connected to the row after the first pick creates the cortical target.
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.selectedRegions.length ?? 0)).toBe(0);
  await expect(analysisTargetText(row)).toContainText("Choose a target");
});

test("a region picked in the scene is the region the ROI picker lists", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  // The jobs table (2026-09-06): the target belongs to a job ROW, and the pane draws the ACTIVE
  // row's atlas. So the atlas is chosen in that row's editor, and the row stays active after it
  // closes — which is what makes the pane's regions and the row's regions the same list.
  const row = optRows(page).first();
  const editor = await openOptEditor(page, row, "settings");
  await editor.getByRole("radio", { name: "Cortical", exact: true }).click();
  await field("Atlas", editor).locator(".combobox-trigger").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: /DK40/i }).first().click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-active", "true");

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
  // The FORM holds what the pane picked — read where the form now lives, in the row's editor.
  const check = await openOptEditor(page, row, "settings");
  await expect(field("Region(s)", check).getByRole("combobox")).toHaveText(`${hemi} · ${picked!.name}`);
  await closeOptEditor(page);
});

test("a region chosen in the ROI picker is highlighted by the pane", async () => {
  // The region to add is chosen from the PANE's own legend, so the assertion is about the sync and
  // not about whether the two catalogs happen to overlap: the picker offers every region the atlas
  // has, the pane can only highlight one its label payload carries.
  const { before, next } = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent");
    const selected = new Set(handle.selectedRegions.map((r) => `${r.hemi}:${r.id}`));
    const row = handle.legend.find((entry) => !selected.has(`${entry.hemi}:${entry.id}`));
    if (!row) throw new Error("every legend region is already selected");
    return { before: handle.selection.regions, next: { key: `${row.hemi}:${row.id}`, label: row.label } };
  });

  const picker = await openOptEditor(page, optRows(page).first(), "settings");
  await field("Region(s)", picker).getByRole("combobox").click();
  // Cleared first, so this measures the FORM -> PANE direction on its own: the previous test left
  // a scene-picked region in the list, and starting from empty means the assertion below is about
  // this selection and not about the sum of two.
  await page.getByTestId("roi-region-select-none").click();
  // Scoped to the picker's own rows: `[role="option"]` alone also matches the Subjects table's
  // rows, which are `role="option"` too and sit behind the open dialog's overlay.
  await page.getByTestId(`roi-region-row-${next.key}`).click();
  await page.getByTestId("roi-region-done").click();
  await closeOptEditor(page);
  void before;

  await expect
    .poll(() => page.evaluate(() => (window.__scenePane?.selection.regions ?? []).length))
    .toBe(1);
  // The pane's list IS the form's list, resolved through the guide legend — same region, same
  // wire label, no second copy.
  const [regions, selected] = await page.evaluate(() => [
    window.__scenePane?.selection.regions ?? [],
    window.__scenePane?.selectedRegions ?? [],
  ]);
  expect(regions).toContain(next.label);
  expect(selected.map((r) => `${r.hemi}:${r.id}`)).toContain(next.key);
});

test("the grey matter is opaque everywhere, with the skin the only surface that has a slider", async () => {
  // The maintainer's call (2026-09-06): the cortex is what the user is aiming at, so it is never a
  // veil over something behind it, and there is no control that could make it one again. Checked on
  // all three run pages because each mounts its own pane.
  for (const [pageId, title] of [
    ["simulator", "Simulator"],
    ["optimizer", "Optimizer"],
    ["analyzer", "Analyzer"],
  ] as const) {
    await gotoPage(page, pageId, title);
    const panel = page.locator(`[data-page-panel="${pageId}"]`);
    await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
    const gm = await page.evaluate(() => {
      const scene = window.__scene;
      if (!scene) throw new Error("window.__scene is absent — was out/ built with VITE_SCENE_HOOKS=1?");
      return scene.parts.find((part) => part.id === "gm") ?? null;
    });
    expect(gm, `${pageId} draws no grey matter`).not.toBeNull();
    expect(gm!.opacity, `${pageId} draws translucent grey matter`).toBe(1);
    await expect(panel.getByRole("slider", { name: "GM opacity", exact: true })).toHaveCount(0);
    await expect(panel.getByRole("slider", { name: "Skin opacity", exact: true })).toHaveCount(1);
  }
  await gotoPage(page, "simulator", "Simulator");
});
