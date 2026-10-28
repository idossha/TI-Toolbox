/**
 * EEG electrodes stand ON an opaque scalp, whole, touching it at the silhouette (2026-10-28).
 *
 * The maintainer's report: in the Simulator's scene pane, with the skin slider at full opacity,
 * every electrode was drawn as a half-disc and those on the silhouette nearly vanished; a first fix
 * lifted screen-facing dots off the scalp, which made them float. Electrodes are now the exporter's
 * electrode model, instanced on the skin (`electrodePose.ts`, `electrodeModel.ts`, `glScene.ts`).
 *
 * The mock serves the guide's skin as an ellipsoid with the net's electrodes exactly ON it
 * (`sceneElectrodePositions` in `tests/mock-server/server.mjs`), so the outward normal at each
 * electrode is the ellipsoid's, p / r^2 — computed here from the manifest's skin bbox, never read
 * back from the renderer. Pixels are classified either side of one switch: `samplePixels` renders
 * the same frame with and without the marker pass, so a pixel no electrode fragment won is
 * byte-identical in both, and a pixel that is the clear colour in the no-marker frame is empty
 * space, not skin.
 *
 * The second test is the **Actual size** switch: off, an electrode in a pair is the small cap
 * marker in its channel colour and the rest of the net is drawn; on, only the montage is drawn and
 * each of its electrodes at the job's electrode width, following the Simulator's **Job settings ▸
 * Electrode width** live — measured against the CPU projection of the configured millimetres, and
 * as a ratio between two widths.
 *
 * The third: with **Electrode names** on, every name shown sits on an electrode the frame drew,
 * with Actual size off and on (a name follows the scalp normal at its electrode, which is what the
 * depth test hides it by), and the two switches share one wrapping row.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { waitForScene } from "./_runPane";
import { cameraBasis, projectToCanvas, type OrbitCamera, type Vec3 } from "../../src/renderer/scene/camera";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const NET = "GSN-HydroCel-185";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-electrodes-opaque-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await page.locator("tr[data-montage-row]").first().locator('td[data-cell="net"]').getByRole("combobox").click();
  await page.getByRole("option", { name: NET, exact: true }).click();
  await waitForScene(page);
});

test.afterAll(async () => {
  await app?.close();
});

type Px = [number, number];

test("at full skin opacity every electrode is visible and touches the scalp, silhouette included", async () => {
  const active = page.locator('[data-page-active="true"]');
  const skin = active.getByRole("slider", { name: "Skin opacity", exact: true });
  await skin.focus();
  await page.keyboard.press("End");
  await expect(skin).toHaveAttribute("aria-valuenow", "100");
  await page.mouse.move(0, 0); // no hover: a hovered electrode is drawn larger
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });

  const manifest = (await (
    await fetch(new URL("/api/guide/manifest", SERVER_URL), { headers: { Authorization: `Bearer ${TOKEN}` } })
  ).json()) as { parts: Array<{ id: string; bbox: number[] }> };
  const bbox = manifest.parts.find((p) => p.id === "skin")!.bbox;
  const radii = [0, 1, 2].map((i) => (bbox[i + 3]! - bbox[i]!) / 2);

  const state = await page.evaluate(() => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — build out/ with VITE_SCENE_HOOKS=1");
    return { camera: scene.camera, canvas: scene.canvas, markers: scene.markers };
  });
  expect(state.markers.length).toBe(185);
  const camera = state.camera as OrbitCamera;
  const { widthCss, heightCss } = state.canvas;
  const { eye } = cameraBasis(camera);
  const project = (p: Vec3) => projectToCanvas(camera, p, widthCss, heightCss);
  const along = (p: Vec3, n: Vec3, mm: number): Vec3 => [p[0] + n[0] * mm, p[1] + n[1] * mm, p[2] + n[2] * mm];

  const electrodes = state.markers.map((m) => {
    const p = m.world as Vec3;
    const g = [0, 1, 2].map((i) => p[i]! / radii[i]! ** 2);
    const gl = Math.hypot(g[0]!, g[1]!, g[2]!);
    const n: Vec3 = [g[0]! / gl, g[1]! / gl, g[2]! / gl];
    const toEye = [0, 1, 2].map((i) => eye[i]! - p[i]!);
    const cos = (n[0] * toEye[0]! + n[1] * toEye[1]! + n[2] * toEye[2]!) / Math.hypot(toEye[0]!, toEye[1]!, toEye[2]!);
    const mid = project(along(p, n, 1.5)); // halfway up the 3 mm-tall model, on its axis
    return { index: m.index, p, n, cos, mid };
  });
  const inside = (q: { x: number; y: number }) => q.x > 20 && q.y > 20 && q.x < widthCss - 20 && q.y < heightCss - 20;
  const isolated = (e: (typeof electrodes)[number]) =>
    electrodes.every((o) => o.index === e.index || o.cos < -0.2 || Math.hypot(o.mid.x - e.mid.x, o.mid.y - e.mid.y) > 14);
  const faceOn = electrodes.filter((e) => e.cos > 0.3 && inside(e.mid) && isolated(e));
  // Seen edge-on: the scalp normal within ~17 degrees of the screen plane.
  const silhouette = electrodes.filter((e) => e.cos > 0 && e.cos < 0.3 && inside(e.mid) && isolated(e));
  expect(faceOn.length, "face-on electrodes to sample").toBeGreaterThanOrEqual(10);
  expect(silhouette.length, "silhouette electrodes to sample").toBeGreaterThanOrEqual(3);

  // Silhouette: walk the screen projection of each electrode's axis from 1 mm inside the scalp to
  // 2 mm out (the model is 3 mm tall), in half-pixel steps.
  const walks = silhouette.map((e) => {
    const a = project(along(e.p, e.n, -1));
    const b = project(along(e.p, e.n, 2));
    const steps = Math.max(2, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) * 2));
    return Array.from({ length: steps + 1 }, (_, k) => [a.x + ((b.x - a.x) * k) / steps, a.y + ((b.y - a.y) * k) / steps] as Px);
  });
  const points: Px[] = [[1, 1], ...faceOn.map((e) => [e.mid.x, e.mid.y] as Px), ...walks.flat()];
  const withMarkers = await page.evaluate((pts) => window.__scene?.samplePixels(pts, true) ?? null, points);
  const without = await page.evaluate((pts) => window.__scene?.samplePixels(pts, false) ?? null, points);
  if (!withMarkers || !without) throw new Error("samplePixels returned null — no renderer or no camera");
  const diff = (a: number[], b: number[]) => Math.max(...[0, 1, 2].map((c) => Math.abs(a[c]! - b[c]!)));
  const background = without[0]!;
  const isElectrode = (i: number) => diff(withMarkers[i]!, without[i]!) > 0;
  const isSkin = (i: number) => diff(without[i]!, background) > 2;

  faceOn.forEach((e, k) => {
    expect(isElectrode(1 + k), `face-on electrode ${e.index} at (${e.mid.x.toFixed(0)}, ${e.mid.y.toFixed(0)}) is drawn`).toBe(true);
  });

  let offset = 1 + faceOn.length;
  const report: string[] = [];
  silhouette.forEach((e, k) => {
    const walk = walks[k]!;
    const kinds = walk.map((_, j) => (isElectrode(offset + j) ? "E" : isSkin(offset + j) ? "s" : "."));
    offset += walk.length;
    report.push(`${e.index}:${kinds.join("")}`);
    // The electrode is there, and between the scalp and it there is no empty space: from the first
    // sample (inside the scalp) to the electrode's last pixel, every sample is skin or electrode.
    const last = kinds.lastIndexOf("E");
    expect(last, `silhouette electrode ${e.index} (cos ${e.cos.toFixed(2)}) is drawn: ${kinds.join("")}`).toBeGreaterThan(0);
    expect(kinds.slice(0, last + 1).join("").includes("."), `a gap between scalp and electrode ${e.index}: ${kinds.join("")}`).toBe(false);
  });
  console.log(`SCENE-ELECTRODES faceOn=${faceOn.length} silhouette=${silhouette.length} walks ${report.join(" ")}`);
});

test("Actual size draws only the montage, each electrode at the configured width, live from the job settings", async () => {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const state = await page.evaluate(() => {
    const scene = window.__scene;
    if (!scene) throw new Error("window.__scene is absent — build out/ with VITE_SCENE_HOOKS=1");
    return { camera: scene.camera, canvas: scene.canvas, markers: scene.markers };
  });
  const camera = state.camera as OrbitCamera;
  const { widthCss, heightCss } = state.canvas;
  const { eye, right } = cameraBasis(camera);
  const project = (p: Vec3) => projectToCanvas(camera, p, widthCss, heightCss);
  // The electrode nearest the eye, well inside the canvas: face-on, so its footprint's on-screen
  // width is the configured width at that depth.
  const ranked = state.markers
    .map((m) => ({ m, q: project(m.world as Vec3), d: Math.hypot(...[0, 1, 2].map((i) => (m.world as Vec3)[i]! - eye[i]!)) }))
    .filter(({ q }) => q.inFront && q.x > 80 && q.y > 80 && q.x < widthCss - 80 && q.y < heightCss - 80)
    .sort((a, b) => a.d - b.d);
  const target = ranked[0];
  if (!target) throw new Error("no electrode near the eye inside the canvas");
  // An electrode the montage does not use, clear of the target's widest pad (24 mm here).
  const bystander = ranked.find(({ m }) => Math.hypot(...[0, 1, 2].map((i) => (m.world as Vec3)[i]! - (target.m.world as Vec3)[i]!)) > 30);
  if (!bystander) throw new Error("no second electrode to watch");
  const box = await page.locator('[data-page-active="true"]').getByTestId("scene-canvas").boundingBox();
  if (!box) throw new Error("no scene canvas");
  // A click with no montage open starts one with this electrode in pair 1: channel 0, a pad.
  await page.mouse.click(box.x + target.q.x, box.y + target.q.y);
  await expect
    .poll(() => page.evaluate((id) => window.__scenePane?.markerChannels[id], target.m.id))
    .toBe(0);
  await page.mouse.move(0, 0);

  /** The run of pad-coloured pixels (channel 0 is the Okabe-Ito blue: blue far above red) along
   *  the screen row through the electrode, which neither the grey cap markers, the pale gel nor the
   *  skin can be. */
  const padWidthPx = async (): Promise<number> => {
    await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
    const xs = Array.from({ length: 241 }, (_, k) => target.q.x - 120 + k);
    const read = await page.evaluate((pts) => window.__scene?.samplePixels(pts, true) ?? null, xs.map((x) => [x, target.q.y] as [number, number]));
    if (!read) throw new Error("samplePixels returned null");
    const pad = read.map((rgba) => rgba[2]! - rgba[0]! > 60);
    let lo = 120;
    let hi = 120;
    if (!pad[120]) return 0;
    while (lo > 0 && pad[lo - 1]) lo -= 1;
    while (hi < pad.length - 1 && pad[hi + 1]) hi += 1;
    return hi - lo + 1;
  };
  const expectedPx = (mm: number) => {
    const p = target.m.world as Vec3;
    const a = project([p[0] - right[0] * (mm / 2), p[1] - right[1] * (mm / 2), p[2] - right[2] * (mm / 2)]);
    const b = project([p[0] + right[0] * (mm / 2), p[1] + right[1] * (mm / 2), p[2] + right[2] * (mm / 2)]);
    return Math.hypot(b.x - a.x, b.y - a.y);
  };

  /** What the marker pass adds at the bystander's own position: 0 when it is not drawn. */
  const bystanderDrawn = async (): Promise<boolean> => {
    const pt: [number, number][] = [[bystander.q.x, bystander.q.y]];
    const a = await page.evaluate((pts) => window.__scene?.samplePixels(pts, true) ?? null, pt);
    const b = await page.evaluate((pts) => window.__scene?.samplePixels(pts, false) ?? null, pt);
    return Math.max(...[0, 1, 2].map((c) => Math.abs(a![0]![c]! - b![0]![c]!))) > 0;
  };
  const sizeSwitch = page.locator('[data-page-active="true"]').getByTestId("scene-actual-size-toggle").getByRole("switch", { name: "Actual size" });

  // Off (the default): the cap marker, 6 mm, and the whole net.
  await expect(sizeSwitch).toHaveAttribute("data-state", "unchecked");
  const asCap = await padWidthPx();
  expect(await bystanderDrawn(), "with Actual size off the whole net is drawn").toBe(true);
  await sizeSwitch.click();
  await page.mouse.move(0, 0);
  await expect(sizeSwitch).toHaveAttribute("data-state", "checked");
  await expect.poll(bystanderDrawn, { timeout: 5000 }).toBe(false);
  const atDefault = await padWidthPx(); // the toolbox default, 8 mm
  await page.locator("tr[data-montage-row]").first().locator('td[data-cell="actions"]').getByRole("button", { name: /^Job settings/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("spinbutton", { name: "Electrode width" }).fill("24");
  await dialog.getByRole("spinbutton", { name: "Electrode height" }).fill("24");
  await page.mouse.move(0, 0);
  await expect.poll(padWidthPx, { timeout: 5000 }).toBeGreaterThan(atDefault * 2);
  const atWide = await padWidthPx();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  // Cancel drops the unsaved size: back to the default.
  await expect.poll(padWidthPx, { timeout: 5000 }).toBe(atDefault);

  console.log(
    `SCENE-PAD-WIDTH cap=${asCap}px (expected ${expectedPx(6).toFixed(1)}) default=${atDefault}px (expected ${expectedPx(8).toFixed(1)}) wide=${atWide}px (expected ${expectedPx(24).toFixed(1)}) ratio=${(atWide / atDefault).toFixed(2)}`,
  );
  // The footprint is the configured millimetres at the electrode's depth (a pixel of rim and of
  // bend either way), and three times the width is three times the pixels.
  expect(Math.abs(asCap - expectedPx(6))).toBeLessThanOrEqual(Math.max(3, 0.2 * expectedPx(6)));
  expect(Math.abs(atDefault - expectedPx(8))).toBeLessThanOrEqual(Math.max(3, 0.2 * expectedPx(8)));
  expect(Math.abs(atWide - expectedPx(24))).toBeLessThanOrEqual(Math.max(3, 0.12 * expectedPx(24)));
  expect(atWide / atDefault).toBeGreaterThan(2.5);
  expect(atWide / atDefault).toBeLessThan(3.5);
  // Off again: the cap markers come back, the whole net with them.
  await sizeSwitch.click();
  await page.mouse.move(0, 0);
  await expect.poll(bystanderDrawn, { timeout: 5000 }).toBe(true);
  await expect.poll(padWidthPx, { timeout: 5000 }).toBe(asCap);
});

