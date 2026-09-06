/**
 * R2 gate (IMPLEMENTATION_PLAN.md): the one shared interactive log renderer — `ui/Jobs.tsx`'s
 * `JobConsole`, used by all four run pages, the Jobs rail and the gallery — really scrolls in both
 * directions and really clears locally.
 *
 * Geometry is the point of doing this in Electron rather than jsdom: `scrollHeight`, `scrollWidth`
 * and the two offsets are all zero in a DOM that lays nothing out. The source-key/watermark
 * semantics (a cleared source shows the next higher-sequence line, and its watermark does not carry
 * to another source key, while the input line array is left byte-for-byte alone) are proved without
 * a browser in `tests/unit/job-console.test.tsx`; the same control's presence on a run page is
 * asserted in `preprocess.spec.ts` and in the Jobs rail in `jobs.spec.ts`.
 *
 * The gallery route only exists in a development-mode build — see package.json's `pree2e`.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
});

test.afterEach(async () => {
  await app?.close();
});

test("the shared console overflows in both axes, scrolls, and clears without touching its input", async () => {
  await gotoPage(page, "dev", "Gallery");
  const console_ = page.getByTestId("gallery-job-console");
  await console_.scrollIntoViewIfNeeded();
  const lines = console_.locator(".job-console-lines");
  await expect(lines).toBeVisible();

  // 100 demo lines in a 160px-tall box, one of them a very long command: both axes overflow.
  const box = await lines.evaluate((el) => ({
    clientHeight: el.clientHeight,
    scrollHeight: el.scrollHeight,
    clientWidth: el.clientWidth,
    scrollWidth: el.scrollWidth,
  }));
  expect(box.clientHeight).toBeGreaterThan(0);
  expect(box.scrollHeight).toBeGreaterThan(box.clientHeight);
  expect(box.scrollWidth).toBeGreaterThan(box.clientWidth);

  // Follow off first: follow-tail re-runs `scrollToIndex` on every commit, which parks the box at
  // the bottom-left, so a reader scrolls back through history exactly this way (see the lane note's
  // proposed `ui/VirtualList.tsx` change to keep `scrollLeft` while following).
  const follow = console_.getByRole("switch", { name: "Follow tail" });
  await follow.click();
  await expect(follow).toHaveAttribute("aria-checked", "false");

  // Scrolling moves both offsets — virtualisation keeps rows mounted as it goes.
  const left = await lines.evaluate((el) => {
    el.scrollLeft = 120;
    el.dispatchEvent(new Event("scroll"));
    return el.scrollLeft;
  });
  const top = await lines.evaluate((el) => {
    el.scrollTop = 60;
    el.dispatchEvent(new Event("scroll"));
    return el.scrollTop;
  });
  const offsets = { top, left };
  expect(offsets.top).toBeGreaterThan(0);
  expect(offsets.left).toBeGreaterThan(0);
  await expect(console_.locator(".job-console-line").first()).toBeVisible();

  // Clear is local and presentational: every rendered line goes, the designed empty state appears.
  await console_.getByRole("button", { name: "Clear terminal" }).click();
  await expect(console_.locator(".job-console-line")).toHaveCount(0);
  await expect(console_.getByTestId("job-console-cleared")).toBeVisible();

  // Follow is retained across the clear (it is still the "off" the reader chose above), and the
  // filter box is still usable and empty.
  await expect(follow).toHaveAttribute("aria-checked", "false");
  await expect(console_.getByLabel("Filter log lines")).toHaveValue("");
});
