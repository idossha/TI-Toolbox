/** Real renderer, synthetic geometry, real host controls. No scientific job is submitted. */
import { chromium, expect, test, type Frame, type Page } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { gotoPage, launchElectronApp, selectSubject } from "./_helpers";

const SERVER = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const REAL_EMBED = process.env.TIT_MOCK_EMBED_DIR;

// A closed octahedron in scanner RAS. The two surfaces differ only in radius; their centre is
// strictly inside both, and has no labels/markers. Transparent surfaces must reveal background.
function octahedron(radius: number): string {
  const vertices = [[radius, 0, 0], [-radius, 0, 0], [0, radius, 0], [0, -radius, 0], [0, 0, radius], [0, 0, -radius]];
  const triangles = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]];
  const array = (intent: string, type: string, rows: number[][]): string =>
    `<DataArray Intent="${intent}" DataType="${type}" ArrayIndexingOrder="RowMajorOrder" Dimensionality="2" Dim0="${rows.length}" Dim1="3" Encoding="ASCII" Endian="LittleEndian"><Data>${rows.flat().join(" ")}</Data></DataArray>`;
  return `<?xml version="1.0"?><GIFTI Version="1.0" NumberOfDataArrays="2"><MetaData/><LabelTable/>${array("NIFTI_INTENT_POINTSET", "NIFTI_TYPE_FLOAT32", vertices)}${array("NIFTI_INTENT_TRIANGLE", "NIFTI_TYPE_INT32", triangles)}</GIFTI>`;
}

async function inspectScene(frame: Frame) {
  return frame.evaluate(() => {
    const engine = (window as unknown as { __tetravox?: { engine?: {
      scene: { view3d: { id: string; camera: unknown }; layers: { name: string; opacity: number }[]; background: number[] };
      caps: { renderer: string; isSoftware: boolean };
      readPixel: (id: string, x: number, y: number) => Uint8Array;
    } } }).__tetravox?.engine;
    const canvas = document.querySelector<HTMLCanvasElement>('[data-testid="engine-canvas"]');
    if (!engine || !canvas) throw new Error("The actual Tetravox engine is not ready");
    const box = canvas.getBoundingClientRect();
    return {
      camera: engine.scene.view3d.camera,
      layers: engine.scene.layers.map(({ name, opacity }) => ({ name, opacity })),
      background: engine.scene.background.slice(0, 3).map((value) => Math.round(value * 255)),
      pixel: Array.from(engine.readPixel(engine.scene.view3d.id, Math.floor(box.width / 2), Math.floor(box.height / 2))).slice(0, 3),
      width: box.width,
      height: box.height,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      renderer: engine.caps.renderer,
      isSoftware: engine.caps.isSoftware,
    };
  });
}

async function displayedPixel(page: Page, x: number, y: number): Promise<number[]> {
  const png = await page.screenshot({ animations: "disabled", scale: "css" });
  return page.evaluate(async ({ data, x, y }) => {
    const bitmap = new Image();
    bitmap.src = `data:image/png;base64,${data}`;
    await bitmap.decode();
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Screenshot decoder is unavailable");
    ctx.drawImage(bitmap, 0, 0);
    return Array.from(ctx.getImageData(x, y, 1, 1).data).slice(0, 3);
  }, { data: png.toString("base64"), x: Math.round(x), y: Math.round(y) });
}

