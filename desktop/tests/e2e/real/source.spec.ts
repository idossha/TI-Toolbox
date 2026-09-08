import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import {
  connectReal,
  expectPage,
  launchElectronApp,
  PROJECT_HOST_ROOT,
  recordPayload,
  openJobRawLog,
  waitForJobTerminal,
  waitForJobTrace,
  type JobStatusLite,
} from "../_helpers";

/**
 * Panel — Source (EEG forward solution), against the shared dev container. Fixture matrix row:
 * "completed if mne is in the image" — confirmed present (`docker exec ... python -c "import mne"`
 * -> 1.12.1) — so this runs to completion, within `JOB_TIMEOUT_MS` below (defect 2: the old 600 s
 * budget measured too tight on this emulated container more than once — see that constant's own
 * comment and `fix-c-notes.md`).
 *
 * `sub-101`, not the matrix's `sub-ernie`: this page's "Build forward solution" writes to the
 * subject's single fixed `forward/` directory (no run-name field to tag), and ernie already has
 * one from an earlier real fsaverage-mapping run (`forward/fsaverage/...Thalamus...npz`). 101 has
 * an m2m and EEG nets but no `forward/` directory yet, so this is a clean create rather than an
 * overwrite of a pre-existing output (P6) — verified below, not assumed.
 *
 * This panel has no page-local `job-terminal` (only the four shape-A run pages do) — its "page
 * terminal" is the shared jobs rail's Console tab (⌘J), asserted the same way `jobs.spec.ts`
 * already does for the mock.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const FORWARD_DIR = join(PROJECT_HOST_ROOT, "derivatives/SimNIBS/sub-101/forward");

// Defect 2 (docs/dev/HISTORY.md § 2026-09-04 (scene service) §2b, fix-round 2026-09-04, lane FIX-C): this
// job's own measured completions on this container — SUB 2026-09-04 exceeded 600 000ms outright
// (`sub-notes.md` §6 item 5), LAY's own run 9.5m (570 000ms, critic-notes.md §7), critic's own run
// 9.7m (582 000ms, critic-notes.md §2b) — cluster at 570-600s+ with no headroom, so the *documented*
// 600s budget was already failing on the emulated container this actually runs against before this
// fix, not a one-off flake. Re-measured fresh for this fix (2026-09-04, this container, sub-101,
// `GET /api/jobs` clean before): job `a9784875fe9144af` succeeded in **571.0s** (whole test,
// including the UI steps around it: 9.7m / 582s). The budget below is that measurement with ~58%
// margin (329s), not the old number nudged up.
const JOB_TIMEOUT_MS = 900_000; // 15 min — 571.0s measured + ~58% margin; see fix-c-notes.md
const TEST_TIMEOUT_MS = JOB_TIMEOUT_MS + 60_000; // the job budget plus room for the UI steps around it

let app: ElectronApplication;
let page: Page;
// Set the moment the job is created (test body), read by `afterAll` — a job id is local to the
// `test()` callback otherwise, and `afterAll` runs in a separate closure that never sees it.
let jobId: string | undefined;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  expect(existsSync(FORWARD_DIR), `sub-101 must have no forward/ yet — ${FORWARD_DIR}`).toBe(false);
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await page.getByRole("link", { name: "Source", exact: true }).click();
  await expectPage(page, "panel-source");
});

const JOB_TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled", "skipped", "lost"]);

/**
 * Waits for the job to finish, or cancels it first, before anything below touches `FORWARD_DIR` —
 * fixing the other half of defect 2. Before this, a slow-but-still-writing job (the exact case a
 * too-tight `JOB_TIMEOUT_MS` produces: `waitForJobTerminal` throws, the test fails, `afterAll`
 * still runs) hit `rmSync(FORWARD_DIR, ...)` while `tit.source`'s real subprocess on the container
 * was still writing into it — measured by lane SUB (`sub-notes.md` §6 item 5): its own timeout left
 * a real forward-solution job running on the container, which SUB had to notice and cancel by hand
 * from outside the spec entirely so it would not hold the one-FEM slot. A short, bounded wait for
 * the job to reach ANY terminal state; if it has not by then, an explicit cancel and one more short
 * wait for that cancel to actually land (`cancelled` means the runner subprocess has been sent
 * SIGTERM and the mock/real server's own record reflects it — not merely that the HTTP call
 * returned) — only then is it safe to delete anything the job might still hold a file handle in.
 */
