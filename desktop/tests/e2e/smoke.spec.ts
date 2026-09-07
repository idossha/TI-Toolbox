import { mkdirSync, mkdtempSync, readFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { MOD, expectPage, expectSubject, gotoPage, launchElectronApp, openPalette } from "./_helpers";
/**
 * The ⌘-number for a rail row, read from the row itself rather than typed here.
 *
 * `registry.ts` makes a page's number its index in `NAV_ORDER` + 1, precisely so the rail, the
 * palette and the `?` sheet cannot disagree — and a spec that hard-codes the digit opts itself out
 * of that guarantee. Three tests in this file broke the day the Notebooks row was inserted after
 * Pipeline and moved every number after it; none of them was about Notebooks.
 *
 * The rail publishes the binding as `aria-keyshortcuts` ("Meta+8" / "Control+8"), which is both the
 * app's own statement of what the key is and the thing a screen-reader user is told. Pressing what
 * the row advertises is a stronger test than pressing what this file remembers: if the two ever
 * disagree, the failure is the disagreement.
 */
async function railKey(pageId: string): Promise<string | null> {
  const advertised = await page.getByTestId(`nav-item-${pageId}`).getAttribute("aria-keyshortcuts");
  return advertised === null ? null : advertised.replace(/^(Meta|Control)\+/, `${MOD}+`);
}

/**
 * Press the row's key and assert it landed — or, for a row that has no key, click it and say so.
 *
 * A row CAN have no key, and that is a finding rather than a bug in this file: `shortcutForSlot`
 * hands out ⌘1..⌘9 and then the first free digit to Settings, so a rail of ten workflow rows has
 * one row past the end of the scheme. Jobs is that row today (the Notebooks insertion made it the
 * tenth). Asserting "every row has a key" here would be asserting a decision this spec does not
 * own; asserting "the key the row advertises works" is the property that must hold either way.
 */
async function jumpTo(pageId: string): Promise<boolean> {
  const key = await railKey(pageId);
  if (key === null) {
    await page.getByTestId(`nav-item-${pageId}`).click();
    await expectPage(page, pageId);
    return false;
  }
  await page.keyboard.press(key);
  await expectPage(page, pageId);
  return true;
}

// Runs the BUILT app: Electron is pointed at desktop/, whose package.json "main" is out/main/index.js
// (launching the directory, not the bare script, gives app.getName()/getVersion() from package.json). Against the mock server by default; set
// TIT_E2E_SERVER_URL + TIT_E2E_TOKEN to run against a real tit.server.
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;
let userDataDir: string;

async function launchApp(): Promise<void> {
  userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
}

async function connectFromLauncher(serverUrl: string, token: string): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", serverUrl);
  await page.fill("#token", token);
  await page.click("#connect");
}

/** End the cookie session from inside the page (the HttpOnly cookie is sent automatically). */
async function logoutFromPage(): Promise<number> {
  return page.evaluate(() => fetch("/auth/logout", { method: "POST", credentials: "same-origin" }).then((r) => r.status));
}

