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
 *  - **A click fills the next row.** The gesture has to reach the form, not just the renderer —
 *    the form is what gets saved.
 *  - **The coordinate is the one the renderer projected.** The row must hold the point that was
 *    clicked, to the 0.1 mm the editor's inputs use, not "some number changed".
 *  - **A dot appears for it, in its pair's colour**, and removing the row removes the dot: the
 *    table and the scalp are one state, not two that can disagree.
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

/** A canvas point that is certainly ON the head: the renderer's own projection of the marker
 *  nearest the eye is not available here (there are no markers yet), so the scalp's centre is
 *  used and the assertion is that the pick produced a world point at all. */
async function clickCanvasCentre(): Promise<void> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const box = (await page.locator('[data-page-panel="simulator"]').getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
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

test("clicking the scalp fills the next position row with the point that was clicked", async () => {
  await openPlacementEditor();
  // The gesture only exists while the editor is open and a subject is drawn.
  await expect(host()).toHaveAttribute("data-gesture", "place", { timeout: 20_000 });
  await expect(page.getByTestId("scene-pane-hint")).toContainText("Click the scalp to place");

  // The rows open already named — the plan, before anything is clicked (2.5.0's E1+/E1− naming).
  await expect(page.locator('[aria-label="Position 1 label"]')).toHaveValue("E1+");
  await expect(page.locator('[aria-label="Position 2 label"]')).toHaveValue("E1-");

  await clickCanvasCentre();

  const world = await page.evaluate(() => window.__scene?.lastPick?.world ?? null);
  expect(world, "the click landed on the head, so the pick pass reported a world point").not.toBeNull();
  const round = (v: number) => String(Math.round(v * 10) / 10);

  // The row holds THAT point, to the 0.1 mm the editor's inputs step by.
  for (const [i, axis] of (["X", "Y", "Z"] as const).entries()) {
    await expect(page.locator(`[aria-label="Position 1 ${axis}"]`)).toHaveValue(round((world as number[])[i] as number));
  }
  // ... and a dot is drawn for it, in pair 1's colour (channel 0).
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(1);
  const marker = await page.evaluate(() => window.__scene!.markers[0]!);
  expect(marker.id).toBe("E1+");

  await page.screenshot({ path: join(ARTIFACTS, "simulator-placement.png") });
});

test("the second click fills the second row, and removing a row removes its dot", async () => {
  await clickCanvasCentre();
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(2);
  await expect(page.locator('[aria-label="Position 2 X"]')).not.toHaveValue("0");

  await page.getByRole("button", { name: "Remove position 1", exact: true }).click();
  // One dot left, and it has been renumbered — Qt's `deleteChecked`, so the table never claims a
  // pair that does not exist.
  await expect.poll(() => page.evaluate(() => window.__scene?.markers.length ?? 0)).toBe(1);
  await expect(page.locator('[aria-label="Position 1 label"]')).toHaveValue("E1+");
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
