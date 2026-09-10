import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { closeOptEditor, openOptEditor, optRowDetail, optRowSummary, optRows, setOptCell } from "../_jobs";
import { cleanupSmokeOutputs, connectReal, getJobStatus, expectPage, gotoPage, launchElectronApp, recordPayload, PROJECT_HOST_ROOT, selectSubject, waitForJobTerminal, waitForJobTrace } from "../_helpers";

/**
 * A real mTI exhaustive search: configure an Ex job row with eight electrode buckets,
 * assert its grouped submission, and verify completion and the Results entry.
 * The real project uses a subcortical ROI because it has no saved mock ROI presets.
 */
const SUBJECT = "101";
const ATLAS = "labeling.nii.gz";
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const RUN_NAME = `smoke-ui-${RUN_ID}-mex`;
const RUN_REL = `derivatives/SimNIBS/sub-${SUBJECT}/m-ex-search/${RUN_NAME}`;
const STOPPED_STATES = new Set(["succeeded", "failed", "cancelled", "skipped"]);

let app: ElectronApplication;
let page: Page;
let jobId: string | undefined;
let submissionStarted = false;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

test.beforeAll(async () => {
  expect(existsSync(join(PROJECT_HOST_ROOT, RUN_REL)), `Refusing to overwrite existing fixture output: ${RUN_REL}`).toBe(false);
  for (const rel of [
    `leadfields/${SUBJECT}_leadfield_EEG10-10_UI_Jurak_2007.hdf5`,
    `m2m_${SUBJECT}/${SUBJECT}.msh`,
    `m2m_${SUBJECT}/segmentation/${ATLAS}`,
  ]) {
    const path = join(PROJECT_HOST_ROOT, "derivatives/SimNIBS", `sub-${SUBJECT}`, rel);
    expect(existsSync(path), `Required real Ex/mEx fixture is missing: ${path}`).toBe(true);
  }
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, SUBJECT);
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
});

test.afterAll(async () => {
  // Status read + cancellation + terminal polling can take longer than the default hook budget.
  test.setTimeout(120_000);
  try {
    if (!jobId) {
      if (submissionStarted) throw new Error(`mEx job identity unknown; retaining ${RUN_REL}`);
      return;
    }
    let final = await getJobStatus(SERVER_URL, TOKEN, jobId);
    if (!final || !STOPPED_STATES.has(final.state)) {
      const response = await fetch(`${SERVER_URL}/api/jobs/${jobId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}` },
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error(`mEx cancellation returned ${response.status}; retaining ${RUN_REL}`);
      final = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: 60_000, pollMs: 2000 });
    }
    if (!STOPPED_STATES.has(final.state)) throw new Error(`mEx job is ${final.state}; retaining ${RUN_REL}`);
    cleanupSmokeOutputs([RUN_REL]);
  } finally {
    await app?.close();
  }
});

