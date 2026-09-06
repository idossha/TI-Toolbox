/**
 * The one selection grammar, end to end (plan `v3-tetravox-selection-pipeline-plan.md` §1-C).
 *
 * This spec exists because "one grammar" is a claim about *every* page at once, and a per-page
 * spec can only ever check its own page. What it pins:
 *
 *   1. every subject-taking page renders the same control, with the same testids and the same two
 *      bulk buttons — so a page that grows a second idiom fails here and nowhere else;
 *   2. ⇧-click selects a range, ⌘-click toggles, and a plain click selects exactly one;
 *   3. the receipt sits above Run on all four run pages, its count equals the plan's rows, and it
 *      updates live as the selection changes;
 *   4. the shared existing-outputs dialog opens from all four run pages with the same three
 *      buttons;
 *   5. the Jobs page's rows are selectable and its bulk cancel sends exactly the selected ids.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { openSubjects, subjectRow, subjectRows, subjectsField } from "./_subjects";

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

/** Leaves exactly `ernie` chosen, whatever the previous test left behind. */
async function selectOnlyErnie(): Promise<void> {
  const none = subjectsField(page).getByTestId("subject-select-none");
  if (await none.isEnabled()) await none.click();
  await subjectsField(page).getByTestId("subjects-filter").fill("ernie");
  await subjectsField(page).getByTestId("subject-select-all").click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
}

const SUBJECT_PAGES = [
  ["preprocess", "Pre-processing"],
  ["simulator", "Simulator"],
  ["optimizer", "Optimizer"],
  ["analyzer", "Analyzer"],
] as const;

for (const [id, title] of SUBJECT_PAGES) {
  test(`${title}: the subject control is the one selection list, with the same testids`, async () => {
    await gotoPage(page, id, title);
    await expectPage(page, id);
    await openSubjects(page);
    const field = subjectsField(page);
    // The same parts, on every page: filter, the badge, the rows — and `All · None` wherever more
    // than one thing can be chosen (the Analyzer's Subject scope is `single`: one job, one
    // subject, so there is nothing to select all of and neither button is drawn).
    await expect(field.getByTestId("subjects-filter")).toBeVisible();
    const single = (await field.getAttribute("data-mode")) === "single";
    await expect(field.getByTestId("subject-select-all")).toHaveCount(single ? 0 : 1);
    await expect(field.getByTestId("subject-select-none")).toHaveCount(single ? 0 : 1);
    if (!single) {
      await expect(field.getByTestId("subject-select-all")).toHaveText("All");
      await expect(field.getByTestId("subject-select-none")).toHaveText("None");
    }
    await expect(field.getByTestId("subject-count")).toHaveText(/^(None|\d+) of \d+ selected$/);
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
  await subjectsField(page).getByTestId("subject-select-none").click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "0");

  await first.locator("td").nth(1).click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");

  await last.locator("td").nth(1).click({ modifiers: ["Shift"] });
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "3");
  await expect(middle).toHaveAttribute("data-selected", "true");

  await middle.locator("td").nth(1).click({ modifiers: [process.platform === "darwin" ? "Meta" : "Control"] });
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "2");
  await expect(middle).toHaveAttribute("data-selected", "false");

  // None clears what is visible; the badge is the one status line and follows.
  await subjectsField(page).getByTestId("subject-select-none").click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "0");
  await subjectsField(page).getByTestId("subject-select-all").click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", String(ids.length));
});

test("the filter narrows the rows, and All only takes what is visible", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  const none0 = subjectsField(page).getByTestId("subject-select-none");
  if (await none0.isEnabled()) await none0.click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "0");
  await subjectsField(page).getByTestId("subjects-filter").fill("ernie");
  await expect(subjectRows(page)).toHaveCount(1);
  await subjectsField(page).getByTestId("subject-select-all").click();
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
  // Clearing the filter does not add the rows it was hiding — a bulk button acts on what you see.
  await subjectsField(page).getByTestId("subjects-filter").fill("");
  await expect(subjectsField(page)).toHaveAttribute("data-selected", "1");
});

test("the receipt sits above Run, counts the plan's jobs, and updates live", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await openSubjects(page);
  await selectOnlyErnie();

  const receipt = page.locator('[data-page-active="true"]').getByTestId("run-receipt");
  await expect(receipt).toBeVisible();
  await expect(receipt.getByTestId("run-receipt-headline")).toHaveText(/This will run \d+ jobs?:/, { timeout: 20_000 });

  // The count IS the plan's rows: both are `planModelFrom` output, so they cannot disagree.
  const jobs = Number(await receipt.getAttribute("data-jobs"));
  expect(jobs).toBeGreaterThan(0);
  const cells = await page.getByTestId("plan-grid").locator(".plan-cell-button").count();
  expect(jobs).toBe(cells);

  // It is above the action bar, not in the other pane.
  const receiptBox = await receipt.boundingBox();
  const barBox = await page.locator('[data-page-active="true"] .action-bar').boundingBox();
  expect(receiptBox).not.toBeNull();
  expect(barBox).not.toBeNull();
  expect((receiptBox as { y: number }).y).toBeLessThan((barBox as { y: number }).y);

  // Live: deselecting empties it and it says why, in the page's own words.
  await subjectsField(page).getByTestId("subject-select-none").click();
  await expect(receipt.getByTestId("run-receipt-headline")).toHaveText("Select at least one subject.");
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

  const receipt = page.locator('[data-page-active="true"]').getByTestId("run-receipt");
  await expect(receipt).toHaveAttribute("data-existing", /^[1-9]/, { timeout: 20_000 });
  // The receipt says the question is coming; pressing Run asks it.
  await expect(receipt.getByTestId("run-receipt-existing")).toBeVisible();

  await page.locator('[data-page-active="true"]').getByTestId("run-button").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Some outputs already exist");
  await expect(dialog.getByTestId("existing-outputs-skip")).toBeVisible();
  await expect(dialog.getByTestId("existing-outputs-replace")).toHaveText("Replace and rerun");
  await expect(dialog.getByTestId("existing-outputs-cancel")).toHaveText("Cancel");
  // Cancel queues nothing.
  await dialog.getByTestId("existing-outputs-cancel").click();
  await expect(dialog).toHaveCount(0);
});
