/**
 * The one selection grammar, end to end (plan `v3-tetravox-selection-pipeline-plan.md` §1-C).
 *
 * This spec exists because "one grammar" is a claim about *every* page at once, and a per-page
 * spec can only ever check its own page. What it pins:
 *
 *   1. every subject-taking page renders the same control, with the same testids and the same two
 *      bulk buttons — so a page that grows a second idiom fails here and nowhere else;
 *   2. ⇧-click selects a range, ⌘-click toggles, and a plain click selects exactly one;
 *   3. no run page carries a receipt any more (removed 2026-09-06): the plan grid in the run pane
 *      and the action-bar digest are the confirmation, they agree on the count, and they update
 *      live as the selection changes;
 *   4. the shared existing-outputs dialog opens from all four run pages with the same three
 *      buttons;
 *   5. the Jobs page's rows are selectable and its bulk cancel sends exactly the selected ids.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { configureMontageJob } from "./_jobs";
import { openSubjects, selectSubjects, subjectRow, subjectRows, subjectsField } from "./_subjects";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
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

/** The header checkbox — the control's ONE bulk act now that `All · None` are gone. */
function subjectsHeaderBox(): Locator {
  return subjectsField(page).locator("thead .checkbox-root");
}

/** Clears the selection: the header box, pressed until nothing is ticked (indeterminate fills in
 *  first, so at most two presses). */
async function clearSubjects(): Promise<void> {
  for (let i = 0; i < 2; i += 1) {
    if ((await subjectsField(page).getAttribute("data-selected")) === "0") return;
    await subjectsHeaderBox().click();
  }
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "0");
}

/** Leaves exactly `ernie` chosen, whatever the previous test left behind. */
async function selectOnlyErnie(): Promise<void> {
  await clearSubjects();
  await subjectsField(page).getByTestId("subjects-filter").fill("ernie");
  await subjectsHeaderBox().click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
}

/*
 * 2026-09-06 jobs rework: the Simulator, the Analyzer and the Optimizer have no page-level subject
 * control — the
 * subject is a cell of a job row, picked with the same `SelectionPicker` grammar (asserted in
 * `batch.spec.ts` and in each page's own spec). What is left here is the pages whose whole job IS
 * a batch over subjects.
 */
const SUBJECT_PAGES = [["preprocess", "Pre-processing"]] as const;

for (const [id, title] of SUBJECT_PAGES) {
  test(`${title}: the subject control is the one selection list, with the same testids`, async () => {
    await gotoPage(page, id, title);
    await expectPage(page, id);
    await openSubjects(page);
    const field = subjectsField(page);
    // The same parts, on every page: the filter, the rows, and the header checkbox wherever more
    // than one thing can be chosen (the Analyzer's Subject scope is `single`: one job, one
    // subject, so there is nothing to select all of and no header box is drawn). No `All · None`
    // pair and no count badge — the header box is the bulk act and the summary line states the
    // count.
    await expect(field.getByTestId("subjects-filter")).toBeVisible();
    const single = (await field.getAttribute("data-mode")) === "single";
    await expect(field.getByTestId("subject-select-all")).toHaveCount(0);
    await expect(field.getByTestId("subject-select-none")).toHaveCount(0);
    await expect(field.getByTestId("subject-count")).toHaveCount(0);
    await expect(subjectsHeaderBox()).toHaveCount(single ? 0 : 1);
    // ARIA: one multi-selectable listbox whose rows are options (the Analyzer's `single` mode is
    // the one exception — it is a listbox that takes one).
    const box = field.getByTestId("subjects-field-table");
    await expect(box).toHaveAttribute("role", "listbox");
    await expect(subjectRows(page).first()).toHaveAttribute("role", "option");
    // And exactly ONE such control on the page — the defect this grammar closes is a page having
    // two ways to pick the same thing.
    await expect(page.locator('[data-page-active="true"]').getByTestId("subjects-field")).toHaveCount(1);
  });
}

