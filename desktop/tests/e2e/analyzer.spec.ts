import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, type PageMetrics } from "./_metrics";
import {
  analysisLine1,
  analysisLine2,
  analysisRows,
  analysisTargetText,
  closeAnalysisTarget,
  openAnalysisTarget,
  setAnalysisCell,
  setAnalysisSphere,
  setAnalysisSubject,
  setAnalysisTissue,
} from "./_jobs";

/**
 * Analyzer (DESIGN.md v3 §2 shape A, wireframes §5), against the mock server. Configures a
 * spherical analysis for ernie/Thalamus, checks the plan grid and the action bar, and measures.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "analyzer";

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

  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
});

test.afterAll(async () => {
  await app?.close();
});


test("shape A, no page header, and one Jobs table instead of a global subject set", async () => {
  await expect(page.locator(".page-header")).toHaveCount(0);
  /*
   * 2026-09-06 rework (maintainer): "we need a list of jobs in a table that allows users
   * flexibility in what they input to the job". The page-level Subjects table, the Scope segment
   * and the single Simulation combobox are gone — a ROW is a (subject, simulation, space, field)
   * job, which is 2.5.0's Subject × Simulation pair table with the two per-job choices folded in.
   */
  await expect(page.locator("#analyzer-subject")).toHaveCount(0);
  await expect(page.locator("#analyzer-simulation")).toHaveCount(0);
  await expect(page.getByTestId("subjects-field")).toHaveCount(0);
  await expect(page.locator(".card")).toHaveCount(0);
  await expect(page.getByTestId("analysis-jobs-table")).toBeVisible();
  // Line 1's four columns; "Target" is a caption on line 2, not a column (maintainer, 2026-09-06).
  await expect(page.locator("table.analysis-jobs-table thead th")).toHaveText([
    "Subject",
    "Simulation",
    "Space",
    "Field",
    "",
  ]);
  /*
   * 2026-09-06, maintainer's second pass: the page-level TARGET section ("Region:
   * Cortical/Subcortical/Spherical", the atlas, the region list) and the OUTPUT section
   * ("Analyses of this simulation…") are both gone. The target is a cell of the row; Results owns
   * a simulation's existing analyses.
   */
  const sectionTitles = page.getByTestId("page-work").locator("[data-fill-section] .form-section-title");
  // The global "Space options · Tissue" section is gone too (maintainer, 2026-09-06): tissue is
  // voxel-only in `tit/analyzer/config.py` and the runner forces GM in mesh, so it is a property of
  // the ROW's space and is a cell on line 1.
  await expect(sectionTitles).toHaveText(["Jobs"]);
  await expect(page.locator("#analyzer-tissue")).toHaveCount(0);
  await expect(page.getByTestId("analyses-table")).toHaveCount(0);
  await expect(page.locator('[data-page-active="true"]').locator(".roi-picker")).toHaveCount(0);
  // Every row states its own target, and says so when it has none.
  await expect(analysisTargetText(analysisRows(page).first())).toHaveText("Choose a target…");
  await expect(analysisRows(page).first().locator(".analysis-target-caption")).toHaveText("Target");
  // Seeded with one row on the context bar's primary subject ("ernie", from beforeAll).
  await expect(analysisRows(page)).toHaveCount(1);
  await expect(analysisRows(page).first()).toHaveAttribute("data-subject", "ernie");

  const pane = page.getByTestId("page-right-pane");
  await expect(pane.getByTestId("run-panel")).toBeVisible();
  await expect(pane.getByTestId("plan-grid")).toBeVisible();
  // S7: the pane's lower half is the Terminal · Scene tab host, and Scene is what a page shows
  // while nothing of its kind is running. The terminal is still there — one click away.
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(pane.getByTestId("job-terminal")).toBeVisible();
  await expect(page.getByTestId("page-work").locator(".action-bar")).toBeVisible();

  // The disabled primary is the only signal that the run cannot start; the reason is its tooltip,
  // and it names what is actually missing — the row's simulation.
  await expect(page.locator(".action-bar-digest")).toHaveCount(0);
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Add a row with a subject and a simulation.");
});

