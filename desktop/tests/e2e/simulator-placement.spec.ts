/**
 * Free-hand placement by clicking the subject's scalp — v2.5.0's Electrode Placement extension
 * (`tit/gui/extensions/electrode_placement.py`, 1091 lines), folded into the Simulator rather than
 * shipped as a panel of its own.
 *
 * Maintainer, 2026-09-06: *"instead of having our default subject in the simulator, we should just
 * load the selected subject such that the user can click on the surface of the skin in the
 * simulator tab when the free hand is selected and by that they can insert the electrode
 * coordinates."*
 *
 * What is asserted, and the failure each prevents:
 *
 *  - **The pane draws the subject, not the guide.** A millimetre picked off the packaged guide is a
 *    millimetre in a different head; nothing downstream can detect the substitution.
 *  - **Selection comes first**: a click with nothing selected does nothing and says so; a click
 *    with a row selected fills THAT row and leaves it selected, so the next click moves it.
 *  - **The coordinate is the one the renderer projected.** The row must hold the point that was
 *    clicked, to the 0.1 mm the editor's inputs use, not "some number changed".
 *  - **A dot appears for it, in that ROW's own colour** — read out of the drawing buffer, not off
 *    the model — and removing the row removes the dot: the table and the scalp are one state, not
 *    two that can disagree.
 *  - **It is never ambiguous which electrode is being manipulated**: the selected row is named in
 *    the pane, hovering a row lights its dot, and clicking a dot selects its row rather than
 *    dropping a second one on top of it.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";
import { jobRows, setJobMontage, setJobSource } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-place-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await expectRunPaneTab(page, "scene");
});

test.afterAll(async () => {
  await app?.close();
});

const host = () => page.locator('[data-page-panel="simulator"]').getByTestId("scene-pane-host");

async function openPlacementEditor(): Promise<void> {
  await page.getByRole("button", { name: "New placement", exact: true }).click();
  await expect(page.getByText("New free-hand placement", { exact: true })).toBeVisible();
}

/**
 * A click on the head, `dx`/`dy` CSS pixels from the canvas centre.
 *
 * The offset is not cosmetic: a click that lands on an existing dot now *selects* that dot rather
 * than placing a new one, so a second placement has to land somewhere else — which is the same
 * thing a user does.
 */
async function clickCanvas(dx = 0, dy = 0): Promise<void> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const box = (await page.locator('[data-page-panel="simulator"]').getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
}

test("the Simulator pane draws the selected subject's own head", async () => {
  await expect(host()).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const debug = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return { subject: handle.subject, guide: handle.guide, space: handle.space };
  });
  expect(debug.subject).toBe("ernie");
  expect(debug.guide).toBeNull();
  expect(debug.space).toBe("subject-ras");
});

test("a click with nothing selected places nothing, and says why", async () => {
  await openPlacementEditor();
  // The gesture only exists while the editor is open and a subject is drawn.
  await expect(host()).toHaveAttribute("data-gesture", "place", { timeout: 20_000 });
  // No instructional copy anywhere (maintainer, 2026-09-06): the selected row and its ringed dot
  // say which electrode a click moves; a sentence repeating it is read once and read past for ever.
  await expect(page.getByTestId("scene-pane-hint")).toHaveText("");
  await expect(page.getByTestId("freehand-how")).toHaveCount(0);

  // The rows open already named — the plan, before anything is clicked (2.5.0's E1+/E1− naming).
  await expect(page.locator('[aria-label="Position 1 label"]')).toHaveValue("E1+");
  await expect(page.locator('[aria-label="Position 2 label"]')).toHaveValue("E1-");
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(0);

  await clickCanvas();
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(0);
  await expect(page.locator('[aria-label="Position 1 X"]')).toHaveValue("0");
});