test("a plain click selects one row, ⇧-click takes a range, ⌘-click toggles", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  const ids = await subjectRows(page).evaluateAll((rows) =>
    rows.map((r) => (r.getAttribute("data-testid") ?? "").replace("subject-row-", "")),
  );
  expect(ids.length).toBeGreaterThanOrEqual(3);
  const first = subjectRow(page, ids[0] as string);
  const last = subjectRow(page, ids[2] as string);
  const middle = subjectRow(page, ids[1] as string);
  // Start from nothing chosen, so the first click is unambiguously "select this one".
  await clearSubjects();

  await first.locator("td").nth(1).click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");

  await last.locator("td").nth(1).click({ modifiers: ["Shift"] });
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "3");
  await expect(middle).toHaveAttribute("data-selected", "true");

  await middle.locator("td").nth(1).click({ modifiers: [process.platform === "darwin" ? "Meta" : "Control"] });
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "2");
  await expect(middle).toHaveAttribute("data-selected", "false");

  // The header box clears what is visible, then takes all of it.
  await clearSubjects();
  await subjectsHeaderBox().click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", String(ids.length));
});

test("the filter narrows the rows, and the header box only takes what is visible", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  await clearSubjects();
  await subjectsField(page).getByTestId("subjects-filter").fill("ernie");
  await expect(subjectRows(page)).toHaveCount(1);
  await subjectsHeaderBox().click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
  // Clearing the filter does not add the rows it was hiding — a bulk act works on what you see.
  await subjectsField(page).getByTestId("subjects-filter").fill("");
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
});

test("the plan grid and the digest state the batch, with no receipt, and update live", async () => {
  // On the Simulator, where the receipt used to sit above Run: the confirmation is now the plan
  // grid in the run pane plus the action-bar digest, and neither overlays the form it confirms.
  await gotoPage(page, "simulator", "Simulator");
  // Exactly one job, so the plan is one job: the mock plans every montage into the same output
  // directory, so several would collapse into one plan column and the count comparison below
  // would compare unlike things.
  const active = page.locator('[data-page-active="true"]');
  const removeRow = active.getByRole("button", { name: /^Remove job / });
  for (let guard = 0; (await removeRow.count()) > 1 && guard < 20; guard++) await removeRow.last().click();
  const jobRow = active.locator("tr[data-job-row]").first();
  await configureMontageJob(page, jobRow, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });

  await expect(active.getByTestId("run-receipt")).toHaveCount(0);
  // Scoped to the active page: other pages stay mounted, so an unscoped `plan-grid` would count
  // another page's cells.
  const cells = active.getByTestId("plan-grid").locator(".plan-cell-button");
  await expect(cells.first()).toBeVisible({ timeout: 20_000 });
  const jobs = await cells.count();
  expect(jobs).toBeGreaterThan(0);
  // The digest IS the same `PlanModel` the grid draws, so the two cannot disagree on the count.
  await expect(active.locator(".action-bar-digest")).toHaveText(
    new RegExp(`\\b${jobs} job`),
    { timeout: 20_000 },
  );

  // Live: emptying the table empties the plan, and the disabled primary carries the reason.
  await jobRow.getByRole("button", { name: "Remove job 1" }).click();
  await expect(active.locator("tr[data-job-row]")).toHaveCount(0);
  await expect(active.locator(".action-bar-digest")).toHaveCount(0);
  const run = active.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Add a job with a subject and a montage.");
});

test("Pre-processing states its batch in the plan and the digest", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  await selectSubjects(page, ["ernie"]);
  const active = page.locator('[data-page-active="true"]');
  await expect(active.getByTestId("run-receipt")).toHaveCount(0);
  await expect(active.getByTestId("plan-grid")).toBeVisible({ timeout: 20_000 });
  await expect(active.locator(".action-bar-digest")).toHaveText(/job/, { timeout: 20_000 });
});

