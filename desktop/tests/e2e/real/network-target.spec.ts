/**
 * The Network target end to end against a real server with real data, offscreen: rebuild a network
 * through the job form, choose thalamocortical edges, create the mask, run one flex and one ex job
 * on it, and rank the ex run. Needs a project with sub-CHN (m2m, QSIPrep, tractography, its
 * Cutini leadfield) and sub-ernie (a head model and no DWI, for the empty state); not Dataset 000,
 * whose network does not exist. Numbers are read from the server, not pinned: this subject is not
 * committed. `TIT_E2E_SCREENS` receives one PNG per state.
 *
 * Run: lockf /tmp/tit-e2e.lock env TIT_E2E_OFFSCREEN=1 TIT_E2E_SERVER_URL=... TIT_E2E_TOKEN=... \
 *   TIT_E2E_SCREENS=... npx playwright test --project=real tests/e2e/real/network-target.spec.ts
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { answerExistingOutputs, connectReal, expectPage, gotoPage, launchElectronApp, selectSubject, waitForJobTerminal } from "../_helpers";
import { addOptRow, clearOptRows, closeOptEditor, openOptEditor, setOptCell, setOptSubject } from "../_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SCREENS = process.env.TIT_E2E_SCREENS ?? join(tmpdir(), "tit-network-screens");
const LEADFIELD_NET = "EEG10-10_Cutini_2011";
const RUN = `ui-network-${Date.now().toString(36)}`;
const MASK = "thalamocortical_lh";
const JOB_TIMEOUT = 2_400_000;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

const shot = (name: string) => page.screenshot({ path: join(SCREENS, `${name}.png`) });
// Every run page stays mounted, so the Optimizer's button is named rather than found by test id.
const runSearch = () => page.getByRole("button", { name: "Run search", exact: true });
const field = (label: string, root: Locator) => root.locator(".field", { hasText: label }).first();

async function setNumber(root: Locator, label: string, value: string): Promise<void> {
  const input = field(label, root).locator("input").first();
  await input.fill(value);
  await input.blur();
}

test.beforeAll(async () => {
  mkdirSync(SCREENS, { recursive: true });
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  // A project with no example data asks once; this spec brings its own subject.
  const offer = page.getByRole("dialog").filter({ hasText: "Add example data?" });
  await offer.waitFor({ timeout: 10_000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click()).catch(() => undefined);
});
test.afterAll(async () => {
  await app?.close();
});

async function groupJobId(run: () => Promise<void>): Promise<string> {
  const response = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  await run();
  const r = await response;
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { jobs: { id: string }[] }).jobs[0]!.id;
}

async function expectSucceeded(id: string, timeoutMs = JOB_TIMEOUT): Promise<void> {
  const status = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: id, timeoutMs });
  expect(status.state, `job ${id}`).toBe("succeeded");
}

test("Pre-processing runs Tractography as a row of its own run, without QSIRecon", async () => {
  test.setTimeout(900_000);
  await selectSubject(page, "CHN");
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
  const row = page.getByRole("option", { name: /CHN/ }).first();
  if ((await row.getAttribute("aria-selected")) !== "true") await row.click();
  for (const label of ["Convert DICOM to NIfTI", "SimNIBS charm (m2m + subject atlas)", "FastSurfer segmentation"]) {
    await page.getByRole("checkbox", { name: label }).uncheck();
  }
  await page.getByRole("checkbox", { name: "Tractography" }).check();
  await page.getByTestId("open-tractography-config").click();
  const form = page.getByTestId("tractography-form");
  await expect(form.getByRole("combobox", { name: "Tractography atlas" })).toContainText("DK40");
  await shot("preprocess_tractography_config");
  await page.getByTestId("tractography-save").click();
  await shot("preprocess_diffusion");
  // CHN has a tractogram: the page's one existing-outputs question, answered skip, keeps it.
  const id = await groupJobId(async () => {
    await page.getByRole("button", { name: "Run preprocessing", exact: true }).click();
    await answerExistingOutputs(page, "skip");
  });
  await expectSucceeded(id, 800_000);
});

test("S0: a subject with no tractography says what it needs", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  const dialog = await openOptEditor(page, row);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  await expect(dialog.getByTestId("network-unavailable")).toContainText("No tractography for sub-ernie");
  await shot("S0_unavailable");
  await closeOptEditor(page);
});

test("S1-S4, flex: thalamocortical edges, a mask, the pane's lines, one flex job", async () => {
  test.setTimeout(JOB_TIMEOUT + 300_000);
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "CHN");
  const dialog = await openOptEditor(page, row);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  const panel = dialog.getByTestId("network-panel");
  await expect(panel).toHaveAttribute("data-state", "S1");
  await shot("S1_seeds");

  await panel.getByTestId("network-seeds").click();
  const seeds = page.getByRole("dialog", { name: "Choose seed regions" });
  await seeds.getByPlaceholder("Filter regions…").fill("Left-Thalamus");
  await seeds.getByRole("option", { name: /Left-Thalamus-Proper/ }).click();
  await seeds.getByRole("button", { name: "Done" }).click();
  await expect(panel).toHaveAttribute("data-state", "S2");

  const edges = panel.getByTestId("network-edges");
  await expect(edges.getByRole("option").first()).toBeVisible();
  await shot("S2_edges");

  // Thalamus -> left cortex only: the filter, then All, which skips rows below the minimum.
  await panel.getByPlaceholder("Filter edges…").fill("lh.");
  await edges.getByRole("button", { name: "All" }).click();
  await panel.getByPlaceholder("Filter edges…").fill("");
  await expect(panel).toHaveAttribute("data-state", "S3");
  await panel.getByTestId("network-mask-name").fill(MASK);
  await setNumber(panel, "Voxel density threshold", "2");
  await shot("S3_mask_form");

  const created = page.waitForResponse((r) => r.url().endsWith("/api/tract/mask"));
  await panel.getByTestId("network-create-mask").click();
  let response = await created;
  if (response.status() === 409) {
    const replaced = page.waitForResponse((r) => r.url().endsWith("/api/tract/mask"));
    await page.getByRole("alertdialog").getByRole("button", { name: "Replace mask" }).click();
    response = await replaced;
  }
  expect(response.status(), await response.text()).toBe(201);
  const mask = await response.json();
  console.log(`real/network: mask = ${JSON.stringify({ ...mask, pairs: mask.pairs.length })}`);
  expect(mask.n_voxels).toBeGreaterThan(0);
  await expect(panel).toHaveAttribute("data-state", "S4");
  await shot("S4_complete");

  await setNumber(dialog, "Optimization runs", "1");
  await setNumber(dialog, "Max iterations", "2");
  await field("Run name", dialog).getByRole("textbox").fill(`${RUN}-flex`);
  await closeOptEditor(page);
  await expect(row).toContainText(`${MASK} · `);

  // The pane: subject's grey matter in the locked atlas, with the listed edges over it.
  await page.waitForFunction(() => (window.__scene?.lines?.streamlines ?? 0) > 0, null, { timeout: 120_000 });
  await expect(page.getByTestId("scene-pane-atlas-locked")).toHaveText("Atlas: DK40");
  const counts = await page.evaluate(() => window.__scene!.lines);
  console.log(`real/network: pane lines = ${JSON.stringify(counts)}`);
  await page.waitForFunction(() => window.__scene?.camera.settled === true);
  await shot("pane_with_edges");

  // A hit on the anatomy for a pick on a line: walk the drawn frame until a line answers.
  const hit = await page.evaluate(() => {
    const scene = window.__scene!;
    const { widthCss, heightCss } = scene.canvas;
    const points: [number, number][] = [];
    for (let y = 20; y < heightCss; y += 20) for (let x = 20; x < widthCss; x += 20) points.push([x, y]);
    const picks = scene.samplePicks(points);
    return picks.findIndex((p) => p?.kind === "edge") >= 0;
  });
  expect(hit, "a click somewhere on the pane lands on a line").toBe(true);

  await expect(runSearch()).toBeEnabled({ timeout: 60_000 });
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const id = await groupJobId(() => runSearch().click());
  const config = (await request).postDataJSON().subject_configs[0].config;
  expect(config.roi).toMatchObject({ _type: "SubcorticalROI", label: null, tissues: "WM", atlas_space: "subject" });
  expect(String(config.roi.atlas_path)).toContain(`masks/tract-${MASK}.nii.gz`);
  await expectSucceeded(id);
});

test("a click on a cortical region in the pane adds it as a seed, by the network's own name", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "CHN");
  const dialog = await openOptEditor(page, row);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  await closeOptEditor(page);
  await page.waitForFunction(() => window.__scene?.ready === true && window.__scene.camera.settled, null, { timeout: 120_000 });
  const point = await page.evaluate(() => {
    const scene = window.__scene!;
    const { widthCss, heightCss } = scene.canvas;
    const points: [number, number][] = [];
    for (let y = 40; y < heightCss; y += 20) for (let x = 40; x < widthCss; x += 20) points.push([x, y]);
    return points[scene.sampleRegions(points).findIndex((r) => r !== null)]!;
  });
  const box = await page.getByTestId("scene-canvas").boundingBox();
  await page.mouse.click(box!.x + point[0], box!.y + point[1]);
  const reopened = await openOptEditor(page, row);
  const panel = reopened.getByTestId("network-panel");
  await expect(panel).toHaveAttribute("data-state", "S2");
  await expect(panel.getByTestId("network-seeds")).toHaveText(/^(lh|rh)\./);
  await expect(panel.getByTestId("network-edges").getByRole("option").first()).toBeVisible();
  console.log(`real/network: seed from the pane = ${await panel.getByTestId("network-seeds").textContent()}`);
  await closeOptEditor(page);
});

test("ex: the same mask, one job", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "CHN");
  await setOptCell(page, row, "method", "Ex");
  const netCell = row.locator('td[data-cell="net"]').getByRole("combobox");
  await netCell.click();
  await page.getByRole("option", { name: new RegExp(`${LEADFIELD_NET} · `) }).click();
  const dialog = await openOptEditor(page, row);
  await field("Run name", dialog).getByRole("textbox").fill(`${RUN}-ex`);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  const panel = dialog.getByTestId("network-panel");
  await panel.getByTestId("network-seeds").click();
  const seeds = page.getByRole("dialog", { name: "Choose seed regions" });
  await seeds.getByPlaceholder("Filter regions…").fill("Left-Thalamus");
  await seeds.getByRole("option", { name: /Left-Thalamus-Proper/ }).click();
  await seeds.getByRole("button", { name: "Done" }).click();
  await panel.getByPlaceholder("Filter edges…").fill("lh.");
  await panel.getByTestId("network-edges").getByRole("button", { name: "All" }).click();
  await panel.getByPlaceholder("Filter edges…").fill("");
  await panel.getByTestId("network-mask-name").fill(MASK);
  await setNumber(panel, "Voxel density threshold", "2");
  await panel.getByTestId("network-create-mask").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Replace mask" }).click();
  await expect(panel).toHaveAttribute("data-state", "S4");

  await dialog.getByRole("radio", { name: "All combinations", exact: true }).click();
  await field("Electrode pool", dialog).getByRole("combobox").click();
  const list = page.getByRole("dialog").filter({ hasText: /choose electrodes|Electrode pool/i }).last();
  for (const electrode of ["C3", "C5", "CP3", "CP5", "FC3", "FC5"]) {
    await list.getByPlaceholder(/Filter/).fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
  }
  await list.getByRole("button", { name: "Done" }).click();
  await closeOptEditor(page);

  await expect(runSearch()).toBeEnabled({ timeout: 60_000 });
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const id = await groupJobId(() => runSearch().click());
  const config = (await request).postDataJSON().subject_configs[0].config;
  expect(config.roi_atlas[0]).toMatchObject({ label: null, atlas_space: "subject" });
  expect(config.roi_names).toEqual([]);
  await expectSucceeded(id);
});

test("Results: rank the ex run on the network; every statistic side by side", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await gotoPage(page, "results", "Results");
  await page.getByTestId("results-subject-CHN").click();
  await page.locator(`[data-testid="results-node-ex:CHN:${RUN}-ex"]`).click();
  const ranking = page.getByTestId("network-ranking");
  await expect(ranking).toBeVisible();
  await ranking.scrollIntoViewIfNeeded();
  await expect(ranking.getByRole("combobox", { name: "Network mask" })).toContainText(MASK);
  const id = await groupJobId(() => ranking.getByTestId("network-rank").click());
  await expectSucceeded(id);
  const table = ranking.getByTestId("network-ranking-table");
  await expect(table).toBeVisible({ timeout: 60_000 });
  await table.scrollIntoViewIfNeeded();
  await shot("ranking_result");
  const rows = await table.getByRole("row").count();
  console.log(`real/network: ranking rows = ${rows - 1}`);
  expect(rows).toBeGreaterThan(1);
});