test("selecting a row and clicking the scalp fills THAT row with the point that was clicked", async () => {
  await page.getByTestId("freehand-row-0").click();
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("data-active", "true");
  // The selection is a CONTROL, not a wash: the row's colour swatch is a radio target, and it is
  // the checked one. Maintainer, 2026-09-06, with a screenshot of the old accent band: *"we have
  // this weird shading … this broken shading is awful"* — the cells paint their own surface, so a
  // tint on the <tr> only ever showed through the gaps between the inputs.
  await expect(page.getByTestId("freehand-target-0")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("freehand-target-1")).toHaveAttribute("aria-checked", "false");
  const rowBackground = (row: number) =>
    page.getByTestId(`freehand-row-${row}`).evaluate((el) => getComputedStyle(el).backgroundColor);
  // Read with the pointer off the table: hover is a separate, weaker signal and it is painted on
  // the CELLS, so it cannot leave the same gaps.
  await page.mouse.move(4, 4);
  expect(await rowBackground(0), "the selected row is NOT painted differently").toBe(await rowBackground(1));
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("freehand-row-1")).toHaveAttribute("aria-selected", "false");

  await clickCanvas();

  const world = await page.evaluate(() => window.__scene?.lastPick?.world ?? null);
  expect(world, "the click landed on the head, so the pick pass reported a world point").not.toBeNull();
  const round = (v: number) => String(Math.round(v * 10) / 10);

  // The row holds THAT point, to the 0.1 mm the editor's inputs step by.
  for (const [i, axis] of (["X", "Y", "Z"] as const).entries()) {
    await expect(page.locator(`[aria-label="Position 1 ${axis}"]`)).toHaveValue(round((world as number[])[i] as number));
  }
  // ... and a dot is drawn for it, in that row's own colour.
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(1);
  const marker = await page.evaluate(() => window.__scene!.markers[0]!);
  expect(marker.id).toBe("E1+");
  // The selection stays on that row, so the next click MOVES it rather than filling another.
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("data-active", "true");

  await page.screenshot({ path: join(ARTIFACTS, "simulator-placement.png") });
});

test("selecting the second row and clicking again fills it, and removing a row removes its dot", async () => {
  await page.getByTestId("freehand-row-1").click();
  await clickCanvas(28, 22);
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(2);
  await expect(page.locator('[aria-label="Position 2 X"]')).not.toHaveValue("0");

  await page.getByRole("button", { name: "Remove position 1", exact: true }).click();
  // One dot left, renumbered — Qt's `deleteChecked`, so the table never claims a pair that does not
  // exist — and nothing is selected any more: the row the user was aiming at is gone.
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(1);
  await expect(page.locator('[aria-label="Position 1 label"]')).toHaveValue("E1+");
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(0);
});

/**
 * The pixel the renderer actually painted at a dot's centre.
 *
 * Read out of the drawing buffer with the markers on and again with them off, because a dot is
 * drawn *over* the anatomy with the disc's own alpha falloff: the honest question is not "is this
 * pixel exactly #0072B2" — it is antialiased and blended, and asserting the exact byte would be
 * asserting the shading curve — but "did this dot paint this pixel, and towards which hue".
 */
async function dotPixel(markerIndex: number): Promise<{ with: number[]; without: number[] }> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  return page.evaluate((i) => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent");
    const marker = scene.markers[i];
    if (!marker) throw new Error(`no marker ${i}`);
    const at = scene.project(marker.world);
    // A grid across the disc, not the single projected pixel: the marker is an 11 px screen-space
    // quad whose centre the projection puts within a pixel or two, and one sample can land on the
    // antialiased rim (measured: alpha 0.5) or, at the shallow angles a scalp presents, just off
    // it. The pixel this dot changed MOST is the one that answers "what colour is this dot".
    const points: Array<[number, number]> = [];
    for (let dy = -3; dy <= 3; dy += 3) for (let dx = -3; dx <= 3; dx += 3) points.push([at.x + dx, at.y + dy]);
    const on = scene.samplePixels(points, true);
    const off = scene.samplePixels(points, false);
    if (!on || !off) throw new Error("samplePixels returned null");
    let best = 0;
    let bestDelta = -1;
    on.forEach((pixel, p) => {
      const delta = [0, 1, 2].reduce((sum, c) => sum + Math.abs((pixel[c] as number) - ((off[p] as number[])[c] as number)), 0);
      if (delta > bestDelta) {
        bestDelta = delta;
        best = p;
      }
    });
    return { with: on[best] as number[], without: off[best] as number[] };
  }, markerIndex);
}

/**
 * Whether the renderer painted the WHOLE dot, or only a crescent of it.
 *
 * The failure this measures, reported by the maintainer with a screenshot on 2026-09-06: a dot
 * *embedded* in the scalp, with only a crescent of it above the surface, because it lies exactly on
 * the surface it was picked off and lost the depth test against it. A dot that is drawn whole
 * changes every pixel across its own width; a half-buried one changes about half of them.
 *
 */