test("a row names its own simulation, space and field, and the plan resolves once the target is complete", async () => {
  const row = analysisRows(page).first();
  await setAnalysisCell(page, row, "simulation", "Thalamus");
  await expect(row).toHaveAttribute("data-runnable", "true");
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Complete the target before running.");

  // Space and Field are the row's, not the page's — a second row can measure a different field of
  // a different simulation, which is what the maintainer's "flexibility in what they input to the
  // job" asks for.
  await expect(row.locator('td[data-cell="space"]')).toContainText("Mesh");
  await setAnalysisCell(page, row, "field", "TI_max");

  // The target is the ROW's: its cell opens the shared picker scoped to this row, and the cell
  // then states the target in words.
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Complete the target before running.");
  await setAnalysisSphere(page, row, { x: -10, y: -18, z: 9, radius: 10 });
  await expect(analysisTargetText(row)).toHaveText("Sphere -10,-18,9 r10 mm · Subject");

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|skip|overwrite|blocked|wait)$/);
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis");

  // §11: no bottom status bar — the plan digest is the action bar's, on the page.
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
});

/**
 * A second row, and the group switch that folds the same rows into one cohort job. The switch
 * lives on the table's footer line, right of `+ Add row` (maintainer, 2026-09-06); 2.5.0's
 * "Quick Add" button was removed in the same pass.
 */
test("a second row plans a second job, and the group switch folds the rows into one cohort job", async () => {
  await expect(page.getByRole("button", { name: /Quick add/ })).toHaveCount(0);

  // §4.7: `+ Add row` and the Combine switch share ONE footer line, the switch right-aligned.
  const footer = page.getByTestId("analysis-jobs-footer");
  const addRow = footer.getByRole("button", { name: "Add row", exact: true });
  const combine = page.getByRole("switch", { name: "Combine into one group analysis" });
  const addBox = await addRow.boundingBox();
  const combineBox = await combine.boundingBox();
  expect(addBox).not.toBeNull();
  expect(combineBox).not.toBeNull();
  // Same row: their vertical centres agree to within a couple of pixels.
  expect(Math.abs(addBox!.y + addBox!.height / 2 - (combineBox!.y + combineBox!.height / 2))).toBeLessThan(4);
  // Right-aligned: the switch sits in the right half of the footer, well past the add button.
  const footerBox = (await footer.boundingBox())!;
  expect(combineBox!.x).toBeGreaterThan(addBox!.x + addBox!.width);
  expect(combineBox!.x).toBeGreaterThan(footerBox.x + footerBox.width / 2);
  // No separate "Combine" field label above it.
  await expect(page.getByTestId("analysis-combine-row").locator(".field-label")).toHaveCount(0);

  await addRow.click();
  await expect(analysisRows(page)).toHaveCount(2);
  const second = analysisRows(page).nth(1);
  await setAnalysisSubject(page, second, "101");
  await setAnalysisCell(page, second, "simulation", "Thalamus");
  await expect(second).toHaveAttribute("data-simulation", "Thalamus");

  const ernieCell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  const cell101 = page.locator('[data-testid^="plan-cell-101-"]').first();
  await expect(ernieCell).toBeVisible({ timeout: 15_000 });
  await expect(cell101).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);
  // Two rows, two single-subject jobs — the plan and the button agree.
  await expect(page.locator('[data-testid="plan-stat-jobs"]')).toContainText("2");
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs");

  // The switch: ONE job over both subjects (`run_group_analysis` over `subject_ids`), which is why
  // the button's label drops back to one.
  await combine.click();
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis", { timeout: 15_000 });
  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);

  // A cohort runs ONE simulation: rows that disagree are refused outright, with the reason on the
  // button, rather than silently resolved to the first row's answer.
  // (`L_Insula` is ernie's alone in the fixture, which is exactly the disagreement.)
  await setAnalysisCell(page, analysisRows(page).first(), "simulation", "L_Insula");
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /A group analysis runs one simulation/);
  await setAnalysisCell(page, analysisRows(page).first(), "simulation", "Thalamus");
  await combine.click();
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs", { timeout: 15_000 });

  // Evidence (§8.1).
  await page.getByTestId("analysis-jobs-table-container").screenshot({ path: "tests/e2e/artifacts/jobs-table-analyzer.png" });

  // Leave one row for the acceptance measurement below.
  await analysisRows(page).nth(1).getByRole("button", { name: "Remove row 2" }).click();
  await expect(analysisRows(page)).toHaveCount(1);
});

