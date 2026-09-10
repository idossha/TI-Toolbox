/**
 * What a selected atlas region looks like at its boundary (`scene/glScene.ts`, the `fwidth` outline).
 *
 * The defect this file exists for was photographed on the Optimizer pane on 2026-09-06: every
 * selected DK40 label had a **jagged white border of uncoloured triangles** around it. The cause
 * was a selection outline defined as *"any fragment whose interpolated selection value is strictly
 * between 0 and 1"* — which is not the rim of the patch, it is the whole of every triangle that
 * straddles the rim, and a decimated cortex has long thin ones. On a surface with 200 000 triangles
 * that is a band of shards several triangles thick, painted 85 % of the way to white.
 *
 * Two properties replace it, and both are checked here on a real parcellated fixture:
 *
 *   1. **No pixel anywhere near a selected patch goes white.** The outline is now darkened, and it
 *      is one screen-space line rather than a set of whole triangles. This is the assertion that
 *      fails on the old shader.
 *   2. **Inside the patch, every pixel carries the label's own hue.** A boundary triangle takes the
 *      colour of its provoking vertex, because `vLabel` is `flat`; nothing is ever a blend of two
 *      labels or of a label and nothing.
 *
 * The fixture is the gallery's banded grey matter, whose legend (`fixtureLegend`) gives every band
 * a distinct mid-lightness hue — so "not white" and "the band's hue" are both statements a test can
 * compute rather than eyeball.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";
import { fixtureLegend } from "../../src/renderer/dev/sceneFixtures";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = join(__dirname, "artifacts");

/**
 * A pixel is "white" if every channel is at least this. The old outline blended 85 % of the way to
 * #f7f7f7, which lands at 230-245 over the fixture's mid-tone bands; the fixture's own colours are
 * `hslHex(h, 0.62, 0.45)`, whose lightest channel is 186. So 220 separates the defect from every
 * legitimate colour on screen with room on both sides, which is the gap a bound has to sit in.
 */
const WHITE_FLOOR = 220;

/** Sample spacing and half-extent of the window swept around the click, in CSS px. */
const GRID_STEP = 5;
const GRID_HALF = 50;

let app: ElectronApplication;
let page: Page;

const chroma = (p: readonly number[]): number[] => {
  const mean = (p[0]! + p[1]! + p[2]!) / 3;
  return [p[0]! - mean, p[1]! - mean, p[2]! - mean];
};
const cosine = (p: readonly number[], q: readonly number[]): number => {
  const a = chroma(p);
  const b = chroma(q);
  const na = Math.hypot(...a);
  const nb = Math.hypot(...b);
  return na < 1e-6 || nb < 1e-6 ? 0 : (a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!) / (na * nb);
};
const delta = (a: readonly number[], b: readonly number[]): number =>
  Math.max(...[0, 1, 2].map((i) => Math.abs(a[i]! - b[i]!)));

