/**
 * One space, two controls — and what each space draws (`docs/dev/DECISIONS.md § 2026-09-17`).
 *
 * Three claims, on the Optimizer and on the Analyzer:
 *
 *  - the Subject | MNI switch **above the pane** and the one **inside the ROI picker** are two
 *    views of the row's single `space`, so driving either moves both;
 *  - **Subject** draws the active row's own subject, not a stand-in;
 *  - **MNI** draws the packaged MNI152 guide and offers only MNI atlases.
 *
 * The middle one is the reversal of the 2026-09-06 rule that the pane draws the fixed guide and
 * never the subject, so it is asserted here rather than left to the unit tests: what the pane is
 * actually keyed on is visible only once the real query chain has run.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";
import { analysisRows, closeAnalysisTarget, closeOptEditor, openAnalysisTarget, openOptEditor, optRows } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

/** The control above the pane, on whichever page is active. */
function paneSwitch(): Locator {
  return page.locator('[data-page-active="true"]').getByTestId("scene-pane-space-control");
}

/** The control inside the ROI picker's open panel. */
function pickerSwitch(root: Locator): Locator {
  return root.getByTestId("roi-picker-space");
}

/** Which segment a `SegmentedControl` currently has pressed. */
async function pressed(control: Locator): Promise<string> {
  return (await control.locator('[data-state="on"]').first().innerText()).trim();
}

/** The pane's own report of what it drew. */
async function paneDebug(): Promise<{ guideId: string | null; subject: string | null; atlas: string | null }> {
  return page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return { guideId: handle.guideId ?? null, subject: handle.subject, atlas: handle.atlas };
  });
}

/** Every option the pane's own atlas selector offers. */
async function paneAtlases(): Promise<string[]> {
  const select = page.locator('[data-page-active="true"]').getByTestId("scene-pane-atlas").getByRole("combobox");
  await select.click();
  const names = (await page.getByRole("option").allInnerTexts()).map((t) => t.trim());
  await page.keyboard.press("Escape");
  return names;
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-scene-space-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

test("Optimizer: subject space draws the row's own subject", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await expectRunPaneTab(page, "scene");
  const host = page.locator('[data-page-panel="optimizer"]').getByTestId("scene-pane-host");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await expect(paneSwitch()).toBeVisible();
  expect(await pressed(paneSwitch())).toBe("Subject");
  // The reversal of the 2026-09-06 rule: this used to be `null` with `guide: "ernie"`.
  await expect.poll(async () => (await paneDebug()).subject, { timeout: 30_000 }).toBe(SUBJECT);
});

test("Optimizer: the switch above the pane and the one in the picker are one value", async () => {
  const row = optRows(page).first();
  const editor = await openOptEditor(page, row, "settings");
  await expect(pickerSwitch(editor)).toBeVisible();
  expect(await pressed(pickerSwitch(editor))).toBe("Subject");

  // Picker -> pane.
  await pickerSwitch(editor).getByRole("radio", { name: "MNI", exact: true }).click();
  expect(await pressed(pickerSwitch(editor))).toBe("MNI");
  await closeOptEditor(page);
  await expect.poll(() => pressed(paneSwitch())).toBe("MNI");

  // Pane -> picker.
  await paneSwitch().getByRole("radio", { name: "Subject", exact: true }).click();
  const check = await openOptEditor(page, row, "settings");
  await expect.poll(() => pressed(pickerSwitch(check))).toBe("Subject");
  await closeOptEditor(page);
});

test("Optimizer: MNI space draws MNI152 and offers only MNI atlases", async () => {
  await paneSwitch().getByRole("radio", { name: "MNI", exact: true }).click();
  const host = page.locator('[data-page-panel="optimizer"]').getByTestId("scene-pane-host");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await expect.poll(async () => (await paneDebug()).guideId, { timeout: 30_000 }).toBe("mni");
  // A millimetre of MNI152 is not this subject's, so the pane is never handed the subject here.
  expect((await paneDebug()).subject).toBeNull();

  const atlases = await paneAtlases();
  expect(atlases.length).toBeGreaterThan(0);
  expect(atlases.some((name) => /MNI152NLin/i.test(name))).toBe(true);
  // The subject's own parcellations have no meaning on the template.
  expect(atlases).not.toContain("DK40");
  expect(atlases.some((name) => name.includes("labeling.nii.gz"))).toBe(false);

  await paneSwitch().getByRole("radio", { name: "Subject", exact: true }).click();
  await expect.poll(async () => (await paneDebug()).guideId, { timeout: 30_000 }).toBeNull();
});

test("Analyzer: the same two controls, over the same one value", async () => {
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
  await expectRunPaneTab(page, "scene");
  const host = page.locator('[data-page-panel="analyzer"]').getByTestId("scene-pane-host");
  await expect(host).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  expect(await pressed(paneSwitch())).toBe("Subject");
  await expect.poll(async () => (await paneDebug()).subject, { timeout: 30_000 }).toBe(SUBJECT);

  await paneSwitch().getByRole("radio", { name: "MNI", exact: true }).click();
  const editor = await openAnalysisTarget(page, analysisRows(page).first());
  await expect.poll(() => pressed(pickerSwitch(editor))).toBe("MNI");
  await pickerSwitch(editor).getByRole("radio", { name: "Subject", exact: true }).click();
  await closeAnalysisTarget(page);
  await expect.poll(() => pressed(paneSwitch())).toBe("Subject");
});
