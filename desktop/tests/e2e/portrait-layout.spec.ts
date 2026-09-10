import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";
import { showRunPaneTab } from "./_runPane";

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-portrait-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectLauncher(page, process.env.TIT_E2E_SERVER_URL!, process.env.TIT_E2E_TOKEN!);
  await expect(page.getByTestId("overview-table")).toBeVisible();
  await gotoPage(page, "optimizer", "Optimizer");
});

test.afterEach(async () => { await app?.close(); });

test("stacked run panes fill the width and give both scene and terminal room", async () => {
  const active = page.locator('[data-page-active="true"]');
  const pane = active.locator('.page-layout-panel[data-pane-kind="run"]');
  const handle = active.getByTestId("inspector-handle");
  // A persisted desktop resize must not constrain the stacked layout.
  await handle.focus();
  await page.keyboard.press("ArrowLeft");
  const desktopWidth = (await pane.boundingBox())!.width;
  await page.setViewportSize({ width: 1040, height: 1716 });
  await expect(handle).toBeHidden();
  for (const tab of ["scene", "terminal"] as const) {
    await showRunPaneTab(page, tab);
    const paneBox = (await pane.boundingBox())!;
    const bodyBox = (await active.locator(".page-layout-body").boundingBox())!;
    const panelBox = (await active.getByTestId(`run-pane-panel-${tab}`).boundingBox())!;
    expect(Math.abs(paneBox.width - bodyBox.width)).toBeLessThan(2);
    expect(paneBox.height).toBeGreaterThan(900);
    expect(panelBox.height).toBeGreaterThan(700);
  }
  await active.getByTestId("pane-collapse").click();
  await expect(pane).toBeHidden();
  const restore = active.locator('.pane-separator[data-pane-mode="collapsed"]');
  await expect(restore).toBeVisible();
  await restore.click();
  await expect(pane).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(handle).toBeVisible();
  expect(Math.abs((await pane.boundingBox())!.width - desktopWidth)).toBeLessThan(2);
});
