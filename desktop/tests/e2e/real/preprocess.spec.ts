import { existsSync, mkdtempSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import {
  answerExistingOutputs,
  connectReal,
  expectPage,
  gotoPage,
  launchElectronApp,
  PROJECT_HOST_ROOT,
  recordPayload,
  waitForJobTerminal,
  waitForJobTrace,
  type JobStatusLite,
} from "../_helpers";

/**
 * Pre-processing, against the shared dev container (v3-pipelines program). Two real runs:
 *
 * 1. "Tissue analyzer" on `sub-101` (fixture matrix §3: "completed (replace_existing_outputs)",
 *    300 s budget) — the lightest stage that produces a real "pre" job on an already-modelled
 *    subject. `sub-101` already has a `tissue_analysis` output on disk (the maintainer's own
 *    earlier run), which is why this row explicitly opts into "replace" rather than "skip" — with
 *    "skip" the plan would resolve to zero new jobs and Run would have nothing to submit.
 * 2. DICOM→NIfTI onboarding of `sub-102` (matrix §3's canonical "creates a new subject" row —
 *    sourcedata DICOMs, no BIDS dir yet). Previously unreachable from this page at all: an earlier
 *    lane found `getSubjects()` never listed a sourcedata-only subject (`catalog.list_subjects`
 *    was m2m/BIDS-only). Lane FX5 (`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` §7) made
 *    `tit.catalog.list_subjects`/`subject_detail` also list a sourcedata-only subject (with
 *    `has_sourcedata: true`, `has_raw: false`), so `sub-102` now appears in this page's own batch
 *    table (with a "not converted" chip) and the DICOM stage can be planned and run for it.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page);
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
});

test.afterAll(async () => {
  await app?.close();
});

test("tissue analysis on sub-101: accepted, started, and completed with a real artifact", async () => {
  test.setTimeout(360_000);

  /*
   * FXU2, against a server that really does hold this project's finished pre-processing jobs (the
   * exact condition of the maintainer's screenshot: opening the tab showed `pre · 102 · succeeded`
   * with a full DICOM-conversion log). Nothing of this page's kind is running, so the terminal
   * pins nothing and says so.
   */
  const terminal = page.getByTestId("job-terminal");
  await expect(terminal).toHaveAttribute("data-source", "empty");
  await expect(terminal.getByTestId("job-terminal-empty")).toBeVisible();
  await expect(terminal.locator(".job-console-line")).toHaveCount(0);

  // Tick sub-101 in the page's own batch table (U6) — matches the fixture matrix's "pre: tissue
  // analysis" row.
  await page.locator(".subject-picker-row", { hasText: "101" }).getByRole("checkbox").click();

  // Turn every default-on stage off, then turn on only Tissue analyzer.
  await page.getByLabel("Convert DICOM to NIfTI").uncheck();
  await page.getByLabel("SimNIBS charm (m2m + subject atlas)").uncheck();
  await page.getByLabel("FastSurfer segmentation").uncheck();
  await page.getByLabel("Tissue analyzer").check();

  await setExistingOutputsPolicy(page, "Replace and rerun");

  // The plan resolves against the real server: the G3 (tissue) column for 101 is not blocked.
  const cell = page.getByTestId("plan-cell-101-G3");
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|overwrite)$/);
  await expect(page.getByTestId("run-button")).toBeEnabled();

  const groupRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const groupResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  await page.getByTestId("run-button").click();

  // 101 already has tissue_analysis on disk (see file header) — the shared existing-outputs
  // question fires. It is a plain `dialog` (`ExistingOutputsDialog.tsx`), answered by test id.
  await answerExistingOutputs(page, "replace");

  const reqBody = (await groupRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: Record<string, unknown> };
  expect(reqBody.kind).toBe("pre");
  expect(reqBody.subject_ids).toEqual(["101"]);
  recordPayload("pre", reqBody);

  const respBody = (await (await groupResponse).json()) as { group_id: string; jobs: JobStatusLite[] };
  const preJob = respBody.jobs.find((j) => j.kind === "pre");
  expect(preJob, "the group response includes a kind=pre job").toBeTruthy();
  const jobId = (preJob as JobStatusLite).id;

  // Jobs rail + in-page terminal: "started" (P4), within the 120 s budget.
  await waitForJobTrace(page, "pre", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  // Completion, on the server's own record (300 s budget, matrix §3).
  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: 300_000 });
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");

  // The maintainer's brief: "look at the artifact it creates". `outputsTree.ts` has no results-tree
  // node kind for tissue analysis (only simulation/flex/ex/mex/analysis/report), and the trailing
  // `report` job every `pre` group plans (F0's known-broken kind — docs/dev/HISTORY.md § 2026-09-03 (pipelines program)
  // §0) would be what turns this run into a Results-visible report, so a "new node in Results"
  // assertion here would fail on F0's bug rather than on anything this lane owns. Assert on the
  // job's own reported artifacts existing on disk instead — the thing this behaviour actually is.
  expect(finalJob.artifacts?.length ?? 0, JSON.stringify(finalJob.artifacts)).toBeGreaterThan(0);
  for (const artifact of finalJob.artifacts ?? []) {
    const hostPath = artifact.path.replace(/^\/mnt\/000/, PROJECT_HOST_ROOT);
    expect(existsSync(hostPath), `artifact on host: ${hostPath}`).toBe(true);
  }

  console.log(
    `real/preprocess: job ${jobId} kind=pre subject=101 stage=tissue state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`,
  );

  // No cleanup: this run replaces sub-101's own pre-existing `tissue_analysis` output in place
  // (program §3's explicit "replace_existing_outputs" row) rather than creating a new smoke-tagged
  // path — there is nothing smoke-tagged here for `cleanupSmokeOutputs` to remove.
});

