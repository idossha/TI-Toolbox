/**
 * The Jobs table's CPU and RSS cells carry `peak · avg x` and are never cut off — with the detail
 * pane closed (full width) and open (the table has the left half). `jobs-rail.css` gives the two
 * columns widths measured against the widest realistic strings ("1106 % · avg 368 %",
 * "50.2 GB · avg 16.1 GB"); this spec is what keeps those widths honest when a font or a column
 * changes. Offscreen like every jobs spec (`_helpers.launchElectronApp`).
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

const MOCK = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
});
test.afterEach(async () => {
  await app.close();
});

async function seedFinishedJob(kind: string, subject: string) {
  const r = await fetch(`${MOCK}/api/jobs`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({ kind, config: { subject_id: subject, __mock_fast: true }, subject_ids: [subject], tags: ["e2e-columns"] }),
  });
  expect(r.status).toBe(201);
  return ((await r.json()) as { id: string }).id;
}

async function cellOverflow(table: ReturnType<Page["getByTestId"]>) {
  return table.locator("tbody tr td").evaluateAll((cells) =>
    cells
      .map((td) => {
        const span = td.querySelector<HTMLElement>(".jobs-cell-resource");
        return span ? { text: span.textContent?.trim() ?? "", clipped: span.scrollWidth > td.clientWidth || td.scrollWidth > td.clientWidth } : null;
      })
      .filter((c): c is { text: string; clipped: boolean } => c !== null),
  );
}

test("CPU and RSS cells are whole with the detail pane closed and open", async () => {
  const id = await seedFinishedJob("ex", "ernie");
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectLauncher(page, MOCK, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page.getByTestId("jobs-toolbar")).toBeVisible();
  const table = page.getByTestId("jobs-table");
  await expect(table.getByText("ex", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  // Wait for the seeded job to finish so the cells carry a peak AND an average.
  await expect
    .poll(async () => (await (await fetch(`${MOCK}/api/jobs/${id}`, { headers: { authorization: `Bearer ${TOKEN}` } })).json()).status.state, { timeout: 15_000 })
    .toBe("succeeded");
  await expect(table.locator(".jobs-cell-resource-avg").first()).toBeVisible();

  for (const width of [1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    const closed = await cellOverflow(table);
    expect(closed.length, `resource cells at ${width}`).toBeGreaterThan(0);
    expect(closed.filter((c) => c.clipped), `clipped with pane closed at ${width}`).toEqual([]);
    expect(closed.every((c) => c.text.includes("· avg")), `every cell shows peak · avg at ${width}`).toBe(true);
  }
  await table.getByRole("row", { name: /ernie/ }).first().click();
  await expect(page.getByTestId("page-right-pane")).toBeVisible();
  await page.getByTestId("page-right-pane").getByTestId("pane-collapse").click();
  await expect(page.getByTestId("page-right-pane")).toBeHidden();
  await table.getByRole("row", { name: /ernie/ }).first().click();
  await expect(page.getByTestId("page-right-pane")).toBeVisible();
  for (const width of [1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    await expect(page.getByTestId("page-right-pane")).toBeVisible();
    const geometry = await table.locator("thead th").evaluateAll((cells) => cells.slice(1).map((cell) => cell.getBoundingClientRect().width));
    expect(Math.max(...geometry) - Math.min(...geometry), "no oversized Subjects gap in split view").toBeLessThan(66);
    const work = await page.locator(".jobs-page-work").boundingBox();
    const detail = await page.getByTestId("page-right-pane").boundingBox();
    expect(work!.x + work!.width).toBeLessThanOrEqual(detail!.x);
    const open = await cellOverflow(table);
    expect(open.filter((c) => c.clipped), `clipped with pane open at ${width}`).toEqual([]);
  }
});
