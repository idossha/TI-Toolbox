import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, PROJECT_HOST_ROOT, selectSubject, waitForJobTerminal } from "../_helpers";
import { removeNewEntriesSince, snapshotDir } from "./_dirDiff";
import {
  analysisRows,
  analysisTargetText,
  closeAnalysisTarget,
  openAnalysisTarget,
  setAnalysisCell,
  setAnalysisSphere,
} from "../_jobs";

/**
 * **Target per job**, against the shared dev container. Maintainer, 2026-09-06: *"The TARGET
 * section must become per-job — each row of the jobs table owns its own analysis target so we can
 * modify our analysis input per job."*
 *
 * The measurement that proves it: two rows on the same subject and the same simulation, one with a
 * spherical target and one with a cortical atlas region, submitted in **one** Run press as **two**
 * jobs, each carrying its own ROI — which is exactly the state the page could not express at all
 * while the target was a page-level section.
 *
 * Cleanup is a verified before/after directory diff (`_dirDiff.ts`), as in `analyzer-mesh`:
 * `AnalyzerConfig.output_dir` is always `null` from this page, so the server names the directory
 * and there is no `smoke-<runid>` convention to lean on.
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
  console.log(`real/analyzer-targets: cleaned up new Analyses entries: ${JSON.stringify(removed)}`);
  await app?.close();
});

test("two rows, two different targets, two jobs from one Run", async () => {
  test.setTimeout(600_000);

  // Row 1 — a sphere at the Thalamus coordinates every other analyzer spec uses.
  const first = analysisRows(page).first();
  await expect(first).toHaveAttribute("data-subject", "ernie");
  await setAnalysisCell(page, first, "simulation", "Thalamus");
  await setAnalysisSphere(page, first, { x: -10, y: -18, z: 9, radius: 10 });
  await expect(analysisTargetText(first)).toHaveText("Sphere -10,-18,9 r10 mm · Subject");

  // Row 2 — same subject, same simulation, a CORTICAL target. The row seeds from the last row, so
  // everything but the target is already right; the target is what this spec changes.
  await page.getByTestId("analysis-jobs-footer").getByRole("button", { name: "Add row", exact: true }).click();
  await expect(analysisRows(page)).toHaveCount(2);
  const second = analysisRows(page).nth(1);
  await expect(second).toHaveAttribute("data-simulation", "Thalamus");

  const dialog = await openAnalysisTarget(page, second);
  await dialog.getByRole("radio", { name: "Cortical", exact: true }).click();
  await dialog.locator(".field", { hasText: "Atlas" }).first().locator(".combobox-trigger").click();
  await page.getByRole("option", { name: /DK40/i }).first().click();
  await dialog.locator(".field", { hasText: "Region(s)" }).first().getByRole("combobox").click();
  const region = page.locator('[role="option"]').first();
  const regionName = ((await region.getAttribute("aria-label")) ?? "").replace(/^[LR] · /, "");
  await region.click();
  await page.getByTestId("roi-region-done").click();
  await closeAnalysisTarget(page);
  await expect(analysisTargetText(second)).toContainText("Cortical · DK40 ·");

  // Two rows, two jobs — the page states it before anything is submitted.
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs", { timeout: 20_000 });
  await page.getByTestId("analysis-jobs-table-container").screenshot({
    path: "tests/e2e/artifacts/analyzer-jobs-target.png",
  });

  const posts: { kind: string; subject_ids: string[]; config: Record<string, unknown> }[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/jobs") && r.method() === "POST") {
      posts.push(r.postDataJSON() as { kind: string; subject_ids: string[]; config: Record<string, unknown> });
    }
  });
  const responses: Promise<{ id: string }>[] = [];
  page.on("response", (r) => {
    if (r.url().endsWith("/api/jobs") && r.request().method() === "POST") responses.push(r.json() as Promise<{ id: string }>);
  });

  await page.getByTestId("run-button").click();
  const confirm = page.getByTestId("existing-outputs-replace");
  if (await confirm.isVisible({ timeout: 5_000 }).catch(() => false)) await confirm.click();

  await expect.poll(() => responses.length, { timeout: 30_000 }).toBe(2);
  const created = await Promise.all(responses);

  // Each job carries ITS OWN ROI: one spherical, one cortical, on the same subject and simulation.
  expect(posts).toHaveLength(2);
  for (const body of posts) {
    expect(body.kind).toBe("analyzer");
    expect(body.subject_ids).toEqual(["ernie"]);
    expect(body.config.simulation).toBe("Thalamus");
  }
  const sphere = posts.find((b) => b.config.analysis_type === "spherical");
  const cortical = posts.find((b) => b.config.analysis_type === "cortical");
  expect(sphere?.config.center).toEqual([-10, -18, 9]);
  expect(sphere?.config.radius).toBe(10);
  expect(cortical?.config.atlas).toBe("DK40");
  expect(cortical?.config.region).toBe(regionName);
  expect(cortical?.config.center).toBeNull();

  for (const job of created) {
    const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: job.id, timeoutMs: 420_000 });
    console.log(
      `real/analyzer-targets: job ${job.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`,
    );
    expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
    expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);
  }
});