// ── sub-102 onboarding (lane FX5) ────────────────────────────────────────────────────────────

/** The two paths this test's own DICOM-conversion job creates *whole* for sub-102, project-
 *  relative — the BIDS subject directory itself and the `derivatives/SimNIBS` scaffold
 *  `run_pipeline` creates as a side effect of the DICOM stage (`tests/smoke/matrix.py`'s
 *  `pre_dicom` row's own `creates=` list). Neither may already exist; both are removed whole. */
const SUB102_MUST_NOT_PREEXIST = ["sub-102", "derivatives/SimNIBS/sub-102"];

/** `derivatives/ti-toolbox/reports/sub-102/` is *not* on that list: it is a shared directory a
 *  subject can carry pre-existing reports in (this dataset's own sub-102 does — an April 2026
 *  report predating the sourcedata-only state this test starts from), exactly the case
 *  `tests/smoke/cleanup.py`'s own `claim_produced` docstring describes. So this run's report
 *  file(s) are found by mtime (>= the moment Run was clicked) and removed individually, in
 *  `finally` below, never the directory. */
const SUB102_REPORTS_DIR = "derivatives/ti-toolbox/reports/sub-102";

function sub102HostPaths(): string[] {
  return SUB102_MUST_NOT_PREEXIST.map((rel) => join(PROJECT_HOST_ROOT, rel));
}

interface SubjectLite {
  id: string;
  has_raw: boolean;
  has_sourcedata?: boolean;
}

