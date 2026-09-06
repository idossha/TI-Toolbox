import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, launchElectronApp, openPalette } from "./_helpers";
import { artifactDir, captureScreen, writeMetrics, type PageMetrics } from "./_metrics";

/**
 * The shared instrument (DESIGN.md §12.2, program U10): every page in the rail, in both themes, at
 * both sizes, with `metrics.json` written beside the pictures.
 *
 * This is not a pass/fail spec about any one page — the per-page limits live in each lane's own
 * spec (§12.3). This is the *measurement*: it produces the artifacts every lane iterates against
 * and the critic panel reviews. It fails only when a page cannot be reached at all, because a page
 * that will not open has no number worth arguing about.
 *
 * The page list is read from the rail rather than hard-coded, so the day lane B3's `optimizer`
 * replaces `optimizer-flex` this spec captures the new page with no edit here.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "screens";

/** The two sizes every acceptance number in §12.3 is stated at. */
const SIZES = [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
] as const;
const THEMES = ["light", "dark"] as const;

/** The subject the mock fixture is populated for; a page with no subject measures its empty state. */
const SUBJECT = "ernie";

let app: ElectronApplication;
let page: Page;
const rows: PageMetrics[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  // Scope the whole run to one subject, through the palette — the way a person does it. A page
  // measured with no subject is measuring its empty state, which is not the populated number
  // §12.3 states its limits against.
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
});

test.afterAll(async () => {
  if (rows.length > 0) await writeMetrics(RUN_ID, rows);
  await app?.close();
});

/** The rail's page ids, in rail order — the app's own statement of which pages exist. */
async function railPages(target: Page): Promise<string[]> {
  return target.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="nav-item-"]')).map((el) =>
      (el.dataset.testid ?? el.getAttribute("data-testid") ?? "").replace(/^nav-item-/, ""),
    ),
  );
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`screens — ${theme} at ${size.width}x${size.height}`, async () => {
      test.setTimeout(300_000);
      await page.setViewportSize(size);
      const ids = await railPages(page);
      expect(ids.length).toBeGreaterThan(0);

      for (const id of ids) {
        await page.getByTestId(`nav-item-${id}`).click();
        await expectPage(page, id);
        const row = await captureScreen(page, {
          runId: RUN_ID,
          pageId: id,
          theme,
          width: size.width,
          height: size.height,
          // The page's own loaded marker: `data-page` is set where the page mounts, and the
          // skeleton wait inside `captureScreen` covers the data that lands after it.
          waitFor: async () => {
            await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", id);
          },
        });
        rows.push(row);
      }
    });
  }
}

test("the shell's own numbers are within their limits at both sizes", async () => {
  // Read from the rows the four capture tests produced, so this asserts the same measurement the
  // artifacts carry rather than a second, differently-taken one.
  const at = (id: string, theme: string, width: number): PageMetrics | undefined =>
    rows.find((r) => r.page === id && r.theme === theme && r.width === width);

  for (const width of [1280, 1440]) {
    const subjects = at("overview", "light", width);
    expect(subjects, `no capture for overview at ${width}`).toBeDefined();
    // U7/Q1: icons below 1440, labels at or above it.
    expect(subjects!.panes.nav).toBe(width >= 1440 ? 216 : 56);
    // §8: no page header outside Settings and Help.
    expect(subjects!.pageHeaderHeight).toBe(0);
    // U8: the shell contributes exactly the connection and version cells; everything else on the
    // left was registered by the page on screen.
    expect(subjects!.statusCells).toEqual(expect.arrayContaining(["connection", "version"]));
    expect(subjects!.statusCells).not.toContain("ras");
    expect(subjects!.statusCells).not.toContain("space");
    expect(subjects!.statusCells).not.toContain("renderer");
  }

  const jobs = at("jobs", "light", 1280);
  expect(jobs, "no capture for jobs at 1280").toBeDefined();
  expect(jobs!.statusCells).not.toContain("ras");
  expect(jobs!.pageHeaderHeight).toBe(0);

  console.log(`screens: ${rows.length} captures in ${artifactDir(RUN_ID)}`);
});
