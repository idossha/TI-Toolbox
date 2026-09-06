import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import { answerExistingOutputs, expectPage, gotoPage, launchElectronApp, openPalette, setSectionOpen } from "./_helpers";
import { setSubjectChecked, subjectsField } from "./_subjects";

/**
 * Subject selection and execution policy (IMPLEMENTATION_PLAN.md R3), against the mock server.
 *
 * The gate this file closes, in its own order:
 *
 *  1. every subject-taking workflow shows the shared selector, OPEN, on first visit;
 *  2. two subjects produce two plan rows;
 *  3. a batch is submitted as ONE `POST /api/jobs/groups` carrying `parallel_subjects` — the UI
 *     never substitutes client-side parallel or spaced-out `POST /api/jobs` calls for the cap;
 *  4. each generated config carries exactly its own subject id;
 *  5. with a cap of 1 the scheduler never has two group members `running`; with a cap of 2 it
 *     does admit two when locks and resources permit.
 *
 * (5) is asserted against the mock server's scheduler rather than a real container: the pipelines
 * program's standing rule is that two FEM simulations must never run concurrently on the shared
 * dev container (`dev/notes/v3-pipelines/RUNBOOK.md`), so a real-data proof of a cap of 2 would
 * be the exact thing it forbids. The cap logic under test is the same shape in both
 * (`tit/jobs/scheduler.py`'s `group_cap` branch, mirrored by the mock's `isReady`), and the
 * server-side half is pinned directly in `tests/test_jobs_routes.py`.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

/** Every job of one group, read straight off the server — the scheduler's own record. */
async function groupJobs(groupId: string): Promise<{ id: string; state: string }[]> {
  const res = await page.request.get(`${SERVER_URL}/api/jobs`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  expect(res.ok()).toBeTruthy();
  const jobs = (await res.json()) as { id: string; state: string; group_id: string | null }[];
  return jobs.filter((j) => j.group_id === groupId);
}

async function submitGroup(body: Record<string, unknown>): Promise<string> {
  const res = await page.request.post(`${SERVER_URL}/api/jobs/groups`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: body,
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { group_id: string }).group_id;
}

/** A short synthetic sim config; `__mock_fast` keeps each member well under a second. */
function fastSimConfig(subject: string) {
  return {
    subject_id: subject,
    montages: [{ _type: "Montage", name: "m1", mode: "net", electrode_pairs: [["E1", "E2"], ["E3", "E4"]], eeg_net: "GSN-HydroCel-185.csv" }],
    __mock_fast: true,
  };
}

// -------------------------------------------------------------------------------------------
// 1. The shared selector, open, on first visit of every subject-taking workflow
// -------------------------------------------------------------------------------------------

const SUBJECT_TAKING: { id: string; nav: string }[] = [
  { id: "preprocess", nav: "Pre-processing" },
  { id: "simulator", nav: "Simulator" },
  { id: "optimizer", nav: "Optimizer" },
  { id: "analyzer", nav: "Analyzer" },
];

for (const workflow of SUBJECT_TAKING) {
  test(`${workflow.id}: the shared subject selector is shown, open, on first visit`, async () => {
    // FIRST visit really is first: this file launches its own app with a fresh user-data dir, and
    // the disclosure is page-session memory, so the assertion below is only true of a page nothing
    // has collapsed yet — which is exactly the state a new user meets.
    await gotoPage(page, workflow.id, workflow.nav);
    await expectPage(page, workflow.id);
    const field = subjectsField(page);
    await expect(field).toHaveCount(1);
    await expect(field).toHaveAttribute("data-open", "true");
    await expect(field.getByTestId("subjects-field-table")).toBeVisible();
  });
}

test("the Source panel shows the same control, open", async () => {
  await gotoPage(page, "panel-source", "Source");
  await expectPage(page, "panel-source");
  await expect(subjectsField(page)).toHaveAttribute("data-open", "true");
});

// -------------------------------------------------------------------------------------------
// 2-4. Two subjects -> two plan rows -> ONE group request carrying the cap
// -------------------------------------------------------------------------------------------

test("two subjects produce two plan rows on Pre-processing", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
  await setSubjectChecked(page, "ernie", true);
  await setSubjectChecked(page, "101", true);
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "2");
  // One matrix row per subject — the plan states the batch before anything is submitted.
  await expect(page.locator('[data-page-active="true"] .plan-matrix tbody tr')).toHaveCount(2, { timeout: 15_000 });
});