/**
 * The maintainer's second jobs pass: *"The TARGET section must become per-job — we can modify our
 * analysis input per job."* Two rows, two different targets, one Run.
 */
test("each row owns its target, the pane follows the active row, and a target change moves nothing", async () => {
  test.setTimeout(120_000);
  const first = analysisRows(page).first();
  await expect(first).toHaveCount(1);
  await setAnalysisCell(page, first, "simulation", "Thalamus");
  await setAnalysisSphere(page, first, { x: -10, y: -18, z: 9, radius: 10 });

  await page.getByTestId("analysis-jobs-footer").getByRole("button", { name: "Add row", exact: true }).click();
  await expect(analysisRows(page)).toHaveCount(2);
  const second = analysisRows(page).nth(1);
  await setAnalysisCell(page, second, "simulation", "Thalamus");

  // Fixed column widths: the geometry of row 1 is recorded BEFORE row 2's target grows from
  // "Choose a target…" to a cortical union, and must be identical after.
  const before = await first.boundingBox();
  const beforeCell = await first.locator('td[data-cell="target"]').boundingBox();

  // Row 2 gets a cortical target — a different KIND of target from row 1's sphere, which is the
  // thing the page could not express at all while TARGET was global.
  const dialog = await openAnalysisTarget(page, second);
  await dialog.getByRole("radio", { name: "Cortical", exact: true }).click();
  await dialog.locator(".field", { hasText: "Atlas" }).first().locator(".combobox-trigger").click();
  await page.getByRole("option", { name: /DK40/i }).first().click();
  await dialog.locator(".field", { hasText: "Region(s)" }).first().getByRole("combobox").click();
  await page.locator('[role="option"][data-option-value="lh:1"]').click();
  await page.getByTestId("roi-region-done").click();
  // The picker's "Combine regions into one ROI" — the row's own, not a page-level toggle.
  await expect(dialog.getByRole("checkbox", { name: "Combine regions into one ROI" })).toBeVisible();
  await closeAnalysisTarget(page);

  await expect(analysisTargetText(second)).toHaveText("Cortical · DK40 · lh.bankssts");
  // The full text is the line's `title` too, so a target long enough to clamp is still readable.
  await expect(second.locator('td[data-cell="target"]').getByRole("button")).toHaveAttribute(
    "title",
    "Cortical · DK40 · lh.bankssts",
  );
  // Row 1 did not move, and neither did its Target cell.
  const after = await first.boundingBox();
  const afterCell = await first.locator('td[data-cell="target"]').boundingBox();
  expect(after).toEqual(before);
  expect(afterCell).toEqual(beforeCell);
  // Row 1's own target is untouched — the targets are per row, not shared.
  await expect(analysisTargetText(first)).toHaveText("Sphere -10,-18,9 r10 mm · Subject");

  // The active row is the one the 3-D pane draws (the Simulator's idiom): clicking a row
  // highlights it, and the cortical row is the one whose atlas the pane picks up.
  await second.locator('td[data-cell="target"]').getByRole("button").click();
  await closeAnalysisTarget(page);
  await expect(second).toHaveAttribute("data-active", "true");
  await expect(first).not.toHaveAttribute("data-active", "true");

  // Two rows, two different targets, two jobs.
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs", { timeout: 15_000 });

  // Evidence (§8.1).
  await page.getByTestId("analysis-jobs-table-container").screenshot({
    path: "tests/e2e/artifacts/analyzer-jobs-target.png",
  });
  await page.getByTestId("analysis-jobs-table-container").screenshot({
    path: "tests/e2e/artifacts/analyzer-jobs-v2.png",
  });

  await second.getByRole("button", { name: "Remove row 2" }).click();
  await expect(analysisRows(page)).toHaveCount(1);
});

