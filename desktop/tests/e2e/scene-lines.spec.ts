/**
 * The pane's line pass, read from the drawing buffer (no screenshot). The gallery draws two straight
 * synthetic streamlines in groups 0 and 1 over its fixture head. The CPU projection
 * (`window.__scene.project`) says where each line's midpoint falls; the GPU must paint that pixel in
 * the group's swatch, exactly, and a pick there must return that group. Between the lines nothing of
 * either colour appears, so a pass that drew one colour for both, or none, fails.
 *
 * Run: cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default tests/e2e/scene-lines.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";
import { SCENE_CATEGORICAL } from "../../src/renderer/scene/palette";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

const MIDPOINTS: [number, number, number][] = [[0, 0, 30], [0, 0, -30]];
const swatchByte = (group: number) => SCENE_CATEGORICAL[group]!.map((c) => Math.round(c * 255));

let app: ElectronApplication;
let page: Page;

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-lines-")) });
  page = await app.firstWindow();
  await connectLauncher(page, SERVER_URL, TOKEN);
});
test.afterAll(async () => {
  await app.close();
});

test("each line's midpoint is its swatch, a pick there returns its group, and nothing is drawn between", async () => {
  await gotoPage(page, "dev", "Gallery");
  await page.getByTestId("scene-mount").scrollIntoViewIfNeeded();
  await page.getByTestId("scene-mount").click();
  await page.waitForFunction(() => window.__scene?.ready === true, null, { timeout: 20_000 });
  await page.getByTestId("scene-gallery-lines").click();
  await page.waitForFunction(() => window.__scene?.lines?.streamlines === 2, null, { timeout: 5_000 });
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });

  const read = await page.evaluate((midpoints) => {
    const scene = window.__scene!;
    const projected = midpoints.map((world) => scene.project(world));
    // A one-pixel line's rasterised row can differ from the projected one by the diamond-exit rule;
    // the window is ±1 px, and the swatch must be exact somewhere inside it.
    const windows = projected.map(({ x, y }) => {
      const points: [number, number][] = [];
      for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) points.push([Math.round(x) + dx, Math.round(y) + dy]);
      return scene.samplePixels(points)!;
    });
    const picks = scene.samplePicks(projected.map(({ x, y }) => [Math.round(x), Math.round(y)]));
    const between = scene.samplePixels([[Math.round((projected[0]!.x + projected[1]!.x) / 2), Math.round((projected[0]!.y + projected[1]!.y) / 2)]])![0]!;
    const far = scene.samplePicks([[Math.round(projected[0]!.x), Math.round((projected[0]!.y + projected[1]!.y) / 2)]])[0];
    return { projected, windows, picks, between, far };
  }, MIDPOINTS);

  for (const group of [0, 1]) {
    const want = swatchByte(group);
    const hit = read.windows[group]!.some((p) => p[0] === want[0] && p[1] === want[1] && p[2] === want[2]);
    expect(hit, `group ${group}: ${JSON.stringify(read.windows[group])} should contain ${want}`).toBe(true);
    expect(read.picks[group]).toEqual({ kind: "edge", index: group });
  }
  // Exactly between the two lines, far outside the 4 px pick radius.
  expect(Math.abs(read.projected[0]!.y - read.projected[1]!.y)).toBeGreaterThan(40);
  for (const group of [0, 1]) {
    const want = swatchByte(group);
    expect(read.between.slice(0, 3), "nothing of either swatch between the lines").not.toEqual(want);
  }
  expect(read.far?.kind ?? null).not.toBe("edge");
});

test("hiding the lines removes them from the frame and from the pick", async () => {
  await page.getByTestId("scene-gallery-lines").click();
  await page.waitForFunction(() => window.__scene?.lines === null, null, { timeout: 5_000 });
  const pick = await page.evaluate((world) => {
    const scene = window.__scene!;
    const { x, y } = scene.project(world);
    return scene.samplePicks([[Math.round(x), Math.round(y)]])[0];
  }, MIDPOINTS[0]!);
  expect(pick?.kind ?? null).not.toBe("edge");
});
