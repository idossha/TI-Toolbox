/**
 * R4's gate: the workflow 3D panes draw a **fixed guide**, not the selected research subject.
 *
 * Each assertion below is one clause of the gate in `docs/dev/HISTORY.md § 2026-09-05` R4, and each
 * exists because of a failure the subject-coupled pane actually had:
 *
 *  - changing the selected subjects re-keyed the pane's queries and reloaded the embed, so ticking
 *    a second subject cost a cold 184 MB mesh extraction and a remount → **zero guide-manifest
 *    requests and zero canvas remounts after the initial load**;
 *  - a manifest that advertises an atlas or a net the package does not have gives the user a
 *    selectable option that 404s → **manifest ids equal the packaged catalog ids and every
 *    referenced asset resolves**;
 *  - an oversized surface silently ships → **≤ 3 MB and ≤ 150 000 triangles per payload**, read
 *    back out of the TVSC1 header rather than off the manifest;
 *  - a click on one subject's anatomy could write a subject-RAS millimetre into another subject's
 *    configuration → **a guide click updates names, never coordinates**.
 *
 * **The Simulator is the deliberate exception** (maintainer, 2026-09-06: *"instead of having our
 * default subject in the simulator, we should just load the selected subject such that the user
 * can click on the surface of the skin"*). A free-hand placement IS a subject-RAS millimetre, so
 * the page that collects one has to draw the subject it belongs to — which is exactly the
 * condition R4's last clause states, read the other way round. Everything below is therefore
 * asserted on the **Optimizer**, whose atlas targets draw the guide and whose spheres use a
 * read-only subject preview; the Simulator's own behaviour is `simulator-placement.spec.ts`.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";
import { closeOptEditor, openOptEditor, optRows } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const NET = "GSN-HydroCel-185";

let app: ElectronApplication;
let page: Page;
/** Every `/api/guide/*` URL the renderer asked for, in order. */
let guideRequests: string[] = [];

test.describe.configure({ mode: "serial" });

const api = (path: string) =>
  fetch(`${SERVER_URL}${path}`, { headers: { authorization: `Bearer ${TOKEN}` } });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-guide-")) });
  page = await app.firstWindow();
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/guide/")) guideRequests.push(url.pathname + url.search);
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  // The net is the montage table's first column now (no standalone "EEG net" selector): setting
  // it on a row is also what tells the scene pane which net's electrodes to draw.
  // Addressed by the CELL, not by a combobox index: the montage table gained a Subject column on
  // 2026-09-06 and `nth(0)` silently became the subject picker.
  await page.locator("tr[data-montage-row]").first().locator('td[data-cell="net"]').getByRole("combobox").click();
  await page.getByRole("option", { name: NET, exact: true }).click();
  await expectRunPaneTab(page, "scene");
  await expect(page.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
});

test.afterAll(async () => {
  await app?.close();
});

test("the pane draws the guide, and says so rather than naming the subject", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await expectRunPaneTab(page, "scene");
  await expect(page.locator('[data-page-panel="optimizer"]').getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", {
    timeout: 20_000,
  });
  const debug = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return JSON.parse(JSON.stringify(handle)) as { guide: string | null; space: string | null; subject: string | null; gesture: string };
  });
  expect(debug.guide).toBe("ernie");
  // The point of the whole change: not the *subject* ernie — the guide, in its own space.
  expect(debug.space).toBe("guide-ras");
  expect(debug.subject).toBeNull();
  expect(guideRequests.some((url) => url.startsWith("/api/guide/manifest"))).toBe(true);
});

