/**
 * "Your own file" through the real app: a file in another space and an empty one are refused with
 * nothing kept; the same streamlines as a by-connection network, loaded as TCK and as TRX, are
 * assessed, set up and rendered, and match that network's figure and numbers.
 *
 * The files come from `dev/export_own_network_fixture.py`. Its reference is `network-figures.spec.ts`'s
 * `2_regions_to_4_regions_v3`, so run that first:
 *   docker exec -w /ti-toolbox <c> simnibs_python dev/export_own_network_fixture.py /mnt/000 CHN <dir in the container> \
 *     "lh.rostralmiddlefrontal|Left-Thalamus-Proper" "lh.caudalmiddlefrontal|Left-Thalamus-Proper" \
 *     "lh.lateralorbitofrontal|Left-Thalamus-Proper" "lh.medialorbitofrontal|Left-Thalamus-Proper"
 *   TIT_E2E_OWN_FILES=<the same dir on the host> TIT_E2E_OWN_SUBJECT=CHN TIT_E2E_OWN_SIMULATION=left_insula_mean \
 *   TIT_E2E_PROJECT_HOST=<project> TIT_E2E_OWN_SHOTS=<dir> ... npx playwright test --project=real tests/e2e/real/network-own-file.spec.ts
 *
 * What it writes under the subject (`tractography/own/`, `tract/own_*`, `networks/own_*`) it removes;
 * the figures and sidecars stay as copies in the shots folder.
 */
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, getServerPanels, setServerPanels, waitForJobTerminal } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const FILES = process.env.TIT_E2E_OWN_FILES;
const SUBJECT = process.env.TIT_E2E_OWN_SUBJECT;
const SIMULATION = process.env.TIT_E2E_OWN_SIMULATION;
const PROJECT = process.env.TIT_E2E_PROJECT_HOST;
const SHOTS = process.env.TIT_E2E_OWN_SHOTS ?? join(tmpdir(), "tit-own-shots");
const REFERENCE = "2_regions_to_4_regions_v3";

test.skip(!FILES || !SUBJECT || !SIMULATION || !PROJECT, "skipping: TIT_E2E_OWN_FILES, _SUBJECT, _SIMULATION and TIT_E2E_PROJECT_HOST name no files or simulation");
test.describe.configure({ mode: "serial" });

let app: ElectronApplication;
let page: Page;
let panelsAsFound: string[] = [];

const derivatives = () => join(PROJECT!, "derivatives");
const networks = () => join(derivatives(), "ti-toolbox", "visual_exports", `sub-${SUBJECT}`, SIMULATION!, "networks");
const simTract = () => join(derivatives(), "SimNIBS", `sub-${SUBJECT}`, "Simulations", SIMULATION!, "tract");
const ownFolder = () => join(derivatives(), "SimNIBS", `sub-${SUBJECT}`, "tractography", "own");

function removeWhatThisSpecWrites(): void {
  rmSync(ownFolder(), { recursive: true, force: true });
  for (const name of ["own_spec_tck", "own_spec_trx"]) {
    rmSync(join(networks(), `own_${name}`), { recursive: true, force: true });
    rmSync(join(simTract(), `own_${name}`), { recursive: true, force: true });
  }
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  removeWhatThisSpecWrites();
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "visual-exporter"]);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1600, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  const offer = page.getByRole("dialog", { name: "Add example data?" });
  await offer.waitFor({ timeout: 8000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: SUBJECT!, exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: SIMULATION!, exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
  await page.getByRole("radio", { name: "Your own file" }).click();
});

test.afterAll(async () => {
  removeWhatThisSpecWrites();
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound);
  await app?.close();
});

async function load(name: string): Promise<void> {
  await page.getByTestId("ve-own-input").setInputFiles(join(FILES!, name));
}

/** Largest and mean per-channel difference of two PNGs, through the window's own image decoder. */
async function difference(a: string, b: string): Promise<{ max: number; mean: number; width: number }> {
  return page.evaluate(async ([one, two]) => {
    const pixels = async (base64: string) => {
      const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
      const image = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
      const canvas = new OffscreenCanvas(image.width, image.height);
      const context = canvas.getContext("2d")!;
      context.drawImage(image, 0, 0);
      return { data: context.getImageData(0, 0, image.width, image.height).data, width: image.width };
    };
    const [x, y] = [await pixels(one!), await pixels(two!)];
    let max = 0;
    let sum = 0;
    for (let i = 0; i < x.data.length; i += 1) {
      const d = Math.abs(x.data[i]! - y.data[i]!);
      max = Math.max(max, d);
      sum += d;
    }
    return { max: max / 255, mean: sum / x.data.length / 255, width: x.width };
  }, [readFileSync(a).toString("base64"), readFileSync(b).toString("base64")]);
}