test("the cap goes to the server in ONE request, and never as client-side parallel POSTs", async () => {
  // The shared `Subjects in parallel` control lives in the collapsed "Existing outputs" section
  // on this page; the same component, testid and meaning appear on Simulator and Optimizer.
  await setSectionOpen(page, "Existing outputs", true);
  // Scoped to the ACTIVE page: the shell keeps every visited page mounted, so an unscoped testid
  // resolves to one control per page that has one.
  const active = page.locator('[data-page-active="true"]');
  const parallel = active.getByTestId("subjects-in-parallel");
  await expect(parallel).toBeVisible();
  await parallel.fill("2");
  await parallel.blur();

  // Record EVERY job-submitting request the click causes, not just the first: a page that fanned
  // out one `POST /api/jobs` per subject (what these pages used to do) would show up here as two
  // or more calls, which is the substitution R3 forbids.
  const submissions: Request[] = [];
  const record = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) submissions.push(r);
  };
  page.on("request", record);
  await active.getByTestId("run-button").click();
  // Some of these subjects already have output, so the one shared existing-outputs question
  // (plan C3) comes first on every run page now. Answering it is what submits.
  await answerExistingOutputs(page);
  await expect(page.getByText(/Queued preprocessing for 2 subjects/)).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(1000); // any straggler POST from a fan-out would land inside this
  page.off("request", record);

  expect(submissions).toHaveLength(1);
  const body = submissions[0]!.postDataJSON() as { kind: string; subject_ids: string[]; parallel_subjects: number };
  expect(new URL(submissions[0]!.url()).pathname).toBe("/api/jobs/groups");
  expect(body.kind).toBe("pre");
  expect(body.subject_ids).toEqual(["ernie", "101"]);
  expect(body.parallel_subjects).toBe(2);
});

test("each generated config carries exactly its own subject id", async () => {
  // Submitted through the same endpoint the UI uses, with a template naming ONE subject: the
  // server is what narrows each job's config, so a page can never leak one subject's id into
  // another subject's run.
  const groupId = await submitGroup({
    kind: "sim",
    config: fastSimConfig("ernie"),
    subject_ids: ["ernie", "101"],
    parallel_subjects: 1,
  });
  const jobs = await groupJobs(groupId);
  expect(jobs).toHaveLength(2);
  for (const job of jobs) {
    const res = await page.request.get(`${SERVER_URL}/api/jobs/${job.id}`, { headers: { Authorization: `Bearer ${TOKEN}` } });
    const detail = (await res.json()) as { spec: { config: Record<string, unknown>; subject_ids: string[] } };
    const subject = detail.spec.subject_ids[0]!;
    expect(detail.spec.config.subject_id).toBe(subject);
    const other = subject === "ernie" ? "101" : "ernie";
    expect(JSON.stringify(detail.spec.config)).not.toContain(other);
  }
});

// -------------------------------------------------------------------------------------------
// 5. Scheduler states under a cap of 1 and a cap of 2
// -------------------------------------------------------------------------------------------

test("a cap of 1 never has two group members running", async () => {
  const groupId = await submitGroup({
    kind: "sim",
    config: fastSimConfig("ernie"),
    subject_ids: ["ernie", "101", "102"],
    parallel_subjects: 1,
  });

  let peak = 0;
  const deadline = Date.now() + 60_000;
  for (;;) {
    const jobs = await groupJobs(groupId);
    const running = jobs.filter((j) => j.state === "running");
    peak = Math.max(peak, running.length);
    expect(running.length, `states: ${jobs.map((j) => j.state).join(",")}`).toBeLessThanOrEqual(1);
    if (jobs.length === 3 && jobs.every((j) => !["queued", "running"].includes(j.state))) break;
    expect(Date.now(), "group did not finish").toBeLessThan(deadline);
    await page.waitForTimeout(150);
  }
  // Not vacuous: the cap really did have something to hold back, and one member did run.
  expect(peak).toBe(1);
});

test("a cap of 2 admits two members at once", async () => {
  const groupId = await submitGroup({
    kind: "sim",
    config: fastSimConfig("ernie"),
    subject_ids: ["ernie", "101", "102"],
    parallel_subjects: 2,
  });

  let peak = 0;
  const deadline = Date.now() + 60_000;
  for (;;) {
    const jobs = await groupJobs(groupId);
    const running = jobs.filter((j) => j.state === "running");
    peak = Math.max(peak, running.length);
    expect(running.length).toBeLessThanOrEqual(2);
    if (peak === 2 || (jobs.length === 3 && jobs.every((j) => !["queued", "running"].includes(j.state)))) break;
    expect(Date.now(), "group did not finish").toBeLessThan(deadline);
    await page.waitForTimeout(100);
  }
  expect(peak).toBe(2);
});
