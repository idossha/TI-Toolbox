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

test("installs a viewer bundle from the release index, then rolls back to the baked one", async () => {
  // docs/dev/HISTORY.md § 2026-09-04 (embed convergence) E1-E4: the whole point is that a Tetravox update does
  // not need a TI-Toolbox release. This drives the loop a user actually performs — see what is
  // running, check the index, install, roll back — against the mock's in-memory install root.
  //
  // (VX briefly replaced this card with a host-app one — a resolved `Tetravox.app` path, a
  // version read off its Info.plist, a download link. The maintainer reversed that: the viewer is
  // the embed again, TI-Toolbox installs it, and the card's subject is the *bundle*.)
  await connect();
  await openSettings();

  const card = page.getByTestId("tetravox-card");
  await expect(card).toBeVisible();
  await expect(page.getByTestId("tetravox-active-version")).toHaveText("v0.3.4 · protocol 1");
  await expect(card).toContainText("Baked into the image");
  await expect(card).toContainText("protocol 1–3");

  // The cached answer is on screen without any check being asked for (A3): the server's own
  // background pass wrote it, so opening Settings costs no GitHub request.
  await expect(page.getByTestId("tetravox-last-checked")).toContainText("Last checked:");
  await page.getByTestId("tetravox-check").click();
  const updates = page.getByTestId("tetravox-updates");
  await expect(updates).toBeVisible();
  // The digest the server will verify before unpacking is on screen, not hidden behind trust.
  await expect(updates).toContainText("sha256 bbbbbbbbbbbb…");
  // A bundle needing a protocol this app cannot host is listed, and not installable.
  await expect(updates).toContainText("needs a newer app");

  await page.getByTestId("tetravox-install-0.4.0").click();
  await expect(page.getByTestId("tetravox-active-version")).toHaveText("v0.4.0 · protocol 3");
  await expect(card).toContainText("pinned to installed 0.4.0");
  // `capabilities.tetravox_embed` is the active bundle, so the About card's "Viewer bundle" row
  // moved with it. It is a server capability again — the row VX deleted.
  await expect(page.locator(".card", { hasText: "About the server" })).toContainText("Viewer bundle");
  await expect(page.locator(".card", { hasText: "About the server" })).toContainText("v0.4.0 · protocol 3 · installed");

  await page.getByTestId("tetravox-activate-baked").click();
  await expect(page.getByTestId("tetravox-active-version")).toHaveText("v0.3.4 · protocol 1");
  // Rollback pins, never deletes: 0.4.0 is still there to go forward to.
  await expect(page.getByTestId("tetravox-activate-0.4.0")).toBeVisible();

  // Leave the (long-lived, cross-spec) mock server as this test found it.
  await page.getByTestId("tetravox-remove-0.4.0").click();
  await expect(card).toContainText("Nothing installed yet");
});

test("turns automatic viewer updates off, and still shows a bundle it can install", async () => {
  // A3: off means the server stops *installing*, not that it stops *knowing*. The switch is the
  // whole policy surface, and it is persisted server-side, not in this window.
  await connect();
  await openSettings();

  await expect(page.getByTestId("tetravox-card")).toBeVisible();
  const toggle = page.locator("#tetravox-auto-update");
  await expect(toggle).toHaveAttribute("data-state", "checked");
  await expect(page.getByTestId("tetravox-last-checked")).toContainText("checks for a newer viewer at startup and every 24 hours");

  await toggle.click();
  await expect(toggle).toHaveAttribute("data-state", "unchecked");
  await expect(page.getByTestId("tetravox-last-checked")).toContainText("Automatic installs are off");
  // What was found is still offered, with an explicit Install.
  await page.getByTestId("tetravox-check").click();
  await expect(page.getByTestId("tetravox-install-0.4.0")).toBeVisible();

  // Leave the long-lived mock as found.
  await toggle.click();
  await expect(toggle).toHaveAttribute("data-state", "checked");
});

test("shows one toast when the server replaces the viewer bundle under the app", async () => {
  // The event the auto-update publishes on /ws/tetravox. Triggered here through the mock's
  // __mock hook rather than by waiting 24 h or installing anything.
  await connect();
  await page.evaluate(async () => {
    await fetch("/api/__mock/tetravox-updated", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ version: "0.3.12", protocol: 2 }),
    });
  });
  await expect(page.getByText("Tetravox 0.3.12 installed and active")).toBeVisible({ timeout: 15_000 });
});