async function connect(target: Page): Promise<void> {
  await expect(target).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(target, SERVER_URL, TOKEN);
  await expect(target).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(target.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
}

/** Every RGBA in one frame, at a grid of canvas CSS points. */
async function grid(target: Page, cx: number, cy: number): Promise<{ x: number; y: number; rgba: number[] }[]> {
  const points: [number, number][] = [];
  for (let dy = -GRID_HALF; dy <= GRID_HALF; dy += GRID_STEP) {
    for (let dx = -GRID_HALF; dx <= GRID_HALF; dx += GRID_STEP) points.push([cx + dx, cy + dy]);
  }
  const read = await target.evaluate(
    (pts) => window.__scene?.samplePixels(pts as [number, number][], false) ?? null,
    points,
  );
  if (!read) throw new Error("samplePixels returned nothing — is the renderer mounted?");
  return points.map(([x, y], i) => ({ x: x!, y: y!, rgba: read[i] as number[] }));
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-scene-edge-")) });
  page = await app.firstWindow();
  await connect(page);
  await gotoPage(page, "dev", "Gallery");
  await expect(page.getByRole("heading", { name: "Design gallery" })).toBeVisible();
  const mount = page.getByTestId("scene-mount");
  await mount.scrollIntoViewIfNeeded();
  await mount.click();
  await page.waitForFunction(() => window.__scene?.ready === true, null, { timeout: 20_000 });
  // The banded fixture (not `folded`, which is deliberately unlabelled) in the mode that selects
  // regions rather than markers.
  await page.getByRole("radiogroup", { name: "Scene mode" }).getByRole("radio", { name: "target" }).click();
  await page.getByTestId("scene-canvas").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

test.describe("a selected region's boundary", () => {
  test("is a thin dark line, not a border of white triangles", async () => {
    const canvas = page.getByTestId("scene-canvas");
    const box = await canvas.boundingBox();
    expect(box, "the scene canvas has no box").not.toBeNull();
    const { x: bx, y: by, width, height } = box as { x: number; y: number; width: number; height: number };
    const cx = Math.round(width / 2);
    const cy = Math.round(height / 2);

    // Aim at a point comfortably INSIDE one band, not merely at the middle of the canvas: the
    // fixture has 32 bands, so a disc round an arbitrary point spans a boundary and the "inside the
    // patch" claim below would be made about two regions at once. A point whose four neighbours a
    // grid step away are all the same colour is inside a band by construction.
    const probe = await grid(page, cx, cy);
    const at = new Map(probe.map((p) => [`${p.x},${p.y}`, p.rgba]));
    const uniform = probe.find((p) => {
      const around = [
        at.get(`${p.x - GRID_STEP},${p.y}`),
        at.get(`${p.x + GRID_STEP},${p.y}`),
        at.get(`${p.x},${p.y - GRID_STEP}`),
        at.get(`${p.x},${p.y + GRID_STEP}`),
      ];
      return around.every((q) => q !== undefined && delta(q, p.rgba) < 6);
    });
    expect(uniform, "no sampled point sits comfortably inside a band").toBeTruthy();
    const ax = uniform!.x;
    const ay = uniform!.y;

    const before = await grid(page, ax, ay);
    await page.mouse.click(bx + ax, by + ay);
    await expect
      .poll(() => page.evaluate(() => window.__scene?.selection.regions.length ?? 0))
      .toBeGreaterThan(0);
    await page.waitForTimeout(150);
    const after = await grid(page, ax, ay);

    const label = await page.evaluate(() => window.__scene?.selection.regions[0] ?? null);
    expect(label, "nothing was selected").not.toBeNull();
    const own = fixtureLegend().find((row) => row.label === label);
    expect(own, `the fixture legend has no row for label ${label}`).toBeTruthy();
    const rgb = [1, 3, 5].map((i) => parseInt(own!.color.slice(i, i + 2), 16));

    // The click actually painted something, or everything below is vacuously true.
    const changed = after.filter((p, i) => delta(p.rgba, (before[i] as { rgba: number[] }).rgba) > 10);
    expect(changed.length, "selecting a region repainted nothing in the sampled window").toBeGreaterThan(20);

    // 1. Nothing in the whole window — inside the patch, on its rim, or outside it — is white.
    //    The old shader failed here: the shards sat 2-6 px outside the patch, exactly where this
    //    grid samples densely.
    const whites = after.filter((p) => p.rgba[0]! >= WHITE_FLOOR && p.rgba[1]! >= WHITE_FLOOR && p.rgba[2]! >= WHITE_FLOOR);
    expect(
      whites.length,
      `${whites.length} of ${after.length} sampled pixels are white — e.g. ` +
        `${whites.slice(0, 4).map((p) => `(${p.x - ax},${p.y - ay})=${JSON.stringify(p.rgba.slice(0, 3))}`).join(" ")}`,
    ).toBe(0);

    // 2. Inside the patch every pixel is the label's own hue.
    //
    //    "The patch", not "everything that changed": selecting a region also DIMS every other known
    //    region (`buildLabelStates`), so a third of the repainted pixels in this window are
    //    neighbours going grey in their own hue, which is correct behaviour and not what this
    //    assertion is about. The disc around the click is inside the patch by construction — the
    //    click is what selected it — so that is where the claim is made.
    //
    //    "Hue", not the raw triple: the fragment is lit and blended under a translucent skin, so
    //    the levels move but the direction away from grey does not. The outline is a darkened
    //    version of the same colour, so it satisfies this too — which is the point of darkening
    //    rather than whitening, and is exactly what the old white rim failed.
    const inside = after.filter((p) => Math.hypot(p.x - ax, p.y - ay) <= 10);
    expect(inside.length, "no samples landed inside the patch").toBeGreaterThan(8);
    const offHue = inside.filter((p) => cosine(p.rgba, rgb) < 0.85);
    expect(
      offHue.length,
      `${offHue.length} of ${inside.length} pixels inside the patch are not the hue of ${own!.color} — e.g. ` +
        `${offHue.slice(0, 4).map((p) => JSON.stringify(p.rgba.slice(0, 3))).join(" ")}`,
    ).toBe(0);

    // 3. The outline is *thin*. It is one screen-space line now, so the fragments it darkens are a
    //    small minority of what the click repainted; a rim made of whole boundary triangles was a
    //    third of them and grew with the triangle size.
    const dark = changed.filter((p) => (p.rgba[0]! + p.rgba[1]! + p.rgba[2]!) / 3 < 40);
    expect(
      dark.length / changed.length,
      `${dark.length} of ${changed.length} repainted pixels are outline`,
    ).toBeLessThan(0.25);

    console.log(
      `SCENE-EDGE label ${label} (${own!.color}): ${changed.length} repainted, ${whites.length} white, ` +
        `${offHue.length} off-hue inside, ${dark.length} outline`,
    );

    await canvas.screenshot({ path: join(ARTIFACTS, "region-selection-after.png") });
  });
});
