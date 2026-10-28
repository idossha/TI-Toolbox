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
