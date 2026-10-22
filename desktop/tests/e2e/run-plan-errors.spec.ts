import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import {
  analysisRows,
  closeOptEditor,
  configureMontageJob,
  jobRows,
  openOptEditor,
  optRows,
  setAnalysisCell,
  setAnalysisSphere,
} from "./_jobs";

/**
 * A plan request the server refuses blocks Run on all four run pages, and the blocked sentence is
 * the server's own `detail` (p19, 2026-10-22; DESIGN.md §4.2 rule 8: never silently disabled).
 *
 * Before: Pre-processing never read the plan's error; the Simulator computed it and ignored it
 * (Run submitted every row); the Analyzer's digest stayed "Resolving the plan…" with Run enabled;
 * the Optimizer stayed on "Resolving the run folders…" forever. Each test answers the page's
 * `POST /api/plan/<kind>` with `422 {detail: DETAIL}` (page.route, mock server otherwise) and
 * asserts the Run button is disabled with DETAIL as its title and the bar is in its blocked state
 * (no digest). The expected title is DETAIL as sent, prefixed with the job's row label where the
 * page plans per job.
 *
 * Run: `cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/run-plan-errors.spec.ts` (mock server, offscreen).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const DETAIL = "mask_path: mask is not accessible (e2e refusal)";

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
});

test.afterAll(async () => {
  await app?.close();
});

/** Every plan request of `kind` is refused with DETAIL until `stop()`. */
async function refusePlans(kind: string): Promise<{ seen: () => number; stop: () => Promise<void> }> {
  let count = 0;
  const pattern = `**/api/plan/${kind}`;
  await page.route(pattern, async (route) => {
    count += 1;
    await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: DETAIL }) });
  });
  return { seen: () => count, stop: () => page.unroute(pattern) };
}

/** The page's verdict: the Run button disabled with `title`, and the bar in its blocked state —
 *  which prints no digest at all (`ui/Chrome.tsx` ActionBar: the disabled primary and its title
 *  are the one signal), so neither a job count nor "Resolving…" can contradict the refusal.
 *  Retries of the refused request (the app's query client retries twice) are why the timeout is
 *  generous. */
async function expectBlocked(title: string): Promise<void> {
  // Visited pages stay mounted (hidden) for page memory, so the CURRENT page's controls are the
  // visible ones.
  const run = page.locator('[data-testid="run-button"]:visible');
  await expect(run).toHaveAttribute("title", title, { timeout: 20_000 });
  await expect(run).toBeDisabled();
  await expect(page.locator(".action-bar-digest:visible")).toHaveCount(0);
}

test("Pre-processing: the refused plan is the blocked reason, verbatim", async () => {
  const refusal = await refusePlans("pre");
  try {
    await gotoPage(page, "preprocess", "Pre-processing");
    await expectPage(page, "preprocess");
    // One request plans every selected subject, so there is no row to name.
    await expectBlocked(DETAIL);
    expect(refusal.seen()).toBeGreaterThan(0);
  } finally {
    await refusal.stop();
  }
});

test("Simulator: a refused row blocks Run and is named by subject and montage", async () => {
  const refusal = await refusePlans("sim");
  try {
    await gotoPage(page, "simulator", "Simulator");
    await expectPage(page, "simulator");
    await expect(jobRows(page)).toHaveCount(1, { timeout: 15_000 });
    await configureMontageJob(page, jobRows(page).first(), { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
    await expectBlocked(`ernie · F3_F4: ${DETAIL}`);
  } finally {
    await refusal.stop();
  }
});

test("Analyzer: a refused job no longer leaves 'Resolving the plan…' with Run enabled", async () => {
  const refusal = await refusePlans("analyzer");
  try {
    await gotoPage(page, "analyzer", "Analyzer");
    await expectPage(page, "analyzer");
    const row = analysisRows(page).first();
    await setAnalysisCell(page, row, "simulation", "Thalamus");
    await setAnalysisSphere(page, row, { x: -10, y: -18, z: 9, radius: 5 });
    await expectBlocked(`Job 1: ${DETAIL}`);
  } finally {
    await refusal.stop();
  }
});

/** Picks DK40 lh.bankssts in an open Optimizer row editor (the flex target gesture). */
async function pickCorticalTarget(dialog: Locator): Promise<void> {
  const field = (label: string) => dialog.locator(".field", { hasText: label }).first();
  await field("Atlas").locator(".combobox-trigger").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: /Desikan-Killiany/i }).click();
  await field("Region(s)").getByRole("combobox").click();
  await page.getByPlaceholder("Filter regions…").fill("bankssts");
  await page.getByRole("option", { name: "L · bankssts", exact: true }).click();
  await page.getByTestId("roi-region-done").click();
}

test("Optimizer: a refused search no longer says 'Resolving the run folders…' forever", async () => {
  const refusal = await refusePlans("flex");
  try {
    await gotoPage(page, "optimizer", "Optimizer");
    await expectPage(page, "optimizer");
    await expect(page.getByRole("button", { name: "Add job", exact: true })).toBeVisible();
    await expect(optRows(page)).toHaveCount(1, { timeout: 15_000 });
    const row = optRows(page).first();
    const dialog = await openOptEditor(page, row);
    await pickCorticalTarget(dialog);
    await closeOptEditor(page);
    await expect(row).toHaveAttribute("data-target-ready", "true");
    await expectBlocked(`Job 1: ${DETAIL}`);
  } finally {
    await refusal.stop();
  }
});
