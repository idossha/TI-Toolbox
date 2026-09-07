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

/**
 * The overlap bug, measured rather than eyeballed (maintainer's screenshot of a live `sim · 101`:
 * "Placing Electrode:", "Using isotropic conductivities" and "Assembling FEM Matrix" drawn on top
 * of one another in blocks).
 *
 * Cause: one server event can carry a whole multi-line block, and the virtual list positions every
 * item absolutely at `index * 18px` — so an item holding nine lines of text painted over the eight
 * rows beneath it. The gallery's console is built through the same `jobEventsToLogLines` transform
 * from the same event shapes, including a real "Placing Electrode:" chunk, a `\r` progress counter
 * and a 500-character path.
 *
 * The assertion is geometric and pairwise: no two rendered lines may share any vertical space, and
 * no line may be taller than its 18 px row. Both are things only a real layout can answer.
 */
test("no two rendered log lines overlap, with follow on and after scrolling", async () => {
  await gotoPage(page, "dev", "Gallery");
  const console_ = page.getByTestId("gallery-job-console");
  await console_.scrollIntoViewIfNeeded();
  const lines = console_.locator(".job-console-lines");
  await expect(lines).toBeVisible();

  async function assertNoOverlap(where: string): Promise<number> {
    const boxes = await console_.locator(".job-console-line").evaluateAll((els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect();
        return { top: r.top, bottom: r.bottom, text: (el.textContent ?? "").slice(0, 60) };
      }),
    );
    expect(boxes.length, `${where}: rows are rendered`).toBeGreaterThan(3);
    for (const box of boxes) {
      // A row taller than its slot is the overlap waiting to happen.
      expect(box.bottom - box.top, `${where}: "${box.text}" fits its 18px row`).toBeLessThanOrEqual(18.5);
    }
    const sorted = [...boxes].sort((a, b) => a.top - b.top);
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1]!;
      const next = sorted[i]!;
      // Half a pixel of tolerance for sub-pixel layout; anything more is text over text.
      expect(next.top, `${where}: "${next.text}" starts below "${prev.text}"`).toBeGreaterThanOrEqual(prev.bottom - 0.5);
    }
    return boxes.length;
  }

  // Follow is on by default, so this is the state the maintainer was looking at: parked at the
  // tail of a stream. Scrolling back through the history must be just as clean.
  await assertNoOverlap("at the tail");
  await lines.evaluate((el) => {
    el.scrollTop = Math.round(el.scrollHeight / 2);
    el.dispatchEvent(new Event("scroll"));
  });
  await assertNoOverlap("mid-history");
  await lines.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });
  await assertNoOverlap("at the top");

  // The head of the transcript is where the multi-line event is, and it really did become one row
  // per line — while the `\r` progress counter collapsed to what a terminal would have left on
  // screen instead of becoming three rows.
  await expect(console_.getByText("definition: plane", { exact: true })).toHaveCount(1);
  await expect(console_.getByText("meshing 100 %", { exact: true })).toHaveCount(1);
  await expect(console_.getByText("meshing 1 %", { exact: true })).toHaveCount(0);
});
