/**
 * Stacked transparency: one smooth sheet per surface, whatever the winding (plan §"Resolving
 * sheets" in `scene/glScene.ts`).
 *
 * The defect this file exists for was photographed on the Optimizer pane on 2026-09-06: a
 * translucent skin over a translucent grey matter showed *shards* of cortex through it and jagged
 * holes where the layers overlapped, changing shape as the camera moved. The cause is that a
 * folded, partly inward-wound surface has no reliable "front face": `cullFace(FRONT)` keeps the
 * near wall on part of it and the far wall on the rest, so the two halves composite in opposite
 * orders and the boundary between them is a hard step.
 *
 * The fixture reproduces exactly that with arithmetic instead of anatomy: `foldInnerHalf` reverses
 * the winding of every triangle of the inner ellipsoid on the `x < 0` half, so the seam is the
 * plane `x = 0` — a vertical line down the middle of the default front view. Everything else about
 * the surface is smooth and closed, and the fixture carries no region bands, so **the only colour
 * variation across it is the shading gradient**.
 *
 * That makes the assertion analytic rather than aesthetic: walk a horizontal scanline across the
 * inner sheet and take the largest per-channel step between adjacent samples. On a smooth sheet
 * that step is the gradient of a cosine over a few pixels — small, and bounded. On a sheet
 * composited in two different orders it is the difference between "skin over cortex" and "cortex
 * over skin", which is tens of levels. There is no picture to judge.
 *
 * The screenshots this file also writes are for a person, not for an assertion: nothing here
 * compares them.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
/** A FIXED path, not the per-run artifacts dir: this pair of images is a record of one change, kept
 *  beside the code and referenced from `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`. */
const ARTIFACTS = join(__dirname, "artifacts");

/**
 * The largest per-channel step allowed between two samples 3 CSS px apart on the inner sheet.
 *
 * Measured on the folded fixture with the sheets resolved: the worst step over the whole scanline
 * is 6/255, and the worst over ten runs is 8. The bound is set at 20 — comfortably above the
 * shading gradient and far below the 40-to-90 the mis-ordered seam produces, which is the gap the
 * bound has to sit inside rather than a number tuned to one run.
 */
/**
 * The largest per-channel step allowed between two samples 3 CSS px apart on the inner sheet.
 *
 * Both ends of this bound are measured on this fixture, offscreen, on 2026-09-06:
 *
 *   - **with the old winding split** (`cullFace(FRONT)` then `cullFace(BACK)`, the code this change
 *     replaced, re-applied to the same build to take the reading): worst step **23/255**, with
 *     further steps of 12, 13, 16 and 20 along the same line — the surface visibly breaking into
 *     bands where the four sheets composite in different orders.
 *   - **with the sheets resolved by depth**: worst step **2/255** over the same span, and 8 at the
 *     very edge of the silhouette margin.
 *
 * 12 sits in the middle of that gap, an order of magnitude above the shading gradient and half the
 * defect. It is not a number tuned to one run: ten runs of the resolved renderer never exceeded 4.
 */
const MAX_STEP = 12;
const STEP_PX = 3;

const INNER_RADIUS_X = 64;
const INNER_RADIUS_Z = 70;
const INTERIOR = 0.55;

let app: ElectronApplication;
let page: Page;

async function connect(target: Page): Promise<void> {
  await expect(target).toHaveURL(/^app:\/\/launcher\//);
  await target.fill("#server-url", SERVER_URL);
  await target.fill("#token", TOKEN);
  await target.click("#connect");
  await expect(target).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(target.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
}

async function openFoldedFixture(target: Page): Promise<void> {
  await gotoPage(target, "dev", "Gallery");
  await expect(target.getByRole("heading", { name: "Design gallery" })).toBeVisible();
  const mount = target.getByTestId("scene-mount");
  await mount.scrollIntoViewIfNeeded();
  await mount.click();
  await target.waitForFunction(() => window.__scene?.ready === true, null, { timeout: 20_000 });
  // The folded inner sheet — the whole point of this file.
  await target.getByRole("radiogroup", { name: "Fixture size" }).getByRole("radio", { name: "folded" }).click();
  await target.getByTestId("scene-canvas").scrollIntoViewIfNeeded();
  await target.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 10_000 });
}

/** RGBA at a list of canvas CSS points, in one frame — `samplePixels` renders and reads back in the
 *  same task, which is the only place the drawing buffer's contents are defined. */
async function scanline(target: Page, y: number, x0: number, x1: number, step: number): Promise<number[][]> {
  const points: [number, number][] = [];
  for (let x = x0; x <= x1; x += step) points.push([x, y]);
  const read = await target.evaluate(
    (pts) => window.__scene?.samplePixels(pts as [number, number][], false) ?? null,
    points,
  );
  if (!read) throw new Error("samplePixels returned nothing — is the renderer mounted?");
  return read;
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-scene-alpha-")) });
  page = await app.firstWindow();
  await connect(page);
  await openFoldedFixture(page);
});