/**
 * The geometry the maintainer asked for after seeing the first pass: *"the job table should use
 * thicker entries so there's place for everything, and the pop-ups should be better organised."*
 * Measured at 1280, where the cramping was ("Choose a sim…", "M…", a truncated atlas name).
 */
test("adding a row does not open the target dialog, and neither does clicking one", async () => {
  // Coordinator, 2026-09-06: the same rule as the Optimizer's table. A single click on a row only
  // moves the active-row focus (the wash and the 3-D pane follow it); the dialog is opened
  // deliberately — the Target line, the Edit pencil, a double-click, or Enter.
  const first = analysisRows(page).first();
  await page.getByTestId("analysis-jobs-footer").getByRole("button", { name: "Add row", exact: true }).click();
  await expect(analysisRows(page)).toHaveCount(2);
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);
  const second = analysisRows(page).nth(1);
  await expect(second).toHaveAttribute("data-active", "true");

  // A single click moves focus back, and opens nothing.
  await first.locator('td[data-cell="space"]').click({ position: { x: 2, y: 2 } });
  await expect(first).toHaveAttribute("data-active", "true");
  await expect(second).not.toHaveAttribute("data-active", "true");
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);

  // Line 2 is inert except for the target TEXT: 40px right of where the sentence ends is still
  // line 2, and clicking there focuses the row and opens nothing (coordinator, 2026-09-06 — the
  // full-width button made every empty pixel of the line an edit gesture).
  await second.locator('td[data-cell="space"]').click({ position: { x: 2, y: 2 } });
  await expect(second).toHaveAttribute("data-active", "true");
  const text = analysisTargetText(first);
  const textBox = (await text.boundingBox())!;
  const line2 = (await analysisLine2(first).boundingBox())!;
  // The click point has to still be inside the row, which is what makes this a real test of the
  // button's width rather than of the table's.
  const rightOfText = textBox.x + textBox.width + 40;
  expect(rightOfText, "40px right of the text is still on line 2").toBeLessThan(line2.x + line2.width);
  await page.mouse.click(rightOfText, line2.y + line2.height / 2);
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);
  await expect(first).toHaveAttribute("data-active", "true");
  // …and the caption is not the button either.
  await first.locator(".analysis-target-caption").click();
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);
  // Clicking the text itself DOES open it.
  await text.click();
  await expect(page.getByTestId("analysis-target-editor")).toBeVisible();
  await closeAnalysisTarget(page);

  // The three deliberate ways in.
  await first.getByRole("button", { name: "Job settings 1" }).click();
  await expect(page.getByTestId("analysis-target-editor")).toBeVisible();
  await closeAnalysisTarget(page);
  await openAnalysisTarget(page, first);
  await closeAnalysisTarget(page);
  await first.locator('td[data-cell="space"]').dblclick({ position: { x: 2, y: 2 } });
  await expect(page.getByTestId("analysis-target-editor")).toBeVisible();
  await closeAnalysisTarget(page);

  // Keyboard: the arrows move the active row, Enter opens its target.
  await first.locator("tr.analysis-job-line1").focus();
  await page.keyboard.press("ArrowDown");
  await expect(second).toHaveAttribute("data-active", "true");
  await page.keyboard.press("ArrowUp");
  await expect(first).toHaveAttribute("data-active", "true");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("analysis-target-editor")).toHaveAttribute("data-row", await first.getAttribute("data-analysis-row") as string);
  await closeAnalysisTarget(page);

  await second.getByRole("button", { name: "Remove row 2" }).click();
  await expect(analysisRows(page)).toHaveCount(1);
});