/** Connect and end the session server-side, then trigger a request so the 401 state shows. */
async function loseSession(): Promise<void> {
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  expect(await logoutFromPage()).toBe(204);
  // Any page that fetches through `api/client` will now see the 401 and flip the shell into its
  // unauthenticated state. Settings is the stable choice: it is pinned in the rail at every width
  // and its first render always issues `GET /api/settings`.
  await gotoPage(page, "settings", "Settings");
  await expect(page.getByTestId("connection-state")).toContainText("not authenticated", { timeout: 15_000 });
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(async () => {
  await launchApp();
});

test.afterEach(async () => {
  await app?.close();
});

test("launcher connects and the shell renders its chrome around the landing page", async () => {
  await expect(page.locator("#start-stack")).toBeDisabled();
  await connectFromLauncher(SERVER_URL, TOKEN);

  // The main window navigated to the server-served bundle (token cookie set by /auth/session).
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  // No page heading is asserted: DESIGN.md §8 puts the page-header budget at 0px outside Settings
  // and Help, so the table — the thing the page is for — is what proves the screen is up.
  await expect(page.getByTestId("overview-table")).toBeVisible();
  await expect(page.getByTestId("overview-table")).toContainText("ernie");
  // §11: the bottom status bar is gone. The connection dot is the shell's only always-on server
  // fact now; the version string is stated at Settings ▸ About the server.
  await expect(page.locator(".status-bar")).toHaveCount(0);
  await expect(page.getByTestId("connection-state")).toBeVisible();

  // Context bar (U11): no project crumb, no subject switcher — the search field took the space
  // they used to occupy, on the left, wide, with the ⌘K hint; the running-jobs chip and the
  // connection dot stay on the right. Measured: 40px, unchanged from v2.
  await expect(page.getByTestId("project-crumb")).toHaveCount(0);
  await expect(page.getByTestId("subject-switcher")).toHaveCount(0);
  const contextBar = page.locator(".context-bar");
  expect(Math.round((await contextBar.boundingBox())!.height)).toBe(40);
  await expect(contextBar).not.toContainText("example");
  const trigger = page.getByTestId("palette-trigger");
  await expect(trigger).toBeVisible();
  await expect(trigger).toContainText(/⌘K|Ctrl\+K/);
  expect((await trigger.boundingBox())!.width).toBeGreaterThan(200);
  await expect(page.getByTestId("jobs-count")).toHaveText(/^\d+ running$/);
  await expect(page.getByTestId("connection-state")).toContainText("connected", { timeout: 15_000 });

  // Nav rail (U7): flat and workflow-ordered — eight rows, then Settings and Help pinned. No group
  // headers, no subject-id label, no shortcut badges.
  const rail = page.getByRole("navigation", { name: "Main" });
  await expect(rail.locator(".nav-group-label")).toHaveCount(0);
  await expect(rail.getByTestId("nav-item-jobs")).toBeVisible();
  await expect(rail.getByTestId("nav-item-settings")).toBeVisible();
  await expect(rail.getByTestId("nav-item-help")).toBeVisible();
  await expect(rail.getByTestId("nav-item-optimizer-ex")).toHaveCount(0);
  await expect(rail.locator(".kbd")).toHaveCount(0);
  // Icons below 1440 (program Q1): the labels are hidden, not absent, so the accessible name and
  // the tooltip both still say what the row is.
  await expect(rail).toHaveAttribute("data-rail-mode", "icons");
  await page.screenshot({ path: join(ARTIFACTS, "subjects.png") });

  // The bridge exists but the token never reaches the renderer. Thirteen entries: twelve, plus
  // `saveFile`, which the Pipeline canvas added (`dev/notes/v3-native-panes-external-viewer/PL.md`)
  // because saving renderer-produced text to a file the user picks is a host action and the
  // renderer had no way to do it at all — its `<a download>` on a blob: URL was inert in this
  // shell and reported success anyway.
  //
  // A fourteenth, `viewer`, existed for a few hours on 2026-09-06: V3 made viewing a
  // host-installed Tetravox desktop app, which needed a route through main to launch. The
  // maintainer reversed that ("We should not install Tetravox on the host machine — forbidden");
  // the viewer is an `<iframe src="/tetravox/">` served by this app's own server again, opening a
  // scene is not a host action, and the entry went with it. ADR row 14's budget is 13, and this
  // list is what holds a fourteenth to an ADR line.
  const bridgeKeys = await page.evaluate(() => Object.keys((window as unknown as { tit: object }).tit).sort());
  expect(bridgeKeys).toEqual([
    "appVersion",
    "connect",
    "getSettings",
    "notify",
    "openExternal",
    "openPath",
    "platform",
    "saveFile",
    "selectDirectory",
    "selectFile",
    "setSettings",
    "showItemInFolder",
    "stack",
  ]);
  const settings = await page.evaluate(() => (window as unknown as { tit: { getSettings(): Promise<unknown> } }).tit.getSettings());
  expect(JSON.stringify(settings)).not.toContain(TOKEN);
});

test("keyboard shortcuts jump screens and toggle the jobs rail", async () => {
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });

  const mod = MOD;

  // DESIGN.md §9: ⌘1 Overview · ⌘2 Pre-processing · ⌘3 Simulator · ⌘4 Optimizer · ⌘5 Analyzer ·
  // ⌘6 Pipeline · ⌘7 Results · ⌘8 Viewer · ⌘9 Jobs · ⌘0 Settings. The number is the page's index in
  // `registry.ts`'s NAV_ORDER, so the rail, the palette and the `?` sheet cannot disagree — and
  // Settings takes the first digit the rail does not, which the Pipeline row moved from 9 to 0.
  await jumpTo("pipeline");

  await jumpTo("results");

  await jumpTo("jobs");

  await jumpTo("simulator");

  // Settings too: `shortcutForSlot` gives it the first digit the rail does not use, which is 9 or
  // 0 depending on how many rows the rail has — exactly the thing that must not be typed here.
  await jumpTo("settings");
  // ⌘, is Settings' alias, and Help is the `?` sheet only — neither takes one of the rail's numbers.
  await jumpTo("overview");
  await page.keyboard.press(`${mod}+,`);
  await expectPage(page, "settings");

  await jumpTo("overview");
  await expect(page.getByTestId("overview-table")).toBeVisible();

  await expect(page.locator(".jobs-rail-expanded")).toHaveCount(0);
  await page.keyboard.press(`${mod}+j`);
  await expect(page.locator(".jobs-rail-expanded")).toHaveCount(1);
  await page.keyboard.press(`${mod}+j`);
  await expect(page.locator(".jobs-rail-expanded")).toHaveCount(0);
});

