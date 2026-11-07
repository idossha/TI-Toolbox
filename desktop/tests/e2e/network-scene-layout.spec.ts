/**
 * The 3D scene is the main object of the run column, measured, not assumed: the canvas's real size
 * in px at a large and a narrow window, a drag that changes the picture, a click that selects an
 * edge, overlays that leave the centre to the canvas, and a wheel that zooms without scrolling the
 * page, in the Networks tab and in the Optimizer's Network target (one shared pane).
 *
 * The numbers are the requirement, 2026-11-05: at least 60 % of the window's height. Picks and camera
 * come from the `window.__scene` debug handle (`VITE_SCENE_HOOKS`, `npm run pree2e`), and "the picture
 * changed" from the canvas's own screenshot bytes. `TIT_E2E_LAYOUT_SHOTS` receives one PNG per window.
 *
 * Run: lockf /tmp/tit-e2e.lock env TIT_E2E_OFFSCREEN=1 npx playwright test --project=default tests/e2e/network-scene-layout.spec.ts
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";
import { addOptRow, clearOptRows, closeOptEditor, openOptEditor, setOptSubject } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "e2e-test-token";
const SHOTS = process.env.TIT_E2E_LAYOUT_SHOTS ?? join(tmpdir(), "tit-layout-shots");
const PANELS = ["visual-exporter"];

let app: ElectronApplication;
let page: Page;

test.afterEach(async () => {
  await app?.close();
});

async function launch(width: number, height: number): Promise<void> {
  mkdirSync(SHOTS, { recursive: true });
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-layout-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width, height });
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ json: { telemetry: { consented: true, enabled: false }, panels: PANELS, image_tag: "idossha/simnibs:v2.3.1", theme: "light" } });
  });
  await page.addInitScript((p: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(p));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, PANELS);
  await connectLauncher(page, SERVER_URL, TOKEN);
}

async function openNetworks(): Promise<void> {
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
  await page.getByRole("radio", { name: "By connection" }).click();
  await page.getByTestId("network-seeds").click();
  await page.getByRole("dialog").getByRole("option", { name: /^Left-Thalamus-Proper/ }).click();
  await page.keyboard.press("Escape");
}

const canvas = () => page.locator('[data-page-active="true"]').getByTestId("scene-canvas");

async function ready(): Promise<void> {
  await page.waitForFunction(() => (window.__scene?.lines?.streamlines ?? 0) > 0 && window.__scene?.camera.settled === true, null, { timeout: 60_000 });
}

/** Every box the canvas could scroll: none may move when the wheel zooms. */
const scrolled = () =>
  canvas().evaluate((el) => {
    const tops: number[] = [];
    for (let at: Element | null = el; at; at = at.parentElement) tops.push(at.scrollTop);
    return { tops, window: window.scrollY };
  });

/** What the requirement says of the pane, wherever it is shown. */
async function expectAUsablePane(height: number, tag: string): Promise<void> {
  await ready();
  // A narrow window stacks the pane under the form.
  await canvas().scrollIntoViewIfNeeded();
  const box = (await canvas().boundingBox())!;
  console.log(`layout ${tag}: canvas ${Math.round(box.width)} x ${Math.round(box.height)} px in a window ${height} high`);
  expect(box.height, "at least 60 % of the window's height").toBeGreaterThanOrEqual(0.6 * height);
  expect(box.width).toBeGreaterThanOrEqual(360);
  await page.screenshot({ path: join(SHOTS, `after_${tag}.png`) });

  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const onCentre = () => page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.getAttribute("data-testid") ?? "", centre);
  expect(await onCentre(), "nothing lies over the centre").toBe("scene-canvas");

  // Layers open over the canvas: its size stays, and its centre still takes the pointer.
  const pane = page.locator('[data-page-active="true"]');
  await expect(pane.getByTestId("scene-layers")).toBeHidden();
  await pane.getByTestId("scene-layers-toggle").click();
  await expect(pane.getByTestId("scene-layers")).toBeVisible();
  expect(await canvas().boundingBox()).toEqual(box);
  expect(await onCentre(), "open layers keep off the centre").toBe("scene-canvas");
  await page.screenshot({ path: join(SHOTS, `after_${tag}_layers.png`) });
  await pane.getByTestId("scene-layers-toggle").click();

  // A drag orbits: the camera turns and the pixels change.
  const before = await canvas().screenshot();
  const cameraBefore = await page.evaluate(() => JSON.stringify(window.__scene!.camera));
  await page.mouse.move(centre.x, centre.y);
  await page.mouse.down();
  await page.mouse.move(centre.x + 80, centre.y + 20, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(() => window.__scene?.camera.settled === true);
  expect(await page.evaluate(() => JSON.stringify(window.__scene!.camera))).not.toBe(cameraBefore);
  expect(Buffer.compare(await canvas().screenshot(), before), "a drag changes the picture").not.toBe(0);

  // The wheel zooms the canvas and scrolls nothing.
  const tops = await scrolled();
  const cameraWheel = await page.evaluate(() => JSON.stringify(window.__scene!.camera));
  await page.mouse.move(centre.x, centre.y);
  await page.mouse.wheel(0, 240);
  await page.waitForFunction(() => window.__scene?.camera.settled === true);
  expect(await page.evaluate(() => JSON.stringify(window.__scene!.camera))).not.toBe(cameraWheel);
  expect(await scrolled()).toEqual(tops);
}

