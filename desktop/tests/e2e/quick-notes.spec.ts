import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp, setTheme } from "./_helpers";

// Quick notes is a global drawer (⌘⇧N), not a nav destination — plan §2. This spec replaces the
// "Quick Notes autosaves and survives a reload" test in panels.spec.ts, which navigated to a
// `panel-quick-notes` page that no longer exists. panels.spec.ts is shared with Subject info and
// belongs to another lane, so it is left alone and the breakage is reported instead.
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

async function openNotes(): Promise<void> {
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Shift+n" : "Control+Shift+n");
  await expect(page.getByTestId("quick-notes")).toBeVisible({ timeout: 20_000 });
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("the notes drawer opens with the keyboard, autosaves, and survives a reload", async () => {
  await connect();

  // It is not a nav item any more.
  await expect(page.getByRole("link", { name: "Quick notes", exact: true })).toHaveCount(0);

  await openNotes();
  const textarea = page.getByTestId("quick-notes-textarea");
  await expect(textarea).toHaveValue(/Mock project notes/, { timeout: 20_000 });
  await expect(page.getByText("Saves automatically")).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "quick-notes-light.png") });

  await textarea.click();
  await textarea.press("End");
  await textarea.type("\nAdded during the E2E run.");
  // The debounce + mutation round trip against the mock is fast enough that catching the transient
  // "Saving…" state is racy — assert the eventual autosaved state instead.
  await expect(page.getByTestId("quick-notes-status")).toHaveText(/^Saved /, { timeout: 5_000 });

  // Esc is scoped to the innermost overlay: it closes the drawer, nothing else.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("quick-notes")).toHaveCount(0);

  await setTheme(page, "dark");
  await openNotes();
  await expect(page.getByTestId("quick-notes-textarea")).toHaveValue(/Added during the E2E run\./);
  await page.screenshot({ path: join(ARTIFACTS, "quick-notes-dark.png") });
  await page.keyboard.press("Escape");

  // Reload to confirm the save round-tripped through the server, not just local component state.
  await page.reload();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  await openNotes();
  await expect(page.getByTestId("quick-notes-textarea")).toHaveValue(/Added during the E2E run\./, { timeout: 20_000 });
});

test("the drawer is reachable from the command palette as well as the shortcut", async () => {
  await connect();

  await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
  await page.keyboard.type("quick notes");
  await expect(page.getByRole("option", { name: /Open quick notes/ }).first()).toBeVisible();
  // Run it with Enter rather than a click: the palette's own overlay currently sits above its
  // list and swallows pointer events on the rows (reported to the shell lane), and Enter is the
  // palette's primary interaction anyway.
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("quick-notes")).toBeVisible({ timeout: 20_000 });
});
