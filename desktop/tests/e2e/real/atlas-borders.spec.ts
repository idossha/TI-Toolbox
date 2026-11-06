/**
 * A cortical atlas on a subject's own head, read per pixel from the real pane, in the Networks tab.
 *
 * The defect, photographed 2026-11-06 on sub-CHN: saw-toothed parcel borders and holes with shards in
 * the cortex. `window.__scene.regionFrame` says which region every pixel is painted as, so the two
 * properties are computed from the frame rather than judged from a picture or a golden:
 *
 *   - islands: a piece of one region under ISLAND_PX pixels (about 4 mm^2 here) is a shard or a hole
 *     showing what is behind it, or a real sliver of a parcel between two folds.
 *   - teeth: the labelled pixels a morphological opening with a 5 x 5 square removes, which is what a
 *     spike narrower than 5 pixels is, or the same thin sliver.
 *
 * Real slivers mean neither count reaches 0, so the bounds sit between the two paths as measured at
 * this camera on sub-CHN, 2026-11-06: the head mesh's clustered GM 123 islands and 3.19 % teeth, the
 * whole central surfaces 53 and 1.74 %. A photograph of each is in the maintainer's review folder.
 *
 * Needs a subject with a cortical atlas: TIT_E2E_ATLAS_SUBJECT=CHN TIT_E2E_ATLAS_SIMULATION=left_insula_mean.
 * TIT_E2E_ATLAS_SHOT names the PNG this camera's frame is saved to; TIT_E2E_ATLAS_NUMBERS a JSON of the counts.
 * Scene hooks are needed (`npm run pree2e`). Reads only; writes nothing to the project.
 */
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { connectReal, getServerPanels, gotoPage, launchElectronApp, setServerPanels } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_ATLAS_SUBJECT;
const SIMULATION = process.env.TIT_E2E_ATLAS_SIMULATION;
const ISLAND_PX = 30;
const MAX_ISLANDS = 85;
const MAX_TOOTH_FRACTION = 0.024;

test.skip(!SUBJECT || !SIMULATION, "skipping: TIT_E2E_ATLAS_SUBJECT and TIT_E2E_ATLAS_SIMULATION name no subject with a cortical atlas");

/** Connected pieces of one region smaller than ISLAND_PX, and the labelled pixels a 5 x 5 opening removes. */
function borderCounts(grid: (number | null)[], width: number, height: number) {
  const at = (x: number, y: number) => (x < 0 || y < 0 || x >= width || y >= height ? null : grid[y * width + x]!);
  const seen = new Uint8Array(grid.length);
  let islands = 0;
  let labelled = 0;
  for (let i = 0; i < grid.length; i += 1) {
    if (grid[i] === null) continue;
    labelled += 1;
    if (seen[i]) continue;
    const stack = [i];
    seen[i] = 1;
    let size = 0;
    while (stack.length) {
      const p = stack.pop()!;
      size += 1;
      const x = p % width;
      const y = (p - x) / width;
      for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]] as const) {
        const q = ny * width + nx;
        if (at(nx, ny) === grid[i] && !seen[q]) {
          seen[q] = 1;
          stack.push(q);
        }
      }
    }
    if (size < ISLAND_PX) islands += 1;
  }
  // Opening: a pixel survives if some 5 x 5 square of one region holds it.
  const kept = new Uint8Array(grid.length);
  for (let y = 0; y + 5 <= height; y += 1) {
    for (let x = 0; x + 5 <= width; x += 1) {
      const id = at(x, y);
      if (id === null) continue;
      let solid = true;
      for (let dy = 0; dy < 5 && solid; dy += 1) for (let dx = 0; dx < 5 && solid; dx += 1) solid = at(x + dx, y + dy) === id;
      if (!solid) continue;
      for (let dy = 0; dy < 5; dy += 1) for (let dx = 0; dx < 5; dx += 1) kept[(y + dy) * width + x + dx] = 1;
    }
  }
  let removed = 0;
  for (let i = 0; i < grid.length; i += 1) if (grid[i] !== null && !kept[i]) removed += 1;
  return { islands, labelled, removed, toothFraction: removed / Math.max(labelled, 1) };
}

test("the atlas on a subject's cortex has clean borders and no holes, read per pixel", async () => {
  test.setTimeout(300_000);
  const panels = await getServerPanels(SERVER_URL, TOKEN);
  if (!panels.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panels, "visual-exporter"]);
  const app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1600, height: 1000 });
    await connectReal(page, { url: SERVER_URL, token: TOKEN });
    const offer = page.getByRole("dialog", { name: "Add example data?" });
    await offer.waitFor({ timeout: 8000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
    await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
    await page.locator("#ve-subject").click();
    await page.getByRole("option", { name: SUBJECT!, exact: true }).click();
    await page.locator("#ve-simulation").click();
    await page.getByRole("option", { name: SIMULATION!, exact: true }).click();
    await page.getByRole("radio", { name: "Networks" }).click();
    await page.waitForFunction(() => { const s = window.__scene; return !!s && s.ready && s.parts.some((p) => p.id === "gm"); }, null, { timeout: 120_000 });
    await page.getByLabel("Camera preset").getByRole("radio").nth(1).click(); // F, L, R, T
    await page.waitForFunction(() => window.__scene!.camera.settled, null, { timeout: 30_000 });
    // A first request may have to build the labels; the frame is read once they are drawn.
    await page.waitForFunction(() => (window.__scene!.regionFrame()?.regions ?? []).some((r) => r !== null), null, { timeout: 120_000, polling: 2000 });
    await page.waitForTimeout(1000);
    const canvas = page.getByTestId("scene-canvas");
    const { fps, gm, frame } = await page.evaluate(() => {
      const s = window.__scene!;
      return { fps: s.fps, gm: s.parts.find((p) => p.id === "gm"), frame: s.regionFrame() };
    });
    const counts = borderCounts(frame!.regions, frame!.width, frame!.height);
    const numbers = { width: frame!.width, height: frame!.height, fps, gm, ...counts };
    console.log(`atlas borders: ${JSON.stringify(numbers)}`);
    if (process.env.TIT_E2E_ATLAS_NUMBERS) writeFileSync(process.env.TIT_E2E_ATLAS_NUMBERS, JSON.stringify(numbers, null, 1));
    if (process.env.TIT_E2E_ATLAS_SHOT) await canvas.screenshot({ path: process.env.TIT_E2E_ATLAS_SHOT });
    expect(counts.labelled, "the pane drew a labelled cortex").toBeGreaterThan(20_000);
    expect(counts.islands, "shards or holes: small pieces of one region inside another").toBeLessThan(MAX_ISLANDS);
    expect(counts.toothFraction, "teeth: labelled pixels only a spike narrower than 5 px holds").toBeLessThan(MAX_TOOTH_FRACTION);
  } finally {
    await setServerPanels(SERVER_URL, TOKEN, panels);
    await app.close();
  }
});