test("the rail's icon/label breakpoint updates on resize even while the Viewer streams (B5's flake)", async () => {
  // B5 (dev/notes/v3-ui-program/b5-viewer-notes.md §4 finding 2): `NavRail.tsx`'s icon/label
  // breakpoint intermittently stayed "icons" after a resize to >=1440 specifically on the Viewer
  // page with a scene already loaded — i.e. while its postMessage channel to the embed is live —
  // never reproduced on a page with no iframe. This reproduces that exact condition end to end.
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await page.setViewportSize({ width: 1280, height: 900 });

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expectSubject(page, "ernie");

  await jumpTo("viewer");
  // R5: the source drafts, Open commands — so this smoke test drafts and stops. What Open does
  // (one request, one scene, a move to the Viewer sub-page) is viewer.spec.ts's.
  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await expect(page.getByTestId("viewer-plan")).toBeVisible({ timeout: 15_000 });
  // VM2: the page is a centred source card and one editable file list, not a bar over a canvas.
  await expect(page.getByTestId("viewer-panel")).toBeVisible();
  await expect(page.getByTestId("viewer-section-source")).toBeVisible();

  const rail = page.getByRole("navigation", { name: "Main" });
  await expect(rail).toHaveAttribute("data-rail-mode", "icons");

  // Resize up, then back down, with the embed's channel open the whole time. A stale
  // `useLabelledRail()` read would leave this at "icons" (or fail to drop back to "icons"), which
  // is exactly the bug: two independent listeners (`matchMedia` "change" and window "resize") back
  // the same state now, so one race dropping an event no longer strands the rail.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(rail).toHaveAttribute("data-rail-mode", "labels", { timeout: 5_000 });
  await expect(rail).toHaveCSS("width", "216px");

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(rail).toHaveAttribute("data-rail-mode", "icons", { timeout: 5_000 });
  await expect(rail).toHaveCSS("width", "56px");
});

test("the right pane collapses with ⌘⇧I and the work pane takes its width", async () => {
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await page.setViewportSize({ width: 1280, height: 800 });

  await jumpTo("preprocess");
  const panel = page.locator('[data-page-active="true"]');
  const pane = panel.getByTestId("page-right-pane");
  const work = panel.getByTestId("page-work");
  await expect(pane).toHaveCount(1);
  const withPane = (await work.boundingBox())!.width;

  // A collapsed pane takes no geometry or focus; its retained content resumes unchanged.
  await page.keyboard.press(`${MOD}+Shift+i`);
  await expect(pane).toBeHidden();
  expect((await work.boundingBox())!.width).toBeGreaterThan(withPane + 300);

  await page.keyboard.press(`${MOD}+Shift+i`);
  await expect(pane).toBeVisible();
  expect(Math.round((await work.boundingBox())!.width)).toBe(Math.round(withPane));

  // A page with no right pane must not swallow the chord — one gesture, one meaning (§6.5).
  await jumpTo("overview");
  await page.keyboard.press(`${MOD}+Shift+i`);
  await expect(panel.getByTestId("page-work")).toHaveCount(1);
});

