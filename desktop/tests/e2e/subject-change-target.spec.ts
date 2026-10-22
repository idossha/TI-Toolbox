import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { analysisRows, analysisTargetText, closeAnalysisTarget, openAnalysisTarget, setAnalysisCell, setAnalysisSubject } from "./_jobs";

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
