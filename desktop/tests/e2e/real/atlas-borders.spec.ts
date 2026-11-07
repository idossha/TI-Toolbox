/**
 * The MNI template's cortical atlas, read per pixel from the real Optimizer pane.
 *
 * `window.__scene.regionFrame` says which region every pixel is painted as, so the two properties are
 * computed from the frame rather than judged from a picture or a golden:
 *
 *   - islands: a piece of one region under ISLAND_PX pixels is a shard or a hole showing what is
 *     behind it, or a real sliver of a parcel between two folds.
 *   - teeth: the labelled pixels a morphological opening with a 5 x 5 square removes, which is what a
 *     spike narrower than 5 pixels is, or the same thin sliver.
 *
 * TIT_E2E_ATLAS_SUBJECT names any subject to connect with; the head drawn is the packaged template.
 * Scene hooks are needed (`npm run pree2e`). Reads only; writes nothing to the project.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_ATLAS_SUBJECT;
const ISLAND_PX = 30;
/**
 * The MNI template's cortex in Harvard-Oxford cortical, read at the same camera. A label volume is
 * 1 mm voxels, so its borders step more than an annotation's: measured 2026-11-07, 100 islands and
 * 2.98 % teeth, and these bounds sit above that. The marching-cubes blocks they replace had 22
 * islands with a gap between all their regions, which no border count can say.
 */
const MNI_MAX_ISLANDS = 125;
const MNI_MAX_TOOTH_FRACTION = 0.036;

test.skip(!SUBJECT, "skipping: TIT_E2E_ATLAS_SUBJECT names no subject");

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

test("a cortical MNI atlas on the template's midlayer has clean borders too", async () => {
  test.setTimeout(180_000);
  const app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1600, height: 1000 });
    await connectReal(page, { url: SERVER_URL, token: TOKEN });
    const offer = page.getByRole("dialog", { name: "Add example data?" });
    await offer.waitFor({ timeout: 8000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
    await selectSubject(page, SUBJECT!);
    await gotoPage(page, "optimizer", "Optimizer");
    const active = page.locator('[data-page-active="true"]');
    await active.getByTestId("scene-pane-space-control").getByRole("radio", { name: "MNI", exact: true }).click();
    await page.waitForFunction(() => {
      const pane = window.__scenePane;
      const cortex = pane?.parts.find((part) => part.id === "gm");
      return pane?.guideId === "mni" && cortex?.labelled === true && window.__scene?.parts.some((part) => part.id === "gm" && part.triangles === cortex.triangles);
    }, null, { timeout: 60_000 });
    await active.getByLabel("Camera preset").getByRole("radio").nth(1).click();
    await page.waitForFunction(() => window.__scene!.camera.settled, null, { timeout: 30_000 });
    await page.waitForTimeout(1000);
    const { frame, atlas } = await page.evaluate(() => ({ frame: window.__scene!.regionFrame(), atlas: window.__scenePane!.atlas }));
    const counts = borderCounts(frame!.regions, frame!.width, frame!.height);
    console.log(`MNI atlas borders (${atlas}): ${JSON.stringify(counts)}`);
    expect(atlas).toMatch(/^HarvardOxford-cortl/);
    expect(counts.labelled).toBeGreaterThan(20_000);
    expect(counts.islands).toBeLessThan(MNI_MAX_ISLANDS);
    expect(counts.toothFraction).toBeLessThan(MNI_MAX_TOOTH_FRACTION);
  } finally {
    await app.close();
  }
});
