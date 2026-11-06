import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, getServerPanels, gotoPage, launchElectronApp, setServerPanels, waitForJobTerminal } from "../_helpers";

/**
 * The Visual exporter's Networks tab against a real server: from the tab, a low-resolution figure and
 * then a short turntable render in the image's Blender, and both appear in the gallery.
 *
 * Needs a simulation with `all.trx`, so a preset needs no assess; it is opt-in:
 *   TIT_E2E_NETWORKS_SUBJECT=CHN TIT_E2E_NETWORKS_SIMULATION=posterior_along \
 *   TIT_E2E_NETWORKS_SHOTS=<dir> npx playwright test --project=real tests/e2e/real/visual-exporter-networks.spec.ts
 * It renders into new dated folders. Emulated Blender takes tens of minutes for
 * the turntable. What the pictures show is judged by eye from the screenshots.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_NETWORKS_SUBJECT;
const SIMULATION = process.env.TIT_E2E_NETWORKS_SIMULATION;
const SHOTS = process.env.TIT_E2E_NETWORKS_SHOTS ?? join(tmpdir(), "tit-networks-shots");

test.skip(!SUBJECT || !SIMULATION, "skipping: TIT_E2E_NETWORKS_SUBJECT and TIT_E2E_NETWORKS_SIMULATION name no simulation with tract outputs");
test.describe.configure({ mode: "serial" });

let app: ElectronApplication;
let page: Page;
let panelsAsFound: string[] = [];

async function shot(name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

/** Run, confirming the replace dialog if earlier renders exist; returns the accepted job's id. */
async function submit(): Promise<string> {
  const request = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByTestId("run-button").click();
  const first = await request;
  let job = (await first.json()) as { id?: string };
  if (first.status() === 409) {
    const retried = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
    await page.getByRole("button", { name: /Replace/ }).click();
    job = (await (await retried).json()) as { id?: string };
  }
  expect(job.id, "the job was accepted").toBeTruthy();
  return job.id!;
}

/** Run and wait for the job to succeed. */
async function runAndWait(minutes: number): Promise<void> {
  const jobId = await submit();
  const job = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: minutes * 60_000, pollMs: 10_000 });
  expect(job.state, `job ${jobId}`).toBe("succeeded");
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "visual-exporter"]);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1600, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  // A project without the example subjects is offered them on opening.
  const offer = page.getByRole("dialog", { name: "Add example data?" });
  await offer.waitFor({ timeout: 10_000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await expectPage(page, "panel-visual-exporter");
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: SUBJECT!, exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
  await shot("01-networks-no-simulation");
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: SIMULATION!, exact: true }).click();
  await page.getByTestId("network-presets").getByRole("option", { name: /Posterior thalamocortical/ }).click();
});

test.afterAll(async () => {
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound);
  await app?.close();
});

test("one low-resolution figure renders from the tab", async () => {
  test.setTimeout(45 * 60_000);
  await shot("02-networks-still-options");
  await runAndWait(40);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const still = page.getByTestId("network-renders").getByRole("img", { name: /^Posterior thalamocortical · .*, Fibre direction$/ }).first();
  await expect(still).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => still.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1600);
  await shot("03-networks-still-rendered");
});

test("one short turntable renders from the tab and plays", async () => {
  test.setTimeout(3 * 60 * 60_000);
  await page.getByRole("checkbox", { name: /^Figure/ }).click();
  await page.getByRole("checkbox", { name: "Turntable video" }).click();
  await shot("04-networks-turntable-options");
  await runAndWait(170);
  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const video = page.getByTestId("network-renders").locator("video").first();
  await expect(video).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.duration), { timeout: 30_000 }).toBeGreaterThan(1);
  await video.evaluate((v: HTMLVideoElement) => { v.currentTime = 1; });
  await page.waitForTimeout(1_500);
  await shot("05-networks-turntable-rendered");
});