test("a job entry is two lines ~56-64px tall, and every cell prints its full value", async () => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  const row = analysisRows(page).first();
  await setAnalysisCell(page, row, "simulation", "Thalamus");
  await setAnalysisSphere(page, row, { x: -10, y: -18, z: 9, radius: 10 });

  const entry = (await row.boundingBox())!;
  const line1 = (await analysisLine1(row).boundingBox())!;
  const line2 = (await analysisLine2(row).boundingBox())!;
  console.log(`JOBS-GEOM entry=${entry.height} line1=${line1.height} line2=${line2.height}`);
  // A thicker two-line entry, not two rows that happen to be adjacent: line 2 starts where line 1
  // ends, and the whole entry is the ~56-64px block the maintainer asked for.
  // The maintainer's band: ~56-64px for the whole entry. Line 2 carries a control (the row's
  // tissue) as well as the target sentence, so its select is the small 24px height.
  expect(entry.height).toBeGreaterThanOrEqual(56);
  expect(entry.height).toBeLessThanOrEqual(64);
  expect(Math.abs(line2.y - (line1.y + line1.height))).toBeLessThan(2);
  // Line 2 spans the whole table — it is the target's own line, not a column.
  const table = (await page.getByTestId("analysis-jobs-table").boundingBox())!;
  expect(Math.abs(line2.width - table.width)).toBeLessThan(2);

  // The widths that fix the cramping: Space prints "Voxel" whole, Field prints a whole field name,
  // and Simulation takes what is left.
  const cellBox = async (name: string) => (await row.locator(`td[data-cell="${name}"]`).boundingBox())!;
  const [subject, simulation, space, field] = await Promise.all([
    cellBox("subject"),
    cellBox("simulation"),
    cellBox("space"),
    cellBox("field"),
  ]);
  console.log(
    `JOBS-COLS subject=${subject.width} simulation=${simulation.width} space=${space.width} field=${field.width}`,
  );
  expect(space.width).toBeGreaterThanOrEqual(96);
  expect(field.width).toBeGreaterThanOrEqual(100);
  expect(simulation.width).toBeGreaterThan(field.width);
  // Nothing is clipped: each control fits inside its own cell.
  for (const [name, box] of [["space", space], ["field", field], ["simulation", simulation]] as const) {
    const control = (await row.locator(`td[data-cell="${name}"] [role="combobox"]`).boundingBox())!;
    expect(control.width, name).toBeLessThanOrEqual(box.width + 1);
  }
  await expect(row.locator('td[data-cell="space"]')).toHaveText("Mesh");
  // Printed whole, not ellipsised: the defect was a Space cell reading "M…". Every cell's own text
  // node fits the box it is drawn in.
  for (const name of ["subject", "simulation", "space", "field"] as const) {
    const clipped = await row
      .locator(`td[data-cell="${name}"] [role="combobox"] span`)
      .first()
      .evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(clipped, `${name} is ellipsised`).toBeLessThanOrEqual(1);
  }

  // The row's explicit way into its settings is the shared `Job settings N` control — same icon,
  // same position and name as the Simulator's and the Optimizer's (a pencil here was a third word
  // for one idea).
  await expect(row.getByRole("button", { name: "Job settings 1" })).toBeVisible();
  await expect(row.getByRole("button", { name: /^Edit row/ })).toHaveCount(0);

  // No horizontal scroll, and switching Space moves nothing.
  const container = page.getByTestId("analysis-jobs-table-container");
  const before = await row.boundingBox();
  await setAnalysisCell(page, row, "space", "Voxel");
  await expect(row.locator('td[data-cell="space"]')).toHaveText("Voxel");
  expect(await row.boundingBox()).toEqual(before);
  expect(
    await container.evaluate((el) => el.scrollWidth - el.clientWidth),
    "the jobs table scrolls sideways",
  ).toBeLessThanOrEqual(1);
  await setAnalysisCell(page, row, "space", "Mesh");
});

/**
 * Tissue is the row's, and only means anything in voxel space (`tit/analyzer/config.py`:
 * "voxel space only"; `analyzer.py` overwrites it with GM in mesh). Maintainer, 2026-09-06: the
 * global "Space options" section that held it is gone.
 */