test("the command palette carries pages, subjects and actions", async () => {
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });

  await openPalette(page);
  const palette = page.getByRole("dialog");
  await expect(palette.getByRole("option", { name: /^Overview/ })).toBeVisible();
  await expect(palette.getByRole("option", { name: /^ernie/ })).toBeVisible();
  await expect(palette.getByRole("option", { name: /^Theme: dark/ })).toBeVisible();
  // A hidden page (navGroup "dev") is in no rail but is reachable here — that is what hidden means.
  await expect(page.getByTestId("nav-item-dev")).toHaveCount(0);
  await expect(palette.getByRole("option", { name: /^Gallery/ })).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "palette-light.png") });

  // It navigates, and it closes behind itself.
  await page.getByTestId("palette-input").fill("Results");
  await palette.getByRole("option", { name: /^Results/ }).first().click();
  await expectPage(page, "results");
  await expect(page.getByTestId("palette-input")).toHaveCount(0);

  // Switching subject from the palette (U11: the only subject control left outside a page's own
  // batch table) re-scopes the shell — never the context bar, which no longer names a subject.
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expectSubject(page, "ernie");
  await expect(page.locator(".context-bar")).not.toContainText("ernie");

  // ? opens the one keyboard sheet, and Esc closes it (Esc is scoped to the innermost overlay).
  // `press("?")`, not `press("Shift+/")`: the latter sends the *unshifted* "/" with a shift
  // modifier through CDP, which is not what a keyboard produces.
  await page.keyboard.press("?");
  await expect(page.getByTestId("keyboard-sheet")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("keyboard-sheet")).toHaveCount(0);
});

test("a wrong token stays in the launcher with an error", async () => {
  await connectFromLauncher(SERVER_URL, "definitely-wrong");
  await expect(page.locator("#status")).toHaveText(/rejected the token/, { timeout: 20_000 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await expect(page.locator("#connect")).toBeEnabled();
  await expect(page.locator("#token")).toHaveValue("");
});

test("navigation outside the server origin is blocked", async () => {
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  // app:// is a registered scheme with no external handler, so the guard runs without opening a browser
  // (file: never reaches will-navigate: Chromium refuses it in the renderer).
  await page.evaluate(() => {
    window.location.href = "app://evil/";
  });
  await page.waitForTimeout(500);
  // Playwright's frame tracking is stale after a cancelled navigation (page.url() is "" and locators
  // resolve to nothing), so assert from inside the page.
  const state = await page.evaluate(() => ({
    href: window.location.href,
    hasTable: document.querySelector("[data-testid=overview-table]") !== null,
  }));
  expect(state).toEqual({ href: new URL("/", SERVER_URL).href, hasTable: true });
  const logsDir = await app.evaluate(({ app: a }) => a.getPath("logs"));
  expect(readFileSync(join(logsDir, "main.log"), "utf8")).toContain("blocked navigation to app://evil/");
  expect(readFileSync(join(logsDir, "main.log"), "utf8")).toContain("refused openExternal for scheme app:");
  expect(realpathSync(logsDir).startsWith(realpathSync(userDataDir))).toBe(true);
});

test("a lost session shows the 401 state and returns to the launcher", async () => {
  await loseSession();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "unauthenticated.png") });
  await page.getByRole("button", { name: "Back to launcher" }).click();
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 10_000 });
});

test("sign out posts /auth/logout and returns to the launcher", async () => {
  await loseSession();
  // The session is already gone, so this logout answers 401; the button must still leave the page.
  const logoutResponse = page.waitForResponse((r) => r.url().endsWith("/auth/logout") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Sign out" }).click();
  expect((await logoutResponse).status()).toBe(401);
  await expect(page).toHaveURL(/^app:\/\/launcher\//, { timeout: 10_000 });
  // A valid session can be ended the same way and the cookie is really gone afterwards.
  await connectFromLauncher(SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  expect(await logoutFromPage()).toBe(204);
  expect(await logoutFromPage()).toBe(401);
  const cookieNames = (await app.evaluate(({ session }) => session.defaultSession.cookies.get({ name: "tit_session" }))).map((c) => c.name);
  expect(cookieNames).toEqual([]);
});