/** A click on a line of the mock's network: at the point it projects to, once the pick says so. */
async function clickALine(): Promise<void> {
  const box = (await canvas().boundingBox())!;
  const at = await page.evaluate(() => {
    const scene = window.__scene!;
    const { widthCss, heightCss } = scene.canvas;
    const grid: [number, number][] = [];
    for (let y = 8; y < heightCss; y += 6) for (let x = 8; x < widthCss; x += 6) grid.push([x, y]);
    const picks = scene.samplePicks(grid);
    return grid[picks.findIndex((p) => p?.kind === "edge")] ?? null;
  });
  expect(at, "a line lies somewhere on the pane").not.toBeNull();
  await page.mouse.click(box.x + at![0], box.y + at![1]);
}

for (const [width, height] of [[1440, 900], [1100, 760]] as const) {
  test(`Networks tab at ${width}x${height}: the scene is the column's main object`, async () => {
    test.setTimeout(120_000);
    await launch(width, height);
    await openNetworks();
    const plan = page.getByTestId("extension-plan-line");
    await expect(plan).toContainText("job");
    await expectAUsablePane(height, `networks_${width}x${height}`);

    // A click on an edge selects it, in the same list the form edits.
    const count = page.getByTestId("network-count");
    await expect(count).toContainText("Nothing chosen yet");
    await clickALine();
    await expect(count).toContainText(/\d+ streamlines · 1 edge/);

    // The plan is one line until asked for; the renders are a tab, not under the canvas.
    const planHeight = (await plan.boundingBox())!.height;
    expect(planHeight).toBeLessThan(48);
    await expect(page.getByRole("radio", { name: /^Renders \d+$/ })).toBeVisible();
    await expect(page.getByTestId("network-renders")).toBeHidden();
    await plan.click();
    await expect(page.getByTestId("extension-plan").locator(".extension-plan-body")).toBeVisible();
    await plan.click();
  });
}

test("the pane's expand button gives the scene the page, and the picker comes back", async () => {
  test.setTimeout(120_000);
  await launch(1440, 900);
  await openNetworks();
  await ready();
  const small = (await canvas().boundingBox())!;
  await page.locator('[data-page-active="true"]').getByTestId("run-pane-tabs").getByRole("button", { name: /expand|full width|maximi[sz]e/i }).first().click();
  await expect.poll(async () => (await canvas().boundingBox())!.width).toBeGreaterThan(small.width + 200);
  await page.screenshot({ path: join(SHOTS, "after_networks_expanded.png") });
});

test("Networks tab: Layers switches the cortex off and on, and the view does not move", async () => {
  test.setTimeout(120_000);
  await launch(1440, 900);
  await openNetworks();
  await ready();
  const pane = page.locator('[data-page-active="true"]');
  // An orbited view, because a re-frame would be the pane moving under the user's hand.
  await pane.getByRole("radio", { name: "L", exact: true }).click();
  await page.waitForFunction(() => window.__scene?.camera.settled === true);
  await pane.getByTestId("scene-layers-toggle").click();
  const cortex = pane.getByRole("switch", { name: "Cortex" });
  await expect(cortex).toBeChecked();

  // Read off the id pass, which draws what a click can hit: a hidden cortex must not catch clicks.
  const state = () =>
    page.evaluate(() => {
      const scene = window.__scene!;
      const grid: [number, number][] = [];
      for (let y = 8; y < scene.canvas.heightCss; y += 12) for (let x = 8; x < scene.canvas.widthCss; x += 12) grid.push([x, y]);
      return {
        opacity: scene.parts.find((part) => part.id === "gm")?.opacity,
        cortex: scene.sampleRegions(grid).filter((label) => label !== null).length,
        lines: scene.lines?.streamlines,
        camera: JSON.stringify(scene.camera),
      };
    });
  const on = await state();
  expect(on.opacity).toBe(1);
  expect(on.cortex, "the cortex is drawn by default").toBeGreaterThan(0);
  const hint = pane.getByTestId("scene-pane-hint");
  await expect(hint).toContainText("Click a region");
  const pixels = await canvas().screenshot();

  await cortex.click();
  await expect(cortex).not.toBeChecked();
  await expect.poll(async () => (await state()).opacity).toBe(0);
  const off = await state();
  expect(off.cortex, "nothing of it is left to click").toBe(0);
  await expect(hint).not.toContainText("region");
  expect(off.lines, "the fibres stay").toBe(on.lines);
  expect(off.camera, "the view stays").toBe(on.camera);
  expect(Buffer.compare(await canvas().screenshot(), pixels), "the picture changes").not.toBe(0);

  await cortex.click();
  await expect(cortex).toBeChecked();
  await expect.poll(state).toEqual(on);
  await expect(hint).toContainText("Click a region");
});

test("the Optimizer's Network target has the same pane, and it is as usable", async () => {
  test.setTimeout(120_000);
  await launch(1440, 900);
  await gotoPage(page, "optimizer", "Optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  const dialog = await openOptEditor(page, row);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  await dialog.getByTestId("network-seeds").click();
  const seeds = page.getByRole("dialog", { name: "Choose seed regions" });
  await seeds.getByRole("option", { name: /Left-Thalamus-Proper/ }).click();
  await seeds.getByRole("button", { name: "Done" }).click();
  await closeOptEditor(page);
  await expectAUsablePane(900, "optimizer_1440x900");
  await expect(page.locator('[data-page-active="true"]').getByTestId("scene-part-switch-gm")).toHaveCount(0);
});
