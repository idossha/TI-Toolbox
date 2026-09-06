import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";

/**
 * The Simulator's montage table as a *table*: how wide its columns are, that the user can change
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

const container = () => page.getByTestId("montage-table-container");
const montageRows = () => page.locator("tr[data-montage-row]");

async function pickNet(row: ReturnType<typeof montageRows>, net: string) {
  await row.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: net, exact: true }).click();
}

async function pickMontage(row: ReturnType<typeof montageRows>, option: string) {
  await row.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** The rendered width of every column, read off the header cells. */
async function columnWidths(): Promise<number[]> {
  return page.locator("table.montage-table thead th").evaluateAll((cells) =>
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

  // Two real rows, one of them multi-polar — the table's widest content.
  const first = montageRows().first();
  await pickNet(first, "GSN-HydroCel-185");
  await pickMontage(first, "mTI_F3F4_P3P4 · mTI");
  await page.getByRole("button", { name: "Add row", exact: true }).click();
  const second = montageRows().nth(1);
  await pickNet(second, "GSN-HydroCel-185");
  await pickMontage(second, "F3_F4 · TI");
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
  expect(widths).toHaveLength(5);
  // Actions is the only fixed column, and it is exactly the three icon buttons wide.
  expect(widths[4]).toBe(96);
  // Every other column got room for its content — no 40px sliver, and nothing left over.
  expect(widths[0]).toBeGreaterThanOrEqual(90);
  expect(widths[1]).toBeGreaterThanOrEqual(110);
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
  expect(after[0], "the dragged column did not grow").toBeGreaterThan(before[0]! + 20);
  // The table still fits: what the net column took came out of the columns beside it.
  const box2 = await container().evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
  expect(box2.scrollWidth).toBeLessThanOrEqual(box2.clientWidth);
  expect(after.reduce((a, b) => a + b, 0)).toBe(box2.clientWidth);
  expect(after[4]).toBe(96);

  const stored = await page.evaluate(() => window.localStorage.getItem("tit-montage-columns-v1"));
  expect(stored, "the drag was not persisted").toBeTruthy();
  expect(JSON.parse(stored!).net).toBeGreaterThan(before[0]! + 20);

  // The keyboard moves the same boundary.
  await handle.focus();
  await handle.press("ArrowLeft");
  const narrower = await columnWidths();
  expect(narrower[0]).toBeLessThan(after[0]!);
});

test("the row the 3-D pane is drawing is tinted, and up/down moves it", async () => {
  const rows = montageRows();
  await rows.nth(1).locator("td.mono").click();
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
    await rows.nth(index).locator("td.mono").click();
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

/* Evidence (§8.1), never the assertion. */
test("records the montage table", async () => {
  await container().screenshot({ path: "tests/e2e/artifacts/montage-table-v3.png" });
});