for (const renderer of ["swiftshader", "platform"] as const) {
  // Playwright requires destructuring for testInfo access; Electron owns this test's page.
  // eslint-disable-next-line no-empty-pattern
  test(`viewport opacity and tab continuity with the real ${renderer} renderer`, async ({}, testInfo) => {
    test.skip(!REAL_EMBED, "Set TIT_MOCK_EMBED_DIR to a built Tetravox viewport bundle; the fake embed cannot prove rendering.");
    test.skip(TOKEN !== "mock-token", "Synthetic route substitutions run only against the isolated mock server.");
    // Match the installed/baked layout: generated manifest and index beside one another.
    // A raw Vite dist has no manifest, and an unpacked release keeps index one level below it.
    const manifest = JSON.parse(await readFile(join(REAL_EMBED!, "manifest.json"), "utf8"));
    expect(manifest.name).toBe("@tetravox/embed");
    expect(manifest.protocol).toBeGreaterThanOrEqual(2);
    await readFile(join(REAL_EMBED!, "index.html"));
    const installed = await fetch(`${SERVER}/api/tetravox/install`, {
      method: "POST",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ version: "0.4.0" }),
    });
    if (!installed.ok) throw new Error(`Mock protocol-2 activation failed: ${installed.status}`);
    // No pixel goldens: sRGB fixes color management, and each leg proves its actual renderer.
    const args = ["--force-color-profile=srgb", ...(renderer === "swiftshader" ? ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : [])];
    // This macOS Electron distribution has no software WebGL2 context. Exercise the same built
    // web renderer in hidden Chromium/SwiftShader, and the native shell on the actual platform GPU.
    const app = renderer === "platform" ? await launchElectronApp({ args }) : null;
    const browser = renderer === "swiftshader" ? await chromium.launch({ headless: true, args }) : null;
    const page = app ? await app.firstWindow() : await browser!.newPage();
    const errors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    try {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.route("**/api/scene/manifest?*", async (route) => {
        const response = await route.fetch();
        const manifest = await response.json();
        await route.fulfill({ json: { ...manifest, bbox: [-60, -60, -60, 60, 60, 60], focus_bbox: [-60, -60, -60, 60, 60, 60], nets: [], atlases: [] } });
      });
      await page.route("**/api/scene/surface?*", async (route) => {
        const radius = new URL(route.request().url()).searchParams.get("part") === "skin" ? 60 : 45;
        await route.fulfill({ contentType: "application/gifti+xml", body: octahedron(radius) });
      });
      if (app) {
        await page.fill("#server-url", SERVER);
        await page.fill("#token", TOKEN);
        await page.click("#connect");
      } else {
        await page.goto(`${SERVER}/auth/session?token=${encodeURIComponent(TOKEN)}`);
      }
      await expect(page.getByTestId("nav-rail")).toBeVisible();
      await page.evaluate(() => {
        const host = window as unknown as { __renderMessages: unknown[] };
        host.__renderMessages = [];
        window.addEventListener("message", (event) => {
          if (["ready", "status", "error", "loaded"].includes(event.data?.type)) {
            host.__renderMessages.push(event.data);
          }
        });
      });
      await selectSubject(page, "ernie");
      await gotoPage(page, "simulator");
      const panel = page.locator('[data-page-panel="simulator"]');
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
      const iframe = panel.getByTestId("scene-pane-tetravox-frame");
      const element = await iframe.elementHandle();
      const frame = await element?.contentFrame();
      if (!frame) throw new Error("No scene browsing context");
      await expect(frame.getByTestId("toolbar")).toHaveCount(0);
      await expect(frame.locator('[data-testid="layers-panel"], [data-testid="info-panel"], [data-testid="status-bar"]')).toHaveCount(0);
      const initial = await inspectScene(frame);
      expect(initial.isSoftware).toBe(renderer === "swiftshader");
      expect(initial.width).toBe(initial.viewport.width);
      expect(initial.height).toBe(initial.viewport.height);
      expect(initial.pixel).not.toEqual(initial.background);

      const camera = initial.camera;
      await panel.getByRole("spinbutton", { name: "Skin opacity value" }).fill("0");
      await panel.getByRole("spinbutton", { name: "Grey matter opacity value" }).fill("0");
      await expect.poll(async () => (await inspectScene(frame)).layers.filter((layer) => ["Skin", "Grey matter"].includes(layer.name)).map((layer) => layer.opacity)).toEqual([0, 0]);
      const transparent = await inspectScene(frame);
      transparent.pixel.forEach((channel, index) => expect(Math.abs(channel - transparent.background[index]!)).toBeLessThanOrEqual(2));
      expect(transparent.camera).toEqual(camera);

      await panel.getByRole("spinbutton", { name: "Skin opacity value" }).fill("35");
      await panel.getByRole("spinbutton", { name: "Grey matter opacity value" }).fill("80");
      await expect.poll(async () => (await inspectScene(frame)).layers.filter((layer) => ["Skin", "Grey matter"].includes(layer.name)).map((layer) => layer.opacity)).toEqual([0.8, 0.35]);
      const before = await inspectScene(frame);
      const box = await iframe.boundingBox();
      if (!box) throw new Error("No visible preview bounds");
      const beforePixel = await displayedPixel(page, box.x + box.width / 2, box.y + box.height / 2);
      await gotoPage(page, "preprocess");
      await gotoPage(page, "analyzer");
      await gotoPage(page, "simulator");
      await expect(iframe).toBeVisible();
      expect(page.frames()).toContain(frame);
      // Read the compositor before any engine call: forcing a repaint here would hide a blank-tab bug.
      const afterPixel = await displayedPixel(page, box.x + box.width / 2, box.y + box.height / 2);
      afterPixel.forEach((channel, index) => expect(Math.abs(channel - beforePixel[index]!)).toBeLessThanOrEqual(2));
      const after = await inspectScene(frame);
      expect(after.camera).toEqual(before.camera);
      expect(after.layers).toEqual(before.layers);
      expect(errors).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`scene-${renderer}.png`), animations: "disabled" });
      const evidence = testInfo.outputPath("renderer-evidence.json");
      await writeFile(evidence, JSON.stringify({ initial, transparent, before, after, beforePixel, afterPixel }, null, 2));
      await testInfo.attach("renderer-evidence", { path: evidence, contentType: "application/json" });
    } finally {
      try {
        const diagnostics = testInfo.outputPath("embed-diagnostics.json");
        await mkdir(dirname(diagnostics), { recursive: true });
        await writeFile(diagnostics, JSON.stringify({ errors, consoleErrors, messages: await page.evaluate(() => (window as unknown as { __renderMessages: unknown[] }).__renderMessages) }, null, 2));
        await testInfo.attach("embed-diagnostics", { path: diagnostics, contentType: "application/json" });
      } finally {
        await app?.close();
        await browser?.close();
      }
    }
  });
}
