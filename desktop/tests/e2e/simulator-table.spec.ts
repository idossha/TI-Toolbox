import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addJobRow, configureMontageJob, jobBlank, jobDetail, jobRows } from "./_jobs";

/**
 * The Simulator's **Jobs table** as a *table*: how wide its columns are, that the user can change
 * that, and that the row the 3-D pane is drawing is visibly the one the 3-D pane is drawing.
 *
 * Its own file, not `simulator.spec.ts`: that one is a serial narrative about the plan a run
 * builds, and these tests deliberately resize columns and write to local storage — state the
 * narrative should not inherit.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

const container = () => page.getByTestId("sim-jobs-table-container");
const montageRows = () => jobRows(page);

/** The rendered width of every column, read off the header cells. */
async function columnWidths(): Promise<number[]> {
  return page.locator("table.sim-jobs-table thead th").evaluateAll((cells) =>
    cells.map((c) => Math.round(c.getBoundingClientRect().width)),
  );
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });

  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");

  // Two real jobs, one of them multi-polar — the table's widest content.
  await configureMontageJob(page, montageRows().first(), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "mTI_F3F4_P3P4 · mTI",
  });
  await configureMontageJob(page, await addJobRow(page), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "F3_F4 · TI",
  });
  await expect(montageRows()).toHaveCount(2);
});

test.afterAll(async () => {
  await app?.close();
});

test("the columns fill the container exactly, with a fixed 96px actions column and no slack", async () => {
  const box = await container().evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
  expect(box.scrollWidth, "the montage table scrolls sideways").toBeLessThanOrEqual(box.clientWidth);

  const widths = await columnWidths();
  console.log("MONTAGE-COLS 1280", JSON.stringify(widths), "container", box.clientWidth);
  // Line 1 is Subject · Source · EEG net · Montage, plus the actions cell that spans both lines.
  expect(widths).toHaveLength(5);
  // Actions is the only fixed column, and it is exactly the three icon buttons wide.
  expect(widths[4]).toBe(96);
  // Room for the real names measured in the app: `GSN-HydroCel-185` (113px) and
  // `VAL_lhipp_flex_focality` (137px), each inside ~36px of select chrome.
  expect(widths[0]).toBeGreaterThanOrEqual(72);
  expect(widths[2]).toBeGreaterThanOrEqual(149);
  expect(widths[3]).toBeGreaterThanOrEqual(173);
  expect(widths.reduce((a, b) => a + b, 0)).toBe(box.clientWidth);
});

test("a header boundary can be dragged, and the width is remembered", async () => {
  const before = await columnWidths();
  const handle = page.getByRole("separator", { name: "Resize EEG net column" });
  const box = (await handle.boundingBox())!;

  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();

  const after = await columnWidths();
  expect(after[2], "the dragged column did not grow").toBeGreaterThan(before[2]! + 20);
  // The table still fits: what the net column took came out of the columns beside it.
  const box2 = await container().evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
  expect(box2.scrollWidth).toBeLessThanOrEqual(box2.clientWidth);
  expect(after.reduce((a, b) => a + b, 0)).toBe(box2.clientWidth);
  expect(after[4]).toBe(96);

  const stored = await page.evaluate(() => window.localStorage.getItem("tit-sim-jobs-columns-v2"));
  expect(stored, "the drag was not persisted").toBeTruthy();
  expect(JSON.parse(stored!).net).toBeGreaterThan(before[2]! + 20);

  // The keyboard moves the same boundary.
  await handle.focus();
  await handle.press("ArrowLeft");
  const narrower = await columnWidths();
  expect(narrower[2]).toBeLessThan(after[2]!);
});