test("changing the selected subjects costs zero guide requests and zero remounts", async () => {
  const optimizer = page.locator('[data-page-panel="optimizer"]');
  const original = await optimizer.getByTestId("scene-canvas").elementHandle();
  if (!original) throw new Error("the Optimizer scene canvas is missing");

  guideRequests = [];
  // Every way a page changes its subject set: the palette's global subject, and the page's own
  // subject table. Neither may reach the pane.
  for (const id of ["101", "MNI152", "ernie"]) {
    await openPalette(page);
    await page.getByTestId("palette-input").fill(id);
    await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${id}`) }).first().click();
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", id, { timeout: 10_000 });
  }
  // Generous: a re-key would have fired long before this.
  await page.waitForTimeout(1500);

  expect(guideRequests).toEqual([]);
  // The SAME canvas element — a remount would have thrown away a 145 k-triangle upload and the
  // camera the user had orbited to.
  expect(await original.evaluate((node) => node.isConnected)).toBe(true);
  expect(
    await original.evaluate(
      (node) => node === document.querySelector('[data-page-panel="optimizer"] [data-testid="scene-canvas"]'),
    ),
  ).toBe(true);
  await expect(optimizer.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  await original.dispose();
});

test("the manifest's atlas and net ids are the packaged ones, and every asset resolves", async () => {
  const manifest = await (await api("/api/guide/manifest")).json();
  expect(manifest.space).toBe("guide-ras");
  expect(manifest.volumes).toEqual([]);
  expect(manifest.atlases.length).toBeGreaterThan(0);
  expect(manifest.nets.length).toBeGreaterThan(0);

  for (const atlas of manifest.atlases) {
    const regions = await api(atlas.url);
    expect(regions.status, atlas.url).toBe(200);
    const body = await regions.json();
    expect(body.atlas).toBe(atlas.id);
    expect(body.space).toBe("guide-ras");
    expect(body.legend.length).toBe(atlas.regions);
    const labels = await api(body.url);
    expect(labels.status, body.url).toBe(200);
  }
  for (const net of manifest.nets) {
    const electrodes = await api(net.url);
    expect(electrodes.status, net.url).toBe(200);
    const body = await electrodes.json();
    expect(body.net).toBe(net.name);
    expect(body.space).toBe("guide-ras");
    expect(body.electrodes.length).toBe(net.electrodes);
  }
});

test("every guide surface keeps the TVSC1 budget: 3 MB and 150 000 triangles", async () => {
  const manifest = await (await api("/api/guide/manifest")).json();
  expect(manifest.parts.map((p: { id: string }) => p.id).sort()).toEqual(["gm", "skin"]);
  for (const part of manifest.parts) {
    const response = await api(part.url);
    expect(response.status, part.url).toBe(200);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    // Read out of the TVSC1 header itself, not off the manifest: a manifest that merely claims a
    // count would let an oversized payload through.
    expect(String.fromCharCode(...bytes.slice(0, 4))).toBe("TVSC");
    const triangles = view.getUint32(12, true) / 3;
    expect(triangles, `${part.id} triangles`).toBeLessThanOrEqual(150_000);
    expect(bytes.byteLength, `${part.id} bytes`).toBeLessThanOrEqual(3 * 1024 * 1024);
    expect(triangles).toBe(part.triangles);
    expect(bytes.byteLength).toBe(part.bytes);
  }
});

test("an electrode pick writes a NAME into the montage form", async () => {
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await expectRunPaneTab(page, "scene");
  const simulator = page.locator('[data-page-panel="simulator"]');
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  // A retained pane can publish a settled fallback camera before its renderer and net finish
  // loading. Wait for the selected 185-electrode net and a rendered frame before projecting it.
  await page.waitForFunction(() =>
    window.__scenePane?.mode === "montage" && window.__scene?.ready === true &&
    window.__scene.markers.length === 185 && window.__scene.camera.settled === true,
  null, { timeout: 20_000 });

  // Aimed by the renderer's OWN projection of the marker nearest the eye — an electrode round the
  // back of the head is behind the scalp by design and clicking where it projects selects nothing.
  const aim = await page.evaluate(() => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — build out/ with VITE_SCENE_HOOKS=1");
    const cam = scene.camera as { target: number[]; distance: number; yaw: number; pitch: number };
    const cp = Math.cos(cam.pitch);
    const eye = [
      (cam.target[0] as number) + cam.distance * cp * Math.sin(cam.yaw),
      (cam.target[1] as number) + cam.distance * cp * Math.cos(cam.yaw),
      (cam.target[2] as number) + cam.distance * Math.sin(cam.pitch),
    ];
    const best = scene.markers
      .map((marker) => ({
        id: marker.id,
        projection: scene.project(marker.world),
        d: Math.hypot(
          marker.world[0] - (eye[0] as number),
          marker.world[1] - (eye[1] as number),
          marker.world[2] - (eye[2] as number),
        ),
      }))
      .filter((c) => c.projection.inFront)
      .sort((a, b) => a.d - b.d)[0];
    if (!best) throw new Error("no marker in front of the camera");
    return { id: best.id, x: best.projection.x, y: best.projection.y };
  });
  // Scoped to the Simulator's own pane: the Optimizer's is retained and mounted by the tests
  // above, and both canvases carry the same testid.
  const box = await simulator.getByTestId("scene-canvas").boundingBox();
  if (!box) throw new Error("the scene canvas has no bounding box");
  await page.mouse.click(box.x + aim.x, box.y + aim.y);

  await expect(page.locator(".electrode-pair-row").first().getByRole("combobox").first()).toContainText(aim.id, {
    timeout: 10_000,
  });
});

test("switching from the guide to a sphere preview keeps subject-RAS coordinates read-only", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  const row = optRows(page).first();
  const editor = await openOptEditor(page, row, "settings");
  await editor.locator(".roi-picker .segmented").first().getByRole("radio", { name: "Spherical", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-active", "true");
  await expectRunPaneTab(page, "scene");
  const panel = page.locator('[data-page-panel="optimizer"]');
  const preview = panel.getByTestId("target-preview");
  await expect(preview).toContainText("Complete the target in the job editor to preview it.");
  await expect(panel.getByTestId("scene-pane-host")).toHaveCount(0);

  // Spheres use a subject-space volumetric preview, replacing the interactive atlas guide.
  // Complete the actual coordinate fields so this test exercises a loaded preview, not an
  // empty pane that cannot emit a pick in the first place.
  const values = { X: "10", Y: "20", Z: "30", radius: "8" };
  const sphereEditor = await openOptEditor(page, row, "settings");
  for (const [label, value] of Object.entries(values)) {
    await sphereEditor.getByLabel(`Sphere 1 ${label}`, { exact: true }).fill(value);
  }
  await closeOptEditor(page);
  const frame = page.frameLocator('[data-page-panel="optimizer"] [data-testid="target-preview-frame"]');
  await expect(frame.getByTestId("fake-embed-layers")).toContainText("spherical-target.nii.gz");
  await expect(preview.getByTestId("target-preview-frame")).toBeVisible();
  await expect(preview).toContainText("Read-only.");

  // The fake embed emits both cursor and pick events on a body click. Coordinates must stay
  // unchanged even if an embed sends these events despite picking being disabled by the host.
  await frame.locator("body").click({ position: { x: 4, y: 4 } });
  const checked = await openOptEditor(page, row, "settings");
  for (const [label, value] of Object.entries(values)) {
    await expect(checked.getByLabel(`Sphere 1 ${label}`, { exact: true })).toHaveValue(value);
  }
  await closeOptEditor(page);
});
