/**
 * The whole chain through the app, offscreen, with no CLI step: tractography from scratch from the
 * Pre-processing row, a posterior network chosen by preset, a mask in both same-side states, an
 * ex-search on it, All-montage ranking, a simulation of the ranking's first montage, and a render
 * of the network from the Networks tab (assessed automatically first), then a second network whose
 * render leaves the first one's files alone.
 *
 * Needs a subject with QSIPrep output, an m2m head model and its leadfield, and NO tractography:
 * every job here writes under that subject, so give it a disposable one.
 *   TIT_E2E_CHAIN_SUBJECT=<id>                  the subject
 *   TIT_E2E_CHAIN_NET=EEG10-10_Cutini_2011      its leadfield's net
 *   TIT_E2E_CHAIN_SHOTS=<dir>                   screenshots and chain-results.json
 * Numbers are read from the server and written to chain-results.json, not pinned: the subject is not
 * committed. Whether the tractogram and mask match a reference is the operator's comparison.
 *
 * Run: lockf /tmp/tit-e2e.lock env TIT_E2E_OFFSCREEN=1 TIT_E2E_SERVER_URL=... TIT_E2E_TOKEN=... \
 *   TIT_E2E_CHAIN_SUBJECT=... npx playwright test --project=real tests/e2e/real/network-chain.spec.ts
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { answerExistingOutputs, connectReal, expectPage, getServerPanels, gotoPage, launchElectronApp, selectSubject, setServerPanels, waitForJobTerminal } from "../_helpers";
import { addOptRow, clearOptRows, closeOptEditor, openOptEditor, setOptCell, setOptSubject } from "../_jobs";
import { createAndSelectMontage, deleteMontage } from "./_simMontage";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_CHAIN_SUBJECT;
const NET = process.env.TIT_E2E_CHAIN_NET ?? "EEG10-10_Cutini_2011";
const SHOTS = process.env.TIT_E2E_CHAIN_SHOTS ?? join(tmpdir(), "tit-chain-shots");
const RUN = "chain_posterior";
const SIMULATION = "chain_posterior_sim";
const POOL = ["CPz", "Pz", "F7", "F8", "CP1", "CP2", "P7", "P8"];
const JOB_TIMEOUT = 2_400_000;

test.skip(!SUBJECT, "skipping: TIT_E2E_CHAIN_SUBJECT names no disposable subject with QSIPrep output and no tractography");
test.describe.configure({ mode: "serial" });

let app: ElectronApplication;
let page: Page;
let panelsAsFound: string[] = [];
let results: Record<string, unknown> = {};
const record = (key: string, value: unknown): void => {
  results[key] = value;
  writeFileSync(join(SHOTS, "chain-results.json"), JSON.stringify(results, null, 1));
};
const shot = (name: string) => page.screenshot({ path: join(SHOTS, `${name}.png`) });
const runSearch = () => page.getByRole("button", { name: "Run search", exact: true });
const field = (label: string, root: Locator) => root.locator(".field", { hasText: label }).first();

async function server<T>(path: string): Promise<T> {
  const response = await fetch(`${SERVER_URL}${path}`, { headers: { authorization: `Bearer ${TOKEN}` } });
  expect(response.status, path).toBe(200);
  return (await response.json()) as T;
}

async function groupJobId(run: () => Promise<void>): Promise<string> {
  const response = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  await run();
  const r = await response;
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { jobs: { id: string }[] }).jobs[0]!.id;
}

async function succeeded(id: string, timeoutMs = JOB_TIMEOUT): Promise<void> {
  const status = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: id, timeoutMs, pollMs: 5_000 });
  expect(status.state, `job ${id}`).toBe("succeeded");
}

/** The mask of the panel's current choice, replacing any of this name; its record from the server. */
async function createMask(panel: Locator): Promise<{ name: string; path: string; n_streamlines: number; n_voxels: number; n_edges: number }> {
  const created = page.waitForResponse((r) => r.url().endsWith("/api/tract/mask"));
  await panel.getByTestId("network-create-mask").click();
  let response = await created;
  if (response.status() === 409) {
    const replaced = page.waitForResponse((r) => r.url().endsWith("/api/tract/mask"));
    await page.getByRole("alertdialog").getByRole("button", { name: "Replace mask" }).click();
    response = await replaced;
  }
  expect(response.status(), await response.text()).toBe(201);
  await expect(panel).toHaveAttribute("data-state", "S4");
  return response.json();
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  // A rerun from a later step (-g) keeps what the earlier ones recorded.
  if (existsSync(join(SHOTS, "chain-results.json"))) results = JSON.parse(readFileSync(join(SHOTS, "chain-results.json"), "utf8"));
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "visual-exporter"]);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1600, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  const offer = page.getByRole("dialog").filter({ hasText: "Add example data?" });
  await offer.waitFor({ timeout: 10_000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click()).catch(() => undefined);
});
test.afterAll(async () => {
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound).catch(() => undefined);
  await app?.close();
});