async function ensureJobStopped(id: string): Promise<JobStatusLite | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  let current: JobStatusLite | null = null;
  try {
    const res = await fetch(`${SERVER_URL}/api/jobs/${id}`, { headers: { Authorization: `Bearer ${TOKEN}` }, signal: controller.signal });
    if (res.ok) {
      const body = (await res.json()) as { status?: JobStatusLite } & Partial<JobStatusLite>;
      current = body.status ?? (body as JobStatusLite) ?? null;
    }
  } catch {
    /* treated as non-terminal below — the cancel POST is the same fetch-and-swallow shape */
  } finally {
    clearTimeout(timer);
  }
  if (current && JOB_TERMINAL_STATES.has(current.state)) return current;

  console.log(`real/source afterAll: job ${id} still ${current?.state ?? "unknown"} — cancelling before touching ${FORWARD_DIR}`);
  try {
    await fetch(`${SERVER_URL}/api/jobs/${id}/cancel`, { method: "POST", headers: { Authorization: `Bearer ${TOKEN}` } });
  } catch {
    /* waitForJobTerminal below still polls either way; a failed cancel POST is not fatal here */
  }
  try {
    return await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: id, timeoutMs: 60_000, pollMs: 2000 });
  } catch (err) {
    // Cancel itself did not land within a minute — surfaced, not swallowed, so a genuinely stuck
    // job on the container is a loud finding rather than a silently-skipped cleanup.
    console.error(`real/source afterAll: job ${id} would not reach a terminal state even after cancel — ${String(err)}`);
    return current;
  }
}

test.afterAll(async () => {
  if (jobId) await ensureJobStopped(jobId);
  if (existsSync(FORWARD_DIR)) rmSync(FORWARD_DIR, { recursive: true, force: true });
  await app?.close();
});

test("build forward solution for sub-101: accepted, started, and completed", async () => {
  test.setTimeout(TEST_TIMEOUT_MS);

  await page.locator(".subject-picker-row", { hasText: "101" }).click();
  await page.getByLabel("EEG net").click();
  await page.getByRole("option", { name: "EEG10-10_UI_Jurak_2007.csv", exact: true }).click();

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByRole("button", { name: "Build forward" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Build forward" }).click();

  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    config: { mode: string; forward: { eeg_net: string } };
  };
  expect(body.kind).toBe("source");
  expect(body.subject_ids).toEqual(["101"]);
  expect(body.config.mode).toBe("forward");
  // `tit/source/config.py`'s documented contract: no `.csv` suffix (the runner appends it itself —
  // `panels/source/config.ts`'s `stripCsvSuffix`, fixed alongside this spec after a real run
  // failed on "EEG10-10_UI_Jurak_2007.csv.csv").
  expect(body.config.forward.eeg_net).toBe("EEG10-10_UI_Jurak_2007");
  recordPayload("source", body);

  const created = (await (await jobResponse).json()) as { id: string };
  jobId = created.id; // afterAll's cleanup needs this the moment it exists, success or not
  // Click the trace (not just wait for it): the detail pane's Raw log renders the *selected*
  // job's log — the pane's `job` prop is `undefined` (empty state, no `.job-console-line` ever)
  // until something calls `select(job.id)`, which only the trace's own `onClick` does.
  const trace = await waitForJobTrace(page, "source", { timeoutMs: 120_000 });
  await trace.click();
  await openJobRawLog(page);
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const startedAtMs = Date.now();
  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: JOB_TIMEOUT_MS });
  const elapsedS = ((Date.now() - startedAtMs) / 1000).toFixed(1);
  console.log(`real/source: job ${created.id} state=${finalJob.state} elapsed=${elapsedS}s artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(existsSync(FORWARD_DIR), `forward/ created at ${FORWARD_DIR}`).toBe(true);
});