test("the row the 3-D pane is drawing is tinted, and up/down moves it", async () => {
  const rows = montageRows();
  await jobBlank(rows.nth(1)).click();
  await expect(rows.nth(1)).toHaveAttribute("data-active", "true");
  await expect(rows.nth(1)).toHaveAttribute("aria-selected", "true");

  // --accent-soft in light: #E6EEFC. Read off the CELL, because `.data-table tbody td` paints
  // every cell --surface and would otherwise cover the row's own background.
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  const tint = await rows.nth(1).locator("td").first().evaluate((td) => getComputedStyle(td).backgroundColor);
  expect(tint).toBe("rgb(230, 238, 252)");
  const bar = await rows.nth(1).locator("td").first().evaluate((td) => getComputedStyle(td).boxShadow);
  expect(bar).toContain("2px");

  // An inactive row keeps the plain surface.
  const plain = await rows.nth(0).locator("td").first().evaluate((td) => getComputedStyle(td).backgroundColor);
  expect(plain).not.toBe(tint);

  // Dark theme uses the dark pair of the same tokens, not a hard-coded colour.
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  const darkTint = await rows.nth(1).locator("td").first().evaluate((td) => getComputedStyle(td).backgroundColor);
  expect(darkTint).toBe("rgb(27, 42, 74)");
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));

  await rows.nth(1).press("ArrowUp");
  await expect(rows.nth(0)).toHaveAttribute("data-active", "true");
  await expect(rows.nth(1)).not.toHaveAttribute("data-active", "true");
});

test("the 3-D pane names the row it is drawing, in the row's own accent", async () => {
  const rows = montageRows();
  const chip = page.getByTestId("scene-pane-showing");

  // Row 2 is the uni-polar one; row 1 the multi-polar. Both name themselves in the pane.
  for (const index of [1, 0]) {
    await jobBlank(rows.nth(index)).click();
    await expect(rows.nth(index)).toHaveAttribute("data-active", "true");
    const montage = await rows.nth(index).getAttribute("data-montage-row");
    await expect(chip).toHaveText(`Showing: ${montage} · GSN-HydroCel-185`);
  }

  // The chip's colours ARE the row's colours — the same two tokens, read back computed.
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  const rowTint = await rows.nth(0).locator("td").first().evaluate((td) => getComputedStyle(td).backgroundColor);
  const chipStyle = await chip.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { background: cs.backgroundColor, bar: cs.borderLeftColor, barWidth: cs.borderLeftWidth };
  });
  expect(chipStyle.background).toBe(rowTint);
  expect(chipStyle.bar).toBe("rgb(31, 91, 215)"); // --accent, light
  expect(chipStyle.barWidth).toBe("2px");

  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  const darkRow = await rows.nth(0).locator("td").first().evaluate((td) => getComputedStyle(td).backgroundColor);
  const darkChip = await chip.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { background: cs.backgroundColor, bar: cs.borderLeftColor };
  });
  expect(darkChip.background).toBe(darkRow);
  expect(darkChip.bar).toBe("rgb(127, 166, 255)"); // --accent, dark
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
});

/**
 * The defect this guards, from the maintainer's screenshot of the six-column table: *"Montage
 * select truncated to 'Ch…', nets 'BioSemi-128-A1…', Pairs 'E09…'"*. No control on a job row may
 * render narrower than the text it is showing.
 */
