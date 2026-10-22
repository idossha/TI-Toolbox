import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addOptRow, clearOptRows, closeOptEditor, openOptEditor, setOptCell, setOptSubject } from "./_jobs";

/**
 * Optimizer flex gates (package p08, 2026-10-22): what the flex form lets run is what FlexConfig
 * accepts, and what it refuses is refused in the form, with the reason under the field.
 *
 * Flows, against the mock server (offscreen):
 *   1. Threshold-based focality, Adaptive thresholds, "Optimize" current ratio: one flex_adaptive
 *      job reaches the wire with the adaptive shares the form shows (80/20) and the ratio search
 *      on. Before this date FlexConfig refused that combination at submit.
 *   2. Fixed thresholds with the box empty: an inline error and a disabled Run, whose title names
 *      the row and the reason; typing "0.1,0.3" clears both.
 *   3. An ellipse electrode is one Diameter (SimNIBS's flex electrode is a disc): no width/height
 *      pair to make unequal; a 10 x 6 rectangle switched to an ellipse becomes a 10 mm disc.
 *   4. Min distance 0 mm: an inline error and a disabled Run.
 * Expected values come from the form's own defaults (app_defaults: adaptive 80/20) and from
 * FlexConfig's rules (tit/opt/config.py), never from the page's builder. The Run-name rule
 * (`Thalamus (L)`) belongs to the shared entity-name package and is not covered here.
 *
 * Run: cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/optimizer-flex-gates.spec.ts
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Locator): Locator {
  return root.locator(".field").filter({ has: page.locator(".field-label-text", { hasText: new RegExp(`^${label}$`) }) });
}

async function pickCorticalTarget(dialog: Locator): Promise<void> {
  await field("Atlas", dialog).locator(".combobox-trigger").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: /Desikan-Killiany/i }).click();
  await field("Region\\(s\\)", dialog).getByRole("combobox").click();
  await page.getByPlaceholder("Filter regions…").fill("bankssts");
  await page.getByRole("option", { name: "L · bankssts", exact: true }).click();
  await page.getByTestId("roi-region-done").click();
}

/** A fresh flex row for ernie with a cortical target and *goal*, its editor open. */
async function flexRow(goal: string): Promise<Locator> {
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  await setOptCell(page, row, "goal", goal);
  const dialog = await openOptEditor(page, row);
  await pickCorticalTarget(dialog);
  return dialog;
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectLauncher(page, SERVER_URL, TOKEN);
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

test("adaptive threshold focality with the current ratio optimised reaches the wire as one flex_adaptive job", async () => {
  const dialog = await flexRow("Threshold-based focality");
  await expect(dialog.getByRole("radio", { name: "Adaptive thresholds", exact: true })).toBeChecked();
  await field("Current ratio", dialog).getByRole("checkbox", { name: "Optimize" }).check();
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await closeOptEditor(page);

  const run = page.getByTestId("run-button");
  await expect(run).toBeEnabled({ timeout: 15_000 });
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await run.click();
  const replace = page.getByTestId("existing-outputs-replace");
  if (await replace.isVisible().catch(() => false)) await replace.click();
  const body = (await request).postDataJSON() as {
    kind: string;
    subject_configs: { subject_id: string; config: Record<string, unknown> }[];
  };
  expect(body.kind).toBe("flex_adaptive");
  expect(body.subject_configs).toHaveLength(1);
  const config = body.subject_configs[0]!.config;
  expect(config.goal).toBe("focality");
  expect(config.optimize_current_ratio).toBe(true);
  expect(config.adaptive).toEqual({ nonroi_percentage: 20, roi_percentage: 80 });
  // The driver derives the thresholds; the form sends none.
  expect(config.thresholds).toBeNull();
});

test("fixed thresholds with an empty box show the reason inline and keep Run disabled", async () => {
  const dialog = await flexRow("Threshold-based focality");
  await dialog.getByRole("radio", { name: "Fixed thresholds", exact: true }).click();
  const thresholds = field("E-field thresholds", dialog);
  const reason = "Enter the E-field thresholds: one value (non-ROI max = ROI min) or two (non-ROI max, ROI min) in V/m.";
  await expect(thresholds.getByRole("alert")).toHaveText(reason);
  await expect(thresholds.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
  await closeOptEditor(page);
  const run = page.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", `Job 1: ${reason}`);

  const again = await openOptEditor(page, page.locator("tbody[data-opt-row]").first());
  await field("E-field thresholds", again).getByRole("textbox").fill("0.5,0.1");
  await expect(field("E-field thresholds", again).getByRole("alert")).toHaveText(
    "The non-ROI maximum (first value) may not exceed the ROI minimum (second value).",
  );
  await field("E-field thresholds", again).getByRole("textbox").fill("0.1,0.3");
  await expect(field("E-field thresholds", again).getByRole("alert")).toHaveCount(0);
  await closeOptEditor(page);
  await expect(run).toBeEnabled({ timeout: 15_000 });
});

test("an ellipse electrode is one diameter; a rectangle keeps width and height", async () => {
  const dialog = await flexRow("Mean TImax");
  await expect(dialog.getByRole("spinbutton", { name: "Electrode diameter" })).toHaveValue("8");
  await expect(dialog.getByRole("spinbutton", { name: "Electrode height" })).toHaveCount(0);

  await dialog.getByRole("radio", { name: "Rectangle", exact: true }).click();
  await dialog.getByRole("spinbutton", { name: "Electrode width" }).fill("10");
  await dialog.getByRole("spinbutton", { name: "Electrode height" }).fill("6");
  await dialog.getByRole("radio", { name: "Ellipse", exact: true }).click();
  // Back to a disc: one diameter, the width, and nothing to make unequal.
  await expect(dialog.getByRole("spinbutton", { name: "Electrode diameter" })).toHaveValue("10");
  await expect(dialog.getByRole("spinbutton", { name: "Electrode height" })).toHaveCount(0);
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await closeOptEditor(page);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15_000 });
});

test("a 0 mm minimum electrode distance shows the reason inline and keeps Run disabled", async () => {
  const dialog = await flexRow("Mean TImax");
  const distance = field("Min distance", dialog);
  await distance.getByRole("spinbutton").fill("0");
  await expect(distance.getByRole("alert")).toHaveText("Min distance must be greater than 0 mm.");
  await expect(distance.getByRole("spinbutton")).toHaveAttribute("aria-invalid", "true");
  await closeOptEditor(page);
  const run = page.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Job 1: Min distance must be greater than 0 mm.");
});
