import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp } from "./_helpers";

/**
 * One rule, swept across the app: **an (i) icon opens on click, never on hover.**
 *
 * The maintainer's report was that the same glyph behaved two ways — a hover `Tooltip` on some
 * section headers, a click `Popover` on form fields. `ui/HelpPopover` is now the only help
 * affordance, and every trigger it renders carries `data-help-icon`, which is what makes this
 * sweep possible: it does not need a list of call sites, it finds them.
 *
 * Out of scope, deliberately: the nav rail's icon labels and the jobs rail's overflow count are
 * `Tooltip`s that repeat a *name*, not help — they carry no `data-help-icon`. So are the `?`
 * keyboard sheet and the scene pane's F/L/R/T view titles.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

/** Every page in the rail that has form content, plus the panels reached through it. */
const PAGES: { id: string; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "preprocess", label: "Pre-processing" },
  { id: "simulator", label: "Simulator" },
  { id: "optimizer", label: "Optimizer" },
  { id: "analyzer", label: "Analyzer" },
  { id: "settings", label: "Settings" },
];

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 45_000 });
});

test.afterAll(async () => {
  await app?.close();
});

/** Longer than the `Tooltip` delay (`delayDuration={400}` in ui/Overlay.tsx) plus a margin. */
const HOVER_DWELL_MS = 700;

test("no help icon anywhere opens anything on hover", async () => {
  for (const { id, label } of PAGES) {
    await gotoPage(page, id, label);
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", id, { timeout: 15_000 });

    const icons = page.locator("[data-help-icon]");
    const count = await icons.count();
    if (count === 0) continue;

    // Sampling the first few is enough and keeps the sweep quick: they are all the same
    // component, and the assertion below is about the component, not about each call site.
    for (let i = 0; i < Math.min(count, 4); i++) {
      const icon = icons.nth(i);
      if (!(await icon.isVisible())) continue;
      await icon.hover();
      await page.waitForTimeout(HOVER_DWELL_MS);
      await expect(page.locator("[role=tooltip]"), `${id} icon ${i}: hover opened a tooltip`).toHaveCount(0);
      await expect(page.locator(".help-popover"), `${id} icon ${i}: hover opened the popover`).toHaveCount(0);
    }
  }
});

test("every help icon is a keyboard-operable button that opens a popover on click", async () => {
  for (const { id, label } of PAGES) {
    await gotoPage(page, id, label);
    await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", id, { timeout: 15_000 });

    const icons = page.locator("[data-help-icon]");
    const count = await icons.count();
    if (count === 0) continue;

    for (let i = 0; i < Math.min(count, 4); i++) {
      const icon = icons.nth(i);
      if (!(await icon.isVisible())) continue;

      // a11y: a real button with an accessible name and the expanded state assistive tech reads.
      expect(await icon.evaluate((el) => el.tagName), `${id} icon ${i}`).toBe("BUTTON");
      await expect(icon, `${id} icon ${i}: unnamed`).not.toHaveAttribute("aria-label", "");
      await expect(icon).toHaveAttribute("aria-expanded", "false");

      await icon.click();
      await expect(page.locator(".help-popover"), `${id} icon ${i}: click opened nothing`).toBeVisible();
      await expect(icon).toHaveAttribute("aria-expanded", "true");

      // Esc dismisses, which is the other half of "it is a real popover".
      await page.keyboard.press("Escape");
      await expect(page.locator(".help-popover")).toHaveCount(0);
      await expect(icon).toHaveAttribute("aria-expanded", "false");
    }
  }
});

test("the help icon can be reached and opened from the keyboard alone", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", "preprocess", { timeout: 15_000 });
  const icon = page.getByTestId("step-help-convert_dicom");
  await expect(icon).toBeVisible();
  // The page restores its scroll position and its subject table on mount, and that settling can
  // steal focus back for a beat — so this retries the focus rather than asserting once, and reads
  // `document.activeElement` rather than OS window focus (the run is offscreen and owns no screen).
  await expect
    .poll(
      async () => {
        await icon.focus();
        return page.evaluate(() => document.activeElement?.getAttribute("data-testid"));
      },
      { timeout: 10_000 },
    )
    .toBe("step-help-convert_dicom");
  await page.keyboard.press("Enter");
  await expect(page.locator(".help-popover")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".help-popover")).toHaveCount(0);
  // Focus returns to where it came from — the popover does not strand the keyboard user. Radix
  // restores it on the close animation frame, so this polls rather than reading once.
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid")), { timeout: 10_000 })
    .toBe("step-help-convert_dicom");
});
