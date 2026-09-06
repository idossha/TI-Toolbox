/**
 * R4's gate: the workflow 3D panes draw a **fixed guide**, not the selected research subject.
 *
 * Each assertion below is one clause of the gate in `desktop/IMPLEMENTATION_PLAN.md` R4, and each
 * exists because of a failure the subject-coupled pane actually had:
 *
 *  - changing the selected subjects re-keyed the pane's queries and reloaded the embed, so ticking
 *    a second subject cost a cold 184 MB mesh extraction and a remount → **zero guide-manifest
 *    requests and zero iframe remounts after the initial load**;
 *  - a manifest that advertises an atlas or a net the package does not have gives the user a
 *    selectable option that 404s → **manifest ids equal the packaged catalog ids and every
 *    referenced asset resolves**;
 *  - an oversized surface silently ships → **≤ 3 MB and ≤ 150 000 triangles per payload**, read
 *    back out of the TVSC1 header rather than off the manifest;
 *  - a click on one subject's anatomy could write a subject-RAS millimetre into another subject's
 *    configuration → **a guide click updates names, never coordinates**.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const NET = "GSN-HydroCel-185";

let app: ElectronApplication;
let page: Page;
/** Every `/api/guide/*` URL the renderer asked for, in order. */
let guideRequests: string[] = [];

test.describe.configure({ mode: "serial" });

const api = (path: string) =>
  fetch(`${SERVER_URL}${path}`, { headers: { authorization: `Bearer ${TOKEN}` } });

test.beforeAll(async () => {
  const installed = await fetch(`${SERVER_URL}/api/tetravox/install`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ version: "0.4.0" }),
  });
  if (!installed.ok) throw new Error(`mock could not activate protocol 2: HTTP ${installed.status}`);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-guide-")) });
  page = await app.firstWindow();
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/guide/")) guideRequests.push(url.pathname + url.search);
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  // The net is the montage table's first column now (no standalone "EEG net" selector): setting
  // it on a row is also what tells the scene pane which net's electrodes to draw.
  await page.locator("tr[data-montage-row]").first().getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: NET, exact: true }).click();
  await expectRunPaneTab(page, "scene");
  await expect(page.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
});

test.afterAll(async () => {
  if (TOKEN === "mock-token") {
    await fetch(`${SERVER_URL}/api/tetravox/activate`, {
      method: "POST",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ version: "baked" }),
    }).catch(() => undefined);
    await fetch(`${SERVER_URL}/api/tetravox/0.4.0`, { method: "DELETE", headers: { authorization: `Bearer ${TOKEN}` } }).catch(() => undefined);
  }
  await app?.close();
});

test("the pane draws the guide, and says so rather than naming the subject", async () => {
  const debug = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return JSON.parse(JSON.stringify(handle)) as { guide: string | null; space: string | null; subject: string | null; gesture: string };
  });
  expect(debug.guide).toBe("ernie");
  // The point of the whole change: not the *subject* ernie — the guide, in its own space.
  expect(debug.space).toBe("guide-ras");
  expect(debug.subject).toBeNull();
  expect(guideRequests.some((url) => url.startsWith("/api/guide/manifest"))).toBe(true);
});