test("tissue is a job setting, read-only in mesh, and a cohort needs the rows to agree", async () => {
  test.setTimeout(120_000);
  const row = analysisRows(page).first();
  // Tissue is a SETTING, so it is in the row's Job settings dialog under "Space options" — off
  // the row itself (maintainer, 2026-09-06). Mesh: read-only GM, with the reason stated.
  await expect(row.locator('td[data-cell="space"]')).toHaveText("Mesh");
  await expect(row.locator('[data-cell-part="tissue"]')).toHaveCount(0);
  let dialog = await openAnalysisTarget(page, row);
  let spaceOptions = dialog.getByTestId("analysis-space-options");
  await expect(spaceOptions.locator("h4")).toHaveText("Space options");
  await expect(spaceOptions.getByRole("combobox")).toHaveText("Gray matter (GM)");
  await expect(spaceOptions.getByRole("combobox")).toBeDisabled();
  await expect(spaceOptions).toContainText("tissue applies to voxel space");
  await closeAnalysisTarget(page);

  await setAnalysisCell(page, row, "space", "Voxel");
  dialog = await openAnalysisTarget(page, row);
  spaceOptions = dialog.getByTestId("analysis-space-options");
  await expect(spaceOptions.getByRole("combobox")).toBeEnabled();
  await closeAnalysisTarget(page);
  await setAnalysisTissue(page, row, "GM + WM (both)");
  // Line 2 names it only because it is no longer the default GM.
  await expect(analysisTargetText(row)).toContainText("· GM+WM");
  // Voxel is also why TI_normal cannot be measured, and the option now says so where it is read.
  await row.locator('td[data-cell="field"]').getByRole("combobox").click();
  await expect(page.getByRole("option", { name: "TI_normal (mesh only)" })).toBeDisabled();
  await page.keyboard.press("Escape");

  // A second voxel row on another tissue: two jobs apart, refused as a cohort.
  await page.getByTestId("analysis-jobs-footer").getByRole("button", { name: "Add row", exact: true }).click();
  const second = analysisRows(page).nth(1);
  await setAnalysisSubject(page, second, "101");
  await setAnalysisCell(page, second, "simulation", "Thalamus");
  await setAnalysisTissue(page, second, "White matter (WM)");
  await expect(analysisTargetText(second)).toContainText("· tissue WM");
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs", { timeout: 15_000 });

  const combine = page.getByRole("switch", { name: "Combine into one group analysis" });
  await combine.click();
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /A group analysis measures one tissue/);
  await setAnalysisTissue(page, second, "GM + WM (both)");
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis", { timeout: 15_000 });

  await combine.click();
  await second.getByRole("button", { name: "Remove row 2" }).click();
  await expect(analysisRows(page)).toHaveCount(1);
  await setAnalysisCell(page, row, "space", "Mesh");
});

/**
 * The dialog's organisation — one structure whatever the mode, at a fixed 560px.
 */
