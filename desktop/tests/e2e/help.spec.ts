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

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("every Help tab renders, including the docs fallback links", async () => {
  await connect();

  // Force pages/help/DocsTab.tsx's "offline docs bundle isn't present" branch: the mock server
  // now serves /docs/ itself (tests/mock-server/server.mjs's own presence-check stub, exercised
  // by tests/mock-server/server.test.ts), which would otherwise make `docsAvailable()` resolve
  // true and render the iframe instead — this spec's job is the fallback link list a real server
  // without the offline bundle shows, not to re-prove the mock's own /docs stub.
  await page.route("**/docs/", (route) => route.fulfill({ status: 404, body: "not found" }));

  await page.getByRole("link", { name: "Help", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Help" })).toBeVisible();

  // Help is one of the two pages DESIGN.md §2.3 still allows a header — capped at "a single 28px
  // eyebrow" (the orchestrator's brief), not the old 86px title-plus-purpose block.
  const headerBox = (await page.locator(".page-header").boundingBox())!;
  expect(Math.round(headerBox.height)).toBe(28);

  // Docs tab: fetch("/docs/") 404s (routed above), so this exercises the fallback link list.
  // ExternalLinkButton renders a <Button> (role "button"), not an <a>, inside Electron — see
  // pages/help/links.tsx.
  await expect(page.getByRole("button", { name: "Full documentation (wiki)" })).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: join(ARTIFACTS, "help-light.png") });

  // Keyboard tab: Q5's copy (a Cmd+number per workflow page in nav order, Settings on the first
  // digit the rail does not take — Cmd+0 since the Pipeline row landed — ? this sheet, plus
  // Cmd+K/Cmd+J/Cmd+Shift+I/Cmd+Shift+V) and nothing about Freeview, Gmsh or X11 — the
  // external-viewer flow those named is gone in v3 (D3). The rows are derived from the registry,
  // so this asserts the derived key, not a hand-typed one.
  await page.getByRole("tab", { name: "Keyboard" }).click();
  const mod = process.platform === "darwin" ? "⌘" : "Ctrl+";
  const keyboardPanel = page.getByRole("tabpanel");
  await expect(keyboardPanel.getByText("Overview", { exact: true })).toBeVisible();
  await expect(keyboardPanel.getByText(`${mod}0`, { exact: true })).toBeVisible();
  await expect(keyboardPanel.getByText("Settings", { exact: true })).toBeVisible();
  await expect(keyboardPanel.getByText(`${mod}K`, { exact: true })).toBeVisible();
  await expect(keyboardPanel.getByText(`${mod}J`, { exact: true })).toBeVisible();
  const bodyText = (await keyboardPanel.textContent()) ?? "";
  expect(bodyText).not.toMatch(/freeview|gmsh|x11/i);

  await page.getByRole("tab", { name: "About" }).click();
  await expect(page.getByText("Automatic update checks aren't wired up yet")).toBeVisible();

  await page.getByRole("tab", { name: "Cite" }).click();
  // Real assertion: the citation text that "Copy citation" would copy is present and correct on
  // the page (the actual clipboard write needs a permission grant Playwright's Electron runner
  // doesn't provide, so CiteTab's try/catch swallows that failure and the label never flips to
  // "Copied" here — that's the app's designed graceful-degradation path, not a bug; see
  // pages/help/CiteTab.tsx). Clicking is still exercised as smoke coverage of the handler.
  await expect(page.getByText(/Haber I, Jackson A, Thielscher A, Hai A, Tononi G\./)).toBeVisible();
  await expect(page.getByText(/doi\.org\/10\.1101\/2025\.10\.06\.680781/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy citation" })).toBeVisible();
  await page.getByRole("button", { name: "Copy citation" }).click();

  await page.getByRole("tab", { name: "Acknowledgments" }).click();
  // CardHeader renders its title as a <span> (see ui/Layout.tsx), not a heading element.
  await expect(page.getByText("SimNIBS CHARM Segmentation Pipeline")).toBeVisible();

  await page.getByRole("tab", { name: "Contact" }).click();
  await expect(page.getByText("Ido Haber")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open discussions" })).toBeVisible();

  // Dark theme
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await setTheme(page, "dark", () => page.getByRole("radio", { name: "Dark" }).click());
  await page.getByRole("link", { name: "Help", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Help" })).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "help-dark.png") });
});