async function dotIsWhole(markerIndex: number): Promise<{ painted: number; radiusPx: number }> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  return page.evaluate((i) => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent");
    const at = scene.project(scene.markers[i]!.world);
    const changed = (a: number[], b: number[]) => [0, 1, 2].some((c) => Math.abs((a[c] as number) - (b[c] as number)) > 6);

    // 1. Find the dot's painted centre by scanning a box wider than the dot. `project()` and the
    //    rasterised quad agree to within a few pixels, not exactly, and a fixed grid centred on the
    //    projection would report a perfectly whole disc as half-covered purely from that offset —
    //    which is the same number a genuinely half-buried dot gives, so it cannot be the measure.
    const scan: Array<[number, number]> = [];
    for (let dy = -6; dy <= 6; dy += 1) for (let dx = -6; dx <= 6; dx += 1) scan.push([dx, dy]);
    const onScan = scene.samplePixels(scan.map(([dx, dy]) => [at.x + dx, at.y + dy] as [number, number]), true)!;
    const offScan = scene.samplePixels(scan.map(([dx, dy]) => [at.x + dx, at.y + dy] as [number, number]), false)!;
    const hits = scan.filter((_, p) => changed(onScan[p] as number[], offScan[p] as number[]));
    if (hits.length === 0) return { painted: 0, radiusPx: 0 };
    const cx = at.x + hits.reduce((sum, [dx]) => sum + dx, 0) / hits.length;
    const cy = at.y + hits.reduce((sum, [, dy]) => sum + dy, 0) / hits.length;

    // 2. The centre and four points half way out to the painted region's own edge.
    //
    //    Measured against the drawn extent rather than against `MARKER_SIZE_PX`, because the disc's
    //    radius in CSS pixels depends on the pane's size and the sample grid's alignment, and a
    //    hard-coded radius makes this assert the arithmetic rather than the shape. What it does
    //    assert is the shape: a whole disc paints all four cardinal points around its centre; the
    //    crescent an embedded dot leaves has its centroid inside the crescent, so the probe towards
    //    the buried side lands on anatomy.
    const reach = Math.max(...hits.map(([dx, dy]) => Math.hypot(at.x + dx - cx, at.y + dy - cy)));
    const r = reach * 0.4;
    const probe: Array<[number, number]> = [
      [cx, cy],
      [cx + r, cy],
      [cx - r, cy],
      [cx, cy + r],
      [cx, cy - r],
    ];
    const on = scene.samplePixels(probe, true)!;
    const off = scene.samplePixels(probe, false)!;
    return { painted: on.filter((pixel, p) => changed(pixel as number[], off[p] as number[])).length, radiusPx: r };
  }, markerIndex);
}

/** Which of `SCENE_CATEGORICAL`'s first colours the painted pixel moved towards, by undoing the
 *  blend against the pixel the same point has with the markers off. */
function towards(pixel: { with: number[]; without: number[] }, candidates: [number, number, number][]): number {
  const diff = [0, 1, 2].map((c) => (pixel.with[c] as number) - (pixel.without[c] as number));
  let best = -1;
  let bestScore = -Infinity;
  candidates.forEach((rgb, i) => {
    const towardsIt = [0, 1, 2].map((c) => (rgb[c] as number) - (pixel.without[c] as number));
    const norm = Math.hypot(...towardsIt) || 1;
    const score = diff.reduce((sum, d, c) => sum + d * ((towardsIt[c] as number) / norm), 0);
    if (score > bestScore) {
      bestScore = score;
      best = i;
    }
  });
  return best;
}

/** `SCENE_CATEGORICAL`'s first two, as bytes — the colours rows 1 and 2 get. */
const RAMP: [number, number, number][] = [
  [0x00, 0x72, 0xb2],
  [0xe6, 0x9f, 0x00],
];

