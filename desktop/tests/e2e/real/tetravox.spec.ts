import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, launchElectronApp } from "../_helpers";

/**
 * Settings → Viewer engine, against the **real** container (E1–E4).
 *
 * The mock's version of this loop is covered by `tests/e2e/settings.spec.ts`; what only a real
 * server can prove is that the card renders the shape `tit.server` actually emits — the bundle
 * resolution in `tit/tetravox/store.py`, the protocol range from `tit/tetravox/protocol.py`, and
 * the release-index answer with its real message. Read-only on purpose: installing here would
 * write into the maintainer's own `~/.config/ti-toolbox`, and the install/rollback/remove loop is
 * proved against the live API with the real 0.3.4 tarball in
 * `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)` §4.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expectPage(page, "settings");
});

test.afterAll(async () => {
  await app?.close();
});

test("shows the live embed bundle, where it came from, and the protocol range this app supports", async () => {
  const card = page.getByTestId("tetravox-card");
  await expect(card).toBeVisible();

  // Whatever the container has installed, the card states it in the app's own grammar: a version,
  // a protocol, a source, and the range — never "up to date" with nothing behind it.
  await expect(page.getByTestId("tetravox-active-version")).toHaveText(/^v\d+\.\d+\.\d+.* · protocol \d+$/);
  await expect(card).toContainText(/Baked into the image|Installed|Developer override/);
  await expect(card).toContainText(/protocol 1–[23]/);
  await expect(page.getByTestId("tetravox-reason")).toContainText("tetravox/embed");

  // The About card reads the same `capabilities.tetravox_embed`, so the two cannot disagree.
  const activeVersion = (await page.getByTestId("tetravox-active-version").textContent()) ?? "";
  await expect(page.locator(".card", { hasText: "About the server" })).toContainText(activeVersion.split(" · ")[0]!);
});

test("checking for updates reports the index's real answer", async () => {
  await page.getByTestId("tetravox-check").click();
  // Either the index answered (a list) or it did not (one sentence). Both are states this page
  // renders; neither is an error banner — an air-gapped install is supported, not broken.
  await expect(page.getByTestId("tetravox-updates").or(page.getByTestId("tetravox-offline"))).toBeVisible({ timeout: 40_000 });
  await expect(page.locator(".callout-danger")).toHaveCount(0);
});
