import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import {
  addOptRow,
  analysisRows,
  analysisTargetText,
  clearOptRows,
  closeAnalysisTarget,
  closeOptEditor,
  openAnalysisTarget,
  openOptEditor,
  setAnalysisCell,
  setAnalysisSubject,
  setOptCell,
  setOptSubject,
} from "./_jobs";

/**
 * Duplicating an Analyzer row onto another subject does not carry the first subject's
 * subject-space mask (p19, 2026-10-22; bug desktop-run-pages:subject-change-target).
 *
 * A subject-space mask is drawn in one subject's scanner frame and the analyzer samples it by world
 * coordinates (`analyzer.py::_analyze_mask_file`), so ernie's mask run for sub-101 measured other
 * anatomy without any error. Now the copy's target is cleared — the row reads "Choose a target…" —
 * and Run is blocked until a target for sub-101 is chosen; the original row keeps its mask. The
 * mask import is answered by page.route (the mock server stores no files).
 *
 * The Optimizer follows the same rule for a flex focality search's "avoid" region (the non-ROI):
 * a subject-space non-ROI sphere on ernie is millimetres in ernie's head, so moving the row to
 * sub-101 clears it (the toast says "Non-ROI: …") and the row builds no job until sub-101's own
 * coordinates are entered, while the MNI-sphere ROI — one frame for every head — is kept.
 *
 * Run: `cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/subject-change-target.spec.ts` (mock server, offscreen).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const MASK = "lesion.nii.gz";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
});

test.afterAll(async () => {
  await app?.close();
});

test("a duplicated row moved to another subject drops the subject-space mask and blocks Run", async () => {
  const first = analysisRows(page).first();
  await expect(first).toHaveAttribute("data-subject", "ernie");
  await setAnalysisCell(page, first, "simulation", "Thalamus");

  // Import a subject-space mask for ernie; the upload answers with ernie's own masks folder.
  await page.route("**/api/files/mask?**", async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({ json: { path: `/mnt/project/masks/sub-${url.searchParams.get("subject")}/imported/${url.searchParams.get("name")}` } });
  });
  try {
    const dialog = await openAnalysisTarget(page, first);
    await dialog.getByRole("radio", { name: "NIfTI mask", exact: true }).click();
    await dialog.getByLabel("Import NIfTI mask").setInputFiles({ name: MASK, mimeType: "application/octet-stream", buffer: Buffer.from("mock NIfTI payload") });
    await expect(dialog.getByRole("textbox", { name: "Imported mask" })).toHaveValue(`/mnt/project/masks/sub-ernie/imported/${MASK}`);
    await dialog.getByRole("radiogroup", { name: "Mask space" }).getByRole("radio", { name: "Subject", exact: true }).click();
    await closeAnalysisTarget(page);
  } finally {
    await page.unroute("**/api/files/mask?**");
  }
  const ernieTarget = `NIfTI mask · ${MASK} · Subject`;
  await expect(analysisTargetText(first)).toHaveText(ernieTarget);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15_000 });

  // Duplicate: the copy is ernie's job, mask included — then point it at 101.
  await first.getByRole("button", { name: "Duplicate row 1", exact: true }).click();
  await expect(analysisRows(page)).toHaveCount(2);
  const copy = analysisRows(page).nth(1);
  await expect(analysisTargetText(copy)).toHaveText(ernieTarget);
  await setAnalysisSubject(page, copy, "101");

  // 101 has run Thalamus too, so the row stays a job — with no target, which blocks Run.
  await expect(copy).toHaveAttribute("data-simulation", "Thalamus");
  await expect(analysisTargetText(copy)).toHaveText("Choose a target…");
  await expect(copy).toHaveAttribute("data-target-ready", "false");
  const run = page.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Complete the target before running.");
  // The toast says what was cleared and why.
  await expect(page.getByText(/subject-space mask was cleared.*sub-ernie.*sub-101/)).toBeVisible();
  // The original row keeps ernie's mask.
  await expect(analysisTargetText(first)).toHaveText(ernieTarget);
});

