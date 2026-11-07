/**
 * Five things the maintainer reported from the desktop app (2026-11-07), against the mock server.
 *
 *  - every cached guide payload is asked for by its version (the stale cortex behind grey
 *    Harvard-Oxford and Glasser);
 *  - the Simulator neither fetches nor draws a cortex, and its scalp alone hides the far side;
 *  - the EEG caps panel draws a net as the Simulator does: the head hides the far side;
 *  - a slow atlas says it is loading, a cached one does not, and a failure is a sentence;
 *  - the legend and the Skin slider keep a whole outline around a long atlas name in a narrow pane.
 *
 * Which electrodes are "far" comes from the mock's skin ellipsoid and the camera (`cameraBasis`), not
 * from the renderer; `samplePixels` differences one frame with and without the marker pass, so a
 * non-zero difference at a marker's pixel means it was painted.
 *
 * Run: npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/scene-pane-status.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette, openSceneLayers } from "./_helpers";
import { showRunPaneTab, waitForScene } from "./_runPane";
import { jobRows } from "./_jobs";
import { cameraBasis, type OrbitCamera, type Vec3 } from "../../src/renderer/scene/camera";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const NET = "GSN-HydroCel-185";
const PANELS = ["caps"];
const LONG_ATLAS = "HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz";

let app: ElectronApplication;
let page: Page;
const requests: string[] = [];

test.describe.configure({ mode: "serial" });

const active = () => page.locator('[data-page-active="true"]');

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-scene-status-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  page.on("request", (request) => requests.push(request.url()));
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ json: { telemetry: { consented: true, enabled: false }, panels: PANELS, image_tag: null, theme: "system" } });
  });
  await page.addInitScript((p: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(p));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, PANELS);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

/** Painted-pixel differences at the electrodes facing the eye, and at those round the back of the
 *  head, picked well away from the silhouette so a marker's radius cannot straddle it. */
async function nearAndFarPainted(): Promise<{ near: number[]; far: number[]; unoccluded: number[] }> {
  await page.mouse.move(0, 0);
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const manifest = (await (
    await fetch(new URL("/api/guide/manifest", SERVER_URL), { headers: { Authorization: `Bearer ${TOKEN}` } })
  ).json()) as { parts: Array<{ id: string; bbox: number[] }> };
  const bbox = manifest.parts.find((p) => p.id === "skin")!.bbox;
  const radii = [0, 1, 2].map((i) => (bbox[i + 3]! - bbox[i]!) / 2);
  const state = await page.evaluate(() => ({ camera: window.__scene!.camera, markers: window.__scene!.markers }));
  const { eye } = cameraBasis(state.camera as OrbitCamera);
  const facing = state.markers.map((marker) => {
    const p = marker.world as Vec3;
    const g = [0, 1, 2].map((i) => p[i]! / radii[i]! ** 2);
    const toEye = [0, 1, 2].map((i) => eye[i]! - p[i]!);
    const dot = g[0]! * toEye[0]! + g[1]! * toEye[1]! + g[2]! * toEye[2]!;
    return { p, cos: dot / (Math.hypot(...g) * Math.hypot(...toEye)) };
  });
  const near = facing.filter((m) => m.cos > 0.5).map((m) => m.p);
  const front = facing.filter((m) => m.cos > -0.1).map((m) => m.p);
  const back = facing.filter((m) => m.cos < -0.3).map((m) => m.p);
  return page.evaluate(
    ({ near: nearWorlds, front: frontWorlds, back: backWorlds }) => {
      const scene = window.__scene!;
      const project = (world: number[]) => {
        const q = scene.project(world as [number, number, number]);
        return [q.x, q.y] as [number, number];
      };
      // A far electrode's pixel can be a near one's: only those clear of everything in front count.
      const fronts = frontWorlds.map(project);
      const far = backWorlds.map(project).filter(([x, y]) => fronts.every(([fx, fy]) => Math.hypot(fx - x, fy - y) > 20));
      const painted = (points: Array<[number, number]>) => {
        const on = scene.samplePixels(points, true)!;
        const off = scene.samplePixels(points, false)!;
        return on.map((pixel, i) => Math.max(...[0, 1, 2].map((c) => Math.abs(pixel[c]! - off[i]![c]!))));
      };
      const shown = { near: painted(nearWorlds.map(project)), far: painted(far) };
      // The control, either side of one switch: with no occlusion these same pixels are painted.
      scene.setMarkerOcclusion(false);
      const unoccluded = painted(far);
      scene.setMarkerOcclusion(true);
      return { ...shown, unoccluded };
    },
    { near, front, back },
  );
}

