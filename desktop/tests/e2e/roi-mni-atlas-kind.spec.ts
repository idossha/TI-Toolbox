/**
 * An MNI atlas is only offered to the mode that can read it
 * (`docs/dev/DECISIONS.md § 2026-09-17 — An atlas manifest with a kind…`).
 *
 * The defect: the MNI atlas list was four filenames in `tit/atlas/constants.py` and nothing said
 * whether a file was a surface parcellation or a label volume, so the ROI picker could not route
 * one to the right targeting flow. Now `resources/atlas/manifest.json` gives every shipped MNI
 * atlas a `kind`, the catalog serves it, and both the server and `getAtlases()` filter on it.
 *
 * Two claims, both driven through the real picker:
 *
 *  - **Subcortical + MNI** offers the packaged MNI *volumes* (all of them are volumes today,
 *    including Glasser — a cortical parcellation distributed as a NIfTI).
 *  - **Cortical + MNI** offers none of them, and says why. The mock deliberately serves the
 *    Glasser volume under `kind=cortical`, so this only passes because the client checks `kind`
 *    rather than trusting the bucket it arrived in.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { closeOptEditor, openOptEditor, optRows } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator): Locator {
  return root.locator(".field", { hasText: label }).first();
}

function pickerSwitch(root: Locator): Locator {
  return root.getByTestId("roi-picker-space");
}

/** Every atlas the picker's own atlas combobox offers, with the popover closed again. */
async function atlasOptions(root: Locator, label: string): Promise<string[]> {
  await field(label, root).locator(".combobox-trigger").click();
  const listbox = page.getByRole("listbox");
  await expect(listbox).toBeVisible();
  const names = (await page.getByRole("option").allInnerTexts()).map((t) => t.trim());
  // Close the listbox only: a second Escape after it has already gone would reach the editor
  // dialog and close it too, and the test's Done click would then time out.
  await page.keyboard.press("Escape");
  await expect(listbox).toHaveCount(0);
  return names;
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-mni-kind-"));
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

  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
});

test.afterAll(async () => {
  await app?.close();
});

test("Subcortical + MNI offers the packaged MNI volumes", async () => {
  const editor = await openOptEditor(page, optRows(page).first(), "settings");
  await editor.locator(".roi-picker .segmented").first().getByRole("radio", { name: "Subcortical", exact: true }).click();
  await pickerSwitch(editor).getByRole("radio", { name: "MNI", exact: true }).click();

  const options = await atlasOptions(editor, "Volume atlas");
  expect(options.length).toBeGreaterThan(0);
  expect(options.some((name) => /CIT168/i.test(name))).toBe(true);
  // Glasser is a cortical parcellation shipped as a volume, so this is where it belongs.
  expect(options.some((name) => /Glasser/i.test(name))).toBe(true);
  // The subject's own volumes are not MNI atlases.
  expect(options.some((name) => name.includes("labeling.nii.gz"))).toBe(false);
  await closeOptEditor(page);
});

test("Cortical + MNI offers no volume atlas, and says why", async () => {
  const editor = await openOptEditor(page, optRows(page).first(), "settings");
  await editor.locator(".roi-picker .segmented").first().getByRole("radio", { name: "Cortical", exact: true }).click();
  await pickerSwitch(editor).getByRole("radio", { name: "MNI", exact: true }).click();

  // The mock serves the Glasser *volume* in the cortical bucket on purpose; `kind` keeps it out.
  await expect(editor.getByText(/is a label volume/i)).toBeVisible();
  const options = await atlasOptions(editor, "Atlas");
  expect(options.some((name) => /Glasser/i.test(name))).toBe(false);
  expect(options.some((name) => /CIT168/i.test(name))).toBe(false);
  await closeOptEditor(page);
});
