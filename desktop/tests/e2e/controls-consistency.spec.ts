import { writeFileSync } from "node:fs";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette, setTheme } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;
/**
 * Pages whose first control is a page-level subject selector. Since the 2026-09-06 jobs rework
 * that is Pre-processing alone among the run pages (and the optional Source panel elsewhere): the
 * Simulator, the Analyzer and — from the same day's Optimizer pass — the Optimizer have none,
 * because the subject is a cell of a job row. Their "first control" clause is asserted on the Jobs
 * table instead (below).
 */
const SUBJECT_FIELD_PAGES = new Set<string>(["preprocess"]);
const JOBS_CONTAINER =
  '[data-testid="sim-jobs-table-container"], [data-testid="analysis-jobs-table-container"], [data-testid="opt-jobs-table-container"]';
const FIRST_CONTROL = `.subjects-field, ${JOBS_CONTAINER}`;

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp();
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible();
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
});

test.afterEach(async () => {
  const errors = page ? await page.pageErrors() : [];
  await app?.close();
  expect(errors.map((error) => error.message)).toEqual([]);
});

function activePage(): Locator {
  return page.locator('[data-page-active="true"]');
}

async function expectContainedLabel(trigger: Locator): Promise<void> {
  const geometry = await trigger.evaluate((element) => {
    const label = element.querySelector(".picker-value")!.getBoundingClientRect();
    const arrow = element.querySelector(".picker-chevron")!.getBoundingClientRect();
    const control = element.getBoundingClientRect();
    const column = element.closest(".field-control")!.getBoundingClientRect();
    return {
      controlWidth: control.width,
      columnWidth: column.width,
      labelRight: label.right,
      arrowLeft: arrow.left,
      arrowRight: arrow.right,
      controlRight: control.right,
      height: control.height,
    };
  });
  expect(geometry.controlWidth).toBeLessThanOrEqual(geometry.columnWidth);
  expect(geometry.labelRight).toBeLessThanOrEqual(geometry.arrowLeft);
  expect(geometry.arrowRight).toBeLessThan(geometry.controlRight);
  expect(geometry.height).toBe(28);
}

