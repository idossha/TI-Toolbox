import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { analysisRows, closeAnalysisTarget, closeOptEditor, openAnalysisTarget, openOptEditor, optRows, setOptCell } from "./_jobs";

/**
 * `pages/_shared/roi` — one idiom per idea, and rows/options that can be addressed (fix round,
 * lane FIX-D, defects 1 and 2).
 *
 * Three defects, each with the measurement that found it:
 *
 * 1. **One idea, two controls** (lane LAY). "Cortical / Subcortical / Spherical" is a `RadioGroup`
 *    inside `RoiPicker` on the Optimizer and a `SegmentedControl` on the Analyzer — two renderings
 *    of one choice, on two pages a user moves between. DESIGN.md §4.2 rule 9 now names one idiom
 *    for a small exclusive choice; this asserts it on both pages, and inside the picker's own
 *    panels (Space: Subject/MNI) where the two idioms were mixed in a single component.
 * 2. **A class that lies** (lane SUB §6.2). `RoiPicker`'s saved-ROI rows carried
 *    `class="subject-picker-row"`, so an unscoped subject-row locator counted them too — measured
 *    on the real project as 5 subjects + 1 saved ROI = 6 rows. The rows are now `.roi-saved-row`.
 * 3. **Options with no accessible name** (lane SCC §6.6). `getByRole("option", {name})` could not
 *    address a region option, so both real scene specs work around it with a regex on the label.
 *    Every option the picker offers now carries its own `aria-label`, which is what a role+name
 *    query reads.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

/** Since the Optimizer's 2026-09-06 jobs rework the method is a cell of a job ROW, and the picker
 *  lives in that row's editor — the same move the Analyzer's target made. */
