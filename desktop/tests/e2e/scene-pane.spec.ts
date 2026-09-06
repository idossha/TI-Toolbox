/**
 * Run-page scene pane integration against the protocol-2 fake Tetravox embed.
 *
 * The old `renderer/scene/**` tests asserted pixels from TI's local WebGL canvas. This file pins the
 * replacement seam: run panes mount an iframe, the pane exposes the form-owned debug state, and a
 * protocol-2 point pick writes back to the Simulator montage editor.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab } from "./_runPane";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const NET = "GSN-HydroCel-185";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const installed = await fetch(`${SERVER_URL}/api/tetravox/install`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ version: "0.4.0" }),
  });
  if (!installed.ok) throw new Error(`mock could not activate protocol 2: HTTP ${installed.status}`);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-scene-pane-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  // The net is the montage table's first column now (no standalone "EEG net" selector): setting
  // it on a row is also what tells the scene pane which net's electrodes to draw.
  await page.locator("tr[data-montage-row]").first().getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: NET, exact: true }).click();
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

test("mounts the embedded Tetravox scene and exposes form-owned state", async () => {
  await expectRunPaneTab(page, "scene");
  await expect(page.getByTestId("scene-pane-host")).toHaveAttribute("data-renderer", "tetravox");
  await expect(page.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(page.getByTestId("scene-pane-tetravox-frame")).toBeVisible();
  await expect(page.getByTestId("scene-canvas")).toHaveCount(0);

  const debug = await page.evaluate(() => {
    const handle = window.__scenePane;
    if (!handle) throw new Error("window.__scenePane is absent — build out/ with VITE_SCENE_HOOKS=1");
    return JSON.parse(JSON.stringify(handle)) as { mode: string; gesture: string; markers: number; parts: { id: string }[]; firstPaintMs: number | null };
  });
  expect(debug).toMatchObject({ mode: "montage", gesture: "electrode", markers: 185 });
  expect(debug.parts.map((part) => part.id).sort()).toEqual(["gm", "skin"]);
  expect(debug.firstPaintMs).not.toBeNull();

  const fake = page.frameLocator('[data-testid="scene-pane-tetravox-frame"]');
  await expect(fake.getByTestId("fake-embed-layers").locator("li")).toHaveText(["Grey matter", "Skin", "TI pane points"]);
});

test("a protocol-2 point pick starts a montage draft in the form", async () => {
  const fake = page.frameLocator('[data-testid="scene-pane-tetravox-frame"]');
  await fake.locator("body").dispatchEvent("click", { bubbles: true });
  await expect(page.locator(".electrode-pair-row").first().getByRole("combobox").first()).toContainText("E1", { timeout: 10_000 });

  const debug = await page.evaluate(() => window.__scenePane?.selection.markers ?? []);
  expect(debug).toEqual([0]);
});

test("surface opacity reaches the live layers and survives other workflow tabs", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  const frameElement = simulator.getByTestId("scene-pane-tetravox-frame");
  await expect(frameElement).toHaveAttribute("src", /presentation=viewport/);
  const originalFrame = await frameElement.elementHandle();
  if (!originalFrame) throw new Error("Simulator frame is missing");

  await simulator.getByRole("spinbutton", { name: "Skin opacity value" }).fill("35");
  await simulator.getByRole("spinbutton", { name: "Grey matter opacity value" }).fill("80");
  const fake = frameElement.contentFrame();
  await expect(fake.locator('[data-layer-id="layer-skin"]')).toHaveAttribute("data-opacity", "0.35");
  await expect(fake.locator('[data-layer-id="layer-gm"]')).toHaveAttribute("data-opacity", "0.8");

  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
  await expect(simulator).toBeHidden();
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  expect(await originalFrame.evaluate((node) => node === document.querySelector('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]'))).toBe(true);
  await expect(simulator.getByRole("slider", { name: "Skin opacity", exact: true })).toHaveAttribute("aria-valuenow", "35");
  await expect(simulator.getByRole("slider", { name: "Grey matter opacity", exact: true })).toHaveAttribute("aria-valuenow", "80");
  await expect(fake.locator('[data-layer-id="layer-skin"]')).toHaveAttribute("data-opacity", "0.35");
  await expect(fake.locator('[data-layer-id="layer-gm"]')).toHaveAttribute("data-opacity", "0.8");
  await originalFrame.dispose();
});

test("a renderer failure stays readable until explicit retry", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  const frameElement = simulator.getByTestId("scene-pane-tetravox-frame");
  const original = await frameElement.elementHandle();
  const frame = await original?.contentFrame();
  if (!frame || !original) throw new Error("Simulator frame is missing");
  await frame.evaluate(() => window.parent.postMessage({ tvx: 1, type: "error", message: "Synthetic mesh load failed" }, window.location.origin));
  await expect(simulator.getByTestId("scene-pane-message")).toHaveText("Synthetic mesh load failed");
  await gotoPage(page, "analyzer");
  await gotoPage(page, "simulator");
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "error");
  expect(await original.evaluate((node) => node.isConnected)).toBe(true);
  await simulator.getByRole("button", { name: "Retry 3D preview" }).click();
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  expect(await original.evaluate((node) => node.isConnected)).toBe(false);
  await expect(frameElement.contentFrame().locator('[data-layer-id="layer-skin"]')).toHaveAttribute("data-opacity", "0.35");
  await expect(frameElement.contentFrame().locator('[data-layer-id="layer-gm"]')).toHaveAttribute("data-opacity", "0.8");
  await original.dispose();
});

/* ------------------------------------------------------------------------------------------------
 * Electrodes as coloured dots (plan `v3-tetravox-selection-pipeline-plan.md` §1-B, B1-B5).
 *
 * These run against the fake embed, which has no renderer — so what they check is not pixels but
 * the payload: the fake mirrors the last `setPoints` into `#points`, one row per point, carrying
 * the state and colour the HOST sent. The pixels are checked against the real bundle in
 * `tests/e2e/real/embed-electrodes.spec.ts`.
 * ---------------------------------------------------------------------------------------------- */

