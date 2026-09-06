import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette, setSectionOpen } from "./_helpers";

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

/**
 * Sections fill the pane by themselves (FXU1), so this opens one only when it is closed — via the
 * converging helper, because the controller can open it between the read and the click and turn
 * this into a close (`_helpers.ts`'s `setSectionOpen`).
 */
async function openSection(title: string): Promise<Locator> {
  const section = await setSectionOpen(page, title, true);
  await expect(section.locator(".form-section-body")).toHaveCount(1);
  return section;
}

/** The rule, stated once: no page shows the other idiom anywhere in its work pane. */
async function noRadioGroup(root: Locator = page.getByTestId("page-work")): Promise<void> {
  await expect(root.locator(".radio-group, .radio-group-cards")).toHaveCount(0);
}

async function pickMethod(name: "Flex" | "Ex" | "mEx"): Promise<void> {
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name, exact: true }).click();
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

test("the Simulator's electrode shape is a segment, and choosing one still changes the form", async () => {
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");

  const electrodes = await openSection("Electrodes");
  const shape = field("Shape", electrodes).locator(".segmented");
  await expect(shape).toHaveCount(1);
  expect(await shape.getByRole("radio").allTextContents()).toEqual(["Ellipse", "Rectangle"]);
  await expect(shape.getByRole("radio", { name: "Ellipse", exact: true })).toBeChecked();

  await shape.getByRole("radio", { name: "Rectangle", exact: true }).click();
  await expect(shape.getByRole("radio", { name: "Rectangle", exact: true })).toBeChecked();
  // The section's own summary is the page's readout of that choice: proof the click reached the
  // form and not just the control's own pressed state.
  await setSectionOpen(page, "Electrodes", false);
  await expect(electrodes.locator(".form-section-summary")).toHaveText(/^rectangle · /);
  await setSectionOpen(page, "Electrodes", true);
  await shape.getByRole("radio", { name: "Ellipse", exact: true }).click();

  await noRadioGroup();
});

test("the Optimizer's shape, threshold mode and search space are segments — and so is the Add ROI dialog's space", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await pickMethod("Flex");

  const electrodes = await openSection("Electrodes");
  expect(await field("Shape", electrodes).locator(".segmented").getByRole("radio").allTextContents()).toEqual([
    "Ellipse",
    "Rectangle",
  ]);

  // Threshold mode appears only for the threshold form of the focality goal.
  await field("Goal").getByRole("combobox").click();
  await page.getByRole("option", { name: "Focality", exact: true }).click();
  const thresholdMode = field("Threshold mode").locator(".segmented");
  await expect(thresholdMode).toHaveCount(1);
  expect(await thresholdMode.getByRole("radio").allTextContents()).toEqual([
    "Manual thresholds",
    "Adaptive (single run)",
    "Pareto sweep",
  ]);
  await noRadioGroup();

  await pickMethod("Ex");
  const searchSpace = field("Search space").locator(".segmented");
  expect(await searchSpace.getByRole("radio").allTextContents()).toEqual(["Bucketed", "All combinations"]);
  await noRadioGroup();

  // `ui/CoordinateInput` — the request FIX-D called the one that matters most. It is reached from
  // the ROI picker's own "Add ROI" dialog, so before this the dialog's space radios and the
  // picker's space segment were two idioms one click apart.
  await page.getByTestId("page-work").getByRole("button", { name: /Add ROI/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const space = dialog.locator(".segmented");
  await expect(space).toHaveCount(1);
  await expect(space).toHaveAttribute("aria-label", "Coordinate space");
  expect(await space.getByRole("radio").allTextContents()).toEqual(["Subject", "MNI"]);
  await space.getByRole("radio", { name: "MNI", exact: true }).click();
  await expect(space.getByRole("radio", { name: "MNI", exact: true })).toBeChecked();
  await noRadioGroup(dialog);
  await dialog.getByRole("button", { name: "Cancel" }).click();
});

test("Pre-processing's existing-output policy and Settings' theme are segments", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");

  const outputs = await openSection("Existing outputs");
  const policy = outputs.locator(".segmented");
  await expect(policy).toHaveAttribute("aria-label", "Existing outputs");
  expect(await policy.getByRole("radio").allTextContents()).toEqual(["Skip existing outputs", "Replace and rerun"]);
  await expect(policy.getByRole("radio", { name: "Skip existing outputs", exact: true })).toBeChecked();
  await policy.getByRole("radio", { name: "Replace and rerun", exact: true }).click();
  // Collapsed, the section states the value the click produced — the page's own readout, not the
  // control's pressed state (a summary only exists while the section is closed).
  await outputs.locator(".form-section-header-trigger").click();
  await expect(outputs.locator(".form-section-summary")).toHaveText(/^replace and rerun · /);
  await outputs.locator(".form-section-header-trigger").click();
  await policy.getByRole("radio", { name: "Skip existing outputs", exact: true }).click();
  await noRadioGroup();

  await gotoPage(page, "settings", "Settings");
  await expectPage(page, "settings");
  const theme = field("Theme").locator(".segmented");
  await expect(theme).toHaveAttribute("aria-label", "Theme");
  expect(await theme.getByRole("radio").allTextContents()).toEqual(["System", "Light", "Dark"]);
  await noRadioGroup();
});
