import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { closeOptEditor, openOptEditor, optRows, setOptCell } from "./_jobs";

/**
 * DESIGN.md §4.2 rule 9 — **a small exclusive choice is a `SegmentedControl`** — on the pages
 * lane FIX-D's own conversion could not reach.
 *
 * FIX-D wrote the rule, converted six call sites inside `pages/_shared/roi`, `pages/analyzer` and
 * `pages/panels`, and listed eight more that still broke it (`fix-d-notes.md` §9 request 2). This
 * spec is the behavioural half of closing that list: `tests/unit/segmented-idiom.test.ts` proves
 * no source file renders a `RadioGroup` any more, and this proves the pages a user actually opens
 * show one idiom — and that the choice still *works*, since the swap has to be invisible to a
 * screen reader (`role="radiogroup"`/`"radio"` on both) but must not be invisible to the form.
 *
 * `ui/CoordinateInput.tsx` is the one that mattered most: its Subject/MNI choice is the same
 * choice `RoiPicker` renders as a segment, and it is reached from that picker's own "Add ROI"
 * dialog — so before this, two idioms for one idea met inside a single flow.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

/** The rule, stated once: no page shows the other idiom anywhere in its work pane. */
async function noRadioGroup(root: Locator = page.getByTestId("page-work")): Promise<void> {
  await expect(root.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
}

/**
 * The Optimizer's method is a cell of a job ROW since the 2026-09-06 jobs table, and every form it
 * used to carry globally lives in that row's editor — so the segments this spec is about are found
 * by opening the row, not by walking the page.
 */
async function pickMethod(name: "Flex" | "Ex"): Promise<void> {
  await setOptCell(page, optRows(page).first(), "method", name);
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-segmented-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
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

test("the Simulator's electrode shape is a segment, in the job's own settings editor", async () => {
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");

  // The three page-level sections are gone (2026-09-06): electrodes, conductivity and output
  // fields belong to a JOB, so the segment lives in the row's own editor.
  await page.locator("tr[data-job-row]").first().locator('td[data-cell="actions"]').getByRole("button", { name: /^Job settings/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("job-settings-form")).toBeVisible();

  const shape = field("Shape", dialog).locator(".segmented");
  await expect(shape).toHaveCount(1);
  expect(await shape.getByRole("radio").allTextContents()).toEqual(["Ellipse", "Rectangle"]);
  await expect(shape.getByRole("radio", { name: "Ellipse", exact: true })).toBeChecked();

  await shape.getByRole("radio", { name: "Rectangle", exact: true }).click();
  await expect(shape.getByRole("radio", { name: "Rectangle", exact: true })).toBeChecked();
  // Proof the click reached the form and not just the control's own pressed state: the row says so
  // once the editor is done with.
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(page.locator('tr[data-job-detail] [data-cell="custom"]').first()).toHaveText(/rect /);

  await noRadioGroup();
});

test("the Optimizer's shape, threshold mode and search space are segments — and so is the Add ROI dialog's space", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await pickMethod("Flex");

  // Every one of these lives in the row's editor now (the jobs table pass): same controls, same
  // idiom claim, reached through the row rather than through the page.
  const editor = await openOptEditor(page, optRows(page).first(), "settings");
  const electrodes = editor.locator(".form-section", { hasText: "Electrodes" }).first();
  expect(await field("Shape", electrodes).locator(".segmented").getByRole("radio").allTextContents()).toEqual([
    "Ellipse",
    "Rectangle",
  ]);

  // Threshold mode appears only for the threshold form of the focality goal.
  await field("Goal", editor).getByRole("combobox").click();
  await page.getByRole("option", { name: "Focality", exact: true }).click();
  const thresholdMode = field("Threshold mode", editor).locator(".segmented");
  await expect(thresholdMode).toHaveCount(1);
  expect(await thresholdMode.getByRole("radio").allTextContents()).toEqual([
    "Manual thresholds",
    "Adaptive (single run)",
    "Pareto sweep",
  ]);
  await noRadioGroup(editor);
  await closeOptEditor(page);

  await pickMethod("Ex");
  const exEditor = await openOptEditor(page, optRows(page).first(), "settings");
  const searchSpace = field("Search space", exEditor).locator(".segmented");
  expect(await searchSpace.getByRole("radio").allTextContents()).toEqual(["Bucketed", "All combinations"]);
  // The electrode count that decides ex from mEx is the same idiom too.
  expect(await field("Electrodes", exEditor).locator(".segmented").getByRole("radio").allTextContents()).toEqual([
    "4 electrodes (TI)",
    "8 electrodes (mTI)",
  ]);
  await noRadioGroup(exEditor);

  // `ui/CoordinateInput` — the request FIX-D called the one that matters most. It is reached from
  // the ROI picker's own "Add ROI" dialog, so before this the dialog's space radios and the
  // picker's space segment were two idioms one click apart. The picker is inside the row editor
  // now, so this is a dialog opened from a dialog.
  await exEditor.getByRole("button", { name: /Add ROI/i }).first().click();
  const dialog = page.getByRole("dialog").filter({ hasText: "Add new ROI" });
  await expect(dialog).toBeVisible();
  const space = dialog.locator(".segmented");
  await expect(space).toHaveCount(1);
  await expect(space).toHaveAttribute("aria-label", "Coordinate space");
  expect(await space.getByRole("radio").allTextContents()).toEqual(["Subject", "MNI"]);
  await space.getByRole("radio", { name: "MNI", exact: true }).click();
  await expect(space.getByRole("radio", { name: "MNI", exact: true })).toBeChecked();
  await noRadioGroup(dialog);
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await closeOptEditor(page);
  // …and the page itself, with every dialog closed, still shows no other idiom.
  await noRadioGroup();
});

test("Settings' existing-output policy and theme are segments", async () => {
  await gotoPage(page, "settings", "Settings");
  await expectPage(page, "settings");

  // Replace remains a project-gated choice even when the local execution preference exists.
  const policy = page.locator('[data-page-active="true"] .segmented[aria-label="Existing outputs"]');
  await expect(policy).toBeVisible();
  expect(await policy.getByRole("radio").allTextContents()).toEqual(["Skip existing outputs", "Replace and rerun"]);
  await expect(policy.getByRole("radio", { name: "Skip existing outputs", exact: true })).toBeChecked();
  await expect(policy.getByRole("radio", { name: "Replace and rerun", exact: true })).toBeDisabled();
  await noRadioGroup();

  await gotoPage(page, "settings", "Settings");
  await expectPage(page, "settings");
  const theme = field("Theme").locator(".segmented");
  await expect(theme).toHaveAttribute("aria-label", "Theme");
  expect(await theme.getByRole("radio").allTextContents()).toEqual(["System", "Light", "Dark"]);
  await noRadioGroup();
});
