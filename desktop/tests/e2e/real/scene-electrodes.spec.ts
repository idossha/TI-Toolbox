/**
 * The run-page pane against the **real** server, the real packaged guide and real electrode
 * positions — read out of the drawing buffer, not off a screenshot (NR gate, plan §3).
 *
 * Every number below is measured from pixels the GPU actually wrote:
 *
 *  1. an idle electrode is the palette's neutral grey, and toggling it into a pair repaints THAT
 *     marker in its channel's Okabe-Ito hue — colour is the whole state signal;
 *  2. selecting adds **no ring**: the changed pixels are one solid disc with the idle marker's own
 *     bounding box, self-calibrated by a radial profile rather than by assuming a device pixel
 *     ratio. A selection ring is by construction a non-zero band *after* a zero one;
 *  3. a selected atlas region is painted in the ROI tint and an unselected one is not;
 *  4. a warm first paint is ≤ 300 ms and orbiting a 145 k-triangle head holds its frame budget at
 *     1280 px.
 *
 * Run it with `--project=real` (`TIT_E2E_SERVER_URL` + `TIT_E2E_TOKEN`), offscreen. It submits no
 * job and writes nothing to the project.
 */
import { expect, test, type Page } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, selectSubject } from "../_helpers";
import { SCENE_PALETTE } from "../../../src/renderer/scene/palette";

// The option label is the net's real filename, as everywhere else in the app.
const NET = process.env.TIT_E2E_NET ?? "GSN-HydroCel-185.csv";
/** Every probe was measured to sit within this of the palette colour: the marker shader's own
 *  centre term is exactly 1.0, so the only slack is the 8-bit round trip and the alpha edge. */
const COLOUR_TOLERANCE = 12;
/** The pane's budget: a warm paint of the packaged guide. */
const FIRST_PAINT_BUDGET_MS = 300;

const rgb255 = (c: readonly number[]): number[] => c.map((v) => Math.round(v * 255));
const delta = (a: number[], b: number[]): number =>
  Math.max(...[0, 1, 2].map((i) => Math.abs((a[i] as number) - (b[i] as number))));

async function settled(page: Page): Promise<void> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 30_000 });
}

/** The marker nearest the eye, with its projection — an electrode round the back of the head is
 *  hidden by the scalp by design, so "any visible one" is not good enough. */
async function frontMarker(page: Page, exclude: string[] = []): Promise<{ index: number; id: string; x: number; y: number }> {
  return page.evaluate((skip: string[]) => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — build out/ with VITE_SCENE_HOOKS=1");
    const cam = scene.camera as { target: number[]; distance: number; yaw: number; pitch: number };
    const cp = Math.cos(cam.pitch);
    const eye = [
      (cam.target[0] as number) + cam.distance * cp * Math.sin(cam.yaw),
      (cam.target[1] as number) + cam.distance * cp * Math.cos(cam.yaw),
      (cam.target[2] as number) + cam.distance * Math.sin(cam.pitch),
    ];
    const ranked = scene.markers
      .map((marker, index) => ({
        index,
        id: marker.id,
        projection: scene.project(marker.world),
        d: Math.hypot(
          marker.world[0] - (eye[0] as number),
          marker.world[1] - (eye[1] as number),
          marker.world[2] - (eye[2] as number),
        ),
      }))
      .filter((c) => c.projection.inFront && !skip.includes(c.id))
      .sort((a, b) => a.d - b.d);
    const best = ranked[0];
    if (!best) throw new Error("no marker in front of the camera");
    return { index: best.index, id: best.id, x: best.projection.x, y: best.projection.y };
  }, exclude);
}

/** RGBA at one canvas CSS point, from the drawing buffer of a freshly rendered frame. */
async function pixelAt(page: Page, x: number, y: number, withMarkers = true): Promise<number[]> {
  const read = await page.evaluate(
    ([px, py, wm]) => window.__scene?.samplePixels([[px as number, py as number]], wm as boolean) ?? null,
    [x, y, withMarkers] as const,
  );
  if (!read?.[0]) throw new Error("samplePixels returned nothing — is the renderer mounted?");
  return read[0];
}

