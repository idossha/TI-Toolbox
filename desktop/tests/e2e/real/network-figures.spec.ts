/**
 * A network's figure through the app, on a simulation of a subject with tractography: one thalamocortical
 * preset with a .blend, one network chosen by connection and one bilateral preset, each one run in TI_max and
 * fibre direction together, then one colour again, in a folder of its own. Each job's peak memory and time go to
 * `figures-results.json` beside the screenshots; whether the pictures hold only the model and its fibres is
 * judged by eye from the copies the spec leaves there.
 *
 *   TIT_E2E_FIGURES_SUBJECT=CHN TIT_E2E_FIGURES_SIMULATION=left_insula_mean TIT_E2E_PROJECT_HOST=<project> \
 *   TIT_E2E_FIGURES_SHOTS=<dir> TIT_E2E_SERVER_URL=... TIT_E2E_TOKEN=... TIT_E2E_OFFSCREEN=1 \
 *     bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/network-figures.spec.ts
 *
 * It assesses networks and renders them into new dated folders of the simulation, and renders at
 * Fast preview. The numbers are read back from network.json, not pinned: the subject is not
 * committed. An eighth optional render, TIT_E2E_FIGURES_LARGEST_SIMULATION, draws the largest preset for
 * the job's memory claim.
 */
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, getServerPanels, gotoPage, launchElectronApp, setServerPanels, waitForJobTerminal } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_FIGURES_SUBJECT;
const SIMULATION = process.env.TIT_E2E_FIGURES_SIMULATION;
const LARGEST = process.env.TIT_E2E_FIGURES_LARGEST_SIMULATION;
const PROJECT = process.env.TIT_E2E_PROJECT_HOST;
const SHOTS = process.env.TIT_E2E_FIGURES_SHOTS ?? join(tmpdir(), "tit-figures-shots");
const JOB_MINUTES = 40;

test.skip(!SUBJECT || !SIMULATION || !PROJECT, "skipping: TIT_E2E_FIGURES_SUBJECT, TIT_E2E_FIGURES_SIMULATION and TIT_E2E_PROJECT_HOST name no simulation of a subject with tractography");
test.describe.configure({ mode: "serial" });

let app: ElectronApplication;
let page: Page;
let panelsAsFound: string[] = [];
const results: Record<string, unknown> = {};

/** What this spec reads of `network.json`. */
interface NetworkRecord {
  colours: Record<string, unknown>;
  blend: { file: string; colour: string; bytes: number } | null;
  metrics: {
    streamlines_total: number;
    median_ti_max_v_per_m: number;
    opposite_hemisphere_removed: { n_removed: number } | null;
    images: Record<string, { panels: string[]; streamlines_drawn: number; sampling: string; lateral_side: string; colour_scale: { range: number[] }; colour_key: { red: string } }>;
  };
}

function networks(simulation: string): string {
  return join(PROJECT!, "derivatives", "ti-toolbox", "visual_exports", `sub-${SUBJECT}`, simulation, "networks");
}

async function openNetworks(simulation: string): Promise<void> {
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await expectPage(page, "panel-visual-exporter");
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: SUBJECT!, exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: simulation, exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
}

/** Run with what the form holds, wait for every job it queues, and return the one new folder it made. */
async function run(key: string, simulation: string): Promise<string> {
  const before = new Set(existsSync(networks(simulation)) ? readdirSync(networks(simulation)) : []);
  const ids: string[] = [];
  const onResponse = async (r: import("@playwright/test").Response) => {
    if (r.url().endsWith("/api/jobs") && r.request().method() === "POST" && r.status() < 300) ids.push(((await r.json()) as { id: string }).id);
  };
  page.on("response", onResponse);
  await expect(page.getByTestId("run-button")).not.toHaveAttribute("title", /.+/, { timeout: 60_000 });
  await page.getByTestId("run-button").click();
  await expect.poll(() => ids.length, { timeout: 30_000 }).toBeGreaterThan(0);
  await page.waitForTimeout(3_000);
  page.off("response", onResponse);
  for (const id of ids) {
    const job = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: id, timeoutMs: JOB_MINUTES * 60_000, pollMs: 10_000 });
    expect(job.state, `job ${id}`).toBe("succeeded");
    const status = JSON.parse(readFileSync(join(PROJECT!, "code", "ti-toolbox", "jobs", id, "status.json"), "utf-8")) as { kind: string; rss_peak: number; started_at: string; finished_at: string };
    results[`${key}/${status.kind}/${id}`] = {
      peak_gb: Number((status.rss_peak / 1e9).toFixed(2)),
      seconds: Math.round((Date.parse(status.finished_at) - Date.parse(status.started_at)) / 1000),
    };
  }
  writeFileSync(join(SHOTS, "figures-results.json"), JSON.stringify(results, null, 1));
  const made = readdirSync(networks(simulation)).filter((name) => !before.has(name));
  expect(made, "a folder of its own").toHaveLength(1);
  expect(made[0]).toMatch(/^\d{8}_\d{6}$/);
  await expect(page.getByTestId("existing-outputs-replace")).toHaveCount(0);
  return join(networks(simulation), made[0]!);
}