function expectFarSideHidden(painted: { near: number[]; far: number[]; unoccluded: number[] }): void {
  expect(painted.near.length, "near electrodes to sample").toBeGreaterThanOrEqual(5);
  expect(painted.far.length, "far electrodes to sample").toBeGreaterThanOrEqual(3);
  expect(painted.far.filter((delta) => delta > 0), "far-side electrodes painted").toEqual([]);
  expect(painted.unoccluded.filter((delta) => delta > 0).length, "the same pixels with occlusion off").toBe(painted.far.length);
  // Most, not all: a near electrode's axis can sit beside its projected centre on a steep part of the skin.
  expect(painted.near.filter((delta) => delta > 0).length, "near electrodes painted").toBeGreaterThan(painted.near.length / 2);
}

test("Simulator: no cortex is fetched or drawn, electrodes stay pickable, the scalp hides the far side", async () => {
  requests.length = 0;
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await jobRows(page).first().locator('td[data-cell="net"]').getByRole("combobox").click();
  await page.getByRole("option", { name: NET, exact: true }).click();
  await waitForScene(page);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0)).toBe(185);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.parts.map((part) => part.id))).toEqual(["skin"]);
  expect(requests.filter((url) => /api\/(scene|guide)\/surface\?.*part=gm/.test(url))).toEqual([]);
  // Two opacities, because a pre-pass that only ran for an opaque scalp would pass only one.
  expectFarSideHidden(await nearAndFarPainted());
  await openSceneLayers(active());
  const skin = active().getByRole("slider", { name: "Skin opacity", exact: true });
  await skin.focus();
  await page.keyboard.press("End");
  expectFarSideHidden(await nearAndFarPainted());
  await page.keyboard.press("Home");
  const picks = await page.evaluate(() => {
    const scene = window.__scene!;
    return scene.samplePicks(scene.markers.map((marker) => {
      const q = scene.project(marker.world);
      return [q.x, q.y] as [number, number];
    }));
  });
  expect(picks.filter((pick) => pick?.kind === "marker").length, "electrodes a click can hit").toBeGreaterThan(20);
});

test("EEG caps: the head hides the far side of a net, and the cortex stays", async () => {
  await page.getByRole("link", { name: "EEG caps", exact: true }).click();
  await expectPage(page, "panel-caps");
  await expect(active().getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await page.getByTestId("caps-table").getByRole("cell", { name: NET, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0)).toBe(185);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.parts.map((part) => part.id))).toEqual(["gm", "skin"]);
  expectFarSideHidden(await nearAndFarPainted());
});