/**
 * The radial profile of the pixels that changed between two frames, in 1 px bins from the centre:
 * `profile[r]` is how many pixels at radius r differ. A solid disc falls to zero and stays there; a
 * ring is a non-zero bin AFTER a zero one, which is what this exists to detect without knowing the
 * device pixel ratio or the marker's size in advance.
 */
async function changedProfile(
  page: Page,
  cx: number,
  cy: number,
  radius: number,
  mutate: () => Promise<void>,
): Promise<{ profile: number[]; changed: number; box: [number, number, number, number] }> {
  const points: [number, number][] = [];
  for (let dy = -radius; dy <= radius; dy += 1) {
    for (let dx = -radius; dx <= radius; dx += 1) points.push([cx + dx, cy + dy]);
  }
  const before = await page.evaluate((pts) => window.__scene?.samplePixels(pts as [number, number][]) ?? null, points);
  await mutate();
  const after = await page.evaluate((pts) => window.__scene?.samplePixels(pts as [number, number][]) ?? null, points);
  if (!before || !after) throw new Error("samplePixels returned nothing");
  const profile = new Array<number>(radius + 2).fill(0);
  let changed = 0;
  const box: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  points.forEach((point, i) => {
    if (delta(before[i] as number[], after[i] as number[]) <= 2) return;
    changed += 1;
    const dx = (point[0] as number) - cx;
    const dy = (point[1] as number) - cy;
    const r = Math.round(Math.hypot(dx, dy));
    if (r < profile.length) profile[r] = (profile[r] as number) + 1;
    box[0] = Math.min(box[0], dx);
    box[1] = Math.min(box[1], dy);
    box[2] = Math.max(box[2], dx);
    box[3] = Math.max(box[3], dy);
  });
  return { profile, changed, box };
}

test("an electrode's colour is its whole state, and selecting it adds no ring", async () => {
  test.setTimeout(180_000);
  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1280, height: 900 });
    await connectReal(page);
    await selectSubject(page, process.env.TIT_E2E_SUBJECT ?? "ernie");
    await gotoPage(page, "simulator");
    const panel = page.locator('[data-page-panel="simulator"]');
    // One row is one job since 2026-09-06; the net is the row's own cell.
    await panel.locator("tr[data-job-row]").first().locator('td[data-cell="net"]').getByRole("combobox").click();
    await page.getByRole("option", { name: NET, exact: true }).click();
    await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 60_000 });
    await settled(page);

    // Prime the pair editor with ONE electrode before measuring anything. Placing the first one
    // makes the channel legend appear above the pane, which shortens the canvas and reframes the
    // camera — every marker then projects somewhere else, and a before/after pixel pair straddling
    // that reflow compares two different points on the head. With a channel already present the
    // second placement changes colour and nothing else, which is the claim under test.
    const primingBox = await panel.getByTestId("scene-canvas").boundingBox();
    if (!primingBox) throw new Error("the scene canvas has no bounding box");
    const priming = await frontMarker(page);
    await page.mouse.click(primingBox.x + priming.x, primingBox.y + priming.y);
    await expect(panel.locator(".electrode-pair-row").first().getByRole("combobox").first()).toContainText(priming.id, {
      timeout: 15_000,
    });
    await page.mouse.move(primingBox.x + 4, primingBox.y + 4);
    await settled(page);

    const marker = await frontMarker(page, [priming.id]);
    const idle = await pixelAt(page, marker.x, marker.y);
    const background = await pixelAt(page, marker.x, marker.y, false);
    // The marker is really painted here: with the marker pass suppressed the same pixel is the
    // anatomy behind it, so this is a difference between two frames and not a colour model.
    expect(delta(idle, background), "no marker is painted at the projected point").toBeGreaterThan(20);
    expect(delta(idle, rgb255(SCENE_PALETTE.idle)), `idle marker ${JSON.stringify(idle)}`).toBeLessThanOrEqual(
      COLOUR_TOLERANCE,
    );

    const box = await panel.getByTestId("scene-canvas").boundingBox();
    if (!box) throw new Error("the scene canvas has no bounding box");
    const profile = await changedProfile(page, marker.x, marker.y, 40, async () => {
      await page.mouse.click(box.x + marker.x, box.y + marker.y);
      await expect(panel.locator(".electrode-pair-row").first()).toContainText(marker.id, { timeout: 15_000 });
      // Park the cursor off the marker before the "after" frame: hover paints white (it is the
      // renderer's only other per-marker colour), so a pointer left where it clicked would make
      // every one of these pixels measure hover feedback instead of selection.
      await page.mouse.move(box.x + 4, box.y + 4);
      await page.waitForTimeout(150);
    });
    // The before/after pair is only a colour measurement if the geometry stayed put: a reflow that
    // moved the camera would make every "changed" pixel a change of subject, not of state.
    const after = await frontMarker(page, [priming.id]);
    expect(Math.hypot(after.x - marker.x, after.y - marker.y), "the pane reflowed under the click").toBeLessThan(1);

    const selected = await pixelAt(page, marker.x, marker.y);
    const channel0 = rgb255(SCENE_PALETTE.channels[0] as number[]);
    expect(delta(selected, channel0), `selected marker ${JSON.stringify(selected)} vs ${channel0}`).toBeLessThanOrEqual(
      COLOUR_TOLERANCE,
    );

    // No ring: the changed pixels are one solid disc. Once the profile reaches zero it stays zero.
    const firstZero = profile.profile.findIndex((count, r) => r > 0 && count === 0);
    expect(firstZero, "the changed pixels never reach a zero radius").toBeGreaterThan(0);
    expect(
      profile.profile.slice(firstZero).every((count) => count === 0),
      `a non-zero band after a zero one is a ring: ${JSON.stringify(profile.profile)}`,
    ).toBe(true);
    // ...and the footprint did not grow: selection changed the hue and nothing else.
    expect(Math.max(-profile.box[0], -profile.box[1], profile.box[2], profile.box[3])).toBeLessThan(firstZero + 1);
    console.log(
      `REAL-SCENE electrode ${marker.id}: idle=${JSON.stringify(idle)} selected=${JSON.stringify(selected)} ` +
        `changed=${profile.changed} px, solid to r=${firstZero}, profile=${JSON.stringify(profile.profile.slice(0, firstZero + 3))}`,
    );
  } finally {
    await app.close();
  }
});