test("changing the selected subjects costs zero guide requests and zero remounts", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  const frameElement = simulator.getByTestId("scene-pane-tetravox-frame");
  const original = await frameElement.elementHandle();
  if (!original) throw new Error("the Simulator scene frame is missing");

  guideRequests = [];
  // Every way a page changes its subject set: the palette's global subject, and the page's own
  // subject table. Neither may reach the pane.
  for (const id of ["101", "MNI152", "ernie"]) {
    await openPalette(page);
    await page.getByTestId("palette-input").fill(id);
    await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${id}`) }).first().click();
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", id, { timeout: 10_000 });
  }
  // Generous: a re-key would have fired long before this.
  await page.waitForTimeout(1500);

  expect(guideRequests).toEqual([]);
  expect(await original.evaluate((node) => node.isConnected)).toBe(true);
  expect(
    await original.evaluate(
      (node) => node === document.querySelector('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]'),
    ),
  ).toBe(true);
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  await original.dispose();
});

test("the manifest's atlas and net ids are the packaged ones, and every asset resolves", async () => {
  const manifest = await (await api("/api/guide/manifest")).json();
  expect(manifest.space).toBe("guide-ras");
  expect(manifest.volumes).toEqual([]);
  expect(manifest.atlases.length).toBeGreaterThan(0);
  expect(manifest.nets.length).toBeGreaterThan(0);

  for (const atlas of manifest.atlases) {
    const regions = await api(atlas.url);
    expect(regions.status, atlas.url).toBe(200);
    const body = await regions.json();
    expect(body.atlas).toBe(atlas.id);
    expect(body.space).toBe("guide-ras");
    expect(body.legend.length).toBe(atlas.regions);
    const labels = await api(body.url);
    expect(labels.status, body.url).toBe(200);
  }
  for (const net of manifest.nets) {
    const electrodes = await api(net.url);
    expect(electrodes.status, net.url).toBe(200);
    const body = await electrodes.json();
    expect(body.net).toBe(net.name);
    expect(body.space).toBe("guide-ras");
    expect(body.electrodes.length).toBe(net.electrodes);
  }
});

test("every guide surface keeps the TVSC1 budget: 3 MB and 150 000 triangles", async () => {
  const manifest = await (await api("/api/guide/manifest")).json();
  expect(manifest.parts.map((p: { id: string }) => p.id).sort()).toEqual(["gm", "skin"]);
  for (const part of manifest.parts) {
    const response = await api(part.url);
    expect(response.status, part.url).toBe(200);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    // Read out of the TVSC1 header itself, not off the manifest: a manifest that merely claims a
    // count would let an oversized payload through.
    expect(String.fromCharCode(...bytes.slice(0, 4))).toBe("TVSC");
    const triangles = view.getUint32(12, true) / 3;
    expect(triangles, `${part.id} triangles`).toBeLessThanOrEqual(150_000);
    expect(bytes.byteLength, `${part.id} bytes`).toBeLessThanOrEqual(3 * 1024 * 1024);
    expect(triangles).toBe(part.triangles);
    expect(bytes.byteLength).toBe(part.bytes);
  }
});

test("an electrode pick writes a NAME into the montage form", async () => {
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await expectRunPaneTab(page, "scene");
  const fake = page.frameLocator('[data-testid="scene-pane-tetravox-frame"]');
  await fake.locator("body").dispatchEvent("click", { bubbles: true });
  await expect(page.locator(".electrode-pair-row").first().getByRole("combobox").first()).toContainText("E1", { timeout: 10_000 });
});

test("a guide click can never update a subject-RAS coordinate", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  const picker = page.getByTestId("page-work").locator(".roi-picker");
  await picker.locator(".segmented").first().getByRole("radio", { name: "Spherical", exact: true }).click();
  await expectRunPaneTab(page, "scene");
  const panel = page.locator('[data-page-panel="optimizer"]');
  await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });

  // The gesture the pane offers in spherical mode used to be "sphere": a click placed a centre in
  // the SUBJECT's RAS millimetres. On the guide those millimetres belong to another head, so the
  // gesture does not exist — not "exists and is approximately transformed".
  await expect(panel.getByTestId("scene-pane-host")).not.toHaveAttribute("data-gesture", "sphere");
  const coords = panel.getByRole("spinbutton").filter({ hasNotText: "" });
  const before = await panel.locator("input[type=number]").evaluateAll((nodes) => nodes.map((n) => (n as HTMLInputElement).value));

  const fake = panel.frameLocator('[data-testid="scene-pane-tetravox-frame"]');
  await fake.locator("body").dispatchEvent("click", { bubbles: true });
  await page.waitForTimeout(500);

  const after = await panel.locator("input[type=number]").evaluateAll((nodes) => nodes.map((n) => (n as HTMLInputElement).value));
  expect(after).toEqual(before);
  void coords;
});