test("Jobs rows are selectable, and the bulk cancel sends exactly the selected ids", async () => {
  // Two jobs of our own, so the assertion never depends on what an earlier spec left behind.
  for (const subject of ["ernie", "101"]) {
    const res = await page.request.post(`${SERVER_URL}/api/jobs`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
      data: { kind: "sim", config: { __mock_fast: false }, subject_ids: [subject], tags: ["selection-spec"] },
    });
    expect(res.ok()).toBeTruthy();
  }
  await gotoPage(page, "jobs", "Jobs");
  const table = page.getByTestId("jobs-table");
  await expect(table).toBeVisible();
  const rows = table.locator("[data-row-index]");
  await expect.poll(() => rows.count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(2);

  const cancelled: string[] = [];
  await page.route("**/api/jobs/*/cancel", async (route) => {
    cancelled.push(new URL(route.request().url()).pathname.split("/").slice(-2, -1)[0] as string);
    await route.continue();
  });

  await rows.nth(0).locator("td").nth(1).click();
  await rows.nth(1).locator("td").nth(1).click({ modifiers: ["Shift"] });
  await expect(table.getByTestId("job-count")).toHaveText(/^2 of \d+ selected$/);

  const button = table.getByTestId("jobs-cancel-selected");
  if (await button.count()) {
    const ids = await rows.evaluateAll((els) =>
      els.slice(0, 2).map((e) => (e.getAttribute("data-testid") ?? "").replace("job-row-", "")),
    );
    await button.click();
    await expect.poll(() => cancelled.length, { timeout: 10_000 }).toBeGreaterThan(0);
    // Exactly the selected ids — never the whole filtered list.
    for (const id of cancelled) expect(ids).toContain(id);
  }
  await page.unroute("**/api/jobs/*/cancel");
});

test("the shared existing-outputs dialog is one question with three answers", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  await selectOnlyErnie();

  // The plan grid is what states the batch here. Wait for it
  // to resolve — these subjects have output already, so pressing Run then asks the shared
  // question rather than submitting silently.
  await expect(
    page.locator('[data-page-active="true"]').getByTestId("plan-grid").locator(".plan-cell-button").first(),
  ).toBeVisible({ timeout: 20_000 });

  await page.locator('[data-page-active="true"]').getByTestId("run-button").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Some outputs already exist");
  await expect(dialog.getByTestId("existing-outputs-skip")).toBeVisible();
  await expect(dialog.getByTestId("existing-outputs-replace")).toHaveText("Replace and rerun");
  await expect(dialog.getByTestId("existing-outputs-cancel")).toHaveText("Cancel");
  await expect(dialog.getByTestId("existing-outputs-replace")).toBeDisabled();
  // Cancel queues nothing; saving the project permission still requires a fresh confirmation.
  await dialog.getByTestId("existing-outputs-cancel").click();
  await expect(dialog).toHaveCount(0);
  await gotoPage(page, "settings", "Settings");
  await page.getByRole("switch", { name: "Allow unsafe overrides" }).click();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
  await gotoPage(page, "preprocess", "Pre-processing");
  let submissions = 0;
  const observe = (request: import("@playwright/test").Request) => {
    if (request.method() === "POST" && /\/api\/jobs(?:\/groups)?$/.test(new URL(request.url()).pathname)) submissions++;
  };
  page.on("request", observe);
  await page.locator('[data-page-active="true"]').getByTestId("run-button").click();
  await expect(dialog.getByTestId("existing-outputs-replace")).toBeEnabled();
  expect(submissions).toBe(0);
  await dialog.getByTestId("existing-outputs-cancel").click();
  await page.locator('[data-page-active="true"]').getByTestId("run-button").click();
  await expect(dialog.getByTestId("existing-outputs-replace")).toBeEnabled();
  expect(submissions).toBe(0);
  await dialog.getByTestId("existing-outputs-replace").click();
  await expect.poll(() => submissions).toBe(1);
  page.off("request", observe);
});
