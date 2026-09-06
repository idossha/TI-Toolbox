import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import {
  cancelJobFromRail,
  connectReal,
  expectPage,
  gotoPage,
  launchElectronApp,
  recordPayload,
  selectSubject,
  waitForJobRunningOrTerminal,
} from "../_helpers";
import { closeOptEditor, openOptEditor, optRowSummary, optRows } from "../_jobs";

/**
 * Optimizer / Flex, against the shared dev container. Fixture matrix row: `sub-ernie`, atlas ROI
 * (list form), started -> cancel.
 *
 * This row was the program's own §0 failure: the UI emits `atlas_path` as `string[]` (ROI unions,
 * PR #130) while `flex.py`'s `_validate_roi_input` assumed a scalar, so the job died in seconds
 * with `TypeError: expected str, bytes or os.PathLike object, not list`. F0 fixed the runner
 * (2026-09-03) and both branches below are kept deliberately: the "running" branch is what a
 * healthy run takes, and the terminal branch keeps the regression witness — if the list-form ROI
 * ever regresses, the failure is named in the assertion message instead of a bare timeout.
 *
 * Re-pointed 2026-09-06 (lane OJ) at the jobs table: the method and the target are cells of a job
 * ROW now, and the submission is `POST /api/jobs/groups` (R3) rather than `POST /api/jobs` — which
 * this spec had never been updated for and would have missed.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "ernie");
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
});

test.afterAll(async () => {
  // Nothing of ours to remove: a cancelled flex writes no run directory (verified on the host
  // after the 2026-09-04 run — `flex-search/` gained no entry).
  await app?.close();
});

test("cortical ROI (DK40 · bankssts, list form): accepted, started, cancelled", async () => {
  test.setTimeout(180_000);

  // The table seeds one row on the shell's subject, already on Flex — the whole configuration is
  // that row's editor.
  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-subject", "ernie");
  await expect(row).toHaveAttribute("data-method", "flex");

  const dialog = await openOptEditor(page, row);
  // Real catalog names the atlas "DK40" (not the mock fixture's friendlier "Desikan-Killiany").
  await field("Atlas", dialog).getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: "DK40", exact: true }).click();
  await field("Region(s)", dialog).getByRole("combobox").click();
  await page.getByPlaceholder(/Filter regions…|Search…/).fill("bankssts");
  await page.getByRole("option", { name: "L · bankssts" }).click();
  await page.getByTestId("roi-region-done").click();
  await closeOptEditor(page);

  // The row says what it will do, in words, before anything is queued.
  await expect(row).toHaveAttribute("data-target-ready", "true");
  await expect(optRowSummary(row)).toHaveText(/^Cortical · DK40 · lh\.bankssts · 2 pairs/);
  console.log(`real/flex: row summary = ${await optRowSummary(row).textContent()}`);

  await expect(page.getByTestId("plan-grid").getByTestId("plan-stat-jobs")).toBeVisible({ timeout: 15_000 });

  const groupResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  const groupRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const body = (await groupRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    subject_configs: { subject_id: string; config: { roi: { _type: string; atlas_path: unknown } } }[];
  };
  expect(body.kind).toBe("flex");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.subject_configs.map((e) => e.subject_id)).toEqual(["ernie"]);
  recordPayload("flex", body);
  // The shape the §0 failure was about, asserted on the real payload: `atlas_path` is an array.
  const roi = body.subject_configs[0]!.config.roi;
  expect(Array.isArray(roi.atlas_path)).toBe(true);
  console.log(`real/flex: config.roi.atlas_path = ${JSON.stringify(roi.atlas_path)}`);

  // `JobGroupResult` is `{group_id, jobs: JobStatus[]}` — one entry per `subject_configs` entry.
  const group = (await (await groupResponse).json()) as { group_id: string; jobs: { id: string }[] };
  const jobId = group.jobs[0]!.id;
  const job = await waitForJobRunningOrTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: 60_000 });

  if (job.state === "running") {
    await expect(page.getByTestId("job-terminal").getByTestId("job-terminal-identity")).toContainText("flex", { timeout: 15_000 });
    await cancelJobFromRail(page, "flex", { timeoutMs: 30_000 });
    console.log(`real/flex: job ${jobId} reached running and was cancelled. run=${RUN_ID}`);
  } else {
    console.log(`real/flex: job ${jobId} state=${job.state} error=${JSON.stringify(job.error)} run=${RUN_ID}`);
    // Regression witness: since F0's fix the healthy path is "running", so a terminal state here
    // is a report of WHICH failure came back, not an expected outcome.
    expect(
      job.state,
      `flex did not reach running — list-form ROI regression? ${JSON.stringify(job.error?.last_lines?.slice(-3) ?? [])}`,
    ).toBe("running");
  }
});