test("the job settings dialog is one 560px structure in every mode", async () => {
  test.setTimeout(120_000);
  const row = analysisRows(page).first();
  const dialog = await openAnalysisTarget(page, row);
  const box = (await dialog.boundingBox())!;
  console.log(`TARGET-DIALOG width=${box.width}`);
  expect(box.width).toBe(560);

  // Title + subtitle name the job this target belongs to.
  await expect(dialog.getByText("Job settings", { exact: true })).toBeVisible();
  await expect(dialog.locator(".dialog-description")).toHaveText("ernie · Thalamus");
  // The mode control is full-width across the top.
  const modes = dialog.locator(".roi-picker > .segmented").first();
  const modesBox = (await modes.boundingBox())!;
  expect(modesBox.width).toBeGreaterThan(box.width - 60);
  expect(modesBox.y).toBeLessThan((await dialog.locator(".field").first().boundingBox())!.y);

  // Spherical: Space and "Open T1 in viewer" share one row, left and right.
  await modes.getByRole("radio", { name: "Spherical", exact: true }).click();
  const spaceRow = (await dialog.locator(".field", { hasText: "Space" }).first().boundingBox())!;
  const viewer = (await dialog.getByRole("button", { name: /Open T1 in viewer/ }).boundingBox())!;
  expect(Math.abs(spaceRow.y + spaceRow.height / 2 - (viewer.y + viewer.height / 2))).toBeLessThan(6);
  expect(viewer.x).toBeGreaterThan(spaceRow.x + spaceRow.width / 2);
  // "Add sphere" is a small left-aligned button under the table, not a centred block.
  const add = (await dialog.getByRole("button", { name: "Add sphere", exact: true }).boundingBox())!;
  const sphereTable = (await dialog.locator("table").first().boundingBox())!;
  expect(add.y).toBeGreaterThan(sphereTable.y + sphereTable.height - 2);
  expect(Math.abs(add.x - sphereTable.x)).toBeLessThan(8);
  expect(add.width).toBeLessThan(140);
  // The explanatory paragraph is gone from the dialog — the row's target line states the sphere
  // count instead. (Hidden by this page's own stylesheet: the sentence belongs to the shared
  // picker, which other pages still show it on.)
  await expect(dialog.getByText(/Each row is a sphere/)).not.toBeVisible();
  // "Volumetric" is one line with its tissue select beside it, not a three-line label.
  const volumetric = dialog.getByRole("checkbox", { name: /Volumetric/ });
  const volumetricRow = (await volumetric.locator("xpath=ancestor::label[1]").boundingBox())!;
  expect(volumetricRow.height).toBeLessThanOrEqual(28);
  await page.screenshot({ path: "tests/e2e/artifacts/analyzer-target-spherical.png" });

  // Cortical: Atlas and Region(s) are label-left rows, and the combine checkbox is ONE line with
  // its (i) beside it — not a checkbox plus a paragraph.
  await modes.getByRole("radio", { name: "Cortical", exact: true }).click();
  const atlas = (await dialog.locator(".field", { hasText: "Atlas" }).first().boundingBox())!;
  const regions = (await dialog.locator(".field", { hasText: "Region(s)" }).first().boundingBox())!;
  expect(regions.y).toBeGreaterThan(atlas.y);
  expect(Math.abs(regions.x - atlas.x)).toBeLessThan(2);
  const combine = page.getByTestId("analysis-target-combine");
  const combineBox = (await combine.boundingBox())!;
  expect(combineBox.height).toBeLessThanOrEqual(32);
  await expect(combine.getByRole("button", { name: "Help" })).toBeVisible();
  await expect(combine.locator("p")).toHaveCount(0);
  await page.screenshot({ path: "tests/e2e/artifacts/analyzer-target-cortical.png" });

  // Footer: Cancel then Done, right-aligned — and Cancel really restores the target.
  const footer = dialog.locator(".dialog-footer");
  await expect(footer.getByRole("button")).toHaveText(["Cancel", "Done"]);
  const cancel = (await page.getByTestId("analysis-target-cancel").boundingBox())!;
  expect(cancel.x).toBeGreaterThan(box.x + box.width / 2);
  await page.getByTestId("analysis-target-cancel").click();
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);
  await expect(analysisTargetText(row)).toHaveText("Sphere -10,-18,9 r10 mm · Subject");
});

test("hits its acceptance numbers at both sizes, in both themes (DESIGN.md §12.3)", async () => {
  test.setTimeout(180_000);
  const rows: PageMetrics[] = [];
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    for (const theme of ["light", "dark"] as const) {
      rows.push(
        await captureScreen(page, {
          runId: RUN_ID,
          pageId: "analyzer",
          theme,
          width: size.width,
          height: size.height,
          waitFor: async () => {
            await expect(page.getByTestId("plan-grid")).toBeVisible();
          },
        }),
      );
    }
  }
  console.log("analyzer metrics:", JSON.stringify(rows, null, 1));

  for (const row of rows) {
    // See preprocess.spec.ts for why this is not §12.3's 25 %. Raised from 0.65 to 0.70 when the
    // run panel went to 45 vw: at 1440 the pane is 610 px of PLAN + TERMINAL. Raised again to 0.78
    // by FXU2, which retired the terminal's "What will run" step list: an idle page's terminal is
    // now literally an empty console with one line, so the pane really is that much ground —
    // measured 0.7553 at 1280 and 0.7427 at 1440, both themes. The number is honest about the
    // state, and the state is the one the maintainer asked for (a tab you open ran nothing).
    // Raised again to 0.80 by the 2026-09-06 target-per-job pass, and for the same kind of reason:
    // the page lost two whole sections — OUTPUT (Results owns a simulation's analyses) and TARGET
    // (a cell of the row now) — so the work pane genuinely holds less. Raised again to 0.86 when
    // SPACE OPTIONS went the same way (tissue is a cell of the row): the work column is now the
    // Jobs table and nothing else, so every row a user adds takes the number back down.
    // `layout.spec.ts` carries the same allowance for the same reason.
    expect(row.deadSpaceRatio, `${row.theme} @${row.width}`).toBeLessThanOrEqual(0.86);
    expect(row.pageHeaderHeight).toBe(0);
    expect(row.panes.nav).toBe(row.width >= 1440 ? 216 : 56);
    // DESIGN.md §2.1: the run panel is `clamp(320px, 45vw, calc(100% - 566px))` — 45 % of the
    // window, ceilinged so the work pane keeps its >=560 px floor. 576 at 1280; at 1440 the
    // ceiling binds, not the 45 %, so 610.
    expect(row.panes.right).toBe(row.width >= 1440 ? 610 : 576);
    expect(row.panes.work).toBeGreaterThanOrEqual(560);
  }

  const first = rows.find((r) => r.width === 1280 && r.theme === "light");
  expect(first?.firstScreenControls.hidden).toEqual([]);
});

