/**
 * Browser mode — the same UI, no Electron.
 *
 * `tit launch` (tit/launch.py) starts the container and hands the user a
 * `/auth/session?token=…` URL instead of opening a window; the server then serves the very
 * bundle this repository builds. Every other spec in this directory drives that bundle inside
 * Electron, where `window.tit` exists. This one drives it in plain Chromium, where it does not,
 * so the launch path documented in `docs/installation/bash-cli.md` has a test behind it.
 *
 * What it is actually guarding: the renderer decides Electron-vs-browser exactly once, at module
 * evaluation (`src/renderer/env.ts` — `isElectron = window.tit !== undefined`), and every
 * bridge-dependent control is gated on that one const. A regression there is invisible to the
 * Electron specs by construction: they all run on the branch that has a bridge. The cheapest
 * thing that catches it is loading the app with no bridge at all and asserting the shell renders,
 * the nav works, data arrives over HTTP, and the Electron-only affordances are *absent* rather
 * than present-and-throwing.
 *
 * It runs against whatever `TIT_E2E_SERVER_URL` names — the mock server by default
 * (`playwright.config.ts` starts it), a live container under `--project real`. Nothing here
 * reaches for `_helpers.ts`'s Electron launcher, so there is no window, no user-data directory
 * and no monitor to hijack.
 */
import { expect, test, type Page } from "@playwright/test";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

/**
 * The one URL `tit launch` prints. Loading it is the whole browser-mode entry sequence: the
 * server trades the token for an HttpOnly session cookie and 303s to `/`, so the token never
 * appears in the address bar again and every later request authenticates by cookie.
 */
function sessionUrl(): string {
  return `${SERVER_URL}/auth/session?token=${encodeURIComponent(TOKEN)}`;
}

async function openApp(page: Page): Promise<void> {
  await page.goto(sessionUrl());
  await expect(page.getByTestId("shell-content")).toBeVisible({ timeout: 30_000 });
}

test.describe("browser mode (no Electron bridge)", () => {
  test("the session URL exchanges the token for a cookie and lands on the app", async ({ page }) => {
    const response = await page.goto(sessionUrl());
    // Playwright follows the 303, so the *final* URL is the app, not /auth/session.
    expect(new URL(page.url()).pathname).toBe("/");
    expect(response?.status()).toBe(200);
    await expect(page.getByTestId("shell-content")).toBeVisible({ timeout: 30_000 });

    const cookies = await page.context().cookies();
    const session = cookies.find((c) => c.name === "tit_session");
    expect(session, "the server set a session cookie").toBeTruthy();
    expect(session?.httpOnly, "the session cookie is HttpOnly").toBe(true);
    // The cookie is not the token: a cookie derived from the token would leak it to anything
    // that can read Set-Cookie in a proxy log.
    expect(session?.value).not.toBe(TOKEN);
  });

  test("there is no bridge, and the renderer knows it", async ({ page }) => {
    await openApp(page);
    expect(await page.evaluate(() => (window as unknown as { tit?: unknown }).tit)).toBeUndefined();
  });

  test("the nav rail reaches every main page over HTTP alone", async ({ page }) => {
    await openApp(page);
    await expect(page.locator(".nav-rail")).toBeVisible();

    // The pages a browser-mode user actually works in. Viewer is included on purpose: it frames
    // the server-served Tetravox embed (`/tetravox/`) rather than anything Electron provides,
    // which is exactly why it works here at all.
    for (const id of ["overview", "preprocess", "simulator", "optimizer", "analyzer", "results", "viewer", "settings"]) {
      const item = page.getByTestId(`nav-item-${id}`);
      if ((await item.count()) === 0) continue; // a page the server did not enable for this project
      await item.click();
      await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", id);
      // No unhandled bridge access anywhere on the way in.
      expect(await page.evaluate(() => (window as unknown as { __titBridgeError?: string }).__titBridgeError)).toBeUndefined();
    }
  });

  test("Electron-only affordances are absent, not broken", async ({ page }) => {
    await openApp(page);
    await page.getByTestId("nav-item-settings").click();
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", "settings");

    // The Docker card drives `window.tit.stack.*`; in a browser the container is not this page's
    // to manage (whoever ran `tit launch` owns it), so the card must not render at all rather
    // than render and throw on click.
    await expect(page.getByText("Docker", { exact: true })).toHaveCount(0);
    // …while the cards that need only the server are there, so this is an absence of one card
    // rather than a page that failed to render.
    await expect(page.getByText("Appearance", { exact: true }).first()).toBeVisible();
  });

  test("the About tab reports Browser instead of guessing a platform", async ({ page }) => {
    await openApp(page);
    const help = page.getByTestId("nav-item-help");
    test.skip((await help.count()) === 0, "no Help page in this build");
    await help.click();
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", "help");
    await page.getByRole("tab", { name: "About", exact: true }).click();
    // `appVersion()` and `platform()` are bridge calls; the browser branch renders the literal
    // "Browser" (src/renderer/pages/help/AboutTab.tsx) rather than leaving an empty row.
    await expect(page.getByText("Browser", { exact: true }).first()).toBeVisible();
    // The Electron-only row is not merely empty — it is not in the list at all.
    await expect(page.getByText("Desktop version", { exact: true })).toHaveCount(0);
  });

  test("the page raises no uncaught error while loading and navigating", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await openApp(page);
    await page.getByTestId("nav-item-overview").click();
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", "overview");
    // A `window.tit` access with no bridge throws TypeError; this is the net under every gate.
    expect(errors, "no uncaught errors in browser mode").toEqual([]);
  });
});