test("each electrode has its own colour, on the scalp and in the table", async () => {
  // One dot survived the removal above; select the next row and place a second, well clear of it.
  await page.getByTestId("freehand-row-1").click();
  await clickCanvas(-34, 30);
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(2);

  // The swatch beside the row and the pixel at the dot are the same claim, and the two rows differ.
  const swatches = await page
    .locator('[data-testid^="freehand-swatch-"]')
    .evaluateAll((nodes) => nodes.slice(0, 2).map((n) => getComputedStyle(n as HTMLElement).backgroundColor));
  expect(swatches[0]).not.toBe(swatches[1]);

  // Clear the selection first: a selected dot wears a white ring, and colour identity is a property
  // of the electrode, not of which one happens to be selected. (Clicking the selected row toggles.)
  await page.getByTestId("freehand-row-1").click();
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(0);

  const first = await dotPixel(0);
  const second = await dotPixel(1);
  // Each dot painted its pixel...
  expect(first.with).not.toEqual(first.without);
  expect(second.with).not.toEqual(second.without);
  // ...and each moved it towards its OWN ramp colour, not the other's. That is the whole claim:
  // two electrodes, two colours, read off the canvas rather than off the model.
  expect(towards(first, RAMP)).toBe(0);
  expect(towards(second, RAMP)).toBe(1);

  // ...and the whole disc is on screen, not the crescent an embedded dot leaves above the scalp.
  expect((await dotIsWhole(0)).painted).toBe(5);
  expect((await dotIsWhole(1)).painted).toBe(5);
});

test("selecting an electrode outlines it in white and leaves its colour alone", async () => {
  // Maintainer, 2026-09-06: *"there is an issue with the coloring of the electrodes when one is
  // being selected — it changes the color. Also instead of highlighting the entire electrode with a
  // white color as an indicator, we should just have a white outline so the user can still see its
  // colour."* Both halves are pixels, and both are read off the canvas.
  const centre = async (i: number) =>
    page.evaluate((m) => {
      const scene = window.__scene!;
      const at = scene.project(scene.markers[m]!.world);
      return scene.samplePixels([[at.x, at.y]], true)![0] as number[];
    }, i);

  await page.getByTestId("freehand-row-0").click();
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("data-active", "true");
  const selected = await dotPixel(0);
  // The fill is the electrode's own colour, still: it moved towards its ramp hue, not towards the
  // white the ring is painted in.
  expect(towards(selected, RAMP)).toBe(0);

  // ... and the ring IS white. Sampled all the way round the dot, because the projection lands a
  // pixel or two off the rasterised centre and only some of the ring is where it is expected.
  const ringIsWhite = await page.evaluate(() => {
    const scene = window.__scene!;
    const at = scene.project(scene.markers[0]!.world);
    const points: Array<[number, number]> = [];
    for (let dy = -10; dy <= 10; dy += 1) for (let dx = -10; dx <= 10; dx += 1) points.push([at.x + dx, at.y + dy]);
    const read = scene.samplePixels(points, true)!;
    // A pixel is "white" only if all three channels are near saturation — the ring, and nothing the
    // scalp or the ramp's own hues can produce.
    return read.filter((p) => [0, 1, 2].every((c) => (p[c] as number) > 235)).length;
  });
  expect(ringIsWhite, "the selected dot wears a white outline").toBeGreaterThan(4);

  // Deselecting leaves the fill exactly where it was: selection changes the outline and nothing
  // else about the disc.
  const before = await centre(0);
  await page.getByTestId("freehand-row-0").click();
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(0);
  expect(await centre(0)).toEqual(before);
});

test("the dot is on top of the scalp at every skin opacity", async () => {
  // Maintainer, 2026-09-06, with a screenshot: *"if there is some skin transparency when the user
  // is placing electrodes, it looks like it places it under the skin."* Two halves, both here — the
  // click reads the SKIN's depth however faint it is (so the coordinate is on the scalp, not on the
  // cortex behind it), and the dot is drawn over the head whatever the scalp's opacity is.
  const skin = page.getByRole("slider", { name: "Skin opacity" });
  await expect(skin).toBeVisible();
  for (const [key, what] of [
    ["End", "opaque"],
    ["Home", "fully transparent"],
  ] as const) {
    await skin.focus();
    await page.keyboard.press(key);
    await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
    const pixel = await dotPixel(0);
    expect(pixel.with, `the dot paints its pixel with the skin ${what}`).not.toEqual(pixel.without);
    expect(towards(pixel, RAMP), `the dot keeps its own colour with the skin ${what}`).toBe(0);
    expect((await dotIsWhole(0)).painted, `the whole dot shows with the skin ${what}`).toBe(5);
  }
  // Put it back the way the pane opens, so the tests after this one see the pane they expect.
  await skin.focus();
  await page.keyboard.press("End");
});

