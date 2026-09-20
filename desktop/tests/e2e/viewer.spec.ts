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
      supportsSceneSave: true,
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

test("the builder footer only opens the selection; scene saving lives in Saved scenes", async () => {
  await expect(page.getByTestId("viewer-open")).toBeVisible();
  await expect(page.getByTestId("viewer-save-preset")).toHaveCount(0);
  await expect(page.getByTestId("viewer-recent")).toHaveCount(0);
  await expect(page.getByTestId("viewer-saved-scenes-section").getByTestId("viewer-scene-save-open")).toBeVisible();
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

test("a native saved scene reopens at its original path without exporting relative datasets", async () => {
  const name = "native-relative";
  const path = `/mnt/example/code/ti-toolbox/viewer/scenes/${name}.tetravox.json`;
  const scene = { version: 2, datasets: [{ id: "t1", kind: "volume", path: "../../../../derivatives/T1.nii.gz", absPath: "/host/project/derivatives/T1.nii.gz" }, { id: "t2", kind: "volume", path: "../../../../../shared/T2.nii.gz", absPath: "/host/shared/T2.nii.gz" }], layers: [] };
  await page.route("**/api/viewer/scenes", (route) => route.fulfill({ json: { scenes: [{ name, slug: name, path, saved_at: "2026-09-20T00:00:00Z", has_thumbnail: false }] } }));
  await page.route(`**/api/viewer/scenes/${name}`, (route) => route.fulfill({ json: { scene } }));
  const exports: string[] = [];
  page.on("request", (request) => { if (request.url().endsWith("/api/view/export")) exports.push(request.url()); });
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  await page.getByTestId(`viewer-saved-scene-${name}`).click();
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { nativePaths?: string[] }).nativePaths ?? [])).toEqual([path]);
  expect(exports).toEqual([]);
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

test("failed startup installation offers a user-triggered retry", async () => {
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
      .getByRole("button", { name: "Retry setup", exact: true }),
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

// Mock IPC proof of renderer behavior; native snapshot correctness is verified separately.
test("Save scene captures the native scene and refreshes only after its receipt", async () => {
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:saveScene");
    ipcMain.handle("tit:tetravox:saveScene", (_event, name: string) => ({
      ok: true, path: `/mnt/example/code/ti-toolbox/viewer/scenes/${name}.tetravox.json`,
    }));
  });
  const writes: string[] = [];
  page.on("request", (request) => { if (request.method() === "PUT") writes.push(request.url()); });
  await page.getByTestId("viewer-scene-save-open").click();
  await page.getByTestId("viewer-scene-name").fill("live-state");
  const refreshed = page.waitForResponse((response) => response.url().endsWith("/api/viewer/scenes"));
  await page.getByTestId("viewer-scene-save").click();
  await refreshed;
  await expect(page.getByTestId("viewer-scene-saved")).toHaveText("Saved /mnt/example/code/ti-toolbox/viewer/scenes/live-state.tetravox.json");
  expect(writes).toEqual([]);
});

test("unsupported native scene saving stays unavailable", async () => {
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:status");
    ipcMain.handle("tit:tetravox:status", () => ({ supported: true, installed: true, installing: false, version: "test", directory: "/tmp/tetravox", supportsSceneSave: false }));
  });
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  await expect(page.getByTestId("viewer-scene-save-open")).toBeDisabled();
  await expect(page.getByTestId("viewer-saved-scenes-section")).toContainText("native scene-saving support");
});

test("a refused native save reports the reason without claiming or refreshing a save", async () => {
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:saveScene");
    ipcMain.handle("tit:tetravox:saveScene", () => ({ ok: false, reason: "No active native scene" }));
  });
  await page.getByTestId("viewer-scene-save-open").click();
  await page.getByTestId("viewer-scene-name").fill("not-saved");
  const reads: string[] = [];
  page.on("request", (request) => { if (request.url().endsWith("/api/viewer/scenes")) reads.push(request.url()); });
  await page.getByTestId("viewer-scene-save").click();
  await expect(page.getByTestId("viewer-scene-save-error")).toHaveText("No active native scene");
  await expect(page.getByTestId("viewer-scene-saved")).toHaveCount(0);
  expect(reads).toEqual([]);
});


test("visible saved scenes gain previews and inline information without opening TetraVox", async () => {
  const name = "preview-details";
  const scenePath = `/mnt/example/code/ti-toolbox/viewer/scenes/${name}.tetravox.json`;
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:previewScene");
    ipcMain.handle("tit:tetravox:previewScene", (_event, path: string) => {
      (globalThis as unknown as { previewPaths: string[] }).previewPaths = [path];
      return { ok: true };
    });
  });
  await page.route("**/api/viewer/scenes", async (route) => {
    const previewed = await app.evaluate(() => !!(globalThis as unknown as { previewPaths?: string[] }).previewPaths?.length);
    await route.fulfill({ json: { scenes: [{ name, slug: name, path: scenePath, saved_at: "2026-09-20T01:02:03Z", modified_at: "2026-09-20T04:05:06Z", created_at: null, layer_count: 3, dataset_count: 2, bytes: 8192, has_thumbnail: previewed, health: "valid", health_message: "All referenced project files are available" }] } });
  });
  await page.route(`**/api/files/raw${scenePath.replace(".tetravox.json", ".png")}`, (route) => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1sAAAAASUVORK5CYII=", "base64") }));
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.reload();
  await gotoPage(page, "viewer", "Viewer");
  const preview = page.getByTestId(`viewer-scene-preview-${name}`);
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  const info = page.getByTestId(`viewer-scene-info-${name}`);
  await info.click();
  const details = page.getByTestId(`viewer-scene-details-${name}`);
  await expect(details).toBeVisible();
  await expect(details.locator("dt")).toHaveText(["Saved", "Modified", "Layers", "Datasets", "Scene file", "Files"]);
  await expect(details.locator("dd").nth(2)).toHaveText("3");
  await expect(details.locator("dd").nth(3)).toHaveText("2");
  await expect(details.locator("dd").nth(4)).toHaveText("8.0 KB");
  expect(await details.locator("dd").nth(0).innerText()).not.toBe(await details.locator("dd").nth(1).innerText());
  await expect(details).toContainText(scenePath);
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await expect(info).toBeFocused();
  expect(await app.evaluate(() => (globalThis as unknown as { nativePaths?: string[] }).nativePaths ?? [])).toEqual([]);
  expect(errors).toEqual([]);
});
