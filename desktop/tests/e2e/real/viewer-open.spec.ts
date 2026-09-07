import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

/**
 * Viewer → Open, against the **real** container and the embed it bakes (IB).
 *
 * The mock's version of this loop is `tests/e2e/viewer.spec.ts`. What only a real server can
 * prove is the whole delivery stack end to end: `/api/view/open` resolving sub-ernie's real
 * simulation, the iframe loading the bundle the image serves at `/tetravox/` (not the mock's
 * `fake-embed`), and that bundle answering `ready` after taking the scene — a real Tetravox
 * engine, wasm and all, drawn by this window on the host's GPU.
 *
 * Dataset 000 has sub-ernie with a `Thalamus` simulation; nothing here writes into it except the
 * scene file `/api/view/open` always writes under `<project>/code/ti-toolbox/viewer/`.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  await app?.close();
});

test("the served embed is a real bundle, not the placeholder", async () => {
  // Read through the app's own session so the request carries the token the way the iframe's will.
  const manifest = await page.evaluate(async (base) => {
    const res = await fetch(new URL("/tetravox/manifest.json", base).href);
    return { status: res.status, csp: res.headers.get("content-security-policy"), body: await res.json() };
  }, SERVER_URL);
  expect(manifest.status).toBe(200);
  expect(manifest.body.version).not.toContain("placeholder");
  expect(typeof manifest.body.protocol).toBe("number");
  expect(manifest.csp ?? "").toContain("wasm-unsafe-eval");
});

test("Open on sub-ernie lands on the Tetravox sub-page with the embed ready", async () => {
  await selectSubject(page, "ernie");
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");

  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();

  await page.getByTestId("viewer-open").click();
  await expect(page.getByTestId("viewer-sub-viewer")).toHaveAttribute("data-active", "true", { timeout: 15_000 });
  await expect(page.getByTestId("viewer-opened")).toContainText(".tetravox.json");
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("simulation.tetravox.json");

  const host = page.getByTestId("tetravox-host");
  await expect(host).toBeVisible();
  // `idle` is silence; `no-webgl2` would be this machine; `ready` is the engine having taken
  // sub-ernie's scene. A real bundle is bigger than the mock's, so the budget is wider.
  await expect(host).not.toHaveAttribute("data-viewer-status", "idle", { timeout: 60_000 });
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("tetravox-frame")).toHaveAttribute("src", /\/tetravox\//);
  await expect(page.getByTestId("viewer-error")).toHaveCount(0);
});

/**
 * The defaults a scene actually opens at, on real volumes (2026-09-07).
 *
 * The maintainer's complaint was about numbers — "very strange defaults ... 5.078e-09 ... it would
 * be much more reasonable to set more logical thresholds, for example 95 to 99.9 of the electric
 * field", and panes so zoomed out "the head is a small square". Only real NIfTIs can prove this:
 * every number below is derived from `sub-101/L_Insula`'s own voxels, and the mock has none.
 *
 * The assertion is made against the scene document the app posted into the embed, cross-checked
 * against the statistics sidecar the server wrote for those same files. That is the strongest
 * check available from out here: the embed is a bare viewport in this presentation (`EMBED.md`
 * §"the viewport retains ... shell shortcuts are inactive"), so it exposes no layer panel to read
 * values off, and the page does not offer `serialize`. What can be proved is that the engine was
 * handed these exact values and answered `ready` rather than rejecting them — plus a screenshot,
 * which is what the complaint was made from in the first place.
 */