test("a name shows only on an electrode the frame drew, and the two switches share one row", async () => {
  const active = page.locator('[data-page-active="true"]');
  // Side by side in one box: the same row, Actual size to the right of Electrode names.
  const toggles = active.getByTestId("scene-toggles");
  const [names, size] = await toggles.locator("label").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
  expect(Math.abs(names!.top - size!.top), "the switches are on one row").toBeLessThan(2);
  expect(size!.left).toBeGreaterThan(names!.right);
  expect(await toggles.evaluate((el) => getComputedStyle(el).flexWrap), "a narrow pane wraps them, never overflows").toBe("wrap");

  const namesSwitch = active.getByTestId("scene-names-toggle").getByRole("switch", { name: "Electrode names" });
  if ((await namesSwitch.getAttribute("data-state")) !== "checked") await namesSwitch.click();
  const sizeSwitch = active.getByTestId("scene-actual-size-toggle").getByRole("switch", { name: "Actual size" });
  /** Every shown name's electrode: does the marker pass change its own pixel (a hidden one draws
   *  nothing)? The
   *  maintainer saw names on electrodes the head hid (2026-10-28); the mock's ellipsoid head hides
   *  some beyond the silhouette that the old centre-direction test called facing. */
  const shownNames = async () => {
    await page.mouse.move(0, 0);
    await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
    const shown = await active.locator(".scene-name:not([hidden])").evaluateAll((els) => els.map((e) => e.getAttribute("data-name")!));
    const drawn = await page.evaluate((ids) => {
      const s = window.__scene!;
      return ids.map((id) => {
        const m = s.markers.find((k) => k.id === id)!;
        const q = s.project(m.world as [number, number, number]);
        const a = s.samplePixels([[q.x, q.y]], true)![0]!;
        const b = s.samplePixels([[q.x, q.y]], false)![0]!;
        return { id, drawn: [0, 1, 2].some((c) => a[c] !== b[c]) };
      });
    }, shown);
    return { shown, wrong: drawn.filter((d) => !d.drawn).map((d) => d.id) };
  };
  for (const on of [false, true]) {
    if ((await sizeSwitch.getAttribute("data-state")) !== (on ? "checked" : "unchecked")) await sizeSwitch.click();
    const { shown, wrong } = await shownNames();
    console.log(`SCENE-NAMES actualSize=${on} shown=${shown.length} wrong=${JSON.stringify(wrong)}`);
    expect(shown.length, "names are shown at all").toBeGreaterThan(0);
    expect(wrong, `names on electrodes not drawn (Actual size ${on ? "on" : "off"})`).toEqual([]);
  }
});