/** Types one sphere into a RoiPicker that is already in Spherical mode. */
async function typeSphere(picker: Locator, s: { x: number; y: number; z: number }): Promise<void> {
  await picker.getByRole("spinbutton", { name: "Sphere 1 X", exact: true }).fill(String(s.x));
  await picker.getByRole("spinbutton", { name: "Sphere 1 Y", exact: true }).fill(String(s.y));
  await picker.getByRole("spinbutton", { name: "Sphere 1 Z", exact: true }).fill(String(s.z));
}

test("Optimizer: a flex row moved to another subject drops its subject-space non-ROI sphere and builds no job", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  // A focality goal is what reads the non-ROI at all.
  await setOptCell(page, row, "goal", "Threshold-free focality");

  const dialog = await openOptEditor(page, row);
  // The ROI: an MNI sphere, one frame for every subject — kept across the move.
  await expect(dialog.locator(".roi-picker")).toHaveCount(1);
  const roiPicker = dialog.locator(".roi-picker").first();
  await roiPicker.getByRole("radio", { name: "Spherical", exact: true }).click();
  await roiPicker.getByRole("radiogroup", { name: "Coordinate space" }).getByRole("radio", { name: "MNI", exact: true }).click();
  await typeSphere(roiPicker, { x: -10, y: -18, z: 9 });
  // The non-ROI: a specific region, a sphere in ERNIE's own millimetres (the picker's default space).
  await dialog
    .locator(".field")
    .filter({ has: page.locator(".field-label-text", { hasText: /^Non-ROI$/ }) })
    .getByRole("combobox")
    .click();
  await page.getByRole("option", { name: "Specific region", exact: true }).click();
  const nonRoiPicker = dialog.locator(".field", { hasText: "Non-ROI region" }).locator(".roi-picker");
  await nonRoiPicker.getByRole("radio", { name: "Spherical", exact: true }).click();
  await expect(nonRoiPicker.getByRole("radiogroup", { name: "Coordinate space" }).getByRole("radio", { name: "Subject", exact: true })).toHaveAttribute("aria-checked", "true");
  await typeSphere(nonRoiPicker, { x: -42, y: -20, z: 55 });
  await closeOptEditor(page);

  const run = page.locator('[data-testid="run-button"]:visible');
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(run).toHaveText("Run search");

  // Move the row to 101: the ernie-frame non-ROI is cleared and the toast says it was the non-ROI.
  await setOptSubject(page, row, "101");
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: /^Non-ROI: The subject-space sphere was cleared/ })).toBeVisible();
  // The row still has its target (the MNI ROI), but a focality search with an empty "avoid"
  // region is no job: Run is blocked rather than optimising against ernie's coordinates in 101.
  await expect(row).toHaveAttribute("data-target-ready", "true");
  await expect(run).toBeDisabled({ timeout: 15_000 });
  await expect(run).toHaveAttribute("title", "No job resolves to a target yet.");

  const reopened = await openOptEditor(page, row);
  const roiAgain = reopened.locator(".roi-picker").first();
  await expect(roiAgain.getByRole("spinbutton", { name: "Sphere 1 X", exact: true })).toHaveValue("-10");
  await expect(roiAgain.getByRole("radiogroup", { name: "Coordinate space" }).getByRole("radio", { name: "MNI", exact: true })).toHaveAttribute("aria-checked", "true");
  const nonRoiAgain = reopened.locator(".field", { hasText: "Non-ROI region" }).locator(".roi-picker");
  for (const axis of ["X", "Y", "Z"]) {
    await expect(nonRoiAgain.getByRole("spinbutton", { name: `Sphere 1 ${axis}`, exact: true })).toHaveValue("");
  }
  // 101's own coordinates are 101's job: Run comes back.
  await typeSphere(nonRoiAgain, { x: -40, y: -22, z: 52 });
  await closeOptEditor(page);
  await expect(run).toBeEnabled({ timeout: 20_000 });
});