async function colours(tiMax: boolean, direction: boolean): Promise<void> {
  await page.getByRole("checkbox", { name: "TI_max", exact: true }).setChecked(tiMax);
  await page.getByRole("checkbox", { name: "Fibre direction (RGB)" }).setChecked(direction);
}

/** One run in both colours: one folder, one sidecar, and both figures in one gallery group. */
async function renderBoth(simulation: string, network: string, firstWithBlend = false): Promise<{ record: NetworkRecord; out: string }> {
  await colours(true, true);
  await expect(page.getByTestId("ve-planned-files")).toContainText("Writes: ti_max.png, direction.png", { timeout: 30_000 });
  await expect(page.getByTestId("extension-plan-line")).toContainText("a new dated folder", { timeout: 30_000 });
  const blend = page.getByRole("checkbox", { name: "Export .blend" });
  if (firstWithBlend) {
    await blend.click();
    await expect(page.getByTestId("ve-planned-files")).toContainText(/network\.blend \(about \d+ MB, the TI_max scene/, { timeout: 30_000 });
  }
  await page.screenshot({ path: join(SHOTS, `plan_${network}.png`) });
  const out = await run(`${network}/both`, simulation);
  if (firstWithBlend) await blend.click();

  const record = JSON.parse(readFileSync(join(out, "network.json"), "utf-8")) as NetworkRecord;
  expect(Object.keys(record.colours).sort()).toEqual(["direction", "ti_max"]);
  for (const file of ["ti_max.png", "direction.png"]) {
    expect(existsSync(join(out, file)), file).toBe(true);
    copyFileSync(join(out, file), join(SHOTS, `${network}_${file}`));
    expect(record.metrics.images[file]!.panels).toEqual(["lateral", "superior", "anterior", "posterior"]);
  }
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const group = page.getByTestId("network-renders").locator(`details[data-network="${basename(out)}"]`);
  await expect(group).toBeVisible({ timeout: 30_000 });
  await expect(group.locator("> summary")).toContainText(/ · \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/);
  await group.evaluate((details: HTMLDetailsElement) => {
    details.open = true;
  });
  await expect(group.getByRole("img")).toHaveCount(2);
  for (const figure of await group.getByRole("img").all()) {
    await expect.poll(() => figure.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1600);
  }
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
  expect(record.metrics.images["ti_max.png"]!.colour_scale.range[1]!).toBeGreaterThan(0);
  expect(record.metrics.images["direction.png"]!.colour_key.red).toBe("left – right");
  expect(record.metrics.median_ti_max_v_per_m).toBeGreaterThan(0);
  results[`${network}/metrics`] = { total: record.metrics.streamlines_total, drawn: record.metrics.images["ti_max.png"]!.streamlines_drawn, blend: record.blend };
  return { record, out };
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "visual-exporter"]);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1600, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  const offer = page.getByRole("dialog", { name: "Add example data?" });
  await offer.waitFor({ timeout: 10_000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
});

test.afterAll(async () => {
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound);
  await app?.close();
});

test("a thalamocortical preset: one figure per colour, its .blend, and what same-side left out", async () => {
  test.setTimeout(3 * JOB_MINUTES * 60_000);
  await openNetworks(SIMULATION!);
  await page.getByTestId("network-presets").getByRole("option", { name: /Posterior thalamocortical/ }).click();
  await expect(page.getByTestId("network-mask-name")).toHaveCount(0);
  const { record, out } = await renderBoth(SIMULATION!, "posterior_thalamocortical", true);
  expect(record.metrics.opposite_hemisphere_removed!.n_removed).toBeGreaterThan(0);
  expect(record.blend).toMatchObject({ file: "network.blend", colour: "ti_max" });
  expect(statSync(join(out, "network.blend")).size).toBe(record.blend!.bytes);
  expect(existsSync(join(out, "bundle_ti_max"))).toBe(false);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  await expect(page.getByTestId("network-renders").getByRole("link", { name: "network.blend" })).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "gallery_posterior_thalamocortical.png") });
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
});

