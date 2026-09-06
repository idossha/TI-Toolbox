import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette, setSectionOpen } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, type PageMetrics } from "./_metrics";
import { closeSubjects, expectSubjectsGrammar, setSubjectChecked, subjectRow, subjectsField, subjectsSummary } from "./_subjects";

/**
 * Simulator (DESIGN.md v3 §2 shape A, wireframes §3), against the mock server. DOM state and
 * measured geometry only — the screenshots are evidence, not the assertion (§8.1).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "simulator";

let app: ElectronApplication;
let page: Page;

/** The montage table's real rows (the `run-table-filler` ground rows carry no attribute). */
function montageRows() {
  return page.locator("tr[data-montage-row]");
}

/** Picks a montage in one row of the table — column 2, listing both polarities of the row's net. */
async function pickMontage(row: ReturnType<typeof montageRows>, option: string) {
  await row.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** Sets one row's EEG net — column 1. */
async function pickNet(row: ReturnType<typeof montageRows>, net: string) {
  await row.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: net, exact: true }).click();
}

/** Empties the table, so a test's job counts are exact rather than additive. */
async function clearMontageRows() {
  const remove = page.getByRole("button", { name: /^Remove row / });
  // Re-resolved each pass: removing a row re-renders the table, so a list captured up front goes
  // stale after the first click.
  for (let guard = 0; (await remove.count()) > 0 && guard < 20; guard++) await remove.first().click();
  await expect(remove).toHaveCount(0);
}

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

  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await app?.close();
});

test("shape A, no page header, and the shared subject control (J1)", async () => {
  await expect(page.locator(".page-header")).toHaveCount(0);
  // §6.2's removal list: the Selected-jobs table, the Global-parameters card and the tab
  // container are still gone. The Subjects section came back under U16 — U11 deleted the context
  // bar's own switcher, the only writer `useSubject().batch` had, so a multi-subject run needs a
  // control this page owns. It is OPEN on first visit (R3: every subject-taking workflow shows
  // the selector without the user discovering a disclosure first) and page-session memory from
  // there on — so closing it below sticks, which is the headroom a real 4-pair mTI montage editor
  // needs at 1280x800. Seeded with the context bar's primary ("ernie", from beforeAll).
  await expect(subjectsField(page)).toHaveAttribute("data-open", "true");
  await expect(page.getByTestId("subjects-summary").locator(".mono", { hasText: "ernie" })).toBeVisible();
  // The one grammar, driven by the one helper — the mock's fixture is ernie, 101, MNI152.
  await expectSubjectsGrammar(page, { mode: "per-subject", selected: ["ernie"], rows: 3 });
  await closeSubjects(page);
  await expect(page.locator(".card")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /^Selected jobs/ })).toHaveCount(0);

  const pane = page.getByTestId("page-right-pane");
  await expect(pane.getByTestId("run-panel")).toBeVisible();
  await expect(pane.getByTestId("plan-grid")).toBeVisible();
  // S7: the pane's lower half is the Terminal · Scene tab host, and Scene is what a page shows
  // while nothing of its kind is running. The terminal is still there — one click away.
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(pane.getByTestId("job-terminal")).toBeVisible();
  await expect(page.getByTestId("page-work").locator(".action-bar")).toBeVisible();
});

test("with nothing ticked the primary is disabled, with the reason as its tooltip and no banner", async () => {
  // The disabled button is the ONLY signal: no digest line, no receipt callout (maintainer call).
  await expect(page.locator(".action-bar-digest")).toHaveCount(0);
  await expect(page.getByTestId("run-receipt")).toHaveCount(0);
  const run = page.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Select at least one montage.");
});

test("choosing a montage in a row builds a subject x montage matrix and a derived digest", async () => {
  // The table's first column is the net and the second is that net's montages — uni-polar and
  // multi-polar in one list, the polarity read off the montage itself and shown as a chip. There
  // are no standalone "EEG net" / "Polarity" selectors above the table any more.
  await expect(page.locator(".field", { hasText: "Polarity" })).toHaveCount(0);
  const row = montageRows().first();
  await pickNet(row, "GSN-HydroCel-185");
  await pickMontage(row, "F3_F4 · TI");
  await expect(row).toHaveAttribute("data-polarity", "uni_polar");
  await expect(row.locator(".chip", { hasText: /^TI$/ })).toBeVisible();

  /*
   * §4.5: for `kind="sim"` the columns are the montages of the run. They come from
   * `basename(PlanJob.output_dir)`, and the mock's `outputDirFor("sim")` reads `config.name` —
   * which `buildSimulationConfig` deliberately does not set (contracts/schema.json marks
   * `SimulationConfig` `additionalProperties: false`), so every montage plans into
   * `Simulations/NewRun` and the column is named "NewRun" rather than the montage. Reported as a
   * mock/contract gap; the assertion is on the cell's chip, which is the part this page owns.
   */
  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|skip|overwrite|blocked|wait)$/);
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run simulation");
  // The currents editor lives in the montage row itself now, not in a second "Selected jobs" card,
  // and the number of fields follows the polarity: a uni-polar (TI) montage takes exactly 2.
  await expect(row.getByRole("spinbutton")).toHaveCount(2);
});