/** The colour the pane must draw pair `channel` in, as the fixture reports it. */
function channelRgb(channel: number): string {
  const OKABE_ITO = [
    [0.0, 0.447, 0.698],
    [0.902, 0.624, 0.0],
    [0.0, 0.62, 0.451],
    [0.8, 0.475, 0.655],
  ];
  const rgb = OKABE_ITO[channel % OKABE_ITO.length] as number[];
  return `rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})`;
}
const IDLE_RGB = "rgb(158,166,179)"; // SCENE_PALETTE.idle

function pointRow(page: Page, id: string) {
  return page
    .locator('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]')
    .contentFrame()
    .locator(`#points li[data-point-id="${id}"]`);
}

test("the pane never sends a point tool or a point selection — there is no selection ring", async () => {
  const frame = page.locator('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]').contentFrame();
  // The fixture records every host message it has received since it booted, which includes the
  // load, the picks of the earlier tests and every points sync. `setPointSelection` is the message
  // that draws the ring; `setPointTool` is the one that would let the embed write to the layer.
  const sent = (await frame.locator("body").getAttribute("data-host-messages")) ?? "";
  expect(sent.split(",")).toContain("setPoints");
  expect(sent.split(",")).not.toContain("setPointSelection");
  expect(sent.split(",")).not.toContain("setPointTool");
});