async function pickMethod(name: "Flex" | "Ex" | "mEx"): Promise<void> {
  await setOptCell(page, optRows(page).first(), "method", name);
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-roi-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
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

test("defect 1: the ROI type is the same control on the Optimizer and the Analyzer", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await pickMethod("Flex");
  // The page itself holds no picker at all any more — it is a property of a search, and a search
  // is a row.
  await expect(page.getByTestId("page-work").locator(".roi-picker")).toHaveCount(0);

  let dialog = await openOptEditor(page, optRows(page).first());
  const picker = dialog.locator(".roi-picker");
  await expect(picker).toHaveCount(1);
  // The one idiom: a segmented control. Not "a segmented control exists somewhere" — the picker
  // must hold no `RadioGroup` at all, which is what the mixed state looked like.
  await expect(picker.locator(".segmented").first()).toBeVisible();
  await expect(picker.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
  const optimizerModes = await picker.locator(".segmented").first().getByRole("radio").allTextContents();
  expect(optimizerModes).toEqual(["Cortical", "Subcortical", "Spherical"]);

  // Spherical and subcortical each carry a Subject/MNI "Space" choice — the same small exclusive
  // choice, and the place the two idioms used to sit 40 px apart inside one component.
  await picker.locator(".segmented").first().getByRole("radio", { name: "Spherical", exact: true }).click();
  await expect(picker.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
  await expect(field("Space", picker).locator(".segmented")).toHaveCount(1);

  // Ex/mEx's saved-ROI mode: the fourth option of the same control, same idiom.
  await closeOptEditor(page);
  await pickMethod("Ex");
  dialog = await openOptEditor(page, optRows(page).first());
  const exPicker = dialog.locator(".roi-picker");
  await expect(exPicker.locator(".segmented").first().getByRole("radio")).toHaveText([
    "Saved",
    "Subcortical",
  ]);
  await expect(exPicker.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
  await closeOptEditor(page);

  /*
   * The Analyzer since 2026-09-06: the target is a cell of a job ROW, opened in a dialog holding
   * this same picker (maintainer: "we can modify our analysis input per job"). The idiom claim is
   * unchanged — it is the picker that must be the same control on both pages — only the place the
   * user opens it moved, so this drives it through the row's Target cell.
   */
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
  await expect(page.locator('[data-page-active="true"]').locator(".roi-picker")).toHaveCount(0);
  const targetDialog = await openAnalysisTarget(page, analysisRows(page).first());
  const analyzerPicker = targetDialog.locator(".roi-picker");
  await expect(analyzerPicker).toHaveCount(1);
  const analyzerModes = await analyzerPicker.locator(".segmented").first().getByRole("radio").allTextContents();
  expect(analyzerModes).toEqual(["Cortical", "Subcortical", "Spherical"]);
  // The Analyzer's own spherical rows carried the last `RadioGroup` on the page (LAY's request).
  await analyzerPicker.locator(".segmented").first().getByRole("radio", { name: "Spherical", exact: true }).click();
  await expect(field("Space", analyzerPicker).locator(".segmented")).toHaveCount(1);
  await expect(analyzerPicker.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
  await closeAnalysisTarget(page);
  await expect(page.locator('[data-page-active="true"]').locator(".radio-group, .radio-group-cards")).toHaveCount(0);
});

test("defect 2a: a saved-ROI row is not a subject row", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await pickMethod("Ex");

  // The Optimizer has no page-level subject control at all since the jobs rework, so the page-wide
  // count is the whole assertion: before the fix it read 3 — the saved-ROI rows, wearing the
  // subject row's class. Scoped to the ACTIVE page, because retained hidden panels keep their own
  // SubjectsField mounted.
  await expect(page.locator('[data-page-active="true"]').getByTestId("subjects-field")).toHaveCount(0);
  await expect(page.locator('[data-page-active="true"]').locator(".subject-picker-row")).toHaveCount(0);

  // The saved ROIs the fixture gives ernie (tests/fixtures/rois_seed.json) live in the row's editor.
  const dialog = await openOptEditor(page, optRows(page).first());
  await expect(dialog.locator(".roi-saved-row")).toHaveCount(3);
  console.log(
    `FIXD-ROWS subject-picker-row=${await page.locator(".subject-picker-row").count()} ` +
      `roi-saved-row=${await page.locator(".roi-saved-row").count()} (row editor open)`,
  );
  // The row's own Subject picker IS a subject list — and it is the only one, opened deliberately.
  await closeOptEditor(page);
  await optRows(page).first().locator('td[data-cell="subject"]').getByRole("combobox").click();
  await expect(page.getByRole("dialog").locator(".subject-picker-row, [role='option']").first()).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
});

test("defect 2b: every region option can be found by its accessible name", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await pickMethod("Flex");
  const editor = await openOptEditor(page, optRows(page).first());
  await editor.getByRole("radio", { name: "Cortical", exact: true }).click();

  await field("Atlas", editor).locator(".combobox-trigger").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  // The mock names it "Desikan-Killiany (DK40)", the real server just "DK40".
  await page.getByRole("option", { name: /DK40/i }).first().click();

  // The whole list, unfiltered — SCC's case was 140 options, not a list narrowed to one by a
  // search term, and the workaround it had to write was a `/^L/` regex on the label.
  await field("Region(s)", editor).getByRole("combobox").click();
  if (process.env.FIXD_DIAG === "1") {
    const dump = await page.$$eval('[role="option"]', (els) =>
      els.slice(0, 6).map((el) => ({
        text: JSON.stringify(el.textContent),
        label: el.getAttribute("aria-label"),
        codes: Array.from((el.textContent ?? "").slice(0, 14)).map((c) => c.codePointAt(0)),
      })),
    );
    console.log(`FIXD-OPTIONS ${(await page.getByRole("option").count())} ${JSON.stringify(dump)}`);
  }
  // The rendered label still names the option — that part was never broken (measured against the
  // container: 70 options, `L`+SP+U+00B7+SP+name, and this query resolves).
  const lh = page.getByRole("option", { name: "L · bankssts", exact: true });
  await expect(lh).toHaveCount(1);

  // What WAS missing, and what both real scene specs had to work around: a spec holding the data
  // the server gave it (`hemi`, `id`, `name`) could not build that string without also knowing
  // which separator the component chose to print — SCC's own words. Every option now carries its
  // value, so an exact query needs no punctuation at all.
  const byValue = page.locator('[role="option"][data-option-value="lh:1"]');
  await expect(byValue, "an option carries its own value").toHaveCount(1);
  await expect(byValue).toHaveAttribute("aria-label", "L · bankssts");
  await byValue.click();

  // A selected region leaves the list; the other hemisphere is still addressable, which is the
  // half of SCC's finding that survived their workaround.
  await expect(page.locator('[role="option"][data-option-value="rh:1"]')).toHaveCount(1);
  await page.getByTestId("roi-region-done").click();
  // The closed control states the selection in words — `ui/SelectionList`'s trigger, which answers
  // "what did I pick?" without being opened (the chip row it replaced truncated at two). One
  // region reads as its own name.
  await expect(field("Region(s)", editor).getByRole("combobox")).toHaveText("L · bankssts");

  // More than one, and the COUNT comes first (maintainer, 2026-09-06) — "how many" is the question
  // a closed control is actually asked, and the old trailing `+N more` answered it last and was
  // the first thing an ellipsis ate.
  await field("Region(s)", editor).getByRole("combobox").click();
  // ⌘-click ADDS, per the one selection grammar (`selection.spec.ts`); a plain click replaces.
  await page.locator('[role="option"][data-option-value="rh:1"]').click({ modifiers: ["Meta"] });
  await page.locator('[role="option"][data-option-value="lh:2"]').click({ modifiers: ["Meta"] });
  await page.getByTestId("roi-region-done").click();
  await expect(field("Region(s)", editor).getByRole("combobox")).toHaveText(/^3 regions · L · bankssts, R · bankssts…$/);
  // The full list is still one hover away.
  await expect(field("Region(s)", editor).getByRole("combobox")).toHaveAttribute("title", /bankssts/);
  await closeOptEditor(page);
});
