/**
 * TI-Toolbox's own update notice, end to end (decision 2026-10-09). Main's release check is
 * pointed at a local fixture feed (`TIT_UPDATE_FEED_URL`, forced on with `TIT_UPDATE_CHECK=1`);
 * every other spec runs with checks off and never sees the popup. The fixture names a version
 * one minor above the app's own package.json, so the spec survives version bumps.
 */
import { createServer, type Server } from "node:http";
import { mkdirSync, readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp, setTheme } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

const CURRENT = (JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf8")) as { version: string }).version;
const [major = 0, minor = 0] = CURRENT.split(".").map(Number);
const LATEST = `${major}.${minor + 1}.0`;

let feed: Server;
let feedUrl: string;
let feedHits = 0;
let app: ElectronApplication;
let page: Page;

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
  feed = createServer((_req, res) => {
    feedHits += 1;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ tag_name: `v${LATEST}`, html_url: `${feedUrl}/release-page`, draft: false, prerelease: false }));
  });
  await new Promise<void>((resolve) => feed.listen(0, "127.0.0.1", resolve));
  feedUrl = `http://127.0.0.1:${(feed.address() as AddressInfo).port}`;
});
test.afterAll(() => new Promise<void>((resolve) => feed.close(() => resolve())));
test.afterEach(async () => {
  await app?.close();
});

test("announces a newer release once per session, in the nav rail and in Settings ▸ Updates", async () => {
  app = await launchElectronApp({ env: { TIT_UPDATE_CHECK: "1", TIT_UPDATE_FEED_URL: `${feedUrl}/latest` } });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  // Record the release page instead of opening the host browser.
  await app.evaluate(({ shell }) => {
    (globalThis as unknown as { opened: string[] }).opened = [];
    shell.openExternal = async (url: string) => { (globalThis as unknown as { opened: string[] }).opened.push(url); };
  });

  // At load, on the project home: the popup with both versions.
  const dialog = page.getByRole("dialog", { name: "Update available" });
  await expect(dialog).toBeVisible({ timeout: 20_000 });
  await expect(dialog).toContainText(`TI-Toolbox ${LATEST} is available (you have ${CURRENT}).`);
  await expect(dialog.getByRole("button", { name: "Download" })).toBeVisible();
  await setTheme(page, "light");
  await page.screenshot({ path: join(ARTIFACTS, "app-update-popup-light.png") });
  await setTheme(page, "dark");
  await page.screenshot({ path: join(ARTIFACTS, "app-update-popup-dark.png") });
  await setTheme(page, "light");
  await dialog.getByRole("button", { name: "Later" }).click();
  await expect(dialog).toHaveCount(0);

  // Connecting reloads the window; the same process does not ask again, nor fetch again.
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  const label = page.getByTestId("nav-app-version");
  await expect(label).toHaveAttribute("data-update", "available");
  await expect(label).toHaveText(`v${CURRENT}`);
  await expect(label).toHaveAccessibleName(`TI-Toolbox ${LATEST} is available (you have ${CURRENT})`);
  await expect(page.getByRole("dialog", { name: "Update available" })).toHaveCount(0);
  expect(feedHits).toBe(1);
  // The 56px icon rail (1280 px window) holds the whole label: inside the rail, text not clipped.
  // (The rail's own 1px horizontal overflow predates the label, so it is not measured here.)
  await expect(page.getByTestId("nav-rail")).toHaveAttribute("data-rail-mode", "icons");
  const fit = await label.evaluate((el) => {
    const rail = el.closest(".nav-rail")!;
    const box = el.getBoundingClientRect();
    const railBox = rail.getBoundingClientRect();
    return { inside: box.left >= railBox.left && box.right <= railBox.left + rail.clientWidth, clipped: el.scrollWidth > el.clientWidth };
  });
  expect(fit).toEqual({ inside: true, clipped: false });
  await label.screenshot({ path: join(ARTIFACTS, "app-update-nav-light.png") });
  await page.locator(".nav-rail").screenshot({ path: join(ARTIFACTS, "app-update-rail-light.png") });
  await setTheme(page, "dark");
  await page.locator(".nav-rail").screenshot({ path: join(ARTIFACTS, "app-update-rail-dark.png") });
  await setTheme(page, "light");

  // The label leads to Settings ▸ Updates, which shows both versions and the status.
  await label.click();
  await expect(page.getByRole("tab", { name: "Updates", exact: true })).toHaveAttribute("aria-selected", "true");
  const card = page.getByTestId("app-update-card");
  await expect(card).toHaveAttribute("data-status", "available");
  await expect(card).toContainText(CURRENT);
  await expect(card).toContainText(LATEST);
  await expect(card).toContainText("Update available");
  await page.locator(".settings-panel[data-state='active']").screenshot({ path: join(ARTIFACTS, "app-update-settings-light.png") });
  await setTheme(page, "dark");
  await page.locator(".settings-panel[data-state='active']").screenshot({ path: join(ARTIFACTS, "app-update-settings-dark.png") });
  await setTheme(page, "light");

  await card.getByRole("button", { name: `Download ${LATEST}` }).click();
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { opened: string[] }).opened)).toEqual([`${feedUrl}/release-page`]);

  // Check again asks the feed anew.
  await card.getByRole("button", { name: "Check again" }).click();
  await expect.poll(() => feedHits).toBe(2);
  await expect(card).toHaveAttribute("data-status", "available");
});