test("1. tractography from scratch, from the Pre-processing row", async () => {
  test.setTimeout(JOB_TIMEOUT);
  const before = await server<{ available: boolean; tractogram_available: boolean }>(`/api/tract/manifest?subject=${SUBJECT}`);
  expect(before.tractogram_available, "the subject starts with no tractogram").toBe(false);
  await selectSubject(page, SUBJECT!);
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
  const row = page.getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first();
  if ((await row.getAttribute("aria-selected")) !== "true") await row.click();
  for (const label of ["Convert DICOM to NIfTI", "SimNIBS charm (m2m + subject atlas)", "FastSurfer segmentation"]) {
    await page.getByRole("checkbox", { name: label }).uncheck();
  }
  await page.getByRole("checkbox", { name: "Tractography" }).check();
  await shot("01_preprocess_tractography");
  const started = Date.now();
  const id = await groupJobId(async () => {
    await page.getByRole("button", { name: "Run preprocessing", exact: true }).click();
    await answerExistingOutputs(page, "skip");
  });
  await succeeded(id);
  const after = await server<{ available: boolean; n_streamlines: number; n_edges: number; qc_passed: boolean }>(`/api/tract/manifest?subject=${SUBJECT}`);
  expect(after.available).toBe(true);
  record("tractography", { job: id, minutes: (Date.now() - started) / 60_000, n_streamlines: after.n_streamlines, n_edges: after.n_edges, qc_passed: after.qc_passed });
});

