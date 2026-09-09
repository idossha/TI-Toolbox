/** The shipping package opens the Docker launcher; it contains no native Python runtime.
 * Build with `npm run package:dir` first. This tests the artifact, including missing main-process
 * dependencies that a source checkout can accidentally resolve from desktop/node_modules.
 * Actual Docker Browse/Start acceptance runs separately against an owned project and image.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { _electron as electron, expect, test, type ElectronApplication } from "@playwright/test";

const APP_ROOT = join(__dirname, "..", "..");
const expectedVersion = JSON.parse(readFileSync(join(APP_ROOT, "package.json"), "utf8")).version as string;

function resolvePackagedAppBinary(): string | null {
  const candidates = process.platform === "darwin"
    ? [
        join(APP_ROOT, "release", "mac-arm64", "TI-Toolbox.app", "Contents", "MacOS", "TI-Toolbox"),
        join(APP_ROOT, "release", "mac", "TI-Toolbox.app", "Contents", "MacOS", "TI-Toolbox"),
      ]
    : process.platform === "win32"
      ? [join(APP_ROOT, "release", "win-unpacked", "TI-Toolbox.exe")]
      : [join(APP_ROOT, "release", "linux-unpacked", "ti-toolbox")];
  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

const APP_BIN = resolvePackagedAppBinary();

test.describe("packaged Docker launcher", () => {
  test.skip(APP_BIN === null, "no packaged app under release/ — run npm run package:dir first");

  let app: ElectronApplication | undefined;
  const ownedDirs: string[] = [];

  test.afterEach(async () => {
    try { await app?.close(); }
    finally {
      app = undefined;
      for (const directory of ownedDirs.splice(0)) rmSync(directory, { recursive: true, force: true });
    }
  });

  test("opens usable Docker controls with the packaged version, stays hidden, and closes normally", async () => {
    const project = mkdtempSync(join(tmpdir(), "tit-packaged-project-"));
    const userData = mkdtempSync(join(tmpdir(), "tit-packaged-userdata-"));
    ownedDirs.push(project, userData);
    const env = { ...process.env };
    // Shell sessions must not bypass the actual launcher or point it at a development server.
    for (const key of Object.keys(env)) {
      if (key.startsWith("TIT_") || key.startsWith("ELECTRON_") || key === "NODE_OPTIONS") delete env[key];
    }
    app = await electron.launch({
      executablePath: APP_BIN!,
      env: { ...env, TIT_USER_DATA_DIR: userData, TIT_E2E_OFFSCREEN: "1" },
    });
    const page = await app.firstWindow();
    const identity = await app.evaluate(({ app }) => ({ packaged: app.isPackaged, version: app.getVersion(), userData: app.getPath("userData") }));
    expect(identity).toEqual({ packaged: true, version: expectedVersion, userData });
    await expect(page).toHaveURL(/^app:\/\/launcher\//);
    await expect(page.getByRole("heading", { name: "TI-Toolbox", exact: true })).toBeVisible();
    await expect(page.getByLabel("Server URL")).toBeEditable();
    await expect(page.getByLabel("Token", { exact: true })).toBeEditable();
    await expect(page.getByLabel("Token", { exact: true })).toHaveValue("");
    await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeEnabled();
    const start = page.getByRole("button", { name: "Start the Docker stack", exact: true });
    await expect(start).toBeDisabled();
    await app.evaluate(({ dialog }, directory) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [directory] });
    }, project);
    await page.getByRole("button", { name: "Browse…", exact: true }).click();
    await expect(page.getByLabel("Project directory")).toHaveValue(project);
    await expect(start).toBeEnabled();
    await expect(page.locator("#footer")).toContainText(`desktop ${expectedVersion}`);

    // Visibility assertions read native Electron windows, not merely DOM visibility.
    for (let sample = 0; sample < 3; sample++) {
      const windows = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().map(window => ({ visible: window.isVisible(), focused: window.isFocused() })));
      expect(windows.length).toBeGreaterThan(0);
      expect(windows.every(window => !window.visible && !window.focused)).toBe(true);
      await page.waitForTimeout(100);
    }
    const childProcess = app.process();
    await app.close();
    app = undefined;
    expect(childProcess.exitCode).toBe(0);
  });
});
