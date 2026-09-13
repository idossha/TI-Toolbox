import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  expect,
  test,
  type ElectronApplication,
  type Page,
} from "@playwright/test";
import {
  connectLauncher,
  gotoPage,
  launchElectronApp,
  openPalette,
} from "./_helpers";
let app: ElectronApplication;
let page: Page;
test.beforeEach(async () => {
  app = await launchElectronApp({
    userDataDir: mkdtempSync(join(tmpdir(), "tit-native-viewer-")),
  });
  page = await app.firstWindow();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:status");
    ipcMain.handle("tit:tetravox:status", () => ({
      supported: true,
      installed: true,
      installing: false,
      version: "test",
      directory: "/tmp/tetravox",
    }));
    ipcMain.removeHandler("tit:tetravox:open");
    ipcMain.handle("tit:tetravox:open", (_event, path: string) => {
      (globalThis as unknown as { nativePaths: string[] }).nativePaths ??= [];
      (globalThis as unknown as { nativePaths: string[] }).nativePaths.push(
        path,
      );
      return { ok: true };
    });
  });
  await connectLauncher(
    page,
    process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790",
    process.env.TIT_E2E_TOKEN ?? "mock-token",
  );
  await expect(page.getByTestId("overview-table")).toBeVisible();
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page
    .getByRole("dialog")
    .getByRole("option", { name: /^ernie/ })
    .first()
    .click();
  await gotoPage(page, "viewer", "Viewer");
});
test.afterEach(async () => {
  await app?.close();
});
test("native viewer menu opens one scene through the checked host bridge", async () => {
  await expect(page.getByTestId("viewer-open")).toBeEnabled();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/view/open") &&
      r.request().postDataJSON()?.dry_run !== true,
  );
  await page.getByTestId("viewer-open").click();
  const written = await (await response).json();
  await expect(page.getByTestId("native-tetravox")).toBeVisible();
  await expect(page.locator('[data-page-panel="viewer"] iframe')).toHaveCount(
    0,
  );
  expect(
    await app.evaluate(
      () => (globalThis as unknown as { nativePaths: string[] }).nativePaths,
    ),
  ).toEqual([written.path]);
});
test("editing the source never launches TetraVox", async () => {
  await expect(page.getByTestId("viewer-open")).toBeVisible();
  expect(
    await app.evaluate(
      () =>
        (globalThis as unknown as { nativePaths?: string[] }).nativePaths ?? [],
    ),
  ).toEqual([]);
  await expect(page.locator('[data-page-panel="viewer"] iframe')).toHaveCount(
    0,
  );
});

test("a saved composition restores the selected files", async () => {
  const files = page.getByTestId("viewer-preview-files");
  await expect(files.locator("li").first()).toBeVisible();
  await page.getByTestId("viewer-tree-node-T2_reg.nii.gz").click();
  await expect(files.locator("li")).toHaveCount(2);
  const selected = await files
    .locator("li")
    .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-testid")));
  const name = `native-composition-${Date.now()}`;
  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId("viewer-preset-name").fill(name);
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/viewer/compositions/${name}`) &&
      response.request().method() === "PUT",
  );
  await page.getByTestId("viewer-preset-save").click();
  expect((await saved).ok()).toBe(true);
  await page.keyboard.press("Escape");
  await files.locator('[data-testid^="viewer-file-remove-"]').first().click();
  await expect(files.locator("li")).toHaveCount(selected.length - 1);
  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId(`viewer-preset-${name}`).click();
  await expect
    .poll(() =>
      files
        .locator("li")
        .evaluateAll((rows) =>
          rows.map((row) => row.getAttribute("data-testid")),
        ),
    )
    .toEqual(selected);
  expect(
    await app.evaluate(
      () =>
        (globalThis as unknown as { nativePaths?: string[] }).nativePaths ?? [],
    ),
  ).toEqual([]);
});

test("an old URL-based saved scene is exported without modifying its original", async () => {
  const name = `legacy-native-${Date.now()}`;
  const scene = {
    version: 2,
    datasets: [
      {
        id: "t1",
        kind: "volume",
        path: "/api/files/raw/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
      },
    ],
    layers: [{ id: "t1-layer", datasetId: "t1", kind: "volume" }],
  };
  await page.evaluate(
    async ({ name, scene }) => {
      const response = await fetch(`/api/viewer/scenes/${name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scene }),
      });
      if (!response.ok) throw new Error("Could not seed saved scene");
    },
    { name, scene },
  );
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  await page.getByTestId("viewer-saved-scenes-open").click();
  const exported = page.waitForResponse((response) =>
    response.url().endsWith("/api/view/export"),
  );
  await page.getByTestId(`viewer-saved-scene-${name}`).click();
  const response = await exported;
  expect(response.request().postDataJSON().scene).toEqual(scene);
  const written = await response.json();
  expect(written.scene.datasets[0].path).not.toContain("/api/files/raw");
  await expect
    .poll(() =>
      app.evaluate(
        () =>
          (globalThis as unknown as { nativePaths?: string[] }).nativePaths ??
          [],
      ),
    )
    .toEqual([written.scene_path]);
  const original = await page.evaluate(
    async (name) =>
      (await (await fetch(`/api/viewer/scenes/${name}`)).json()).scene,
    name,
  );
  expect(original).toEqual(scene);
});

test("a refused native launch shows its reason and allows retry", async () => {
  await app.evaluate(({ ipcMain }) => {
    let attempts = 0;
    ipcMain.removeHandler("tit:tetravox:open");
    ipcMain.handle("tit:tetravox:open", () =>
      ++attempts <= 2
        ? { ok: false, reason: "Native launch refused for test" }
        : { ok: true },
    );
  });
  await page.getByTestId("viewer-open").click();
  const panel = page.getByTestId("native-tetravox");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Open scene in TetraVox" }).click();
  await expect(panel.getByRole("alert")).toContainText(
    "Native launch refused for test",
  );
  await panel.getByRole("button", { name: "Open scene in TetraVox" }).click();
  await expect(
    panel.getByRole("button", { name: "Open scene in TetraVox" }),
  ).toBeEnabled();
  await expect(panel.getByRole("alert")).toHaveCount(0);
});

test("missing native installation offers setup without automatic installation", async () => {
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:status");
    ipcMain.handle("tit:tetravox:status", () => ({
      supported: true,
      installed: false,
      installing: false,
      version: null,
      directory: "/tmp/native-test",
    }));
    ipcMain.removeHandler("tit:tetravox:install");
    ipcMain.handle("tit:tetravox:install", () => {
      throw new Error("Unexpected automatic installation");
    });
  });
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  await page.getByTestId("viewer-open").click();
  await expect(
    page
      .getByTestId("native-tetravox")
      .getByRole("button", { name: "Install TetraVox", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByTestId("native-tetravox").getByRole("alert"),
  ).toHaveCount(0);
});