test("2. the posterior preset gives a mask with and without opposite-hemisphere connections, then an ex-search", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await gotoPage(page, "optimizer", "Optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, SUBJECT!);
  await setOptCell(page, row, "method", "Ex");
  const netCell = row.locator('td[data-cell="net"]').getByRole("combobox");
  await netCell.click();
  await page.getByRole("option", { name: new RegExp(`${NET} · `) }).click();
  const dialog = await openOptEditor(page, row);
  await field("Run name", dialog).getByRole("textbox").fill(RUN);
  await dialog.getByRole("radio", { name: "Network", exact: true }).click();
  const panel = dialog.getByTestId("network-panel");
  await panel.getByRole("radio", { name: "Preset", exact: true }).click();
  await panel.getByTestId("network-presets").getByRole("option", { name: /Posterior thalamocortical/ }).click();
  await shot("02_optimizer_preset_same_side");
  const count = panel.getByTestId("network-count");
  const sameSideCount = Number(await count.getAttribute("data-streamlines"));
  const removedLine = await panel.getByTestId("network-removed").textContent();

  const threshold = field("Voxel density threshold", panel).locator("input");
  await threshold.fill("2");
  await threshold.blur();

  await panel.getByRole("checkbox", { name: "Include opposite-hemisphere connections" }).click();
  await expect(panel.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical_with_opposite");
  const withOppositeCount = Number(await count.getAttribute("data-streamlines"));
  await shot("03_optimizer_preset_with_opposite");
  const withOpposite = await createMask(panel);
  record("mask_with_opposite", { count: withOppositeCount, ...withOpposite, pairs: undefined });

  await panel.getByRole("checkbox", { name: "Include opposite-hemisphere connections" }).click();
  await expect(panel.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical");
  const sameSide = await createMask(panel);
  record("mask_same_side", { count: sameSideCount, removed: removedLine, ...sameSide, pairs: undefined });
  expect(sameSide.n_streamlines).toBe(sameSideCount);
  expect(withOpposite.n_streamlines).toBe(withOppositeCount);
  await shot("04_optimizer_mask_same_side");

  await dialog.getByRole("radio", { name: "All combinations", exact: true }).click();
  await field("Electrode pool", dialog).getByRole("combobox").click();
  const list = page.getByRole("dialog").filter({ hasText: /choose electrodes|Electrode pool/i }).last();
  for (const electrode of POOL) {
    await list.getByPlaceholder(/Filter/).fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
  }
  await list.getByRole("button", { name: "Done" }).click();
  await closeOptEditor(page);
  await expect(runSearch()).toBeEnabled({ timeout: 60_000 });
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const id = await groupJobId(() => runSearch().click());
  const config = (await request).postDataJSON().subject_configs[0].config;
  expect(String(config.roi_atlas[0].atlas_path)).toContain("masks/tract-posterior_thalamocortical.nii.gz");
  const started = Date.now();
  await succeeded(id);
  record("ex_search", { job: id, minutes: (Date.now() - started) / 60_000, pool: POOL });
});

test("3. Results ranks every montage of the run on the same-side network", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await gotoPage(page, "results", "Results");
  await page.getByTestId(`results-subject-${SUBJECT}`).click();
  await page.locator(`[data-testid="results-node-ex:${SUBJECT}:${RUN}"]`).click();
  const ranking = page.getByTestId("network-ranking");
  await expect(ranking).toBeVisible();
  await expect(() => ranking.scrollIntoViewIfNeeded({ timeout: 5_000 })).toPass({ timeout: 30_000 });
  await expect(ranking.getByRole("combobox", { name: "Network mask" })).toContainText("posterior_thalamocortical");
  const scope = ranking.getByRole("combobox", { name: "Montages to rank" });
  await expect(scope).toHaveText(/All montages in the run \(\d[\d,]*, (about \d+ min|under a minute)\)/);
  const allLabel = await scope.textContent();
  await ranking.getByRole("combobox", { name: "Network mask" }).click();
  await page.getByRole("option", { name: /^posterior_thalamocortical · / }).click();
  await shot("05_ranking_options");
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  const id = await groupJobId(() => ranking.getByTestId("network-rank").click());
  expect((await request).postDataJSON().config.target.top_n).toBeNull();
  const started = Date.now();
  await succeeded(id);
  await expect(ranking.getByTestId("network-ranking-table").first()).toBeVisible({ timeout: 60_000 });
  await shot("06_ranking_result");
  const body = await server<{ rankings: { name: string; montages: { montage: string[]; rank_by_ti_along: number; median_sl_mean_ti_along: number; median_sl_mean_ti_max: number }[] }[] }>(`/api/tract/rankings?subject=${SUBJECT}&ex_run=${RUN}`);
  const own = body.rankings.find((r) => r.name === "posterior_thalamocortical")!;
  const first = own.montages.find((m) => m.rank_by_ti_along === 1)!;
  record("ranking", { job: id, minutes: (Date.now() - started) / 60_000, all_label: allLabel, n_montages: own.montages.length, first });
});

test("4. the ranking's first montage is simulated from the Simulator", async () => {
  test.setTimeout(JOB_TIMEOUT);
  const body = await server<{ rankings: { name: string; montages: { montage: string[]; rank_by_ti_along: number }[] }[] }>(`/api/tract/rankings?subject=${SUBJECT}&ex_run=${RUN}`);
  const [a, b, c, d] = body.rankings.find((r) => r.name === "posterior_thalamocortical")!.montages.find((m) => m.rank_by_ti_along === 1)!.montage as [string, string, string, string];
  await selectSubject(page, SUBJECT!);
  await gotoPage(page, "simulator", "Simulator");
  await createAndSelectMontage(page, { subject: SUBJECT!, net: `${NET}.csv`, name: SIMULATION, pairs: [[a, b], [c, d]] });
  // Every run page stays mounted, so the button is named rather than found by test id.
  const run = page.getByRole("button", { name: "Run simulation", exact: true });
  await expect(run).toBeEnabled({ timeout: 30_000 });
  await shot("07_simulator");
  const started = Date.now();
  const id = await groupJobId(() => run.click());
  await succeeded(id);
  record("simulation", { job: id, minutes: (Date.now() - started) / 60_000, electrodes: [a, b, c, d] });
  // The montage list is the project's, shared with every subject: leave it as found.
  await deleteMontage(page, SIMULATION).catch(() => undefined);
});

async function openNetworksTab(): Promise<void> {
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await expectPage(page, "panel-visual-exporter");
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: SUBJECT!, exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: SIMULATION, exact: true }).click();
}

