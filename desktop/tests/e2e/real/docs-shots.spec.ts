/**
 * The documentation website's screenshots, taken from the **real** container.
 *
 * `docs/` ships pictures of the product; a picture drawn by the mock server shows fixture names
 * and empty tables, which is exactly what a reader must not be shown. This spec drives the app
 * offscreen against a dev container on Dataset 000 (sub-101 and sub-ernie, real simulations, real
 * job history) and writes each frame straight into `docs/assets/imgs/v3/`. The one command that
 * starts the container, builds, runs this under the e2e lock and cleans up is
 * `dev/capture_docs_screenshots.ts` (see docs/dev/TESTING.md, "Documentation screenshots");
 * `-g "<test title>"` re-takes one picture.
 *
 * It is **read-only against the project**: it opens existing notebooks and simulations, fills job
 * rows without running them, and never submits a job, saves a notebook, saves settings or writes a
 * montage.
 *
 * Light theme at 1900x1000, the size of the maintainer's own window captures, so the rail shows
 * labels (DESIGN.md §9) and pictures taken here sit beside hand-taken ones. Downscale to 1600 px
 * wide (`sips --resampleWidth 1600`) before committing. `TIT_DOCS_SHOTS_DIR` redirects the output,
 * e.g. to check selectors against the mock server without touching docs/.
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject, setTheme } from "../_helpers";
import { analysisRows, jobRows, setAnalysisCell, setAnalysisSphere, setAnalysisSubject } from "../_jobs";

/** Dataset 000's sub-101 and its L_Insula simulation; overridable for another project. */
const SUBJECT = process.env.TIT_DOCS_SUBJECT ?? "101";
const SIMULATION = process.env.TIT_DOCS_SIMULATION ?? "L_Insula";
const SHOTS = process.env.TIT_DOCS_SHOTS_DIR ?? join(__dirname, "..", "..", "..", "..", "docs", "assets", "imgs", "v3");

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

async function shot(name: string): Promise<void> {
  await page.mouse.move(4, 4);
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

async function open(id: string): Promise<void> {
  await gotoPage(page, id);
  await expectPage(page, id);
}

async function sceneReady(id: string): Promise<void> {
  await expect(page.locator(`[data-page-panel="${id}"]`).getByTestId("scene-pane-host")).toHaveAttribute(
    "data-state",
    "ready",
    { timeout: 60_000 },
  );
}

async function settingsTab(name: string): Promise<void> {
  await open("settings");
  await page.getByRole("tab", { name, exact: true }).click();
  await page.waitForTimeout(1500);
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-docs-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1900, height: 1000 });
  await connectReal(page);
  await setTheme(page, "light");
  await selectSubject(page, SUBJECT);
});

test.afterAll(async () => {
  await app?.close();
});

test("Overview with the project open", async () => {
  await open("overview");
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await shot("overview-project");
});

test("Pre-processing", async () => {
  await open("preprocess");
  await page.waitForTimeout(2500);
  await shot("preprocessing-page");
});

test("Optimizer with an atlas region picked in the pane", async () => {
  test.setTimeout(120_000);
  await open("optimizer");
  await sceneReady("optimizer");
  // A pick in the atlas pane names a region and adds it to the ROI (ARCHITECTURE §3).
  const box = (await page.locator('[data-page-panel="optimizer"]').getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 - 40, box.y + box.height / 2 - 30);
  await page.waitForTimeout(1500);
  await shot("optimizer-page");
});

test("Simulator with a montage drawn on the head", async () => {
  test.setTimeout(120_000);
  await open("simulator");
  await expect(jobRows(page).first()).toBeVisible({ timeout: 20_000 });
  await sceneReady("simulator");
  await shot("simulator-run-page");
});

test("Simulator free-hand editor with dots on the scalp", async () => {
  test.setTimeout(180_000);
  await open("simulator");
  const pane = page.locator('[data-page-panel="simulator"]');
  await sceneReady("simulator");
  await page.getByRole("button", { name: "New placement", exact: true }).click();
  await expect(page.getByText("New free-hand placement", { exact: true })).toBeVisible();
  await expect(pane.getByTestId("scene-pane-host")).toHaveAttribute("data-gesture", "place", { timeout: 30_000 });
  const canvas = pane.getByTestId("scene-canvas");
  const markers = () => page.evaluate(() => window.__scene?.markers.length ?? 0);
  /** Clicks the head until this row actually gets a dot; an offset can miss the silhouette. */
  const place = async (row: number, offsets: [number, number][]) => {
    await page.getByTestId(`freehand-row-${row}`).click();
    const before = await markers();
    for (const [dx, dy] of offsets) {
      const box = (await canvas.boundingBox())!;
      await page.mouse.click(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
      await page.waitForTimeout(600);
      if ((await markers()) > before) return;
    }
  };
  await place(0, [[30, 20], [10, -40], [60, 0]]);
  await place(1, [[-60, 30], [-30, -50], [-80, -10]]);
  await shot("simulator-freehand");
  await page.keyboard.press("Escape");
});

test("Analyzer with a row on an existing simulation", async () => {
  test.setTimeout(120_000);
  await open("analyzer");
  const row = analysisRows(page).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await setAnalysisSubject(page, row, SUBJECT);
  await setAnalysisCell(page, row, "simulation", SIMULATION);
  // Left insula in MNI space: the target the simulation was designed for.
  await setAnalysisSphere(page, row, { x: -38, y: 4, z: 2, radius: 10, space: "MNI" });
  await shot("analyzer-page");
});

test("Viewer compose", async () => {
  await open("viewer");
  await page.waitForTimeout(2500);
  await shot("viewer-compose");
});

test("Results with a simulation selected", async () => {
  await open("results");
  await page.getByTestId(`results-subject-${SUBJECT}`).click();
  await page.getByTestId(`results-node-simulation:${SUBJECT}:${SIMULATION}`).click();
  await page.waitForTimeout(2500);
  await shot("results-page");
});

test("Notebooks with the worked example", async () => {
  await open("notebooks");
  const example = page.getByTestId("nb-list-item").filter({ hasText: "example_workflow" }).first();
  await expect(example).toBeVisible({ timeout: 20_000 });
  await example.click();
  await expect(page.getByTestId("nb-output").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("nb-output").last().scrollIntoViewIfNeeded();
  await shot("notebooks-example");
});

test("Jobs with the project's history", async () => {
  await open("jobs");
  await page.waitForTimeout(2500);
  await shot("jobs-page");
});

for (const [id, name] of [
  ["panel-source", "extension-source"],
  ["panel-cluster-permutation", "extension-cluster-permutation"],
  ["panel-visual-exporter", "extension-visual-exporter"],
] as const) {
  test(`Extension ${id}`, async () => {
    await open(id);
    await page.waitForTimeout(2500);
    await shot(name);
  });
}

test("System", async () => {
  await open("system");
  await page.waitForTimeout(4000);
  await shot("system-page");
});

for (const [tab, name] of [
  ["Project", "settings-project"],
  ["Pre-processing", "settings-preprocessing"],
  ["Extensions", "settings-extensions"],
  ["Viewer", "settings-viewer"],
  ["Server", "settings-server"],
] as const) {
  test(`Settings ${tab}`, async () => {
    await settingsTab(tab);
    await shot(name);
  });
}

test("Help", async () => {
  await open("help");
  await page.waitForTimeout(3000);
  await shot("help-page");
});
