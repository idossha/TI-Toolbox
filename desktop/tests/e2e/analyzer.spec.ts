import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, type PageMetrics } from "./_metrics";
import { analysisRows, setAnalysisCell } from "./_jobs";

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
  await expect(page.locator("table.analysis-jobs-table thead th")).toHaveText([
    "Subject",
    "Simulation",
    "Space",
    "Field",
    "",
  ]);
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

  // Spherical target: the fixture's Thalamus coordinates. The ROI stays global (2.5.0's shape).
  await page.getByLabel("Sphere 1 X").fill("-10");
  await page.getByLabel("Sphere 1 Y").fill("-18");
  await page.getByLabel("Sphere 1 Z").fill("9");
  await page.getByLabel("Sphere 1 radius").fill("10");

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|skip|overwrite|blocked|wait)$/);
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis");

  // §11: no bottom status bar — the plan digest is the action bar's, on the page.
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
});

/**
 * 2.5.0's **Quick Add** — "every subject that has run this simulation" in one press — and the
 * group switch that folds the same rows into one cohort job.
 */
test("Quick add fills the table, and the group switch folds the rows into one cohort job", async () => {
  await page.getByRole("button", { name: /^Quick add: every subject with "Thalamus"$/ }).click();
  // The mock's fixture: ernie and 101 have run Thalamus; MNI152 has not, so it is not added.
  await expect(analysisRows(page)).toHaveCount(2);
  await expect(analysisRows(page).nth(1)).toHaveAttribute("data-subject", "101");
  await expect(analysisRows(page).nth(1)).toHaveAttribute("data-simulation", "Thalamus");

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
  await page.getByRole("switch", { name: "Combine into one group analysis" }).click();
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis", { timeout: 15_000 });
  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);

  // A cohort runs ONE simulation: rows that disagree are refused outright, with the reason on the
  // button, rather than silently resolved to the first row's answer.
  // (`L_Insula` is ernie's alone in the fixture, which is exactly the disagreement.)
  await setAnalysisCell(page, analysisRows(page).first(), "simulation", "L_Insula");
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /A group analysis runs one simulation/);
  await setAnalysisCell(page, analysisRows(page).first(), "simulation", "Thalamus");
  await page.getByRole("switch", { name: "Combine into one group analysis" }).click();
  await expect(page.getByTestId("run-button")).toHaveText("Queue 2 jobs", { timeout: 15_000 });

  // Evidence (§8.1).
  await page.getByTestId("analysis-jobs-container").screenshot({ path: "tests/e2e/artifacts/jobs-table-analyzer.png" });

  // Leave one row for the acceptance measurement below.
  await analysisRows(page).nth(1).getByRole("button", { name: "Remove row 2" }).click();
  await expect(analysisRows(page)).toHaveCount(1);
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
    // run panel went to 45 vw: at 1440 the pane is 610 px of PLAN + TERMINAL, and before a run the
    // terminal is empty by definition — measured 0.6716 light and dark, 0.6154 at 1280.
    expect(row.deadSpaceRatio, `${row.theme} @${row.width}`).toBeLessThanOrEqual(0.7);
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