test("sub-101/L_Insula opens windowed p95–p99.9, fitted, and crosshaired on the field peak", async () => {
  await selectSubject(page, "101");
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");

  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "L_Insula", exact: true }).click();

  // The card says the window before anything opens — the whole point of showing it.
  const summary = page.getByTestId("viewer-window-summary");
  await expect(summary).toBeVisible({ timeout: 30_000 });
  await expect(summary).toContainText("p95–p99.9");
  // The card keeps the previous selection's numbers while the next one resolves, greyed — so the
  // chip is only comparable to what Open returns once the page says it has stopped resolving.
  // Without this the two disagree by exactly one selection, which is the feature working.
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });

  const opened = page.waitForResponse(
    (r) => r.url().includes("/api/view/open") && r.request().method() === "POST" && r.status() === 200,
  );
  await page.getByTestId("viewer-open").click();
  const body = (await (await opened).json()) as {
    view: {
      layers: { id: string; kind: string; visible: boolean; colormap?: string; scale?: Record<string, number | string>; threshold?: Record<string, unknown> }[];
      slices: { camera: { mmPerPx: number } }[];
      view3d: { camera: { target: number[]; distance: number } };
      cursor: number[];
    };
  };
  const view = body.view;

  // ── the field overlay ──────────────────────────────────────────────────────────────────────
  // The **visible** heat layer, which is the same one `lib.ts::windowSummary` describes. A
  // simulation scene also carries the whole-head and WM copies of the field as hidden layers, and
  // asserting on one of those would compare the chip against a window nobody is looking at.
  const field = view.layers.find((l) => l.kind === "volume" && l.visible && l.scale?.kind === "heat");
  expect(field, "the simulation scene must carry a visible heat field layer").toBeDefined();
  // Every field layer, visible or not, gets the same rule — that is the rule, not a special case.
  for (const heat of view.layers.filter((l) => l.kind === "volume" && l.scale?.kind === "heat")) {
    expect(heat.threshold!.lo, `${heat.id} floors at its own p95`).toBeCloseTo(heat.scale!.min as number, 9);
    expect(heat.threshold!.mode).toBe("hide");
    expect(heat.scale!.min as number, `${heat.id} does not open at "every non-zero voxel"`).toBeGreaterThan(1e-4);
  }
  const min = field!.scale!.min as number;
  const max = field!.scale!.max as number;

  // The defect, pinned: the window used to open at the smallest non-zero voxel, 5.08e-09 V/m.
  expect(min).toBeGreaterThan(1e-4);
  expect(max).toBeGreaterThan(min);
  expect(field!.threshold!.lo).toBeCloseTo(min, 9);
  expect(field!.threshold!.hi, "an open top — null reads back as +Infinity").toBeNull();
  expect(field!.threshold!.mode, "clamp would paint the sub-threshold voxels rather than hide them").toBe("hide");

  // Cross-check: the number the Menu showed a person and the number the engine was handed are the
  // same number, reached by different code (`lib.ts::windowSummary` off the resolved scene, and
  // the scene itself). Three significant figures, which is what the chip prints.
  const shown = (await summary.textContent()) ?? "";
  expect(shown).toContain(Number(min.toPrecision(3)).toString());
  expect(shown).toContain(Number(max.toPrecision(3)).toString());

  // ── the anatomy ────────────────────────────────────────────────────────────────────────────
  const t1 = view.layers.find((l) => l.kind === "volume" && l.scale?.kind === "linear" && l.colormap === "gray");
  expect(t1, "the scene must carry a T1 base layer").toBeDefined();
  // p2–p98, not min–max: sub-101's T1 maxes at 3238 on a few scalp-fat voxels.
  expect(t1!.scale!.hi as number).toBeLessThan(3000);
  expect(t1!.scale!.lo as number).toBeGreaterThanOrEqual(0);

  // ── sizing ─────────────────────────────────────────────────────────────────────────────────
  // Fitted to the head, not the engine's fixed 0.5 mm/px. A ~190 mm head across a 512 px pane is
  // a shade under 0.5; the assertion that matters is that all three panes carry the *same*,
  // data-derived number rather than the constant 0.6 this module used to emit.
  const mmPerPx = view.slices.map((s) => s.camera.mmPerPx);
  expect(new Set(mmPerPx).size, "every 2D pane fits the same scene").toBe(1);
  expect(mmPerPx[0]).toBeGreaterThan(0.05);
  expect(mmPerPx[0]).not.toBeCloseTo(0.6, 6);
  // A head fills a 512 px pane at roughly 0.4–0.6 mm/px; anything outside that is not a head.
  expect(mmPerPx[0]).toBeGreaterThan(0.2);
  expect(mmPerPx[0]).toBeLessThan(1.0);

  // The 3D camera frames the head rather than sitting at a fixed 350 mm from the world origin.
  expect(view.view3d.camera.target.some((c) => Math.abs(c) > 1e-6), "the 3D camera targets the data").toBe(true);
  expect(view.view3d.camera.distance).not.toBeCloseTo(350, 6);

  // ── location ───────────────────────────────────────────────────────────────────────────────
  // The crosshair is on the field's peak. World (0,0,0) is the scanner origin, which for a
  // subject-space head volume is off in a corner of the field of view.
  expect(view.cursor.some((c) => Math.abs(c) > 1e-6), "the crosshair must not sit at world zero").toBe(true);

  // ── and the engine accepted all of it ──────────────────────────────────────────────────────
  const host = page.getByTestId("tetravox-host");
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-error")).toHaveCount(0);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(2_000); // let the engine redraw at the new size
  await page.screenshot({ path: process.env.TIT_E2E_SHOT ?? "test-results/viewer-defaults-after.png" });

  console.log(
    `sub-101/L_Insula defaults: window [${min}, ${max}] V/m · threshold.lo ${field!.threshold!.lo} ` +
      `· mmPerPx ${mmPerPx[0]} · cursor [${view.cursor.map((c) => c.toFixed(1)).join(", ")}]`,
  );
});