async function fetchSubject(id: string): Promise<SubjectLite | undefined> {
  const res = await fetch(`${SERVER_URL}/api/catalog/subjects`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  const body = (await res.json()) as { subjects: SubjectLite[] };
  return body.subjects.find((s) => s.id === id);
}

test("sub-102 DICOM onboarding: not converted -> plan -> run -> converted (lane FX5)", async () => {
  test.setTimeout(120_000);

  // Claim-before-create discipline (tests/smoke/cleanup.py): verified once, up front. If any of
  // these already exist, this is not a clean sub-102 -- a prior interrupted run, or something
  // real -- and cleanup must not run blindly, so the test fails here rather than deleting it.
  const hostPaths = sub102HostPaths();
  for (const p of hostPaths) {
    expect(existsSync(p), `pre-flight: ${p} must not already exist before this run`).toBe(false);
  }
  // Reassigned right before the Run click, below; declared out here so `finally` can read it too.
  let submittedAtMs = Date.now();

  // The bug this lane fixes, confirmed independently of the page: sub-102 is listed, not
  // converted (`tit.catalog.list_subjects`/`subject_detail`, `tit/server/routes/catalog*.py`).
  const before = await fetchSubject("102");
  expect(before, "GET /api/catalog/subjects lists sub-102 before conversion").toBeTruthy();
  expect(before?.has_raw).toBe(false);
  expect(before?.has_sourcedata).toBe(true);

  try {
    // The batch table lists sub-102 (previously invisible to this page at all) with a chip
    // flagging it as staged but not converted.
    const row102 = page.locator(".subject-picker-row", { hasText: "102" });
    await expect(row102).toBeVisible();
    await expect(row102.getByText("not converted")).toBeVisible();

    // Leave only sub-102 selected: untick 101 (selected by the previous test in this file), tick
    // 102, and plan only the DICOM stage — the fixture matrix's own `pre_dicom` row.
    await page.locator(".subject-picker-row", { hasText: "101" }).getByRole("checkbox").uncheck();
    await row102.getByRole("checkbox").check();
    await page.getByLabel("Convert DICOM to NIfTI").check();
    await page.getByLabel("SimNIBS charm (m2m + subject atlas)").uncheck();
    await page.getByLabel("FastSurfer segmentation").uncheck();
    await page.getByLabel("Tissue analyzer").uncheck();

    await setExistingOutputsPolicy(page, "Skip existing outputs");

    // The plan resolves against the real server: the G1 (DICOM) column for 102 is a new job.
    const cell = page.getByTestId("plan-cell-102-G1");
    await expect(cell).toBeVisible({ timeout: 15_000 });
    await expect(cell).toHaveText("new");
    await expect(page.getByTestId("run-button")).toBeEnabled();

    const groupRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
    const groupResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
    // For the reports-directory mtime cleanup in `finally` (claim_produced's discipline) — a
    // couple of seconds before the click, not after, so a report the server writes in the same
    // second as this timestamp is never mistaken for a pre-existing one.
    submittedAtMs = Date.now() - 2000;
    await page.getByTestId("run-button").click();
    // sub-102 already carries a pre-existing report (see SUB102_REPORTS_DIR), so the group's own
    // trailing `report` job trips the shared existing-outputs question even though the DICOM stage
    // itself is new. Skip: the DICOM job runs either way, and nothing pre-existing is overwritten.
    await answerExistingOutputs(page, "skip");

    const reqBody = (await groupRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: Record<string, unknown> };
    expect(reqBody.kind).toBe("pre");
    expect(reqBody.subject_ids).toEqual(["102"]);
    // Row id, not the bare kind: `pre.json` is already owned by the tissue-analysis row above, and
    // lane S1's own notes ask for exactly this filename for the DICOM-stage payload.
    recordPayload("pre_dicom", reqBody);

    const respBody = (await (await groupResponse).json()) as { group_id: string; jobs: JobStatusLite[] };
    const preJob = respBody.jobs.find((j) => j.kind === "pre");
    expect(preJob, "the group response includes a kind=pre job").toBeTruthy();
    const jobId = (preJob as JobStatusLite).id;

    // "started" (P4).
    await waitForJobTrace(page, "pre", { timeoutMs: 60_000 });

    // Completion — matrix §3 budget for pre_dicom is 300 s; lane S1 measured 8.0 s of real work.
    const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: 60_000 });
    expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
    expect(finalJob.artifacts?.length ?? 0, JSON.stringify(finalJob.artifacts)).toBeGreaterThan(0);
    for (const artifact of finalJob.artifacts ?? []) {
      const hostPath = artifact.path.replace(/^\/mnt\/000/, PROJECT_HOST_ROOT);
      expect(existsSync(hostPath), `artifact on host: ${hostPath}`).toBe(true);
    }

    // The point of this lane: the subject is now onboarded, on the same route the page used to
    // list it as not-converted through.
    const after = await fetchSubject("102");
    expect(after?.has_raw, "sub-102 now has a converted BIDS anat directory").toBe(true);

    console.log(
      `real/preprocess: job ${jobId} kind=pre subject=102 stage=dicom state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`,
    );

    // Also wait out the group's trailing `report` job (F0's consolidated report) before `finally`
    // reads the reports directory below — the DICOM stage's own job report and this one both land
    // there, and reading the directory while the second is still mid-write is exactly how a run's
    // own report file escaped the mtime cleanup once (found and fixed on the very first real run
    // of this test; left the stray file exactly where its own log line said, on host).
    const reportJob = respBody.jobs.find((j) => j.kind === "report");
    if (reportJob) {
      const finalReportJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: reportJob.id, timeoutMs: 30_000 });
      // "skipped" is the right answer when the dialog above was answered "skip" — the point is
      // only that the report job reached a terminal state before `finally` reads the directory.
      expect(["succeeded", "skipped"], JSON.stringify(finalReportJob.error)).toContain(finalReportJob.state);
    }
  } finally {
    // The two whole-directory claims: the pre-flight check already proved neither pre-existed, so
    // removing them here (whether the run above succeeded or threw) cannot destroy real data
    // (tests/smoke/cleanup.py's discipline, applied to a UI-driven run).
    for (const p of hostPaths) {
      if (existsSync(p)) rmSync(p, { recursive: true, force: true });
    }
    // The reports directory is shared and this dataset's own sub-102 already carries a
    // pre-existing report in it (see SUB102_REPORTS_DIR above) — delete only the file(s) this
    // run's own jobs wrote (mtime at/after the click), mirroring claim_produced exactly, never
    // the directory or anything older.
    const reportsDirHost = join(PROJECT_HOST_ROOT, SUB102_REPORTS_DIR);
    if (existsSync(reportsDirHost)) {
      for (const name of readdirSync(reportsDirHost)) {
        const filePath = join(reportsDirHost, name);
        if (statSync(filePath).mtimeMs >= submittedAtMs) rmSync(filePath, { force: true });
      }
    }
  }
});

/**
 * The existing-output policy is a user-level setting (Settings ▸ Execution, 2026-09-06). Set it
 * there and return to the page the caller was on.
 */
async function setExistingOutputsPolicy(page: Page, label: "Skip existing outputs" | "Replace and rerun"): Promise<void> {
  const from = await page.getByTestId("shell-content").getAttribute("data-page");
  await gotoPage(page, "settings", "Settings");
  await expectPage(page, "settings");
  await page
    .locator('[data-page-active="true"] .segmented[aria-label="Existing outputs"]')
    .getByRole("radio", { name: label, exact: true })
    .click();
  await gotoPage(page, from ?? "preprocess");
  await expectPage(page, from ?? "preprocess");
}
