import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp, setTheme } from "./_helpers";

// Mirrors system.spec.ts's launch/connect pattern.
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

async function launchApp(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

async function openSettings(): Promise<void> {
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  // Settings is one of the two pages DESIGN.md §2.3 still allows a header — capped at "a single
  // 28px eyebrow" (the orchestrator's brief), not the old 86px title-plus-purpose block.
  const headerBox = (await page.locator(".page-header").boundingBox())!;
  expect(Math.round(headerBox.height)).toBe(28);
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("changes theme, toggles a panel, and sees it appear in the nav after saving", async () => {
  await connect();
  await openSettings();

  // Fresh profile: nothing under Panels shows in the nav until this Settings visit mirrors
  // settings.panels into localStorage (pages/panels/_shared.ts) — Nilearn Visuals in particular
  // is off by default in the mock's fixture, so it must still be absent here.
  await expect(page.getByRole("link", { name: "Nilearn visuals" })).toHaveCount(0);

  // The mock's seeded panels (Settings.panels fixture) are already checked once Settings loads.
  // Scope to the Feature panels card, not just any "Source" text — the nav rail link is also
  // named "Source" once the panel is enabled.
  const featurePanelsCard = page.locator(".card", { hasText: "Feature panels" });
  await expect(featurePanelsCard.getByText("Source", { exact: true })).toBeVisible();
  await expect(featurePanelsCard.locator("label", { hasText: "Source" }).getByRole("checkbox")).toHaveAttribute("data-state", "checked");

  await page.screenshot({ path: join(ARTIFACTS, "settings-light.png") });

  // Change theme -> applies immediately, independent of Save.
  await setTheme(page, "dark", () => page.getByRole("radio", { name: "Dark" }).click());
  await page.screenshot({ path: join(ARTIFACTS, "settings-dark.png") });

  // Toggle Nilearn Visuals on (idempotent: click only if it isn't already checked, so this test
  // doesn't depend on no earlier run having left the long-lived mock's settings.panels mutated),
  // then save.
  const nilearnCheckbox = page.locator("label", { hasText: "Nilearn visuals" }).getByRole("checkbox");
  if ((await nilearnCheckbox.getAttribute("data-state")) !== "checked") await nilearnCheckbox.click();
  await expect(nilearnCheckbox).toHaveAttribute("data-state", "checked");

  await page.getByRole("button", { name: "Save changes" }).click();

  // Save triggers a reload (the panel list changed) so the nav rail — a static read of
  // PageDef.enabled — picks up the new panel list (pages/settings/index.tsx, PARITY.md).
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("link", { name: "Nilearn visuals" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("link", { name: "Source" })).toBeVisible();
  // Quick notes is not a rail entry any more — it is the ⌘⇧N drawer, covered by quick-notes.spec.ts.
  // Subject info is gone entirely (R1): its facts are Overview's, and neither the rail nor
  // Settings' panel list offers it.
  await expect(page.getByRole("link", { name: "Subject info" })).toHaveCount(0);

  // Theme survived the reload too (persisted in localStorage independently of the settings save).
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("Settings shows the Tetravox install TI-Toolbox manages", async () => {
  // V3 made the viewer an ordinary desktop app; V6 (dev/notes/v3-native-panes-external-viewer/TI.md)
  // made TI-Toolbox the thing that installs and updates it, so the card's subject is the *managed*
  // install: which version is here, that this app put it here, when it last looked for a newer
  // one, and what it costs on disk.
  await connect();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: true,
      path: "/Users/tester/Library/Application Support/TI-Toolbox/tetravox/0.3.11/Tetravox.app",
      version: "0.3.11",
      source: "managed",
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
      managed: {
        supported: true,
        version: "0.3.11",
        pending: null,
        lastCheckedAt: "2026-09-06T12:00:00.000Z",
        bytes: 420_000_000,
        root: "/Users/tester/Library/Application Support/TI-Toolbox/tetravox",
        busy: false,
      },
    }));
  });
  await openSettings();

  const card = page.getByTestId("viewer-card");
  await expect(card).toBeVisible();
  await page.getByTestId("viewer-card-refresh").click();
  await expect(page.getByTestId("viewer-card-path")).toContainText("tetravox/0.3.11/Tetravox.app");
  await expect(page.getByTestId("viewer-card-version")).toHaveText("0.3.11");
  await expect(page.getByTestId("viewer-card-status")).toBeVisible();
  // The sentence the whole lane exists to make true: the user installed nothing.
  await expect(page.getByTestId("viewer-card-source")).toHaveText("Installed by TI-Toolbox");
  await expect(page.getByTestId("viewer-card-checked")).not.toHaveText("Never");
  await expect(page.getByTestId("viewer-card-disk")).toHaveText("401 MB");
  await expect(page.getByTestId("viewer-card-check-updates")).toBeVisible();
  await expect(page.getByTestId("viewer-card-remove")).toBeVisible();
  // The override is a field, not a dialog, and it is now framed as an alternative to the managed
  // copy rather than the only way to have a viewer at all.
  await expect(page.getByTestId("viewer-card-override-input")).toBeVisible();

  // Nothing about the viewer is a server capability, so the About card must not claim one.
  // (It listed "Viewer bundle vX · protocol N · baked" until V4.)
  await expect(page.locator(".card", { hasText: "About the server" })).not.toContainText("Viewer bundle");
});

test("shows an update that is downloaded and waiting for the next launch", async () => {
  await connect();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: true,
      path: "/managed/0.3.11/Tetravox.app",
      version: "0.3.11",
      source: "managed",
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
      managed: {
        supported: true,
        version: "0.3.11",
        pending: "0.3.12",
        lastCheckedAt: "2026-09-06T12:00:00.000Z",
        bytes: 800_000_000,
        root: "/managed",
        busy: false,
      },
    }));
  });
  await openSettings();
  // A new version never replaces a running one; the card says so rather than the app doing it.
  await expect(page.getByTestId("viewer-card-pending")).toContainText("0.3.12");
  await expect(page.getByTestId("viewer-card-pending")).toContainText("next time you start");
});

test("offers to install Tetravox when nothing is there yet", async () => {
  await connect();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: false,
      path: null,
      version: null,
      source: null,
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
      managed: { supported: true, version: null, pending: null, lastCheckedAt: null, bytes: 0, root: "/managed", busy: false },
    }));
  });
  await openSettings();
  // Not an error and not a dead end: one button, and the Viewer page's Open does it anyway.
  await expect(page.getByTestId("viewer-card-missing")).toBeVisible();
  await expect(page.getByTestId("viewer-card-install")).toBeVisible();
  await expect(page.getByTestId("viewer-card-checked")).toHaveCount(0);
});

test("says so honestly on a platform Tetravox does not publish a build for", async () => {
  await connect();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: false,
      path: null,
      version: null,
      source: null,
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
      managed: { supported: false, version: null, pending: null, lastCheckedAt: null, bytes: 0, root: null, busy: false },
    }));
  });
  await openSettings();
  await expect(page.getByTestId("viewer-card-unsupported")).toBeVisible();
  // No Install button that could not work: the card does not offer what it cannot do.
  await expect(page.getByTestId("viewer-card-install")).toHaveCount(0);
});