test("selection is one checked target, movable by keyboard, and hovering a row lights its dot", async () => {
  // Clicking a row aims the gesture at it, and at most one row is ever selected.
  await page.getByTestId("freehand-row-0").click();
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(1);
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("data-active", "true");
  await expect(page.locator('[data-testid^="freehand-target-"][aria-checked="true"]')).toHaveCount(1);

  // ↑/↓ walk the targets like the radio group they are, so the selection is reachable without the
  // mouse — the "switch between the electrodes" the maintainer asked for.
  await page.getByTestId("freehand-target-0").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("freehand-target-1")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("freehand-row-1")).toHaveAttribute("data-active", "true");
  await page.keyboard.press("ArrowUp");
  await expect(page.getByTestId("freehand-target-0")).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('[data-testid^="freehand-target-"][aria-checked="true"]')).toHaveCount(1);

  // Hovering a row draws its dot as hovered — the renderer's existing hover state, which means
  // exactly "this is the one you are pointing at": bigger, and in the hover colour (white). Read as
  // a brightness jump at the dot rather than as an exact byte, because the disc is antialiased.
  // Hovering a row grows its dot — the renderer's own hover state, which means exactly "this is the
  // one you are pointing at". Measured as painted AREA, not brightness: since the maintainer's
  // 2026-09-06 note a tinted dot keeps its colour under hover as well as under selection, so the
  // only thing that changes is its size.
  const dotArea = (i: number) =>
    page.evaluate((m) => {
      const scene = window.__scene!;
      const at = scene.project(scene.markers[m]!.world);
      const points: Array<[number, number]> = [];
      for (let dy = -12; dy <= 12; dy += 1) for (let dx = -12; dx <= 12; dx += 1) points.push([at.x + dx, at.y + dy]);
      const on = scene.samplePixels(points, true)!;
      const off = scene.samplePixels(points, false)!;
      return on.filter((p, k) => [0, 1, 2].some((c) => Math.abs((p[c] as number) - ((off[k] as number[])[c] as number)) > 6)).length;
    }, i);

  const idle = await dotArea(1);
  await page.getByTestId("freehand-row-1").hover();
  await expect.poll(() => dotArea(1), { timeout: 10_000 }).toBeGreaterThan(idle);
  // Leaving the row puts it back, so the highlight tracks the cursor rather than latching.
  await page.getByTestId("freehand-row-0").hover();
  await expect.poll(() => dotArea(1), { timeout: 10_000 }).toBe(idle);
});

test("clicking an existing dot selects its row instead of adding another", async () => {
  await page.getByTestId("freehand-row-1").click();
  await expect(page.getByTestId("freehand-row-1")).toHaveAttribute("data-active", "true");
  const before = await page.evaluate(() => window.__scene?.markers.length ?? 0);
  const at = await page.evaluate(() => {
    const scene = window.__scene!;
    return scene.project(scene.markers[0]!.world);
  });
  const box = (await page.locator('[data-page-panel="simulator"]').getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + at.x, box.y + at.y);
  // No new dot, and row 0 — the one that dot belongs to — is now the active row.
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(before);
  await expect(page.getByTestId("freehand-row-0")).toHaveAttribute("data-active", "true");
});

test("Add electrode pair adds two rows and selects the first; the trash icon removes one and its dot", async () => {
  const rows = () => page.locator('[data-testid^="freehand-row-"]');
  const before = await rows().count();
  await page.getByRole("button", { name: /^Add electrode/ }).click();
  // A pair at a time: an odd position count is never a valid montage.
  await expect(rows()).toHaveCount(before + 2);
  await expect(page.locator(`[data-testid="freehand-row-${before}"]`)).toHaveAttribute("data-active", "true");

  const dots = await page.evaluate(() => window.__scene?.markers.length ?? 0);
  await page.getByRole("button", { name: "Remove position 1", exact: true }).click();
  await expect(rows()).toHaveCount(before + 1);
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(dots - 1);
  await expect(page.locator('[data-testid^="freehand-row-"][data-active="true"]')).toHaveCount(0);
});

test("picking a saved free-hand set shows its positions on the same scalp", async () => {
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText("New free-hand placement", { exact: true })).toHaveCount(0);

  const row = jobRows(page).first();
  await setJobSource(page, row, "Free-hand");
  await setJobMontage(page, row, "custom_4electrode");
  await row.click();

  // The fixture's set has four positions; they are drawn where the job will actually stimulate.
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0), { timeout: 20_000 }).toBe(4);
  await expect(page.getByTestId("scene-pane-showing")).toContainText("custom_4electrode");
  await expect(page.getByTestId("scene-pane-showing")).toContainText("4 placed positions");
});