test("a selected atlas region is painted in its own .annot colour, and the pane holds its budgets", async () => {
  test.setTimeout(180_000);
  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1280, height: 900 });
    await connectReal(page);
    await selectSubject(page, process.env.TIT_E2E_SUBJECT ?? "ernie");
    await gotoPage(page, "optimizer");
    const panel = page.locator('[data-page-panel="optimizer"]');
    await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "Flex", exact: true }).click();
    await panel.getByRole("radio", { name: "Cortical", exact: true }).click();
    await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 60_000 });
    await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-gesture", "region");
    await settled(page);

    // Warm: this pane is the second one this session to ask for the same immutable payloads, so
    // nothing here is a cold download. What is being budgeted is decode + upload + first frame.
    const firstPaint = await page.evaluate(() => window.__scenePane?.firstPaintMs ?? null);
    expect(firstPaint, "the pane never reported a first paint").not.toBeNull();
    expect(firstPaint!, `warm first paint ${firstPaint} ms`).toBeLessThanOrEqual(FIRST_PAINT_BUDGET_MS);

    const box = await panel.getByTestId("scene-canvas").boundingBox();
    if (!box) throw new Error("the scene canvas has no bounding box");
    const cx = box.width / 2;
    const cy = box.height / 2;
    const before = await pixelAt(page, cx, cy);
    await page.mouse.click(box.x + cx, box.y + cy);
    await expect.poll(() => page.evaluate(() => (window.__scenePane?.selectedRegions ?? []).length)).toBeGreaterThan(0);
    await page.waitForTimeout(150);
    const after = await pixelAt(page, cx, cy);
    expect(delta(before, after), "selecting a region repainted nothing").toBeGreaterThan(10);

    // **The selected region is painted in its OWN atlas colour** — the one the `.annot` colour
    // table gives it — not in one flat blue for all 70 regions. The expected value is read from the
    // pane's own legend, which is the same `legend[].color` the shader's colour texture was packed
    // from, so this closes the loop from the annotation file to the pixel.
    const picked = await page.evaluate(() => window.__scenePane?.selectedRegions[0] ?? null);
    expect(picked, "nothing was selected").not.toBeNull();
    const hex = await page.evaluate(
      (region) =>
        window.__scenePane?.legend.find((row) => row.id === region!.id && row.hemi === region!.hemi)?.color ?? null,
      picked,
    );
    expect(hex, `the legend has no colour for ${picked?.name}/${picked?.hemi}`).toMatch(/^#[0-9a-f]{6}$/);
    const own = [1, 3, 5].map((i) => parseInt((hex as string).slice(i, i + 2), 16));

    // The comparison is on **chroma direction**, not on the raw triple, and that is not a dodge —
    // it is the only thing the renderer promises. A fragment is lit (a lambert term and a fresnel
    // silhouette boost) and then blended under a translucent scalp, both of which move every
    // channel towards white by an amount that depends on where on the head the click landed:
    // measured here, the atlas' #4b327d [75,50,125] reaches the screen as [150,137,169]. What
    // survives all of that is the *direction* of the colour away from grey — which is exactly what
    // "this region is purple and that one is green" means to a person.
    const chroma = (p: readonly number[]): number[] => {
      const mean = (p[0]! + p[1]! + p[2]!) / 3;
      return [p[0]! - mean, p[1]! - mean, p[2]! - mean];
    };
    const cosine = (p: readonly number[], q: readonly number[]): number => {
      const a = chroma(p);
      const b = chroma(q);
      const dot = a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
      const na = Math.hypot(...a);
      const nb = Math.hypot(...b);
      return na < 1e-6 || nb < 1e-6 ? 0 : dot / (na * nb);
    };

    const toOwn = cosine(after, own);
    expect(toOwn, `selected pixel ${JSON.stringify(after)} is not the hue of its atlas colour ${hex}`).toBeGreaterThan(
      0.9,
    );

    // …and it is that hue rather than the flat ROI blue this change replaced, which is the whole
    // point. Skipped for the handful of parcels whose ctab entry is itself a blue near the accent:
    // asserting there would be asserting a coincidence, not a behaviour.
    const flat = rgb255(SCENE_PALETTE.selected as number[]);
    const toFlat = cosine(after, flat);
    if (cosine(own, flat) < 0.9) {
      expect(toOwn, `pixel hue matches the flat ROI blue (${toFlat.toFixed(3)}) better than ${hex}`).toBeGreaterThan(
        toFlat,
      );
    }

    // Selecting saturates: at rest a labelled region already carries its atlas hue, desaturated so
    // the cortex reads as anatomy, and selection takes it to full. So the change on click is a
    // change in chroma *magnitude*, not in direction — which is why the assertion above is about
    // direction and this one is about length.
    const chromaLen = (p: readonly number[]): number => Math.hypot(...chroma(p));
    expect(chromaLen(after), "selecting a region did not saturate it").toBeGreaterThan(chromaLen(before));

    console.log(
      `REAL-SCENE region ${picked?.name}/${picked?.hemi}: ${JSON.stringify(before)} -> ${JSON.stringify(after)} ` +
        `(atlas colour ${hex} = ${JSON.stringify(own)}, cos to own ${toOwn.toFixed(3)}, ` +
        `cos to flat blue ${toFlat.toFixed(3)}), warm first paint ${firstPaint} ms`,
    );

    // Orbit at 1280: a drag across the canvas, then the renderer's own frame counter.
    await page.mouse.move(box.x + cx, box.y + cy);
    await page.mouse.down();
    for (let i = 1; i <= 40; i += 1) await page.mouse.move(box.x + cx + i * 4, box.y + cy + (i % 7));
    await page.mouse.up();
    await settled(page);
    const stats = await page.evaluate(() => ({
      fps: window.__scene?.fps ?? 0,
      lastFrameMs: window.__scene?.stats.lastFrameMs ?? 0,
      triangles: window.__scene?.stats.triangles ?? 0,
    }));
    console.log(`REAL-SCENE orbit at 1280: ${stats.fps} fps, last frame ${stats.lastFrameMs.toFixed(2)} ms CPU, ${stats.triangles} triangles`);
    expect(stats.triangles).toBeGreaterThan(200_000);
    // 30 fps is the plan's floor for an interactive pane (S8); the CPU side of a submit is the
    // half this process controls, and it must leave room for the GPU inside a 16.7 ms frame.
    expect(stats.fps).toBeGreaterThanOrEqual(30);
    expect(stats.lastFrameMs).toBeLessThan(16.7);
  } finally {
    await app.close();
  }
});