for (const theme of ["light", "dark"] as const) {
  test(`run pages share subject disclosure and action placement in ${theme}`, async () => {
    const testInfo = test.info();
    await setTheme(page, theme);
    const measured = [];
    for (const id of RUN_PAGES) {
      await gotoPage(page, id);
      await expectPage(page, id);
      const work = activePage().getByTestId("page-work");
      if (SUBJECT_FIELD_PAGES.has(id)) {
        const subjects = work.getByTestId("subjects-field");
        await expect(subjects).toBeVisible();
        const disclosure = subjects.getByTestId("subjects-change");
        if ((await disclosure.getAttribute("aria-expanded")) !== "true") await disclosure.click();
        const selectedSubject = subjects.getByRole("checkbox", { name: "ernie", exact: true });
        await expect(selectedSubject).toBeVisible();
        await expect(disclosure).toHaveAttribute("aria-expanded", "true");
        expect(await disclosure.getAttribute("aria-controls")).toBeTruthy();
        await disclosure.click();
        await expect(disclosure).toHaveAttribute("aria-expanded", "false");
      } else {
        // The jobs pages: the row owns the subject, so the first control is the table, and its
        // Subject cell is the one selection grammar behind a combobox trigger.
        const table = work.locator(JOBS_CONTAINER).first();
        await expect(table).toBeVisible();
        await expect(table.locator('td[data-cell="subject"]').first().getByRole("combobox")).toBeVisible();
      }

      const primary = work.getByTestId("run-button");
      await expect(primary).toBeVisible();
      const geometry = await work.evaluate((element, firstControl) => {
        const subject = element.querySelector(firstControl)!;
        // The first section that is NOT the one holding that control: on a jobs page the table
        // lives inside its own `Jobs` section, so "the subject control comes first" is a claim
        // about the sections that follow it.
        // `null` where the page has no OTHER section: the Optimizer's 2026-09-06 pass dissolved
        // target, objective/electrodes, solver and the subject table into the row, leaving the
        // Jobs table as the only section on the page. "The first control comes first" has nothing
        // to order against there, and is reported as such rather than as a passing claim.
        const firstSection = Array.from(element.querySelectorAll(".form-section")).find((s) => !s.contains(subject)) ?? null;
        const bar = element.querySelector(".action-bar")!.getBoundingClientRect();
        const button = element.querySelector('[data-testid="run-button"]')!.getBoundingClientRect();
        // The digest is absent while a run is blocked (the disabled primary carries the reason),
        // so it is measured only when it is there.
        const digest = element.querySelector(".action-bar-digest")?.getBoundingClientRect() ?? null;
        const pane = element.getBoundingClientRect();
        return {
          subjectsFirst: firstSection
            ? !!(subject.compareDocumentPosition(firstSection) & Node.DOCUMENT_POSITION_FOLLOWING)
            : null,
          sectionsAfterFirstControl: firstSection !== null,
          primaryHeight: button.height,
          actionHeight: bar.height,
          primaryRight: button.right,
          paneRight: pane.right,
          primaryLeft: button.left,
          digestRight: digest ? digest.right : null,
          overlap: button.bottom > bar.bottom || button.top < bar.top,
          overflow: element.scrollWidth - element.clientWidth,
        };
      }, FIRST_CONTROL);
      measured.push({ page: id, ...geometry });
      // Only where there is a section to come after it; see `firstSection` above.
      if (geometry.sectionsAfterFirstControl) expect(geometry.subjectsFirst, id).toBe(true);
      else expect(geometry.subjectsFirst, `${id}: single-section page`).toBeNull();
      expect(geometry.primaryHeight, id).toBe(32);
      expect(geometry.actionHeight, id).toBeGreaterThanOrEqual(44);
      expect(geometry.primaryRight, id).toBeLessThan(geometry.paneRight);
      if (geometry.digestRight !== null) expect(geometry.digestRight, id).toBeLessThan(geometry.primaryLeft);
      expect(geometry.overlap, id).toBe(false);
      expect(geometry.overflow, id).toBe(0);
    }
    const metricsPath = testInfo.outputPath("control-geometry.json");
    writeFileSync(metricsPath, JSON.stringify(measured, null, 2));
    await testInfo.attach("control-geometry", { path: metricsPath, contentType: "application/json" });
    await page.screenshot({ path: testInfo.outputPath(`analyzer-controls-${theme}.png`) });

    // Source submits from its forward-solution card, not an action bar. Its primary button
    // must use the same 32px size instead of falling back to ordinary 28px controls.
    await gotoPage(page, "panel-source", "Source");
    await expectPage(page, "panel-source");
    const sourceHeights: Record<string, number> = {};
    for (const name of ["Build forward"]) {
      const primary = activePage().getByRole("button", { name, exact: true });
      await expect(primary).toBeVisible();
      const height = await primary.evaluate((element) => element.getBoundingClientRect().height);
      sourceHeights[name] = height;
      expect(height, `Source ${name} primary in ${theme}`).toBe(32);
    }
    const sourceMetricsPath = testInfo.outputPath("source-primary-geometry.json");
    writeFileSync(sourceMetricsPath, JSON.stringify(sourceHeights, null, 2));
    await testInfo.attach("source-primary-geometry", { path: sourceMetricsPath, contentType: "application/json" });
  });

  test(`long dropdown labels stay contained and menus remain keyboard usable in ${theme}`, async () => {
    const testInfo = test.info();
    await gotoPage(page, "dev", "Gallery");
    await expect(page.getByRole("heading", { name: "Design gallery" })).toBeVisible();
    await setTheme(page, theme);
    const field = (label: string) => activePage().locator(".field").filter({
      has: page.locator(".field-label-text", { hasText: new RegExp(`^${label}$`) }),
    }).first();

    // Resize the gallery's real component to a valid narrow form column. The selected long
    // name used to force the 200px trigger outside its available 188px control column.
    const region = field("Atlas region");
    await region.evaluate((element) => { (element as HTMLElement).style.width = "360px"; });
    const combo = region.locator(".combobox-trigger");
    await combo.click();
    await page.getByRole("option", { name: "Dorsolateral prefrontal cortex", exact: true }).click();
    await expect(combo).toHaveAttribute("title", "Dorsolateral prefrontal cortex");
    await expectContainedLabel(combo);
    await combo.click();
    await page.keyboard.press("Escape");
    await expect(combo).toBeFocused();

    const goal = field("Goal");
    await goal.evaluate((element) => { (element as HTMLElement).style.width = "360px"; });
    const select = goal.getByRole("combobox");
    await select.click();
    const menu = page.locator(".select-content");
    await expect(menu.getByRole("option", { name: "Mean", exact: true })).toBeFocused();
    const geometry = await menu.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        viewportWidth: innerWidth,
        viewportHeight: innerHeight,
        labelLefts: Array.from(element.querySelectorAll(".picker-option-label"), (label) => label.getBoundingClientRect().left),
        rowHeights: Array.from(element.querySelectorAll('[role="option"]'), (option) => option.getBoundingClientRect().height),
      };
    });
    expect(geometry.left).toBeGreaterThanOrEqual(0);
    expect(geometry.top).toBeGreaterThanOrEqual(0);
    expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportHeight);
    expect(geometry.labelLefts).toHaveLength(3);
    expect(new Set(geometry.labelLefts).size).toBe(1);
    expect(geometry.rowHeights.every((height) => height >= 28)).toBe(true);
    await page.keyboard.press("End");
    // Radix moves focus in the next task; Enter must commit the destination, not race that move.
    await expect(menu.getByRole("option", { name: "Focality", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(select).toHaveText("Focality");
    await expect(select).toBeFocused();
    await expectContainedLabel(select);
    const metricsPath = testInfo.outputPath("dropdown-geometry.json");
    writeFileSync(metricsPath, JSON.stringify(geometry, null, 2));
    await testInfo.attach("dropdown-geometry", { path: metricsPath, contentType: "application/json" });
    await goal.screenshot({ path: testInfo.outputPath(`dropdown-${theme}.png`) });
  });
}