test("a file in another space and an empty one are refused, with nothing kept", async () => {
  test.setTimeout(300_000);
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Load a file, or choose one already loaded.");
  await load("own_spec_shifted.tck");
  const error = page.getByTestId("ve-own-error");
  await expect(error).toContainText("Only 0.0% of this file's points fall inside this head model's brain", { timeout: 120_000 });
  await expect(error).toContainText("not transformed");
  await page.screenshot({ path: join(SHOTS, "own_file_refused_wrong_space.png") });
  await load("own_spec_empty.tck");
  await expect(error).toContainText("holds no streamlines", { timeout: 120_000 });
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Load a file, or choose one already loaded.");
  const body = await (await fetch(`${SERVER_URL}/api/tract/own?subject=${SUBJECT}`, { headers: { authorization: `Bearer ${TOKEN}` } })).json();
  expect(body.networks).toEqual([]);
});

for (const [file, stored] of [["own_spec_tck.tck", "own_spec_tck"], ["own_spec_trx.trx", "own_spec_trx"]] as const) {
  test(`${file} is checked, assessed and rendered, and matches the same streamlines chosen by connection`, async () => {
    test.setTimeout(30 * 60_000);
    await load(file);
    const checks = page.getByTestId("ve-own-checks");
    await expect(checks).toContainText("552 streamlines", { timeout: 180_000 });
    await expect(checks).toContainText("0 left unlabelled");
    await expect(checks).toContainText("cannot prove");
    await page.locator("#ve-network-metric").click();
    await page.getByRole("option", { name: "TI_max", exact: true }).click();
    // The reference lights what it was chosen by; a file has no seeds, so the same one is named here.
    if (!(await page.getByTestId("ve-setup-lit").isVisible())) await page.getByTestId("network-advanced").locator("summary").click();
    if (stored === "own_spec_tck") {
      await page.getByTestId("ve-setup-lit").click();
      await page.getByRole("dialog").getByRole("option", { name: /^Left-Thalamus-Proper/ }).click();
      await page.keyboard.press("Escape");
    }
    // Two jobs: the assess, and the render that waits for it.
    await expect(page.getByTestId("extension-plan-line")).toContainText(new RegExp(`2 jobs .*${stored} .*replaces nothing`), { timeout: 60_000 });
    await expect(page.getByTestId("ve-assess-first")).toBeAttached();
    await page.screenshot({ path: join(SHOTS, `own_file_plan_${stored}.png`) });
    const ids: string[] = [];
    const onResponse = async (r: import("@playwright/test").Response) => {
      if (r.url().endsWith("/api/jobs") && r.request().method() === "POST" && r.status() < 300) ids.push(((await r.json()) as { id: string }).id);
    };
    page.on("response", onResponse);
    await page.getByTestId("run-button").click();
    await expect.poll(() => ids.length, { timeout: 30_000 }).toBe(2);
    page.off("response", onResponse);
    for (const id of ids) {
      const job = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: id, timeoutMs: 25 * 60_000, pollMs: 10_000 });
      expect(job.state, `job ${id}`).toBe("succeeded");
    }
    const folder = join(networks(), `own_${stored}`);
    const own = JSON.parse(readFileSync(join(folder, "network.json"), "utf-8"));
    const reference = JSON.parse(readFileSync(join(networks(), REFERENCE, "network.json"), "utf-8"));
    copyFileSync(join(folder, "ti_max.png"), join(SHOTS, `own_${stored}_ti_max.png`));
    copyFileSync(join(folder, "network.json"), join(SHOTS, `own_${stored}_network.json`));
    expect(own.metrics.source.source_filename).toBe(file);
    expect(own.metrics.source.checks.fraction_points_in_brain).toBeGreaterThanOrEqual(0.95);
    expect(own.metrics.source.n_unlabelled).toBe(0);
    expect(own.metrics.streamlines_total).toBe(reference.metrics.streamlines_total);
    expect(own.metrics.streamlines_per_region).toEqual(reference.metrics.streamlines_per_region);
    for (const key of ["median_ti_max_v_per_m", "median_ti_along_v_per_m", "median_align_index"]) {
      expect(Math.abs(own.metrics[key] - reference.metrics[key]), key).toBeLessThanOrEqual(0.001);
    }
    const seen = await difference(join(folder, "ti_max.png"), join(networks(), REFERENCE, "ti_max.png"));
    console.log(`${stored} against ${REFERENCE}: ${JSON.stringify(seen)}`);
    expect(seen.width).toBe(1600);
    expect(seen.mean, "the same streamlines, the same picture").toBeLessThan(0.002);
    await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
    await expect(page.getByTestId("network-renders").getByRole("img", { name: `own_${stored}, TI_max`, exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: join(SHOTS, `own_file_gallery_${stored}.png`) });
    await page.getByRole("radio", { name: "Scene", exact: true }).click();
  });
}
