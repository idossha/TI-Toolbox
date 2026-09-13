/**
 * The documentation website's screenshots, taken from the **real** container.
 *
 * `docs/` ships pictures of the product; a picture drawn by the mock server shows fixture names
 * and empty tables, which is exactly what a reader must not be shown. This spec drives the app
 * against the shared dev container on Dataset 000 (sub-ernie, real simulations, real job history)
 * and writes each frame straight into `docs/assets/imgs/v3/`, so re-taking the site's screenshots
 * after a UI change is one command rather than a manual tour:
 *
 * ```
 * TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> \
 *   npx playwright test --project=real docs-shots
 * ```
 *
 * It is **read-only against the project**: it opens existing notebooks and simulations
 * and never submits a job, saves a notebook or writes a montage. The one exception is the scene
 * file `/api/view/open` always writes under `<project>/code/ti-toolbox/viewer/`, which the Viewer
 * writes on any open.
 *
 * Light theme at 1440x900 — the site's pages are read on a laptop, and the rail shows labels at or
 * above 1440 (DESIGN.md §9).
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject, setTheme } from "../_helpers";
import { jobRows, setJobMontage, setJobNet } from "../_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = "ernie";

/** `docs/assets/imgs/v3/` from `desktop/tests/e2e/real/`. */
const SHOTS = join(__dirname, "..", "..", "..", "..", "docs", "assets", "imgs", "v3");

let app: ElectronApplication;
let page: Page;

async function shot(name: string): Promise<void> {
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-docs-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await setTheme(page, "light");
  await selectSubject(page, SUBJECT);
});

test.afterAll(async () => {
  await app?.close();
});

/** Every page the rail offers, in rail order — the app's own statement of which pages exist. */
test("every page in the rail", async () => {
  test.setTimeout(300_000);
  const ids: string[] = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="nav-item-"]')).map((el) =>
      (el.getAttribute("data-testid") ?? "").replace(/^nav-item-/, ""),
    ),
  );
  expect(ids.length).toBeGreaterThan(0);
  for (const id of ids) {
    await page.getByTestId(`nav-item-${id}`).click();
    await expectPage(page, id);
    // Give a run page's scene pane and a catalog read time to land before the frame is taken.
    await page.waitForTimeout(2500);
    await shot(id);
  }
});

test("the Simulator, with a montage chosen and its pairs and currents shown", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  const row = jobRows(page).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  // sub-ernie's own saved montage on a 10-10 net — a real study montage, not a fixture name.
  await setJobNet(page, row, "EEG10-10_Cutini_2011.csv");
  await setJobMontage(page, row, "Thalamus · TI");
  await expect(page.locator('[data-page-panel="simulator"]').getByTestId("scene-pane-host")).toHaveAttribute(
    "data-state",
    "ready",
    { timeout: 60_000 },
  );
  await page.mouse.move(4, 4);
  await shot("simulator");
});

test("the Simulator's free-hand editor, with dots on the scalp", async () => {
  test.setTimeout(180_000);
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  const pane = page.locator('[data-page-panel="simulator"]');
  await expect(pane.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 60_000 });

  await page.getByRole("button", { name: "New placement", exact: true }).click();
  await expect(page.getByText("New free-hand placement", { exact: true })).toBeVisible();
  await expect(pane.getByTestId("scene-pane-host")).toHaveAttribute("data-gesture", "place", { timeout: 30_000 });

  const canvas = pane.getByTestId("scene-canvas");
  const markers = () => page.evaluate(() => window.__scene?.markers.length ?? 0);
  /** Clicks the head until this row actually gets a dot — an offset can miss the silhouette. */
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
  await place(0, [
    [30, 20],
    [10, -40],
    [60, 0],
  ]);
  await place(1, [
    [-60, 30],
    [-30, -50],
    [-80, -10],
  ]);
  await page.mouse.move(4, 4);
  await shot("simulator-placement");
});

test("the Optimizer, with an atlas region picked in the pane", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  const pane = page.locator('[data-page-panel="optimizer"]');
  await expect(pane.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 60_000 });
  // A pick in the atlas pane names a region and adds it to the ROI (ARCHITECTURE §3).
  const box = (await pane.getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 - 40, box.y + box.height / 2 - 30);
  await page.waitForTimeout(1200);
  await page.mouse.move(4, 4);
  await shot("optimizer");
});

test("the Viewer, with sub-ernie's simulation open in Tetravox", async () => {
  test.setTimeout(180_000);
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");
  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await page.getByTestId("viewer-open").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 120_000 });
  await page.waitForTimeout(3000);
  await shot("viewer");
});

test("a notebook with real output — the seeded worked example", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "notebooks", "Notebooks");
  await expectPage(page, "notebooks");
  const example = page.getByTestId("nb-list-item").filter({ hasText: "getting-started" }).first();
  await expect(example).toBeVisible({ timeout: 20_000 });
  await example.click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 20_000 });
  // The stored outputs (a matplotlib figure and two DataFrame tables) are what makes this shot
  // worth taking; scroll to the figure rather than photographing the imports.
  await expect(page.getByTestId("nb-output").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("nb-output").last().scrollIntoViewIfNeeded();
  await shot("notebooks");
});