/** Run, which queues an assess job when the network is not assessed; both job ids, assess first. */
async function runExport(): Promise<string[]> {
  const ids: string[] = [];
  const onResponse = async (r: import("@playwright/test").Response) => {
    if (r.url().endsWith("/api/jobs") && r.request().method() === "POST" && r.status() < 300) ids.push(((await r.json()) as { id: string }).id);
  };
  page.on("response", onResponse);
  await page.getByRole("button", { name: "Run export", exact: true }).click();
  await expect.poll(() => ids.length, { timeout: 30_000 }).toBeGreaterThan(0);
  await page.waitForTimeout(3_000);
  page.off("response", onResponse);
  return ids;
}

test("5. the Networks tab assesses and renders the chosen network, and its figure reaches the gallery", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await openNetworksTab();
  await page.getByTestId("network-presets").getByRole("option", { name: /Posterior thalamocortical/ }).click();
  await expect(page.getByTestId("network-mask-name")).toHaveCount(0);
  await page.locator("#ve-network-metric").click();
  await page.getByRole("option", { name: "TI_max", exact: true }).click();
  await page.getByTestId("network-advanced").locator("summary").click();
  await expect(page.getByTestId("network-setup-removed")).toContainText("opposite-hemisphere removed", { timeout: 30_000 });
  await page.waitForFunction(() => (window.__scene?.lines?.streamlines ?? 0) > 0, null, { timeout: 120_000 }).catch(() => undefined);
  await shot("08_networks_preset_plan_pane");
  const started = Date.now();
  const ids = await runExport();
  expect(ids, "an assess job, then a render that waits for it").toHaveLength(2);
  await shot("09_networks_running");
  for (const id of ids) await succeeded(id);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const renders = page.getByTestId("network-renders");
  const still = renders.getByRole("img", { name: /^Posterior thalamocortical · .*, TI_max$/ });
  await expect(still).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => still.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1600);
  await shot("10_networks_gallery");
  record("render", { jobs: ids, minutes: (Date.now() - started) / 60_000 });
});

test("6. another network renders beside the first, and each way of choosing is on screen", async () => {
  test.setTimeout(JOB_TIMEOUT);
  await page.getByTestId("network-presets").getByRole("option", { name: /Frontal thalamocortical/ }).click();
  // Setup is still open from the last step: its side, set by hand.
  await page.locator("#ve-setup-side").click();
  await page.getByRole("option", { name: "Right" }).click();
  await shot("11_networks_advanced");
  const ids = await runExport();
  for (const id of ids) await succeeded(id);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const renders = page.getByTestId("network-renders");
  await expect(renders.getByRole("img", { name: /^Frontal thalamocortical · .*, TI_max$/ })).toBeVisible({ timeout: 30_000 });
  await renders.locator("details", { hasText: "Posterior thalamocortical" }).locator("> summary").click();
  await expect(renders.getByRole("img", { name: /^Posterior thalamocortical · .*, TI_max$/ })).toBeVisible();
  await shot("12_two_networks_in_gallery");
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
  const body = await server<{ networks: string[]; has_edges: boolean; assessed: { name: string; n_streamlines: number }[] }>(`/api/catalog/simulations/${SIMULATION}/networks?subject=${SUBJECT}`);
  record("second_network", { jobs: ids, assessed: body.assessed, networks: body.networks });
  expect(body.assessed.map((a) => a.name).sort()).toEqual(["frontal_thalamocortical", "posterior_thalamocortical"]);

  await page.getByRole("radio", { name: "By region" }).click();
  await shot("13_by_region");
  await page.getByRole("radio", { name: "By connection" }).click();
  await shot("14_by_connection");
  await page.getByRole("radio", { name: "Strongest here" }).click();
  await page.locator("#network-metric").click();
  await page.getByRole("option", { name: "Median TI_max (V/m)" }).click();
  await page.waitForFunction(() => (window.__scene?.lines?.streamlines ?? 0) > 0, null, { timeout: 60_000 });
  await shot("15_strongest_here");
  await page.getByRole("radio", { name: "Your own file" }).click();
  await expect(page.getByTestId("ve-own-load")).toBeVisible();
  await shot("16_your_own_file");
});