test("no select or pairs text is truncated at 1280 or 1600", async () => {
  for (const width of [1280, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    console.log("JOBS-COLS", width, JSON.stringify(await columnWidths()));
    const overflowing = await page
      .locator("table.sim-jobs-table .select-trigger span, table.sim-jobs-table [data-cell='pairs']")
      .evaluateAll((els) =>
        els
          .filter((el) => el.scrollWidth > el.clientWidth + 1)
          .map((el) => `${el.textContent} (${el.scrollWidth} > ${el.clientWidth})`),
      );
    expect(overflowing, `truncated at ${width}`).toEqual([]);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
});

/** "Nothing moves on interaction": the rects of every job cell, before and after a row is made
 *  active and a source is switched back and forth. */
test("configuring a row moves no cell in another row", async () => {
  const rects = () =>
    page.locator("table.sim-jobs-table tbody td").evaluateAll((cells) =>
      cells.map((c) => {
        const r = c.getBoundingClientRect();
        return [Math.round(r.x), Math.round(r.width)];
      }),
    );
  await page.keyboard.press("Escape"); // no popup left open by an earlier test
  const before = await rects();
  // Making a row active, then the other: a tint changes, no geometry may.
  await jobBlank(montageRows().first()).click();
  await jobBlank(montageRows().nth(1)).click();
  expect(await rects()).toEqual(before);
});

/**
 * Line 2's geometry, from the maintainer's screenshot of the first two-line draft: *"the second
 * layer is vertically clipped, the chip floats under the Source column while the pairs sit
 * mid-row, the empty rows leave a blank second line, and a stray vertical rule separates the
 * action column."* Every claim below is one of those.
 */
test("line 2 is unclipped, on line 1's grid, and every job is the same height", async () => {
  const rows = montageRows();
  // Nothing is cut off: no cell on either line scrolls its own content.
  const clipped = await page
    .locator("table.sim-jobs-table tbody td")
    .evaluateAll((cells) =>
      cells
        .filter((c) => c.scrollHeight > c.clientHeight + 1)
        .map((c) => `${c.getAttribute("data-cell")} (${c.scrollHeight} > ${c.clientHeight})`),
    );
  expect(clipped, "a cell clips its content vertically").toEqual([]);

  // One height for every job of the same shape, configured or not — the table does not jump when
  // a montage is picked. (An mTI job's four pairs and four currents legitimately take a second
  // wrapped line at 1280; a TI job and an empty job must agree.)
  const heights = await page.evaluate(() => {
    const out: number[] = [];
    for (const line1 of document.querySelectorAll("tr[data-job-row]")) {
      const line2 = line1.nextElementSibling!;
      out.push(Math.round(line1.getBoundingClientRect().height + line2.getBoundingClientRect().height));
    }
    return out;
  });
  console.log("JOBS-HEIGHTS", JSON.stringify(heights));

  // The chip starts where the Source column starts; the currents end where Montage ends; line 2
  // stays inside its own job.
  const geom = await page.evaluate(() => {
    const line1 = document.querySelector("tr[data-job-row]")!;
    const line2 = line1.nextElementSibling!;
    const px = (el: Element | null) => (el ? el.getBoundingClientRect() : null);
    return {
      source: px(line1.querySelector('td[data-cell="source"]'))!.x,
      chip: px(line2.querySelector('td[data-cell="polarity"] .chip'))!.x,
      montageRight: px(line1.querySelector('td[data-cell="montage"]'))!.right,
      currentsRight: px(line2.querySelector(".job-currents"))!.right,
      line2Bottom: px(line2)!.bottom,
      detailBottom: px(line2.querySelector(".job-line2"))!.bottom,
    };
  });
  console.log("JOBS-GEOM", JSON.stringify(geom));
  expect(Math.abs(geom.chip - geom.source), "the chip is not on the Source column's left edge").toBeLessThanOrEqual(8);
  expect(Math.abs(geom.currentsRight - geom.montageRight), "the currents do not end at the Montage column").toBeLessThanOrEqual(8);
  expect(geom.detailBottom).toBeLessThanOrEqual(geom.line2Bottom);

  // An empty job says so on line 2, at the same height as a configured one.
  const empty = await addJobRow(page);
  await expect(jobDetail(empty).locator(".job-line2-empty")).toHaveText(/Pairs and currents appear/);
  const withEmpty = await page.evaluate(() => {
    const out: number[] = [];
    for (const line1 of document.querySelectorAll("tr[data-job-row]")) {
      const line2 = line1.nextElementSibling!;
      out.push(Math.round(line1.getBoundingClientRect().height + line2.getBoundingClientRect().height));
    }
    return out;
  });
  // The empty job is exactly as tall as the configured TI job beside it.
  expect(withEmpty[2], `an unconfigured job is a different height: ${withEmpty.join(", ")}`).toBe(withEmpty[1]);
  await empty.getByRole("button", { name: /^Remove job / }).click();
  await expect(rows).toHaveCount(2);
});

/* Evidence (§8.1), never the assertion. */
test("records the jobs table", async () => {
  await container().screenshot({ path: "tests/e2e/artifacts/jobs-table-sim.png" });
  for (const width of [1280, 1600] as const) {
    await page.setViewportSize({ width, height: 900 });
    await container().screenshot({ path: `tests/e2e/artifacts/jobs-table-sim-v3-${width}.png` });
  }
  await page.setViewportSize({ width: 1280, height: 800 });
});