test("subcortical ROI, eight electrode buckets: accepted, started, and completed", async () => {
  test.setTimeout(700_000);

  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-subject", SUBJECT);
  await setOptCell(page, row, "method", "Ex");
  await row.locator('td[data-cell="net"]').getByRole("combobox").click();
  const ready = page.getByRole("option", { name: /EEG10-10_UI_Jurak_2007 · [\d.]+ [MG]B/ });
  await expect(ready, `Dataset 000 subject ${SUBJECT} requires its EEG10-10_UI_Jurak_2007 leadfield`).toBeVisible({ timeout: 20_000 });
  await ready.click();
  await expect(row).toHaveAttribute("data-net", "EEG10-10_UI_Jurak_2007");

  const dialog = await openOptEditor(page, row);
  await dialog.locator(".optimizer-dialog-meta").getByRole("textbox").fill(RUN_NAME);
  await field("Electrodes", dialog).getByRole("radio", { name: "8 electrodes (mTI)", exact: true }).click();
  await expect(dialog.getByLabel("Combine selected ROIs into one target")).toHaveCount(0);
  await dialog.getByRole("radio", { name: "Subcortical", exact: true }).click();
  await field("Volume atlas", dialog).locator(".combobox-trigger").click();
  await page.getByPlaceholder("Search atlases…").fill(ATLAS);
  await page.getByRole("option", { name: ATLAS, exact: true }).click();
  await field("Region(s)", dialog).getByRole("combobox").click();
  await page.getByPlaceholder(/Filter regions…|Search…/).fill("Hippocampus");
  await page.getByRole("option", { name: "Left-Hippocampus", exact: true }).click();
  await page.getByTestId("roi-region-done").click();

  const buckets = [
    ["E1+", "Fp1"],
    ["E1-", "Fp2"],
    ["E2+", "F3"],
    ["E2-", "F4"],
    ["E3+", "C3"],
    ["E3-", "C4"],
    ["E4+", "P3"],
    ["E4-", "P4"],
  ] as const;
  for (const [bucket, electrode] of buckets) {
    await field(bucket, dialog).getByRole("combobox").click();
    const list = page.getByRole("dialog").filter({ hasText: `${bucket} — choose electrodes` });
    await list.getByPlaceholder("Filter electrodes…").fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
    await list.getByRole("button", { name: "Done" }).click();
  }

  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "mex");
  await expect(optRowSummary(row)).toHaveText(/Left-Hippocampus/);
  await expect(optRowDetail(row)).toHaveText(/^8 electrodes \(mTI\) · 2 mA/);

  const cell = page.getByTestId(`plan-cell-${SUBJECT}-mex`);
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^1 (new|overwrite)$/);
  await expect(page.getByTestId("run-button")).toBeEnabled();

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  submissionStarted = true;
  await page.getByTestId("run-button").click();
  const created = (await (await jobResponse).json()) as { jobs: { id: string }[] };
  jobId = created.jobs?.[0]?.id;
  expect(created.jobs).toHaveLength(1);

  const requestBody = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    subject_configs: { subject_id: string; config: { run_name: string; leadfield_hdf: string; roi_atlas: unknown; electrodes: Record<string, unknown> } }[];
  };
  expect(requestBody.kind).toBe("mex");
  expect(requestBody.subject_ids).toEqual([SUBJECT]);
  expect(requestBody.subject_configs).toHaveLength(1);
  expect(requestBody.subject_configs[0]!.subject_id).toBe(SUBJECT);
  const config = requestBody.subject_configs[0]!.config;
  expect(config.run_name).toBe(RUN_NAME);
  expect(config.leadfield_hdf).toContain(`sub-${SUBJECT}/leadfields/${SUBJECT}_leadfield_`);
  // CHARM's labeling_labels.txt names label 17 Left-Hippocampus for this subject.
  expect(config.roi_atlas).toEqual([{
    atlas_path: `/mnt/000/derivatives/SimNIBS/sub-${SUBJECT}/m2m_${SUBJECT}/segmentation/${ATLAS}`,
    label: 17,
  }]);
  expect(config.electrodes).toMatchObject({
    _type: "BucketElectrodes",
    e1_plus: ["Fp1"],
    e1_minus: ["Fp2"],
    e2_plus: ["F3"],
    e2_minus: ["F4"],
    e3_plus: ["C3"],
    e3_minus: ["C4"],
    e4_plus: ["P3"],
    e4_minus: ["P4"],
  });
  recordPayload("mex", requestBody);

  await waitForJobTrace(page, "mex", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("mex", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.jobs[0]!.id, timeoutMs: 600_000 });
  console.log(`real/mex: job ${created.jobs[0]!.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);

  // The reload is load-bearing: the Results tree's catalog queries have a 60 s `staleTime` and
  // nothing invalidates them when a job finishes (measured on the sibling `ex.spec.ts` run —
  // the tree served a listing fetched 42 s before the job ended, with no further request). See
  // that spec's comment and this lane's notes; a fresh renderer is what a user is left with.
  await page.reload();
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 30_000 });
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId(`results-subject-${SUBJECT}`).click();
  await expect(page.getByTestId(`results-node-mex:${SUBJECT}:${RUN_NAME}`)).toBeVisible({ timeout: 20_000 });
});
