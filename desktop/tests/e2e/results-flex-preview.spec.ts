/**
 * Results › a flex run's preview reads the manifest the Python writer produced (2026-10-22, p12).
 *
 * The mock catalog's ernie flex run carries `tests/fixtures/flex_meta_contract/
 * subcortical_union_mapped.json`, written by the real `tit/opt/flex/manifest.py::write_manifest`
 * (`dev/regen_flex_manifest_fixtures.py`): a two-label MASSP union stored as lists, mapped onto
 * GSN-HydroCel-185. Expected text is derived from that file here (basename, labels, best value),
 * not typed from the page. Offscreen against the mock server: `TIT_E2E_OFFSCREEN=1`.
 */
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

const manifest = JSON.parse(
  readFileSync(resolve(__dirname, "../../../tests/fixtures/flex_meta_contract/subcortical_union_mapped.json"), "utf8"),
) as {
  roi: { atlas_path: string[]; label: number[]; tissues: string };
  eeg_net: string;
  result: { best_value: number };
};

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
});
test.afterEach(async () => {
  await app?.close();
});

test("a flex run's ROI row names the atlas file and every label, and its best value is the manifest's", async () => {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId("results-subject-ernie").click();
  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();

  const summary = page.getByTestId("results-summary-rows");
  const row = (label: string) => summary.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("xpath=following-sibling::dd[1]");

  const file = manifest.roi.atlas_path[0]!.split("/").pop()!;
  // One file for both labels: "<file> labels 13+14".
  await expect(row("ROI")).toHaveText(`subcortical · ${file} labels ${manifest.roi.label.join("+")} · ${manifest.roi.tissues}`);
  await expect(row("EEG net")).toHaveText(manifest.eeg_net.replace(/\.csv$/, ""));
  // trimNumber: four decimals at most.
  await expect(row("Best value")).toHaveText(String(Number(manifest.result.best_value.toFixed(4))));
});
