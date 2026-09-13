import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp, setTheme } from "./_helpers";

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
  await connectLauncher(page, SERVER_URL, TOKEN);
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
  await page.getByRole("tab", { name: "Extensions", exact: true }).click();

  // The mock's seeded panels (Settings.panels fixture) are already checked once Settings loads.
  // Scope to the Feature panels card, not just any "Source" text — the nav rail link is also
  // named "Source" once the panel is enabled.
  const featurePanelsCard = page.locator(".card", { hasText: "Feature panels" });
  await expect(featurePanelsCard.getByText("Source", { exact: true })).toBeVisible();
  await expect(featurePanelsCard.locator("label", { hasText: "Source" }).getByRole("checkbox")).toHaveAttribute("data-state", "checked");

  await page.screenshot({ path: join(ARTIFACTS, "settings-light.png") });

  // Change theme -> applies immediately, independent of Save.
  await page.getByRole("tab", { name: "Project", exact: true }).click();
  await setTheme(page, "dark", () => page.getByRole("radio", { name: "Dark" }).click());
  await page.screenshot({ path: join(ARTIFACTS, "settings-dark.png") });

  // Toggle Nilearn Visuals on (idempotent: click only if it isn't already checked, so this test
  // doesn't depend on no earlier run having left the long-lived mock's settings.panels mutated),
  // then save.
  await page.getByRole("tab", { name: "Extensions", exact: true }).click();
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

test("Viewer settings show native installation status", async () => {
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:tetravox:status");
    ipcMain.handle("tit:tetravox:status", () => ({ supported: true, installed: false, installing: false, version: null, directory: "/tmp/tetravox" }));
  });
  await connect();
  await openSettings();
  await page.getByRole("tab", { name: "Viewer", exact: true }).click();
  await expect(page.getByTestId("native-tetravox")).toBeVisible();
  await expect(page.getByRole("button", { name: "Install TetraVox", exact: true })).toBeEnabled();
  await expect(page.getByText("TetraVox opens in its own native window.")).toBeVisible();
});
