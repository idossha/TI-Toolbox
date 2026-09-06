/** Real catalog/surfaces and the installed renderer; navigation and draft edits, never a job. */
import { expect, test, type Frame } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

async function viewState(frame: Frame) {
  return frame.evaluate(() => {
    const engine = (window as unknown as { __tetravox?: { engine?: {
      scene: { view3d: { camera: unknown }; layers: { name: string; opacity: number }[] };
    } } }).__tetravox?.engine;
    if (!engine) throw new Error("The installed renderer has no live engine");
    return {
      camera: engine.scene.view3d.camera,
      surfaces: engine.scene.layers.filter((layer) => layer.name === "Skin" || layer.name === "Grey matter" || layer.name.startsWith("TI pane atlas · ")),
    };
  });
}

test("all three workflow previews retain the real subject's camera and opacity", async () => {
  test.setTimeout(180_000); // Three cold surface/atlas loads, no compute pipeline is submitted.
  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1280, height: 900 });
    await connectReal(page);
    await selectSubject(page, process.env.TIT_E2E_SUBJECT ?? "ernie");
    for (const id of ["simulator", "optimizer", "analyzer"] as const) {
      await gotoPage(page, id);
      const panel = page.locator(`[data-page-panel="${id}"]`);
      await expect(panel).toBeVisible();
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 45_000 });
      const iframe = panel.getByTestId("scene-pane-tetravox-frame");
      await expect(iframe).toHaveAttribute("src", /presentation=viewport/);
      const original = await iframe.elementHandle();
      const frame = await original?.contentFrame();
      if (!frame || !original) throw new Error(`${id}: no live preview frame`);
      await expect(frame.getByTestId("toolbar")).toHaveCount(0);
      const box = await iframe.boundingBox();
      if (!box) throw new Error(`${id}: no preview bounds`);
      const initial = await viewState(frame);
      expect(initial.surfaces, id).toHaveLength(2);
      // Engine input/gestures.ts binds right-drag to pan in every 3D mode. A primary press
      // intentionally places an ROI in Analyzer's sphere mode, so it is not an orbit there.
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down({ button: "right" });
      await page.mouse.move(box.x + box.width / 2 + 55, box.y + box.height / 2 + 25, { steps: 8 });
      await page.mouse.up({ button: "right" });
      await expect.poll(async () => (await viewState(frame)).camera).not.toEqual(initial.camera);
      await panel.getByRole("spinbutton", { name: "Skin opacity value" }).fill("35");
      await panel.getByRole("spinbutton", { name: "Grey matter opacity value" }).fill("80");
      await expect.poll(async () => (await viewState(frame)).surfaces.map((layer) => layer.opacity)).toEqual([0.8, 0.35]);
      const before = await viewState(frame);
      await gotoPage(page, "preprocess");
      await gotoPage(page, id);
      await expect(panel).toBeVisible();
      expect(await original.evaluate((node) => node.isConnected)).toBe(true);
      expect(page.frames()).toContain(frame);
      expect(await viewState(frame)).toEqual(before);
      console.log(`REAL-PREVIEW ${id}: two surfaces, changed camera, skin=35%, grey matter=80%, same iframe/camera/layers after return`);
      await original.dispose();
    }
  } finally {
    await app.close();
  }
});