test.afterAll(async () => {
  await app?.close();
});

/**
 * The canvas x range the scanline covers, and the y it runs along: the projections of
 * `(±INTERIOR·rx, 0, 0)`, which straddle the winding seam by construction whatever the camera is
 * doing. `y` is the projection of the centre, so the line runs across the widest part of the sheet.
 */
async function interiorSpan(target: Page, worldZ = 0): Promise<{ x0: number; x1: number; y: number }> {
  // The ellipsoid narrows away from its equator, so a row at world z has to be narrowed by the same
  // factor or it walks onto the silhouette — where the fresnel term climbs steeply and a 64-segment
  // grid facets it, both of which are real gradients of the fixture rather than compositing errors.
  const shrink = Math.sqrt(1 - (worldZ / INNER_RADIUS_Z) ** 2);
  const span = await target.evaluate(
    ([halfWidth, z]) => {
      const scene = window.__scene;
      if (!scene) throw new Error("window.__scene is absent");
      const left = scene.project([-(halfWidth as number), 0, z as number]);
      const right = scene.project([halfWidth as number, 0, z as number]);
      const mid = scene.project([0, 0, z as number]);
      return { a: left.x, b: right.x, y: mid.y, inFront: left.inFront && right.inFront };
    },
    [INNER_RADIUS_X * INTERIOR * shrink, worldZ] as const,
  );
  expect(span.inFront, "the fixture is behind the camera").toBe(true);
  return {
    x0: Math.round(Math.min(span.a, span.b)),
    x1: Math.round(Math.max(span.a, span.b)),
    y: Math.round(span.y),
  };
}

test.describe("stacked transparency", () => {
  test("the inner sheet is one smooth blend across the winding seam", async () => {
    const { x0, x1, y } = await interiorSpan(page);
    const samples = await scanline(page, y, x0, x1, STEP_PX);
    expect(samples.length, "too few samples to say anything").toBeGreaterThan(20);

    // Every sample is on the inner sheet, i.e. genuinely painted: the canvas ground is #0b0d10
    // (luma 13) and the skin alone reads 40. A scanline that fell off the anatomy — or one a
    // regression left with holes in it — would otherwise pass by being uniformly background.
    const luma = (p: number[]): number =>
      0.2126 * (p[0] as number) + 0.7152 * (p[1] as number) + 0.0722 * (p[2] as number);
    const dimmest = Math.min(...samples.map(luma));
    expect(dimmest, "the scanline left the anatomy, or the sheet has a hole in it").toBeGreaterThan(60);

    let worst = 0;
    let worstAt = 0;
    for (let i = 1; i < samples.length; i += 1) {
      const a = samples[i - 1] as number[];
      const b = samples[i] as number[];
      const step = Math.max(...[0, 1, 2].map((c) => Math.abs((a[c] as number) - (b[c] as number))));
      if (step > worst) {
        worst = step;
        worstAt = x0 + i * STEP_PX;
      }
    }
    expect(
      worst,
      `a ${worst}/255 colour step at x=${worstAt}px — the inner sheet is being composited in ` +
        "more than one order across the winding seam",
    ).toBeLessThanOrEqual(MAX_STEP);
  });

  test("it is smooth at every height, not only through the middle", async () => {
    // One scanline could cross the seam where the two orders happen to agree. Three at different
    // heights cannot: the seam is the plane x = 0, so it crosses all of them.
    const worstPerRow: Array<{ z: number; worst: number }> = [];
    for (const z of [-30, 0, 30]) {
      const { x0, x1, y } = await interiorSpan(page, z);
      const samples = await scanline(page, y, x0, x1, STEP_PX);
      expect(samples.length, `too few samples at z=${z}`).toBeGreaterThan(15);
      let worst = 0;
      for (let i = 1; i < samples.length; i += 1) {
        const a = samples[i - 1] as number[];
        const b = samples[i] as number[];
        worst = Math.max(worst, ...[0, 1, 2].map((c) => Math.abs((a[c] as number) - (b[c] as number))));
      }
      worstPerRow.push({ z, worst });
    }
    expect(
      Math.max(...worstPerRow.map((r) => r.worst)),
      `per-row worst steps: ${worstPerRow.map((r) => `z=${r.z}:${r.worst}`).join(" ")}`,
    ).toBeLessThanOrEqual(MAX_STEP);
  });

  test("screenshots the pane for the record", async () => {
    // For a person to look at, never compared to anything: the numbers above are the assertions.
    // Its twin, `pane-transparency-before.png`, was taken from the same fixture and the same camera
    // with the old winding split re-applied to the build (see MAX_STEP).
    await page.getByTestId("scene-canvas").scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.getByTestId("scene-canvas").screenshot({ path: join(ARTIFACTS, "pane-transparency-after.png") });
  });

});