test("NIfTI masks import with explicit Subject and MNI space in the analysis config", async () => {
  const row = analysisRows(page).first();
  if ((await row.getAttribute("data-subject")) !== "ernie") await setAnalysisSubject(page, row, "ernie");
  await setAnalysisCell(page, row, "simulation", "Thalamus");
  const uploads: URL[] = [];
  const configs: Record<string, unknown>[] = [];
  await page.route("**/api/files/mask?**", async (route) => {
    const url = new URL(route.request().url());
    uploads.push(url);
    await route.fulfill({ json: { path: `/mnt/project/m2m_ernie/masks/${url.searchParams.get("name")}` } });
  });
  await page.route("**/api/plan/analyzer", async (route) => {
    const body = route.request().postDataJSON() as { config: Record<string, unknown> };
    configs.push(body.config);
    await route.continue();
  });
  try {
    for (const [name, space] of [["analyzer-subject.nii", "Subject"], ["analyzer-mni.nii.gz", "MNI"]] as const) {
      const dialog = await openAnalysisTarget(page, row);
      await dialog.getByRole("radio", { name: "NIfTI mask", exact: true }).click();
      const picker = dialog.getByLabel("Import NIfTI mask");
      await expect(picker).toHaveAttribute("accept", ".nii,.gz,application/gzip,application/x-gzip");
      await picker.setInputFiles({ name, mimeType: "application/octet-stream", buffer: Buffer.from("mock NIfTI payload") });
      const path = `/mnt/project/m2m_ernie/masks/${name}`;
      await expect(dialog.getByRole("textbox", { name: "Imported mask" })).toHaveValue(path);
      await expect(dialog.getByRole("textbox", { name: "Imported mask" })).toBeEditable();
      await dialog.getByRole("radiogroup", { name: "Mask space" }).getByRole("radio", { name: space, exact: true }).click();
      await closeAnalysisTarget(page);
      await expect(analysisTargetText(row)).toHaveText(`NIfTI mask · ${name} · ${space}`);
      await expect.poll(() => configs.some((config) =>
        config.analysis_type === "mask" && config.mask_path === path && config.coordinate_space === space.toLowerCase(),
      )).toBe(true);
      const reopened = await openAnalysisTarget(page, row);
      await expect(reopened.getByRole("radiogroup", { name: "Mask space" }).getByRole("radio", { name: space, exact: true })).toHaveAttribute("aria-checked", "true");
      await expect(reopened.getByRole("textbox", { name: "Imported mask" })).toHaveValue(path);
      await closeAnalysisTarget(page);
    }
    expect(uploads.map((url) => url.searchParams.get("name"))).toEqual(["analyzer-subject.nii", "analyzer-mni.nii.gz"]);
    expect(uploads.every((url) => url.searchParams.get("subject") === "ernie")).toBe(true);
  } finally {
    await page.unroute("**/api/files/mask?**");
    await page.unroute("**/api/plan/analyzer");
  }
});