test("a network chosen by connection, and one colour again goes to a new folder and replaces nothing", async () => {
  test.setTimeout(3 * JOB_MINUTES * 60_000);
  await openNetworks(SIMULATION!);
  await page.getByRole("radio", { name: "By connection" }).click();
  await page.getByTestId("network-seeds").click();
  for (const seed of [/^Left-Thalamus-Proper/, /^Right-Thalamus-Proper/]) await page.getByRole("dialog").getByRole("option", { name: seed }).click();
  await page.keyboard.press("Escape");
  for (const parcel of ["rostralmiddlefrontal", "caudalmiddlefrontal", "lateralorbitofrontal", "medialorbitofrontal"]) {
    await page.getByTestId("network-edges").getByRole("option", { name: new RegExp(`(Left-Thalamus-Proper.*lh\\.${parcel}|lh\\.${parcel}.*Left-Thalamus-Proper)`) }).click();
  }
  const name = "by_connection";
  const { out } = await renderBoth(SIMULATION!, name);
  await page.screenshot({ path: join(SHOTS, "plan_setup_after.png") });

  const before = { direction: statSync(join(out, "direction.png")).mtimeMs, ti_max: statSync(join(out, "ti_max.png")).mtimeMs };
  await colours(true, false);
  await expect(page.getByTestId("ve-planned-files")).toHaveText("Writes: ti_max.png", { timeout: 30_000 });
  const again = await run(`${name}/ti_max_again`, SIMULATION!);
  expect(existsSync(join(again, "ti_max.png"))).toBe(true);
  expect(statSync(join(out, "ti_max.png")).mtimeMs).toBe(before.ti_max);
  expect(statSync(join(out, "direction.png")).mtimeMs).toBe(before.direction);
  // An older folder of the same simulation reads in the gallery beside the new ones.
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const renders = page.getByTestId("network-renders");
  await renders.locator('details[data-network="2_regions_to_4_regions"] > summary').click();
  await expect(renders.getByRole("img", { name: "2_regions_to_4_regions, Fibre direction · lateral" })).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "gallery_with_an_older_folder.png") });
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
});

test("a bilateral preset shows the left in its lateral panel", async () => {
  test.setTimeout(3 * JOB_MINUTES * 60_000);
  await openNetworks(SIMULATION!);
  await page.getByRole("radio", { name: "Preset", exact: true }).click();
  await page.getByTestId("network-presets").getByRole("option", { name: /Interhemispheric/ }).click();
  const { record } = await renderBoth(SIMULATION!, "interhemispheric_cortical");
  expect(record.metrics.images["ti_max.png"]!.lateral_side).toBe("left");
});

test("the largest preset, for the job's memory claim", async () => {
  test.skip(!LARGEST, "skipping: TIT_E2E_FIGURES_LARGEST_SIMULATION names no simulation with all.trx");
  test.setTimeout(2 * JOB_MINUTES * 60_000);
  await openNetworks(LARGEST!);
  await page.getByRole("radio", { name: "Preset", exact: true }).click();
  await page.getByTestId("network-presets").getByRole("option", { name: /Basal ganglia/ }).click();
  await colours(true, true);
  await page.getByRole("checkbox", { name: "Export .blend" }).click();
  const out = await run("basal_ganglia_cortical_v3/both", LARGEST!);
  copyFileSync(join(out, "ti_max.png"), join(SHOTS, "basal_ganglia_cortical_v3_ti_max.png"));
  const record = JSON.parse(readFileSync(join(out, "network.json"), "utf-8")) as NetworkRecord;
  expect(record.metrics.images["ti_max.png"]!.sampling).toBe("even sample");
  results["basal_ganglia_cortical_v3/metrics"] = { total: record.metrics.streamlines_total, drawn: record.metrics.images["ti_max.png"]!.streamlines_drawn, blend: record.blend };
  writeFileSync(join(SHOTS, "figures-results.json"), JSON.stringify(results, null, 1));
});
