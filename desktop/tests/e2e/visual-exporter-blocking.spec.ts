import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import { connectLauncher, expectPage, launchElectronApp } from "./_helpers";

/**
 * The 3D Visual Exporter blocks a montage export of a simulation placed by coordinates (mock
 * server, offscreen; 2026-10-22).
 *
 * A free-hand / flex_free simulation records `eeg_net: null` in its documentation/config.json
 * (Dataset 000 `sub-101/20260919_131736_879_1`). `tit.blender.montage_publication` refuses it with
 * "This simulation has no recorded EEG net." and so does the server's preflight; the panel used
 * to let Run queue the job anyway. Here, in the packaged app: Run in montage mode carries that
 * sentence as its reason, a click shows it and sends nothing to `POST /api/jobs`, and the same
 * simulation still exports cortical regions (which read no net).
 *
 * The mock serves one Dataset 000 net-montage config for every simulation, so this spec answers
 * the one `GET /api/files/text` for ernie/L_Insula's config.json with the Dataset 000 XYZ record's
 * keys (typed out below) — the shared mock and its fixtures stay unchanged.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const PANELS = ["source", "visual-exporter"];
const NO_NET = "This simulation has no recorded EEG net.";
const XYZ_RECORD = {
  subject_id: "ernie",
  simulation_name: "L_Insula",
  simulation_mode: "TI",
  montage_mode: "flex_free",
  eeg_net: null,
  conductivity: "scalar",
  electrode_pairs: [
    [
      [72.1, 10.5, -19.1],
      [75.6, 0.9, -24.3],
    ],
    [
      [-80.0, 19.2, -78.6],
      [-77.3, 30.0, -73.3],
    ],
  ],
  is_xyz_montage: true,
};

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.afterEach(async () => {
  await app?.close();
});

async function launch(): Promise<void> {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-veb-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  // The rail gates a panel on the server's settings.panels; the mock's seed has not this one.
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: { telemetry: { consented: true, enabled: false }, panels: PANELS, image_tag: "idossha/simnibs:v2.3.1", theme: "system" },
    });
  });
  await page.route("**/api/files/text?**", (route) => {
    const path = new URL(route.request().url()).searchParams.get("path") ?? "";
    if (!path.endsWith("/sub-ernie/Simulations/L_Insula/documentation/config.json")) return route.continue();
    return route.fulfill({ status: 200, contentType: "text/plain", body: JSON.stringify(XYZ_RECORD) });
  });
  await page.addInitScript((p: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(p));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, PANELS);
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("link", { name: "3D visual exporter", exact: true }).click();
  await expectPage(page, "panel-visual-exporter");
}

async function choose(simulation: string): Promise<void> {
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: simulation, exact: true }).click();
}

test("a montage of a simulation placed by coordinates is refused with the runner's sentence", async () => {
  await launch();
  const jobPosts: Request[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/jobs") jobPosts.push(r);
  });
  await choose("L_Insula");
  await page.getByRole("radio", { name: "Montage visualizer" }).click();

  const run = page.getByTestId("run-button");
  // The record is read once the simulation is chosen; the gate follows the answer.
  await expect(run).toHaveAttribute("title", NO_NET, { timeout: 20_000 });
  await run.click();
  // The click is answered (a toast with the same sentence) and nothing was submitted.
  await expect(page.getByText(NO_NET, { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  expect(jobPosts).toHaveLength(0);

  // Regions read no net: the same simulation exports them.
  await page.getByRole("radio", { name: "Cortical regions" }).click();
  await expect(run).not.toHaveAttribute("title", NO_NET);
  const request = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/jobs" && r.method() === "POST");
  await run.click();
  const job = (await request).postDataJSON() as { kind: string; config: Record<string, unknown> };
  expect(job.kind).toBe("blender");
  expect(job.config).toMatchObject({ _type: "RegionConfig", subject_id: "ernie", simulation_name: "L_Insula" });
});

test("a montage of a simulation that recorded its net still runs", async () => {
  await launch();
  await choose("Thalamus");
  await page.getByRole("radio", { name: "Montage visualizer" }).click();
  const run = page.getByTestId("run-button");
  // The plan answers once validate/plan have run on the config, i.e. after the record was read.
  await expect(page.getByText(/visual_exports\/sub-ernie\/montage_publication/)).toBeVisible({ timeout: 20_000 });
  await expect(run).not.toHaveAttribute("title", NO_NET);
  const request = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/jobs" && r.method() === "POST");
  await run.click();
  const job = (await request).postDataJSON() as { config: Record<string, unknown> };
  expect(job.config).toMatchObject({ _type: "MontageConfig", subject_id: "ernie", simulation_name: "Thalamus" });
});
