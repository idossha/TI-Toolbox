import { existsSync, mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import {
  cleanupSmokeOutputs,
  connectReal,
  expectPage,
  launchElectronApp,
  PROJECT_HOST_ROOT,
  recordPayload,
  selectJobsPanelTab,
  waitForJobTerminal,
  waitForJobTrace,
} from "../_helpers";

/**
 * Panel — Cluster permutation (job kind `stats`), against the shared dev container. Fixture
 * matrix row: "group comparison / correlation … same three subjects … completed or readable
 * refusal (needs >= 2 per group)". Uses all three of the project's `L_Insula` subjects
 * (101/ernie/MNI152) — 101+MNI152 as Responders, ernie as the lone Non-Responder — the closest a
 * 3-subject dataset can get to "2 per group" (an unpaired t-test with 1 vs 1, tried first, has
 * `dof = n1+n2-2 = 0`: numpy correctly returns NaN p-values and the run reports 0 clusters without
 * ever exercising a real per-voxel test; 2 vs 1 gives `dof = 1`, a real if underpowered test).
 *
 * A real cluster-permutation test at this N can legitimately complete with zero significant
 * clusters — that is what "needs >= 2 per group" in the matrix is warning about, not a bug. What
 * *is* a small finding this spec reports rather than hides: `GET /api/jobs/<id>` answers
 * `artifacts: []` for this kind even on a real `succeeded` run that wrote 9 real files (NIfTI
 * maps, a PDF, a summary) — verified directly on the host filesystem below, since the API's own
 * `artifacts` list cannot be trusted for this kind.
 */
const STATS_OUTPUT_DIR = (name: string) => join(PROJECT_HOST_ROOT, "derivatives/ti-toolbox/stats/group_comparison", name);
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const ANALYSIS_NAME = `smoke-ui-${RUN_ID}`;

let app: ElectronApplication;
let page: Page;
let cleanupPath: string | null = null;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await page.getByRole("link", { name: "Cluster permutation", exact: true }).click();
  await expectPage(page, "panel-cluster-permutation");
});

test.afterAll(async () => {
  if (cleanupPath) cleanupSmokeOutputs([cleanupPath]);
  await app?.close();
});

test("classification, 2 responders + 1 non-responder: accepted, started, and a real outcome", async () => {
  test.setTimeout(360_000);

  // Rows are addressed through the shared participants grammar (`pages/panels/_participants`,
  // lane FIX-D defect 3): one `participant-row-<id>` per row, its three comboboxes in column
  // order (Subject, Simulation, Response). They used to be counted positionally across the whole
  // "Subjects" card, which broke the moment that card became a table with a `#` column.
  await page.getByTestId("participants-add").click(); // 2 rows -> 3
  const rows = page.getByTestId("participants-field").locator("[data-testid^='participant-row-']");
  async function fillRow(index: number, subject: string, response?: string): Promise<void> {
    const row = rows.nth(index);
    await row.getByRole("combobox").nth(0).click();
    await page.getByRole("option", { name: subject, exact: true }).click();
    await row.getByRole("combobox").nth(1).click();
    await page.getByRole("option", { name: "L_Insula", exact: true }).click();
    if (response) {
      await row.getByRole("combobox").nth(2).click();
      await page.getByRole("option", { name: response, exact: true }).click();
    }
  }
  await fillRow(0, "101"); // Responder, the default
  await fillRow(1, "ernie", "Non-responder");
  await fillRow(2, "MNI152"); // Responder — makes Responders n=2

  // The grammar's own contract: the summary says what will run (J4), and no row is blocked.
  await expect(page.getByTestId("participants-summary")).toHaveText(
    "3 subjects · 101, ernie, MNI152 · one job over all subjects",
  );
  await expect(page.locator("[data-testid^='participant-reason-']")).toHaveCount(0);

  await page.getByLabel("Analysis name").fill(ANALYSIS_NAME);

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const body = (await jobRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: { analysis_name: string; subjects: unknown[] } };
  expect(body.kind).toBe("stats");
  expect(new Set(body.subject_ids)).toEqual(new Set(["101", "ernie", "MNI152"]));
  expect(body.config.analysis_name).toBe(ANALYSIS_NAME);
  expect(body.config.subjects).toHaveLength(3);
  recordPayload("stats", body);

  const created = (await (await jobResponse).json()) as { id: string };
  // Click the trace (not just wait for it): the Console tab renders the *selected* job's log —
  // `ConsolePane`'s `job` prop is `undefined` (empty state, no `.job-console-line` ever) until
  // something calls `select(job.id)`, which only the trace's own `onClick` does.
  const trace = await waitForJobTrace(page, "stats", { timeoutMs: 120_000 });
  await trace.click();
  await selectJobsPanelTab(page, "Console");
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 300_000 });
  console.log(
    `real/cluster-permutation: job ${created.id} state=${finalJob.state} error=${JSON.stringify(finalJob.error)} api-artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`,
  );
  // "completed or readable refusal" (matrix): either is a pass, an opaque crash is not.
  expect(["succeeded", "failed"]).toContain(finalJob.state);
  if (finalJob.state === "succeeded") {
    // Not `finalJob.artifacts` — verified empty for this kind even on a real run that wrote
    // files (see file header). The host filesystem is the honest check.
    const outDir = STATS_OUTPUT_DIR(ANALYSIS_NAME);
    expect(existsSync(outDir), `output dir on host: ${outDir}`).toBe(true);
    const files = readdirSync(outDir);
    console.log(`real/cluster-permutation: ${files.length} files on disk: ${files.join(", ")}`);
    expect(files.length).toBeGreaterThan(0);
    cleanupPath = `derivatives/ti-toolbox/stats/group_comparison/${ANALYSIS_NAME}`;
  } else {
    expect(finalJob.error?.message ?? "").not.toBe("");
  }
});
