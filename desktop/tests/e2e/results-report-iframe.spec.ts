/**
 * Results renders a real generated report in its sandboxed iframe, under the real report CSP,
 * and the report's own script runs there.
 *
 * The pages are the real simulation and ex-search generators' output on synthetic runs
 * (`dev/regen_mock_reports.py`), and the mock serves them with `tit/server/routes/files.py`'s
 * `REPORT_CSP` (script-src 'unsafe-inline', img-src data:, sandbox allow-scripts; pinned in
 * `tests/mock-server/contract.test.ts`). Expected values come from the generators' source: the
 * section titles are read from each generator's `toc` list, not retyped; the envelope figure is the
 * 124 px wide ramp the regen script authors.
 *
 * What a failure here means: the report's inline script or data: images are blocked (a CSP or
 * sandbox regression), the iframe shows a stub instead of the generator's page, or a simulation
 * with no report shows an empty frame instead of its files.
 *
 * Offscreen (TIT_E2E_OFFSCREEN=1) against the mock server, one Playwright run at a time:
 * `npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/results-report-iframe.spec.ts`.
 */
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Frame, type Locator, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SIM_REPORT = "ernie/simulation_report_20260801_110000";
const EX_REPORT = "ernie/ex_search_report_20260812_093000";

/** The `(anchor, title)` pairs of a generator's `toc = [...]` list, read from its source. */
function tocTitles(generator: string): string[] {
  const source = readFileSync(join(__dirname, "..", "..", "..", "tit", "reporting", "generators", `${generator}.py`), "utf8");
  const block = /^\s*toc = \[([\s\S]*?)^\s*\]/m.exec(source);
  if (!block) throw new Error(`no toc list in ${generator}.py`);
  const titles = [...block[1]!.matchAll(/\("([a-z_]+)",\s*"([^"]+)"/g)].map((m) => m[2]!);
  expect(titles.length, `${generator}.py toc`).toBeGreaterThanOrEqual(4);
  return titles;
}

/** A contents link's own title: its text, without the status pill a section may carry. */
function linkTitles(links: Locator): Promise<string[]> {
  return links.evaluateAll((anchors) =>
    anchors.map((a) => [...a.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent ?? "").join("").trim()),
  );
}

let app: ElectronApplication;
let page: Page;
const cspErrors: string[] = [];

test.beforeEach(async () => {
  cspErrors.length = 0;
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-report-iframe-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  // Console messages of every frame, the report's included: a blocked inline script or data:
  // image is logged as "Refused to ... Content Security Policy ...".
  page.on("console", (message) => {
    if (/Content Security Policy/i.test(message.text())) cspErrors.push(message.text());
  });
  page.on("pageerror", (error) => cspErrors.push(`pageerror: ${error.message}`));
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId("results-subject-ernie").click();
  await expect(page.getByTestId("results-tree").getByRole("treeitem").first()).toBeVisible({ timeout: 20_000 });
});
test.afterEach(async () => {
  await app?.close();
});

async function reportFrame(): Promise<Frame> {
  const iframe = page.getByTestId("results-report-frame");
  await expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
  const frame = await (await iframe.elementHandle())!.contentFrame();
  if (!frame) throw new Error("the report iframe has no frame");
  await frame.waitForLoadState("load");
  return frame;
}

test("a simulation report renders its sections, its data: figure and its own script under the real CSP", async () => {
  await page.getByTestId(`results-node-report:ernie:${SIM_REPORT}`).click();
  await expect(page.getByTestId("results-report-frame")).toHaveAttribute("src", `/api/files/report/${encodeURIComponent(SIM_REPORT)}`);
  const frame = await reportFrame();

  // The contents rail lists the generator's sections, in its order.
  const expected = tocTitles("simulation");
  const rail = frame.getByRole("navigation", { name: "Report contents" });
  const links = rail.locator('a[href^="#"]:not(.brand)');
  await expect(links).toHaveCount(expected.length);
  expect(await linkTitles(links)).toEqual(expected);
  // Every section but the verdict (whose heading is the headline) is headed by its title.
  for (const title of expected.slice(1)) await expect(frame.getByRole("heading", { level: 2, name: title, exact: true })).toBeVisible();
  await expect(frame.getByRole("heading", { level: 1, name: "Thalamus", exact: true })).toBeVisible();

  // The envelope figure is a data: image, decoded at the ramp's own width.
  const figure = frame.locator("#field img").first();
  await expect(figure).toHaveAttribute("src", /^data:/);
  await expect.poll(() => figure.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBe(124);

  // The report's inline script ran: the theme button starts in "system" and cycles to "light".
  const theme = frame.getByRole("button", { name: "Switch colour theme" });
  await expect(theme).toHaveText("Theme: system");
  await theme.click();
  await expect(theme).toHaveText("Theme: light");
  expect(await frame.locator("html").getAttribute("data-theme")).toBe("light");

  expect(cspErrors).toEqual([]);
});

test("an ex-search report's ranked table sorts in place when a header is clicked", async () => {
  await page.getByTestId(`results-node-report:ernie:${EX_REPORT}`).click();
  const frame = await reportFrame();
  const expected = tocTitles("ex_search");
  const links = frame.getByRole("navigation", { name: "Report contents" }).locator('a[href^="#"]:not(.brand)');
  expect(await linkTitles(links)).toEqual(expected);

  const table = frame.locator("table.sortable").first();
  const headers = table.locator("thead th");
  // The script marks every header sortable, then the clicked one ascending and only that one.
  await expect(headers.first()).toHaveAttribute("aria-sort", "none");
  const column = (await headers.count()) - 1; // the last column is numeric in the ranked table
  await headers.nth(column).click();
  await expect(headers.nth(column)).toHaveAttribute("aria-sort", "ascending");
  for (let i = 0; i < column; i += 1) await expect(headers.nth(i)).toHaveAttribute("aria-sort", "none");
  const values = await table.locator(`tbody tr td:nth-child(${column + 1})`).evaluateAll((cells) =>
    cells.map((c) => Number((c as HTMLElement).dataset.v ?? c.textContent)),
  );
  expect(values.length).toBeGreaterThan(1);
  expect(values.every((v) => Number.isFinite(v))).toBe(true);
  expect(values).toEqual([...values].sort((a, b) => a - b));
  await headers.nth(column).click();
  await expect(headers.nth(column)).toHaveAttribute("aria-sort", "descending");

  expect(cspErrors).toEqual([]);
});

test("a simulation with no report shows its files, not an empty report frame", async () => {
  await page.getByTestId("results-node-simulation:ernie:L_Insula").click();
  await expect(page.getByTestId("results-files")).toContainText("TI_max · subject");
  await expect(page.getByTestId("results-report-frame")).toHaveCount(0);
  // ...while the Thalamus simulation, which has one, shows it inline.
  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();
  await expect(page.getByTestId("results-report-frame")).toHaveAttribute("src", `/api/files/report/${encodeURIComponent(SIM_REPORT)}`);
});