test("a slow atlas says so, a cached one does not, and a failure is a sentence", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await showRunPaneTab(page, "scene");
  const host = active().getByTestId("scene-pane-host");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  const status = active().getByTestId("scene-pane-status");
  const atlas = active().getByTestId("scene-pane-atlas").getByRole("combobox");
  const choose = async (name: RegExp) => {
    await atlas.click();
    await page.getByRole("option", { name }).first().click();
  };
  await expect(status).toHaveCount(0, { timeout: 30_000 });

  await page.route("**/api/scene/labels?*atlas=a2009s*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await choose(/^a2009s/);
  await expect(status).toHaveText("Loading a2009s labels…");
  await expect(status).toHaveCount(0, { timeout: 10_000 });
  await expect.poll(() => page.evaluate(() => window.__scenePane?.parts.find((part) => part.id === "gm")?.labelled)).toBe(true);

  // Back and forth: both are in the query cache now, so the status must not appear even briefly.
  await page.evaluate(() => {
    (window as unknown as { __statusSeen: number }).__statusSeen = 0;
    new MutationObserver(() => {
      if (document.querySelector('[data-page-active="true"] [data-testid="scene-pane-status"]')) (window as unknown as { __statusSeen: number }).__statusSeen += 1;
    }).observe(document.body, { childList: true, subtree: true });
  });
  await choose(/^DK40/);
  await page.waitForTimeout(600);
  await choose(/^a2009s/);
  await page.waitForTimeout(600);
  expect(await page.evaluate(() => (window as unknown as { __statusSeen: number }).__statusSeen)).toBe(0);

  await page.route("**/api/scene/labels?*atlas=HCP_MMP1*", (route) => route.fulfill({ status: 500, json: { detail: "the labels file is unreadable" } }));
  await choose(/^HCP_MMP1/);
  await expect(status).toHaveText("The HCP_MMP1 labels could not be loaded: the labels file is unreadable", { timeout: 10_000 });
  await page.unroute("**/api/scene/labels?*atlas=a2009s*");
  await page.unroute("**/api/scene/labels?*atlas=HCP_MMP1*");
});

test("MNI: every guide payload is asked for by version, and a long atlas name keeps the outlines whole", async () => {
  requests.length = 0;
  await active().getByTestId("scene-pane-space-control").getByRole("radio", { name: "MNI", exact: true }).click();
  await active().getByTestId("scene-pane-atlas").getByRole("combobox").click();
  await page.getByRole("option", { name: LONG_ATLAS }).first().click();
  await expect.poll(() => page.evaluate(() => window.__scenePane?.atlas)).toBe(LONG_ATLAS);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.parts.find((part) => part.id === "gm")?.labelled), { timeout: 20_000 }).toBe(true);
  const cached = requests.filter((url) => /api\/guide\/(surface|labels|regions|electrodes)\?/.test(url));
  expect(cached.length, "guide payloads requested").toBeGreaterThan(0);
  expect(cached.filter((url) => !/[?&]v=mock-guide-mni/.test(url))).toEqual([]);

  await openSceneLayers(active());
  // The window's narrow layout stacks the pane at full width, so the narrowest pane is set directly.
  for (const width of [600, 300]) {
    await active().locator(".scene-pane-stage").evaluate((stage, w) => {
      (stage as HTMLElement).style.width = `${w}px`;
    }, width);
    await page.waitForTimeout(300);
    const boxes = await active().getByTestId("scene-layers").evaluate((layers) => {
      const right = (selector: string) => layers.querySelector(selector)!.getBoundingClientRect().right;
      const label = [...layers.querySelectorAll<HTMLElement>(".scene-legend-label")].find((el) => el.title.includes("HarvardOxford"))!;
      return {
        layers: layers.getBoundingClientRect().right,
        clipped: layers.scrollWidth - layers.clientWidth,
        legend: right(".scene-legend"),
        opacity: right(".scene-opacity"),
        truncated: label.scrollWidth > label.clientWidth,
        title: label.title,
      };
    });
    expect(boxes.clipped, `nothing overflows the panel in a ${width} px pane`).toBeLessThanOrEqual(0);
    expect(boxes.legend).toBeLessThanOrEqual(boxes.layers);
    expect(boxes.opacity).toBeLessThanOrEqual(boxes.layers);
    expect(boxes.truncated, "the long name is cut by the ellipsis").toBe(true);
    expect(boxes.title).toBe(LONG_ATLAS);
  }
  await active().locator(".scene-pane-stage").evaluate((stage) => {
    (stage as HTMLElement).style.width = "";
  });
});
