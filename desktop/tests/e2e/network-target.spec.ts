/**
 * The Optimizer's Network target against the mock server, offscreen: S0 (no network, the job's form
 * on the wire), S1-S4 (seeds, edges, mask, stale), and the Results ranking as an explicit action.
 * The mock's numbers are authored in `tests/mock-server/server.mjs`; the configs a page sends are
 * asserted from what the user chose here. Real data: `tests/e2e/real/network-target.spec.ts`.
 *
 * Run: cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default tests/e2e/network-target.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";
import { clearOptRows, addOptRow, openOptEditor, closeOptEditor, setOptSubject } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-network-")) });
  page = await app.firstWindow();
  await connectLauncher(page, SERVER_URL, TOKEN);
});
test.afterAll(async () => {
  await app.close();
});

async function networkEditor(subject: string): Promise<{ row: Locator; dialog: Locator }> {
  await gotoPage(page, "optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, subject);
  const dialog = await openOptEditor(page, row);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  return { row, dialog };
}

test("S0: a subject with QSIPrep and no network is offered the job, which goes out on the wire", async () => {
  const { dialog } = await networkEditor("101");
  await expect(dialog.getByTestId("network-unavailable")).toContainText("No tractography for sub-101");
  await dialog.getByTestId("network-build").click();
  const form = page.getByTestId("tract-job-form");
  await expect(form.getByRole("combobox", { name: "Network atlas" })).toContainText("DK40");
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await page.getByTestId("tract-job-run").click();
  const body = (await request).postDataJSON();
  expect(body.kind).toBe("tract");
  expect(body.subject_ids).toEqual(["101"]);
  expect(body.subject_configs[0].config).toMatchObject({ _type: "TractConfig", subject_id: "101", stages: ["track", "network"], network: { atlas: "DK40" } });
  await closeOptEditor(page);
});

test("S1-S4: seeds list the edges, a mask completes the row, an edit makes it stale", async () => {
  const { row, dialog } = await networkEditor("ernie");
  const panel = dialog.getByTestId("network-panel");
  await expect(panel).toHaveAttribute("data-state", "S1");
  await expect(panel.getByTestId("network-summary")).toContainText("DK40 network");

  await panel.getByTestId("network-seeds").click();
  const seeds = page.getByRole("dialog", { name: "Choose seed regions" });
  await seeds.getByRole("option", { name: /Left-Thalamus-Proper/ }).click();
  await seeds.getByRole("button", { name: "Done" }).click();
  await expect(panel).toHaveAttribute("data-state", "S2");

  // Sorted by n, with no word ranking them; the one under min-n states why.
  const edges = panel.getByTestId("network-edges");
  const rows = edges.getByRole("option");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("lh.insula – Left-Thalamus-Proper");
  await expect(rows.nth(0)).toContainText("300");
  await rows.nth(0).click();
  await expect(panel).toHaveAttribute("data-state", "S3");
  // The choice names the mask until the user does.
  await expect(panel.getByTestId("network-mask-name")).toHaveValue("lh_insula_Left-Thalamus-Proper");
  await expect(panel.getByTestId("network-create-mask")).toBeEnabled();

  await panel.getByTestId("network-mask-name").fill("bad name");
  await expect(panel.getByText("Use letters, digits, _ and - only.")).toBeVisible();
  await expect(panel.getByTestId("network-create-mask")).toBeDisabled();
  await panel.getByTestId("network-mask-name").fill("thal_insula");
  const created = page.waitForRequest((r) => r.url().endsWith("/api/tract/mask"));
  await panel.getByTestId("network-create-mask").click();
  expect((await created).postDataJSON()).toEqual({
    subject: "ernie",
    name: "thal_insula",
    pairs: [["lh.insula", "Left-Thalamus-Proper"]],
    min_count: 1,
    min_n: 5,
    overwrite: false,
  });
  await expect(panel).toHaveAttribute("data-state", "S4");
  await expect(panel.getByTestId("network-mask-result")).toHaveText("1 edge · 300 streamlines · 1,200 mm³");
  await closeOptEditor(page);
  await expect(row).toContainText("thal_insula · 1 edge · network");

  // The same mask name again is the explicit overwrite policy.
  const reopened = await openOptEditor(page, row);
  await reopened.getByTestId("network-mask-name").fill("thal_insula2");
  await expect(reopened.getByTestId("network-mask-stale")).toBeVisible();
  await expect(reopened.getByTestId("network-create-mask")).toHaveText("Create the mask again");
  await closeOptEditor(page);
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /Create the mask again/);
  const third = await openOptEditor(page, row);
  await third.getByTestId("network-mask-name").fill("thal_insula");
  await third.getByTestId("network-create-mask").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Replace mask" }).click();
  await expect(third.getByTestId("network-panel")).toHaveAttribute("data-state", "S4");
  await closeOptEditor(page);
});

test("the pane draws the listed edges and a click on a line toggles that edge", async () => {
  await page.waitForFunction(() => (window.__scene?.lines?.streamlines ?? 0) > 0, null, { timeout: 15_000 });
  const before = await page.evaluate(() => window.__scene!.lines);
  expect(before).toEqual({ streamlines: 2, points: 4, groups: 2 });
  // Line 0 is the mock's z = 10 line, the selected edge; a pick there names group 0.
  const pick = await page.evaluate(() => {
    const scene = window.__scene!;
    const { x, y } = scene.project([0, 0, 10]);
    return scene.samplePicks([[Math.round(x), Math.round(y)]])[0];
  });
  expect(pick).toEqual({ kind: "edge", index: 0 });
  await expect(page.getByTestId("scene-pane-atlas-locked")).toHaveText("Atlas: DK40");

  // A real click on group 1, the unselected edge, adds it: the row is edited, its mask goes stale.
  const canvas = await page.getByTestId("scene-canvas").boundingBox();
  const at = await page.evaluate(() => window.__scene!.project([0, 0, 20]));
  await page.mouse.click(canvas!.x + at.x, canvas!.y + at.y);
  await expect(page.getByRole("button", { name: "Run search", exact: true })).toHaveAttribute("title", /Create the mask again/);
});

test("Results: ranking is an action, and every statistic is a column with none preferred", async () => {
  await gotoPage(page, "results");
  const ranking = await openFirstExRun(page);
  await expect(ranking.getByTestId("network-ranking-table")).toHaveCount(0);
  // All is the default, its size and time stated, and a top-N the other choice.
  await expect(ranking.getByRole("combobox", { name: "Montages to rank" })).toContainText("All montages in the run");
  const queued = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await ranking.getByTestId("network-rank").click();
  const body = (await queued).postDataJSON();
  expect(body.kind).toBe("tract");
  expect(body.config.stages).toEqual(["target"]);
  expect(body.config.target.top_n).toBeNull();
  expect(body.config.target.selection).toEqual({ name: "thal_insula", kind: "edges", pairs: [["lh.insula", "Left-Thalamus-Proper"]] });
  const table = ranking.getByTestId("network-ranking-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  for (const header of ["Median streamline mean ti_along (V/m)", "Pooled mean ti_along (V/m)", "Median streamline mean ti_max (V/m)", "Pooled mean ti_max (V/m)", "Median streamline mean ti_avg (V/m)", "Pooled mean ti_avg (V/m)", "Alignment index", "Rank by ti_along", "Rank by ti_max"]) {
    await expect(table.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
  }
  await expect(table.getByText(/preferred|recommended|best/i)).toHaveCount(0);
  // Reachable without scrolling sideways at 1440 px: both ranks end inside the table's scroll box.
  await page.setViewportSize({ width: 1440, height: 900 });
  const scroller = (await ranking.locator(".scroll-x").first().boundingBox())!;
  for (const header of ["Rank by ti_along", "Rank by ti_max"]) {
    const box = (await table.getByRole("columnheader", { name: header, exact: true }).boundingBox())!;
    expect(box.x + box.width, header).toBeLessThanOrEqual(scroller.x + scroller.width);
  }
  // Opens by montage name, not by either rank.
  await expect(table.getByRole("row").nth(1)).toContainText("AF3 F3 C1 Cz");
});

async function openFirstExRun(target: Page): Promise<Locator> {
  await target.getByTestId("results-subject-ernie").click();
  await target.getByTestId("results-node-ex:ernie:ex_L_Insula_20260812_090000").click();
  const ranking = target.getByTestId("network-ranking");
  await expect(ranking).toBeVisible();
  return ranking;
}

test("Pre-processing: Diffusion lists QSIPrep, DTI, Tractography, QSIRecon, and Tractography joins the run after QSIPrep", async () => {
  await gotoPage(page, "preprocess");
  const section = page.locator('[data-tier="1"]').filter({ hasText: "Diffusion" });
  await expect(page.getByText("DWI (docker)")).toHaveCount(0);
  await expect(section.getByRole("checkbox")).toHaveCount(4);
  const labels = await section.getByRole("checkbox").evaluateAll((boxes) => boxes.map((box) => box.closest("label")?.textContent?.trim() ?? box.getAttribute("aria-label")));
  expect(labels).toEqual(["QSIPrep", "Extract DTI tensor", "Tractography", "QSIRecon"]);

  await page.getByRole("checkbox", { name: "QSIPrep" }).check();
  await page.getByRole("checkbox", { name: "Tractography" }).check();
  await page.getByTestId("open-tractography-config").click();
  await expect(page.getByTestId("tractography-form").getByRole("combobox", { name: "Tractography atlas" })).toContainText("DK40");
  await page.getByTestId("tractography-save").click();
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const response = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups"));
  await page.getByRole("button", { name: /Run preprocessing|Queue/ }).click();
  await page.getByTestId("existing-outputs-skip").click({ timeout: 3000 }).catch(() => undefined);
  const body = (await request).postDataJSON();
  expect(body.kind).toBe("pre");
  expect(body.config).toMatchObject({ run_qsiprep: true, run_tractography: true, tractography_atlas: "DK40" });
  // The page's three default steps, QSIPrep and Tractography: its one run, one job per stage.
  expect((await (await response).json()).jobs).toHaveLength(5);
});
