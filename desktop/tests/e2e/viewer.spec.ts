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
test("Viewer opens one scene and keeps the composer visible", async () => {
  await expect(page.getByTestId("viewer-open")).toBeEnabled();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/view/open") &&
      r.request().postDataJSON()?.dry_run !== true,
  );
  await page.getByTestId("viewer-open").click();
  const written = await (await response).json();
  await expect(page.getByTestId("native-tetravox")).toBeVisible();
  await expect(page.getByTestId("viewer-open")).toBeVisible();
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
  await expect(page.getByTestId("viewer-view-error")).toContainText("Native launch refused for test");
  await page.getByTestId("viewer-open").click();
  await expect(page.getByTestId("viewer-view-error")).toContainText("Native launch refused for test");
  await page.getByTestId("viewer-open").click();
  await expect(page.getByTestId("viewer-view-error")).toHaveCount(0);
  await expect(page.getByTestId("viewer-open")).toBeVisible();
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

test("Viewer is one page with visible saved scenes and an empty native launch", async () => {
  await expect(page.getByRole("link", { name: "Menu", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("viewer-saved-scenes-section")).toBeVisible();
  await page.getByRole("button", { name: "Launch TetraVox", exact: true }).click();
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { nativePaths: string[] }).nativePaths)).toEqual([""]);
  await expect(page.getByTestId("viewer-open")).toBeVisible();
});

test("Viewer panels contain a large scene library without scrolling the page", async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/api/viewer/scenes", async (route) => {
    await route.fulfill({ json: { scenes: Array.from({ length: 50 }, (_, i) => ({
      name: `Saved scene ${i}`, slug: `bounded-${i}`, path: `/mnt/example/code/ti-toolbox/viewer/scenes/bounded-${i}.tetravox.json`,
      health: i === 0 ? "missing" : "valid", missing_count: i === 0 ? 2 : 0,
      health_message: i === 0 ? "2 referenced files are missing." : "All referenced files are available.",
    })) } });
  });
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  const library = page.getByTestId("viewer-saved-scenes-scroll");
  await expect(page.getByTestId("viewer-saved-scene-bounded-0")).toBeVisible();
  await expect(library).toContainText(/missing/i);
  const builder = page.getByTestId("viewer-builder-scroll");
  for (const size of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }, { width: 1024, height: 768 }]) {
    await page.setViewportSize(size);
    const left = await builder.boundingBox();
    const right = await library.boundingBox();
    expect(left).not.toBeNull(); expect(right).not.toBeNull();
    expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
    expect(right!.y + right!.height).toBeLessThanOrEqual(size.height);
    expect(await library.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    expect(await page.locator(".viewer-scroll").evaluate((el) => el.scrollHeight - el.clientHeight)).toBeLessThanOrEqual(1);
  }
  await page.screenshot({ path: test.info().outputPath("viewer-bounded-panels.png") });
  await library.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(page.getByTestId("viewer-saved-scene-bounded-49")).toBeVisible();
  await expect(page.getByTestId("viewer-open")).toBeVisible();
  await expect(page.getByRole("button", { name: "Launch TetraVox", exact: true })).toBeVisible();
});

test("scene deletion supports cancel, reports errors, and retries", async () => {
  const name = `delete-scene-${Date.now()}`;
  await page.evaluate(async (name) => {
    const response = await fetch(`/api/viewer/scenes/${name}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene: { version: 2, datasets: [{ id: "t1", kind: "volume", path: "/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz" }], layers: [{ id: "t1-layer", datasetId: "t1", kind: "volume" }] } }),
    });
    if (!response.ok) throw new Error("Could not seed saved scene");
  }, name);
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  let attempts = 0;
  await page.route(`**/api/viewer/scenes/${name}`, async (route) => {
    if (route.request().method() === "DELETE" && ++attempts === 1) {
      await route.fulfill({ status: 500, json: { detail: "Scene file is locked" } });
    } else await route.continue();
  });
  const row = page.getByTestId(`viewer-saved-scene-${name}`);
  await expect(row).toBeVisible();
  await page.getByTestId(`viewer-delete-scene-${name}`).click();
  await page.getByRole("group", { name: `Delete ${name}`, exact: true }).getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(row).toBeVisible();
  expect(attempts).toBe(0);
  await page.getByTestId(`viewer-delete-scene-${name}`).click();
  await page.getByTestId(`viewer-confirm-delete-${name}`).click();
  await expect(page.getByTestId("viewer-saved-scenes-section")).toContainText("Scene file is locked");
  await expect(row).toBeVisible();
  await page.getByTestId(`viewer-confirm-delete-${name}`).click();
  await expect(row).toHaveCount(0);
  expect(attempts).toBe(2);
});
