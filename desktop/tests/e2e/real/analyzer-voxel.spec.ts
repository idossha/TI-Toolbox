import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, PROJECT_HOST_ROOT, recordPayload, selectSubject, waitForJobTerminal, waitForJobTrace } from "../_helpers";
import { removeNewEntriesSince, snapshotDir } from "./_dirDiff";
import { analysisRows, setAnalysisCell, setAnalysisSphere } from "../_jobs";

/**
 * Analyzer, voxel space — see `analyzer-mesh.spec.ts`'s file header for the shared rationale
 * (fixture matrix "sub-ernie · Thalamus · sphere", verified before/after cleanup since the page
 * has no output-naming field). Voxel space's default tissue type (GM) needs no extra field either.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const ANALYSES_DIR = join(PROJECT_HOST_ROOT, "derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses");

let app: ElectronApplication;
let page: Page;
let before: Set<string>;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  before = snapshotDir(ANALYSES_DIR);
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "ernie");
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
});

test.afterAll(async () => {
  const removed = removeNewEntriesSince(ANALYSES_DIR, before);
  console.log(`real/analyzer-voxel: cleaned up new Analyses entries: ${JSON.stringify(removed)}`);
  await app?.close();
});

test("spherical target, voxel space: accepted, started, and completed", async () => {
  test.setTimeout(360_000);

  // The Jobs table's one seeded row is already on the shell's subject (2026-09-06 rework: the row
  // owns its subject, its simulation, its space and its field).
  const row = analysisRows(page).first();
  await expect(row).toHaveAttribute("data-subject", "ernie");
  await setAnalysisCell(page, row, "simulation", "Thalamus");

  await setAnalysisCell(page, row, "space", "Voxel");

  // Since 2026-09-06 the target is the ROW's: its Target cell opens the shared picker
  // scoped to that row (maintainer: "we can modify our analysis input per job").
  await setAnalysisSphere(page, row, { x: -10, y: -18, z: 9, radius: 10 });

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|overwrite)$/);

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  // The shared existing-outputs question (C3) has three answers now — Skip / Replace / Cancel —
  // and is a `dialog`, not the two-button `alertdialog` this spec was written against.
  const confirm = page.getByTestId("existing-outputs-replace");
  if (await confirm.isVisible({ timeout: 5_000 }).catch(() => false)) await confirm.click();

  const body = (await jobRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: { space: string; simulation: string; tissue_type: string } };
  expect(body.kind).toBe("analyzer");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.config.space).toBe("voxel");
  expect(body.config.tissue_type).toBe("GM");
  recordPayload("analyzer-voxel", body);

  const created = (await (await jobResponse).json()) as { id: string };
  await waitForJobTrace(page, "analyzer", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("analyzer", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 300_000 });
  console.log(`real/analyzer-voxel: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);
});
