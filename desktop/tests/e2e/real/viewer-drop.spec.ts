import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp } from "../_helpers";

let app: ElectronApplication;

test.afterEach(async () => {
  await app?.close();
});

test("empty Tetravox accepts a dropped NIfTI and retains it through Menu navigation", async () => {
  // A real embed needs time to initialize wasm before it can import a dropped volume.
  test.setTimeout(90_000);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-drop-")) });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1500, height: 900 });
  await connectReal(page, {
    url: process.env.TIT_E2E_SERVER_URL as string,
    token: process.env.TIT_E2E_TOKEN as string,
  });
  await gotoPage(page, "viewer", "Viewer");
  await page.getByTestId("nav-subitem-viewer-tetravox").click();
  await expect(page.getByTestId("viewer-empty")).toHaveCount(0);
  const frame = page.getByTestId("tetravox-frame");
  const embed = page.frameLocator('[data-testid="tetravox-frame"]');
  await expect(frame).toBeVisible();
  await expect(embed.getByTestId("shell")).toBeVisible({ timeout: 60_000 });
  await expect(embed.getByTestId("toolbar")).toBeVisible();
  await expect(embed.getByTestId("layer-panel-empty")).toBeVisible();
  await expect(embed.getByTestId("engine-canvas")).toBeVisible();

  // A synthetic browser File exercises the real drop handler and NIfTI decoder, without a
  // desktop file dialog or modifying the connected research project. It is not an OS drag test.
  await embed.getByTestId("shell").evaluate((shell) => {
    const bytes = new Uint8Array(352 + 64);
    const header = new DataView(bytes.buffer);
    header.setInt32(0, 348, true);
    [3, 4, 4, 4, 1, 1, 1, 1].forEach((value, index) => header.setInt16(40 + index * 2, value, true));
    header.setInt16(70, 2, true); // uint8
    header.setInt16(72, 8, true);
    for (let index = 0; index < 8; index += 1) header.setFloat32(76 + index * 4, 1, true);
    header.setFloat32(108, 352, true);
    header.setFloat32(112, 1, true);
    bytes.set([110, 43, 49, 0], 344); // NIfTI-1 single-file magic: n+1\0
    for (let index = 0; index < 64; index += 1) bytes[352 + index] = index + 1;
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File([bytes], "empty-viewer-drop.nii", { type: "application/octet-stream" }));
    shell.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer }));
  });

  // A filename in a load card is only pending work. A layer row exists after the decoder has
  // committed the volume into the scene; the empty panel must disappear as well.
  const layer = embed.locator('[data-testid^="layer-row-"]').filter({ hasText: "empty-viewer-drop.nii" });
  await expect(layer).toBeVisible({ timeout: 60_000 });
  await expect(embed.getByTestId("layer-panel-empty")).toHaveCount(0);
  await frame.evaluate((node) => node.setAttribute("data-e2e-identity", "dropped-volume"));
  await page.getByTestId("nav-subitem-viewer-menu").click();
  await expect(frame).toBeHidden();
  await page.getByTestId("nav-subitem-viewer-tetravox").click();
  await expect(frame).toHaveAttribute("data-e2e-identity", "dropped-volume");
  await expect(layer).toBeVisible();
});