test("a pick on an idle dot fills the active slot and repaints exactly that dot in the pair's colour", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  // Test 2 left pair 1 slot A filled by a body-click pick; the cursor is therefore on slot B.
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-active-channel", "0");

  const target = "E9";
  await expect(pointRow(page, target)).toHaveAttribute("data-state", "idle");
  await expect(pointRow(page, target)).toHaveAttribute("data-color", IDLE_RGB);
  // An idle dot carries no name, which is how "names for the selected only" is expressed: the
  // embed skips a point whose `name` is absent when it builds the label list.
  await expect(pointRow(page, target)).toHaveAttribute("data-name", "");

  await pointRow(page, target).click();

  // The FORM is the source of truth, and it moved first.
  await expect(simulator.locator(".electrode-pair-row").first().getByRole("combobox").nth(1)).toContainText(target);
  // …and the next `setPoints` marks exactly that id selected, in pair 1's colour.
  await expect(pointRow(page, target)).toHaveAttribute("data-state", "selected");
  await expect(pointRow(page, target)).toHaveAttribute("data-color", channelRgb(0));
  await expect(pointRow(page, target)).toHaveAttribute("data-name", target);
  const selected = await page
    .locator('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]')
    .contentFrame()
    .locator('#points li[data-state="selected"]')
    .evaluateAll((rows) => rows.map((r) => (r as HTMLElement).dataset.pointId));
  expect(selected.sort()).toEqual(["E1", target].sort());
});

test("a pick on a selected dot removes it and puts the grey back", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  await pointRow(page, "E9").click();
  await expect(pointRow(page, "E9")).toHaveAttribute("data-state", "idle");
  await expect(pointRow(page, "E9")).toHaveAttribute("data-color", IDLE_RGB);
  await expect(pointRow(page, "E9")).toHaveAttribute("data-name", "");
  // The slot it vacated is where the cursor parked, so the same click twice is an undo.
  await expect(simulator.locator(".electrode-pair-row").first().getByRole("combobox").nth(1)).not.toContainText("E9");
});

test("two pairs are two hues, and a legend chip decides which pair the next click fills", async () => {
  const simulator = page.locator('[data-page-panel="simulator"]');
  // The draft the Simulator opens already has more than one pair; what matters is that the legend
  // has exactly one chip per pair, whatever that number is.
  const chips = simulator.getByTestId("channel-legend").locator(".channel-chip");
  const before = await chips.count();
  await simulator.getByRole("button", { name: "Add pair" }).first().click();
  await expect(chips).toHaveCount(before + 1);
  await expect(simulator.locator(".electrode-pair-row")).toHaveCount(before + 1);

  // The chip is the control: clicking it makes pair 2 the active one without touching the form.
  await simulator.getByTestId("channel-chip-1").click();
  await expect(simulator.getByTestId("scene-pane-host")).toHaveAttribute("data-active-channel", "1");
  await expect(simulator.getByTestId("channel-chip-1")).toHaveAttribute("data-active", "true");
  await expect(simulator.getByTestId("channel-chip-0")).toHaveAttribute("data-active", "false");

  await pointRow(page, "E20").click();
  await expect(simulator.locator(".electrode-pair-row").nth(1).getByRole("combobox").first()).toContainText("E20");

  // Two channels, two different hues — neither of them the idle grey. This is the property a
  // 4-pair mTI montage is unreadable without.
  await expect(pointRow(page, "E1")).toHaveAttribute("data-color", channelRgb(0));
  await expect(pointRow(page, "E20")).toHaveAttribute("data-color", channelRgb(1));
  expect(channelRgb(0)).not.toBe(channelRgb(1));

  // And the legend agrees with the scene about which hue is which pair.
  await expect(simulator.getByTestId("channel-chip-0")).toHaveAttribute("data-color", channelRgb(0));
  await expect(simulator.getByTestId("channel-chip-1")).toHaveAttribute("data-color", channelRgb(1));

  // The active channel's dots are the ones marked larger (inert in embed 0.4.0, sent regardless —
  // see the lane note); nothing in pair 1 is.
  await expect(pointRow(page, "E20")).toHaveAttribute("data-radius-px", "7");
  await expect(pointRow(page, "E1")).toHaveAttribute("data-radius-px", "");

  // Still no ring, after everything above.
  const sent = (await page.locator('[data-page-panel="simulator"] [data-testid="scene-pane-tetravox-frame"]').contentFrame().locator("body").getAttribute("data-host-messages")) ?? "";
  expect(sent.split(",")).not.toContain("setPointSelection");
  expect(sent.split(",")).not.toContain("setPointTool");
});