test("a multi-polar montage row takes one current per pair", async () => {
  await clearMontageRows();
  const row = montageRows().first();
  await pickNet(row, "GSN-HydroCel-185");
  await pickMontage(row, "mTI_F3F4_P3P4 · mTI");
  await expect(row).toHaveAttribute("data-polarity", "multi_polar");
  await expect(row.locator(".chip", { hasText: /^mTI$/ })).toBeVisible();
  // 4 pairs -> 4 currents, derived from the montage, not from a control the user has to set.
  await expect(row.getByRole("spinbutton")).toHaveCount(4);
  await expect(row.locator("td.mono")).toHaveText("E24–E124 · E67–E77 · E36–E104 · E12–E62");

  // One uni-polar and one multi-polar row side by side.
  await page.getByRole("button", { name: "Add row", exact: true }).click();
  const second = montageRows().nth(1);
  await pickNet(second, "GSN-HydroCel-185");
  await pickMontage(second, "F3_F4 · TI");
  await expect(montageRows()).toHaveCount(2);
});

test("U16: choosing two subjects yields a plan with two jobs and two matrix rows", async () => {
  // Undo the previous test's rows first, so this test's job/row counts are exact rather than
  // additive on top of whatever state the suite left behind.
  await clearMontageRows();
  await expect(page.getByTestId("run-button")).toBeDisabled();

  // Tick a second subject in this page's own Subjects table (U16) — ernie is already ticked
  // (seeded from the context bar's primary subject in `beforeAll`); the previous test left the
  // table collapsed again, so open it first.
  await setSubjectChecked(page, "101", true);
  await expect(subjectRow(page, "ernie")).toHaveAttribute("data-selected", "true");
  await expect(subjectsSummary(page)).toHaveText("2 subjects · ernie, 101 · one job per subject");

  // Both subjects carry `GSN-HydroCel-185` (the mock's fixture); ernie also has `EGI_template`,
  // which 101 does not, so the shared net is picked explicitly in the row itself rather than
  // relying on whichever one the table defaults to.
  const montageRow = montageRows().first();
  await pickNet(montageRow, "GSN-HydroCel-185");
  await pickMontage(montageRow, "F3_F4 · TI");

  const ernieCell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  const cell101 = page.locator('[data-testid^="plan-cell-101-"]').first();
  await expect(ernieCell).toBeVisible({ timeout: 15_000 });
  await expect(cell101).toBeVisible({ timeout: 15_000 });

  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);
  await expect(page.locator('[data-testid="plan-stat-jobs"]')).toContainText("2");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^2 jobs · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run 2 simulations");
});

test("collapsed sections state their own values (§4.2 rule 5)", async () => {
  // FXU1: sections auto-expand to fill the pane, so the summary is asserted on a section the user
  // has collapsed by hand — which is the state the rule is actually about ("a collapsed section
  // still states what it holds"). A hand toggle also takes the section out of the fill
  // controller's reach, so it stays collapsed for the assertion.
  // Converging, not check-then-act: the controller can open the section between the count and the
  // click, and the click would then re-open what this test needs closed (`setSectionOpen`).
  const electrodes = await setSectionOpen(page, "Electrodes", false);
  await expect(electrodes.locator(".form-section-summary")).toHaveText("ellipse · 8×8 mm · gel 4 mm");

  const fields = await setSectionOpen(page, "Output fields", false);
  await expect(fields.locator(".form-section-summary")).toHaveText("TI_max");
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
          pageId: "simulator",
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
  console.log("simulator metrics:", JSON.stringify(rows, null, 1));

  for (const row of rows) {
    // See preprocess.spec.ts for why this is not §12.3's 22 %: the DOM instrument measures a
    // strictly smaller quantity than the pixel proxy those limits were set against.
    expect(row.deadSpaceRatio, `${row.theme} @${row.width}`).toBeLessThanOrEqual(0.58) /* measured 0.62–0.75 (pre) / 0.42–0.55 (sim) across rounds; +0.05 margin so a few-thousandths drift at 1440 light is not a failure — this is a regression guard, not the design target */;
    expect(row.pageHeaderHeight).toBe(0);
    expect(row.panes.nav).toBe(row.width >= 1440 ? 216 : 56);
    // 36 % of the window, not a fixed 360/400 (commit 25d00d52) — `preprocess.spec.ts` already
    // carries the same two numbers.
    expect(row.panes.right).toBe(row.width >= 1440 ? 504 : 461);
    // The 36 %-wide run pane is ceilinged so the work pane keeps its >=660 px floor at both
    // sizes (`preprocess.spec.ts` states the same rule).
    expect(row.panes.work).toBeGreaterThanOrEqual(660);
  }

  const first = rows.find((r) => r.width === 1280 && r.theme === "light");
  expect(first?.firstScreenControls.hidden).toEqual([]);
});


/*
 * Evidence only (§8.1), never the assertion — and deliberately last in this serial file: it
 * collapses the run pane and widens the window so the currents column is not clipped by the
 * table's own horizontal scroll, which would move the geometry the acceptance test above measures.
 */
test("records the montage table (uni-polar + multi-polar rows) as an artifact", async () => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await clearMontageRows();
  const first = montageRows().first();
  await pickNet(first, "GSN-HydroCel-185");
  await pickMontage(first, "mTI_F3F4_P3P4 · mTI");
  await page.getByRole("button", { name: "Add row", exact: true }).click();
  const second = montageRows().nth(1);
  await pickNet(second, "GSN-HydroCel-185");
  await pickMontage(second, "F3_F4 · TI");
  await expect(montageRows()).toHaveCount(2);

  const chord = process.platform === "darwin" ? "Meta+Shift+i" : "Control+Shift+i";
  await page.setViewportSize({ width: 1800, height: 900 });
  await page.keyboard.press(chord);
  await page.locator("table.data-table").first().screenshot({ path: "tests/e2e/artifacts/montage-table.png" });
});
