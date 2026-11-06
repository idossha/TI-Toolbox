/**
 * A network's figure through the app, on a simulation of a subject with tractography: one thalamocortical
 * preset with a .blend, one network chosen by connection and one bilateral preset, each in TI_max and fibre
 * direction, then the same colour again, which replaces only itself. Each job's peak memory and time go to
 * `figures-results.json` beside the screenshots; whether the pictures hold only the model and its fibres is
 * judged by eye from the copies the spec leaves there.
 *
 *   TIT_E2E_FIGURES_SUBJECT=CHN TIT_E2E_FIGURES_SIMULATION=left_insula_mean TIT_E2E_PROJECT_HOST=<project> \
 *   TIT_E2E_FIGURES_SHOTS=<dir> TIT_E2E_SERVER_URL=... TIT_E2E_TOKEN=... TIT_E2E_OFFSCREEN=1 \
 *     bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/network-figures.spec.ts
 *
 * It assesses and renders networks into the simulation's own folders, with names this spec owns, and
 * renders at Fast preview. The numbers are read back from network.json, not pinned: the subject is not
 * committed. An eighth optional render, TIT_E2E_FIGURES_LARGEST_SIMULATION, draws the largest preset for
 * the job's memory claim.
 */
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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
  blend: { file: string; colour: string; bytes: number } | null;
  metrics: {
    streamlines_total: number;
    median_ti_max_v_per_m: number;
    opposite_hemisphere_removed: { n_removed: number } | null;
    images: Record<string, { panels: string[]; streamlines_drawn: number; sampling: string; lateral_side: string; colour_scale: { range: number[] }; colour_key: { red: string } }>;
  };
}

function folder(simulation: string, network: string): string {
  return join(PROJECT!, "derivatives", "ti-toolbox", "visual_exports", `sub-${SUBJECT}`, simulation, "networks", network);
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

/** Run with what the form holds, answering Replace if asked, and wait for every job it queues. */
async function run(key: string, replace = false): Promise<void> {
  const ids: string[] = [];
  const onResponse = async (r: import("@playwright/test").Response) => {
    if (r.url().endsWith("/api/jobs") && r.request().method() === "POST" && r.status() < 300) ids.push(((await r.json()) as { id: string }).id);
  };
  page.on("response", onResponse);
  await expect(page.getByTestId("run-button")).not.toHaveAttribute("title", /.+/, { timeout: 60_000 });
  await page.getByTestId("run-button").click();
  if (replace) await page.getByTestId("existing-outputs-replace").click();
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
}

async function colour(name: "TI_max" | "Fibre direction (RGB)"): Promise<void> {
  await page.locator("#ve-network-metric").click();
  await page.getByRole("option", { name, exact: true }).click();
}

/** Render in both colours and check the sidecar, the gallery and that the folder holds one image per colour. */
async function renderBoth(simulation: string, network: string, firstWithBlend = false): Promise<NetworkRecord> {
  const out = folder(simulation, network);
  await colour("TI_max");
  // Run answers from the Plan, which follows the form after a debounce: wait for this network's.
  await expect(page.locator(".extension-plan-line summary")).toContainText(network, { timeout: 30_000 });
  const blend = page.getByRole("checkbox", { name: "Export .blend" });
  if (firstWithBlend) {
    await blend.click();
    await expect(page.getByTestId("ve-planned-files")).toContainText(/network\.blend \(about \d+ MB/, { timeout: 30_000 });
  }
  await page.screenshot({ path: join(SHOTS, `plan_${network}.png`) });
  await run(`${network}/ti_max`);
  if (firstWithBlend) await blend.click();
  await colour("Fibre direction (RGB)");
  await expect(page.getByTestId("ve-planned-files")).toHaveText("Writes: direction.png", { timeout: 30_000 });
  await run(`${network}/direction`);

  const record = JSON.parse(readFileSync(join(out, "network.json"), "utf-8")) as NetworkRecord;
  for (const [file, label] of [["ti_max.png", "TI_max"], ["direction.png", "Fibre direction"]] as const) {
    expect(existsSync(join(out, file)), file).toBe(true);
    copyFileSync(join(out, file), join(SHOTS, `${network}_${file}`));
    expect(record.metrics.images[file]!.panels).toEqual(["lateral", "superior", "anterior", "posterior"]);
    await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
    const figure = page.getByTestId("network-renders").getByRole("img", { name: `${network}, ${label}`, exact: true });
    await expect(figure).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => figure.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1600);
    await page.getByRole("radio", { name: "Scene", exact: true }).click();
  }
  expect(record.metrics.images["ti_max.png"]!.colour_scale.range[1]!).toBeGreaterThan(0);
  expect(record.metrics.images["direction.png"]!.colour_key.red).toBe("left – right");
  expect(record.metrics.median_ti_max_v_per_m).toBeGreaterThan(0);
  results[`${network}/metrics`] = { total: record.metrics.streamlines_total, drawn: record.metrics.images["ti_max.png"]!.streamlines_drawn, blend: record.blend };
  return record;
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
  await expect(page.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical");
  const record = await renderBoth(SIMULATION!, "posterior_thalamocortical", true);
  expect(record.metrics.opposite_hemisphere_removed!.n_removed).toBeGreaterThan(0);
  expect(record.blend).toMatchObject({ file: "network.blend", colour: "ti_max" });
  const out = folder(SIMULATION!, "posterior_thalamocortical");
  expect(statSync(join(out, "network.blend")).size).toBe(record.blend!.bytes);
  expect(existsSync(join(out, "bundle_ti_max"))).toBe(false);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  await expect(page.getByTestId("network-renders").getByRole("link", { name: "network.blend" })).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "gallery_posterior_thalamocortical.png") });
  await page.getByRole("radio", { name: "Scene", exact: true }).click();
});

