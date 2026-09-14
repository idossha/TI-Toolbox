/** Authored fixture proves selection → subject preview → exact editable simulation draft.
 * Electron uses the shared hidden launch policy; run only under /tmp/tit-e2e.lock after pree2e.
 * This is UI/metadata evidence, not a numerical FEM validation.
 */
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp } from "./_helpers";

import { setJobPlacement } from "./_jobs";

const SERVER = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const fixture = JSON.parse(readFileSync(join(__dirname, "../fixtures/optimization_candidates.json"), "utf8"));
let app: ElectronApplication;
let page: Page;
test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-candidates-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectLauncher(page, SERVER, process.env.TIT_E2E_TOKEN ?? "mock-token");
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
});
test.afterEach(async () => { await app?.close(); });

test("candidate table and trade-off plot select one exact subject montage for a normal draft", async () => {
  const plans: Record<string, unknown>[] = [];
  const submitted: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    if (request.url().endsWith("/api/plan/sim")) plans.push(request.postDataJSON().config);
    if (/\/api\/jobs(?:\/groups)?$/.test(request.url())) submitted.push(request.url());
  });
  await gotoPage(page, "results", "Results");
  await page.getByTestId("results-subject-ernie").click();
  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();
  await page.getByRole("button", { name: "Expand the preview pane", exact: true }).click();
  const browser = page.getByTestId("candidate-browser");
  await expect(browser.locator(".candidate-table tbody tr")).toHaveCount(50);
  const tableBox = await browser.locator(".candidate-table").boundingBox();
  expect(tableBox!.height).toBeLessThanOrEqual(301);
  const plotBox = await browser.locator(".candidate-plot-panel").boundingBox();
  expect(plotBox!.x).toBeGreaterThanOrEqual(tableBox!.x + tableBox!.width);
  await expect(browser.locator("circle")).toHaveCount(60);
  await browser.locator('circle[aria-label="Select candidate trial-55"]').focus();
  await browser.locator('circle[aria-label="Select candidate trial-55"]').press("Enter");
  await expect(browser.getByRole("button", { name: "trial-55", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(browser).toContainText("Selected: trial-55");
  await expect(browser).toContainText("51–60 of 60");
  await expect(browser.locator(".candidate-table tbody tr")).toHaveCount(10);
  await browser.getByRole("button", { name: "Previous", exact: true }).click();
  const point = browser.locator('circle[aria-label="Select candidate trial-1"]');
  await point.focus(); await point.press("Enter");
  await expect(browser.getByRole("button", { name: "trial-1", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(browser).toContainText("Selected: trial-1");
  await expect.poll(() => page.evaluate(() => window.__scenePane?.subject), { timeout: 20_000 }).toBe("ernie");
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers)).toBe(4);
  await browser.getByRole("button", { name: "trial-2", exact: true }).click();
  await expect(browser.locator('circle[aria-label="Select candidate trial-2"]')).toHaveAttribute("data-selected", "true");
  await browser.getByRole("button", { name: "Use in Simulator", exact: true }).click();
  await expectPage(page, "simulator");
  await expect(page.getByTestId("sim-jobs-table").locator(".job-candidate-source")).toHaveAttribute("title", /Candidate trial-2/);
  await expect.poll(() => plans.find((config) => (config.montages as { name: string }[])?.[0]?.name === "candidate_trial-2"), { timeout: 20_000 }).toBeTruthy();
  const expected = structuredClone(fixture.simulation_config);
  expected.montages[0].provenance = { candidate_id: "trial-2", run: "flex_Thalamus_20260810_101500" };
  expect(plans.find((config) => (config.montages as { name: string }[])?.[0]?.name === "candidate_trial-2")).toEqual(expected);
  expect(submitted).toEqual([]);
  const signedCurrent = page.getByRole("spinbutton", { name: "candidate_trial-2 channel 2 current (mA)" });
  await expect(signedCurrent).toHaveCount(1);
  await signedCurrent.fill("-1.1");
  await signedCurrent.press("Tab");
  await expect.poll(() => plans.at(-1)?.intensities).toEqual([0.7, -1.1]);
  expect((plans.at(-1)?.montages as typeof expected.montages)[0].electrode_poses).toEqual(expected.montages[0].electrode_poses);
  await expect(page.getByText("its optimization metrics no longer describe this simulation", { exact: false })).toBeVisible();
  const row = page.getByTestId("sim-jobs-table").locator("tbody tr").first();
  const table = page.getByTestId("sim-jobs-table");
  await expect(table.locator('[data-cell="custom"]')).toHaveCount(0);
  const channels = table.locator(".job-channel");
  const firstChannel = await channels.nth(0).boundingBox();
  const secondChannel = await channels.nth(1).boundingBox();
  expect(Math.abs(firstChannel!.y - secondChannel!.y)).toBeLessThan(2);
  const labels = ["E0-0", "E0-1", "E0-2", "E0-3"];
  const cap = JSON.parse(readFileSync(join(__dirname, "../fixtures/scene/electrodes.json"), "utf8"));
  await page.route("**/api/scene/electrodes?**", (route) => route.fulfill({ json: { ...cap, electrodes: cap.electrodes.map((electrode: { id: string; world: number[] }) => ({ name: electrode.id, world: electrode.world })) } }));
  const mappingRequests: string[] = [];
  await page.route("**/api/catalog/optimization-candidates/trial-2/mapping?**", (route) => {
    mappingRequests.push(route.request().url());
    return route.fulfill({ json: { eeg_net: "GSN-HydroCel-185", pairs: [labels.slice(0, 2), labels.slice(2)], optimized_positions: [], mapped_positions: [], distances: [] } });
  });
  await setJobPlacement(page, row, "GSN-HydroCel-185");
  await expect.poll(() => mappingRequests.length).toBe(1);
  await expect.poll(() => (plans.at(-1)?.montages as Record<string, unknown>[])?.[0]?.mode).toBe("flex_mapped");
  expect((plans.at(-1)?.montages as Record<string, unknown>[])[0]?.electrode_poses).toBeUndefined();
  expect((plans.at(-1)?.montages as Record<string, unknown>[])[0]?.electrode_pairs).toEqual([labels.slice(0,2),labels.slice(2)]);
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__scenePane?.selection.markers.length)).toBe(4);
  const links = page.getByTestId("scene-displacements");
  await expect(links.locator("line")).toHaveCount(4);
  await expect(links.locator("text").first()).toContainText("mm");
  await expect(links.locator("line").first()).toHaveAttribute("x1", /^-?\d+(\.\d+)?$/);
  await expect.poll(() => links.locator("g").evaluateAll((groups) => groups.filter((group) => (group as SVGGElement).style.display !== "none").length)).toBeGreaterThan(0);
  await setJobPlacement(page, row, "Optimised (XYZ)");
  // Restoring an identical config reuses the plan cache, so it need not POST again.
  await expect(page.getByTestId("sim-jobs-table").getByText("XYZ", { exact: true })).toHaveCount(2);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers)).toBe(4);
  await expect(page.getByTestId("scene-displacements")).toHaveCount(0);
  expect(submitted).toEqual([]);
});
