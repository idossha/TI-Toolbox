import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette, setTheme } from "./_helpers";

// Screenshots the design-system gallery and the Subjects page in both themes, for design QA
// (DESIGN.md §8: "one Playwright screenshot per screen in both themes ... committed to
// tests/e2e/artifacts/"). The gallery route only exists in a development-mode build (it is
// tree-shaken out of a real production build) — see package.json's `pree2e` (`--mode
// development`) and pages/dev/index.tsx (`enabled: import.meta.env.DEV`).
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
});

test.afterEach(async () => {
  await app?.close();
});

// The shared console's scroll geometry and local Clear are the R2 gate and live in
// `tests/e2e/terminal.spec.ts`, which drives this same gallery console. The case that used to sit
// here asserted the identical things but set `scrollTop` and `scrollLeft` in one `evaluate` while
// Follow tail was still re-parking the box, so its read-back `scrollLeft` was 0.

/**
 * The shell is a fixed-viewport app (`.shell-content` scrolls internally; `<body>` never grows),
 * so Playwright's `fullPage` screenshot — which captures the document's own scroll height — sees
 * only one viewport of a long page like the gallery. This temporarily lets every ancestor grow to
 * its content's real height so `fullPage` has something to capture, then puts it back.
 */
async function withFullContentHeight<T>(target: Page, fn: () => Promise<T>): Promise<T> {
  const style = await target.addStyleTag({
    content: `
      html, body, #root, .shell, .shell-main, .shell-content { height: auto !important; min-height: 0 !important; overflow: visible !important; }
      .jobs-rail { position: static !important; }
    `,
  });
  try {
    return await fn();
  } finally {
    await style.evaluate((el: Element) => el.remove());
  }
}

test("gallery and overview screenshot cleanly in light and dark", async () => {
  // Overview, light — and light because U9 says so: a fresh profile with no stored preference
  // renders light on any machine, not "light because this one happens not to force dark".
  await page.screenshot({ path: join(ARTIFACTS, "overview-light.png") });

  await gotoPage(page, "dev", "Gallery");
  await expect(page.getByRole("heading", { name: "Design gallery" })).toBeVisible();

  // Real assertion (not just a screenshot/theme attribute): a primitive actually works, not just
  // renders — the "Combine ROIs" Switch swatch really toggles its checked state on click.
  const combineRoisSwitch = page.getByRole("switch", { name: "Combine ROIs" });
  await expect(combineRoisSwitch).toHaveAttribute("aria-checked", "true");
  await combineRoisSwitch.click();
  await expect(combineRoisSwitch).toHaveAttribute("aria-checked", "false");

  await setTheme(page, "light", () => page.getByRole("button", { name: "Light", exact: true }).click());
  await withFullContentHeight(page, () => page.screenshot({ path: join(ARTIFACTS, "gallery-light.png"), fullPage: true }));

  await setTheme(page, "dark", () => page.getByRole("button", { name: "Dark", exact: true }).click());
  await withFullContentHeight(page, () => page.screenshot({ path: join(ARTIFACTS, "gallery-dark.png"), fullPage: true }));

  // Theme persists across an in-app navigation (same document, memory router). Assert
  // `data-theme` explicitly right before this screenshot too — an in-app route change is a
  // React remount of the page tree, not a document reload, so nothing should touch the stamp
  // set on <html> above, but asserting it here (rather than trusting the earlier assertion to
  // still hold) is what makes this capture deterministic instead of racing the navigation.
  await gotoPage(page, "overview", "Overview");
  // Not a heading: DESIGN.md §8 puts the page-header budget at 0px outside Settings and Help, so
  // the shell's own statement of which screen is on is what a spec waits for.
  await expectPage(page, "overview");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: join(ARTIFACTS, "subjects-dark.png") });
});

test("the shell's chrome, the palette and a full-bleed page screenshot in both themes", async () => {
  // A run screen, both themes: this is where the rail groups, the context bar and the status bar
  // are read side by side with a page's own content.
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await page.screenshot({ path: join(ARTIFACTS, "simulator-light.png") });

  await openPalette(page);
  await page.screenshot({ path: join(ARTIFACTS, "palette-light.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("palette-input")).toHaveCount(0);

  await setTheme(page, "dark");
  await page.screenshot({ path: join(ARTIFACTS, "simulator-dark.png") });
  await openPalette(page);
  await page.screenshot({ path: join(ARTIFACTS, "palette-dark.png") });
  await page.keyboard.press("Escape");

  // The Viewer is the only full-bleed page today: its own `.viewer-page` wrapper (`.page-layout`
  // + `.page-layout-full-bleed`, ui/components.css) negates the shell's content padding, so it
  // must fill the shell's content box edge to edge, and neither it nor the document may grow a
  // second scrollbar (plan §1, DESIGN.md §4.1). (The dev-only `viewer-dev` harness this test used
  // to exercise was un-vendored along with the bundled Tetravox engine, W5/R2 item 8 — the real
  // Viewer page now carries the same full-bleed contract, so the check moved here. V1 replaced
  // the embed with a selector; the full-bleed contract is unchanged and is what is measured.)
  await gotoPage(page, "viewer", "Viewer");
  await expect(page.getByTestId("viewer-source-bar")).toBeVisible();
  const geometry = await page.evaluate(() => {
    const content = document.querySelector(".shell-content") as HTMLElement;
    const pane = document.querySelector(".viewer-page") as HTMLElement;
    const box = (el: HTMLElement) => {
      const r = el.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom) };
    };
    return {
      content: box(content),
      pane: box(pane),
      contentScrollsX: content.scrollWidth > content.clientWidth,
      contentScrollsY: content.scrollHeight > content.clientHeight,
      documentScrolls: document.documentElement.scrollHeight > document.documentElement.clientHeight,
    };
  });
  expect(geometry.pane.left).toBe(geometry.content.left);
  expect(geometry.pane.right).toBe(geometry.content.right);
  expect(geometry.pane.top).toBe(geometry.content.top);
  expect(geometry.pane.bottom).toBe(geometry.content.bottom);
  expect(geometry.contentScrollsX).toBe(false);
  expect(geometry.contentScrollsY).toBe(false);
  expect(geometry.documentScrolls).toBe(false);

  await page.screenshot({ path: join(ARTIFACTS, "viewer-dark.png") });
  await setTheme(page, "light");
  await page.screenshot({ path: join(ARTIFACTS, "viewer-light.png") });

  // §11: the bottom status bar is gone entirely, so the Viewer registers nothing into one and
  // leaving the page cannot leave a stale cell behind — there is no bar to leave it in. What the
  // shell still states on every page is the connection, in the context bar.
  await page.getByTestId("viewer-select-subject").getByRole("combobox").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await expect(page.getByTestId("viewer-plan")).toBeVisible({ timeout: 15_000 });
  await gotoPage(page, "overview", "Overview");
  await expectPage(page, "overview");
  await expect(page.locator(".status-bar")).toHaveCount(0);
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
  await expect(page.getByTestId("connection-state")).toHaveCount(1);
});