test("a network chosen by connection, under a new name, and the same colour again replaces only itself", async () => {
  test.setTimeout(3 * JOB_MINUTES * 60_000);
  await openNetworks(SIMULATION!);
  await page.getByRole("radio", { name: "By connection" }).click();
  await page.getByTestId("network-seeds").click();
  for (const seed of [/^Left-Thalamus-Proper/, /^Right-Thalamus-Proper/]) await page.getByRole("dialog").getByRole("option", { name: seed }).click();
  await page.keyboard.press("Escape");
  for (const parcel of ["rostralmiddlefrontal", "caudalmiddlefrontal", "lateralorbitofrontal", "medialorbitofrontal"]) {
    await page.getByTestId("network-edges").getByRole("option", { name: new RegExp(`(Left-Thalamus-Proper.*lh\\.${parcel}|lh\\.${parcel}.*Left-Thalamus-Proper)`) }).click();
  }
  const name = "2_regions_to_4_regions_v3";
  await page.getByTestId("network-mask-name").fill(name);
  await renderBoth(SIMULATION!, name);
  await page.screenshot({ path: join(SHOTS, "plan_setup_after.png") });

  const out = folder(SIMULATION!, name);
  const before = { direction: statSync(join(out, "direction.png")).mtimeMs, ti_max: statSync(join(out, "ti_max.png")).mtimeMs };
  await colour("TI_max");
  await expect(page.getByTestId("ve-replaced-files")).toHaveText("Replaces: ti_max.png. This network's other colours stay.", { timeout: 30_000 });
  await run(`${name}/ti_max_again`, true);
  expect(statSync(join(out, "ti_max.png")).mtimeMs).toBeGreaterThan(before.ti_max);
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
  // A name typed in the last test stays until another is typed.
  await page.getByTestId("network-mask-name").fill("interhemispheric_cortical");
  const record = await renderBoth(SIMULATION!, "interhemispheric_cortical");
  expect(record.metrics.images["ti_max.png"]!.lateral_side).toBe("left");
});

test("the largest preset, for the job's memory claim", async () => {
  test.skip(!LARGEST, "skipping: TIT_E2E_FIGURES_LARGEST_SIMULATION names no simulation with all.trx");
  test.setTimeout(2 * JOB_MINUTES * 60_000);
  await openNetworks(LARGEST!);
  await page.getByRole("radio", { name: "Preset", exact: true }).click();
  await page.getByTestId("network-presets").getByRole("option", { name: /Basal ganglia/ }).click();
  await page.getByTestId("network-mask-name").fill("basal_ganglia_cortical_v3");
  await colour("TI_max");
  await page.getByRole("checkbox", { name: "Export .blend" }).click();
  await run("basal_ganglia_cortical_v3/ti_max");
  const out = folder(LARGEST!, "basal_ganglia_cortical_v3");
  copyFileSync(join(out, "ti_max.png"), join(SHOTS, "basal_ganglia_cortical_v3_ti_max.png"));
  const record = JSON.parse(readFileSync(join(out, "network.json"), "utf-8")) as NetworkRecord;
  expect(record.metrics.images["ti_max.png"]!.sampling).toBe("even sample");
  results["basal_ganglia_cortical_v3/metrics"] = { total: record.metrics.streamlines_total, drawn: record.metrics.images["ti_max.png"]!.streamlines_drawn, blend: record.blend };
  writeFileSync(join(SHOTS, "figures-results.json"), JSON.stringify(results, null, 1));
});
