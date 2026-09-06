import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, type PageMetrics } from "./_metrics";
import { closeSubjects, expectSubjectsGrammar, setSubjectChecked, subjectsField, subjectsSummary } from "./_subjects";

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

function field(label: string) {
  return page.locator(".field", { hasText: label }).first();
}

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

test("shape A, no page header, no subject Select — the shared subject control instead (J1)", async () => {
  await expect(page.locator(".page-header")).toHaveCount(0);
  // Never a `<Select id="analyzer-subject">` dropdown — U6's actual claim, still true. U16 gave
  // the page its own multi-select Subjects *table* instead (below), which is a different control
  // shape entirely: U11 deleted the context bar's own switcher, the only writer
  // `useSubject().batch` had, so Group mode needs a control this page owns. It is OPEN on first
  // visit (R3) and page-session memory after that, so it can still be closed to give
  // `ResultsPanel` its room once a simulation is picked (see `AnalyzerPage.tsx`). Seeded with the
  // context bar's primary ("ernie", from beforeAll).
  await expect(page.locator("#analyzer-subject")).toHaveCount(0);
  await expect(page.locator(".card")).toHaveCount(0);
  await expect(subjectsField(page)).toHaveAttribute("data-open", "true");
  await expect(page.getByTestId("subjects-summary").locator(".mono", { hasText: "ernie" })).toBeVisible();
  // The one grammar, driven by the one helper. Subject scope is `single` — one job for one
  // subject (`AnalyzerConfig.subject_id`), which the summary line states outright (J4) and the
  // control enforces, rather than the page silently analysing the first of several ticked ids.
  await expectSubjectsGrammar(page, { mode: "single", selected: ["ernie"], rows: 3 });
  await closeSubjects(page);

  const pane = page.getByTestId("page-right-pane");
  await expect(pane.getByTestId("run-panel")).toBeVisible();
  await expect(pane.getByTestId("plan-grid")).toBeVisible();
  // S7: the pane's lower half is the Terminal · Scene tab host, and Scene is what a page shows
  // while nothing of its kind is running. The terminal is still there — one click away.
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(pane.getByTestId("job-terminal")).toBeVisible();
  await expect(page.getByTestId("page-work").locator(".action-bar")).toBeVisible();

  // The disabled primary is the only signal that the run cannot start; the reason is its tooltip.
  await expect(page.locator(".action-bar-digest")).toHaveCount(0);
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Pick a simulation to analyze.");
});

test("scope, space and target are segments, and the plan resolves once the target is complete", async () => {
  // Scope: Subject / Group as a segmented control, not a radio pair.
  await expect(field("Scope").getByRole("radiogroup")).toBeVisible();

  await page.locator("#analyzer-simulation").click();
  await page.getByRole("option", { name: "Thalamus" }).first().click();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Complete the target before running.");

  // Spherical target: the fixture's Thalamus coordinates.
  await page.getByLabel("Sphere 1 X").fill("-10");
  await page.getByLabel("Sphere 1 Y").fill("-18");
  await page.getByLabel("Sphere 1 Z").fill("9");
  await page.getByLabel("Sphere 1 radius").fill("10");

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|skip|overwrite|blocked|wait)$/);
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis");

  // §11.1: the page registers `planCost`; the viewer's cells are nowhere near this bar.
  await expect(page.locator('[data-status-cell="planCost"]')).toBeVisible();
  await expect(page.locator('[data-status-cell="ras"]')).toHaveCount(0);
});

test("J4: the scope decides the grammar — Group ticks two subjects, Subject narrows back to one", async () => {
  // Subject scope is single-select, so the second subject is reachable only in Group scope —
  // which is the truth about what this page submits, and the reason the mode is stated in the
  // summary line rather than left for a user to infer from a plan row count.
  await field("Scope").getByRole("radio", { name: "Group" }).click();
  await setSubjectChecked(page, "101", true);
  await expect(subjectsSummary(page)).toHaveText("2 subjects · ernie, 101 · one job over all subjects");
  await closeSubjects(page);

  const ernieCell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  const cell101 = page.locator('[data-testid^="plan-cell-101-"]').first();
  await expect(ernieCell).toBeVisible({ timeout: 15_000 });
  await expect(cell101).toBeVisible({ timeout: 15_000 });

  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);
  await expect(page.locator('[data-testid="plan-stat-jobs"]')).toContainText("2");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^2 jobs · \d+ CPU · \d+ GB/);
  // The run button's own label counts *configs* (one per sphere row — `AnalyzerPage.tsx`'s
  // `runLabel`), not subjects: Group mode submits one job carrying both subject ids
  // (`run_group_analysis over subject_ids`, the page's own comment), which is exactly what
  // "the submitted payload carries all ids" means here — the two-*job* count above is the Plan
  // preview's, not the submission's.
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis");

  // Back to Subject scope: the control narrows the set to one, visibly, instead of the payload
  // builder dropping the rest on the way to the wire.
  await field("Scope").getByRole("radio", { name: "Subject" }).click();
  await expect(subjectsSummary(page)).toHaveText("ernie · one job");
  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(1);
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
