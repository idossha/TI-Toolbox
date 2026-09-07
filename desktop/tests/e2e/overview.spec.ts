/**
 * Overview — the project's front door and R1's gate
 * (`docs/dev/HISTORY.md § 2026-09-05`; DESIGN.md §12.3).
 *
 * The gate this file closes, in the plan's own words: *in mock projects containing 3 and 30
 * subjects, opening Overview makes exactly one overview catalog request, renders every subject and
 * every defined presence/count column, and Cmd+1, first launch, catch-all, rail and palette all
 * resolve to `/overview`. No Subject Info route or toggle is discoverable.*
 *
 * The request count is the point: the page this replaced fanned out one detail read per subject
 * plus five output lists per subject plus one analyses list per simulation, and gave up past 25
 * subjects. So the 30-subject project here is not a bigger fixture for its own sake — it is the
 * only size at which "does not grow with the project" is a measurement rather than a claim.
 *
 * The mock's two projects are switched with `POST /api/__mock/project` (`tests/mock-server/
 * server.mjs`), which is why this spec talks to the server directly before launching the app.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { MOD, expectPage, expectSubject, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { captureScreen, deadSpaceRatio, paneWidths, type PageMetrics } from "./_metrics";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "overview";

/** Every column the page defines — the gate's "every defined presence/count column". */
const PRESENCE_COLUMNS = ["raw", "fast", "free", "m2m", "dwi", "ct", "lf", "net"];
const COUNT_COLUMNS = ["Sim", "Opt", "Anly"];

let app: ElectronApplication;
let page: Page;
/** Every `/api/catalog/overview` request the renderer made since the last reset. */
let overviewRequests: string[] = [];

/** Switch the mock between its 3- and 30-subject projects. */
async function useProject(subjects: 3 | 30): Promise<void> {
  const res = await fetch(`${SERVER_URL}/api/__mock/project`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ subjects }),
  });
  expect(res.status, "the mock accepted the project switch").toBe(200);
}

async function launchApp(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  overviewRequests = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname === "/api/catalog/overview") overviewRequests.push(r.url());
  });
  await page.setViewportSize({ width: 1280, height: 800 });
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
}

/** The 30-subject project, rendered — the size at which the matrix is meant to fill the pane. */
async function loaded30(): Promise<void> {
  await expect(page.getByTestId("overview-row-S030")).toBeVisible({ timeout: 20_000 });
}

/** Loaded when the counts have landed — the last thing the single request fills in. */
async function loaded(): Promise<void> {
  await expect(page.getByTestId("overview-row-ernie")).toContainText("GSN-HydroCel-185", { timeout: 20_000 });
}

test.beforeEach(async () => {
  await useProject(3);
  await launchApp();
});
test.afterEach(async () => {
  await app?.close();
  await useProject(3);
});

test("is the coverage strip and the presence matrix — no readiness board, no page header", async () => {
  await connect();
  await loaded();
  await expectPage(page, "overview");
  await expect(page.locator(".page-header")).toHaveCount(0);

  // Coverage, five tiles, over the fixture's three subjects — the server's own totals.
  const tiles = (await page.getByTestId("overview-coverage").innerText()).replace(/\s+/g, " ").toLowerCase();
  expect(tiles).toContain("raw 2/3");
  expect(tiles).toContain("m2m 3/3");
  expect(tiles).toContain("leadfield 1/3");

  // Presence: eight dots per row, each labelled — this page is the only place they appear (U6).
  const ernie = page.getByTestId("overview-row-ernie");
  await expect(ernie.getByRole("img")).toHaveCount(PRESENCE_COLUMNS.length);
  await expect(ernie.getByRole("img", { name: "m2m present" })).toBeVisible();
  await expect(ernie.getByRole("img", { name: "ct missing" })).toBeVisible();
  // `partial` is its own reading, not a second word for "missing" — ernie has a leadfield for one
  // of its two nets.
  await expect(ernie.getByRole("img", { name: "leadfield partial" })).toBeVisible();
  await expect(page.getByTestId("overview-row-101").getByRole("img", { name: "fastsurfer missing" })).toBeVisible();

  // The readiness board of four stage cards is gone: it restated the matrix one chip at a time and
  // its mostly-empty chip wells owned the lower half of the page.
  await expect(page.getByTestId("overview-readiness")).toHaveCount(0);
  for (const stage of ["preprocess", "simulator", "optimizer", "analyzer"]) {
    await expect(page.getByTestId(`overview-stage-${stage}`)).toHaveCount(0);
    await expect(page.getByTestId(`overview-run-${stage}`)).toHaveCount(0);
  }

  // What the dot colours mean is said once, in one line under the matrix, not learned by hovering.
  const legend = (await page.getByTestId("overview-legend").innerText()).replace(/\s+/g, " ").toLowerCase();
  for (const word of ["present", "partial", "running now", "last run failed", "missing"]) {
    expect(legend, `the legend names ${word}`).toContain(word);
  }

  // §11: no bottom status bar — the counts are the table's own.
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
});

test("GATE: one overview request renders every subject and every column — at 3 subjects and at 30", async () => {
  test.setTimeout(180_000);

  // --- the 3-subject project -----------------------------------------------------------------
  await connect();
  await loaded();
  expect(overviewRequests.length, "exactly one overview request for the whole page").toBe(1);

  const header = page.getByTestId("overview-table").locator(".overview-head");
  for (const column of PRESENCE_COLUMNS) await expect(header).toContainText(column);
  for (const column of COUNT_COLUMNS) await expect(header).toContainText(column);
  for (const id of ["ernie", "101", "MNI152"]) await expect(page.getByTestId(`overview-row-${id}`)).toBeVisible();
  // Counts are rendered, not blank: the fan-out this replaced printed nothing past its cap.
  await expect(page.getByTestId("overview-row-ernie")).toContainText("3");

  // Every other page in the rail, then back: still one request per mount, never a fan-out.
  const before = overviewRequests.length;
  await gotoPage(page, "results");
  await expectPage(page, "results");
  await gotoPage(page, "overview");
  await loaded();
  expect(overviewRequests.length - before, "returning to the page re-reads at most once").toBeLessThanOrEqual(1);

  // --- the 30-subject project ----------------------------------------------------------------
  await app.close();
  await useProject(30);
  await launchApp();
  await connect();
  await expect(page.getByTestId("overview-row-S030")).toBeVisible({ timeout: 20_000 });
  expect(overviewRequests.length, "still exactly one request at 30 subjects").toBe(1);

  // Every subject renders — there is no eager limit any more (the old page stopped at 25).
  const rows = await page.locator('[data-testid^="overview-row-"]').count();
  expect(rows).toBe(30);
  for (const id of ["S001", "S025", "S026", "S030"]) {
    await expect(page.getByTestId(`overview-row-${id}`)).toBeVisible();
  }
  // …with their counts, past where the 25-subject cap used to blank them.
  await expect(page.getByTestId("overview-row-S030").getByRole("img")).toHaveCount(PRESENCE_COLUMNS.length);

  // All five presence states are reachable in one project, and read differently.
  for (const name of ["fastsurfer present", "fastsurfer missing", "fastsurfer partial", "fastsurfer running now", "fastsurfer last run failed"]) {
    await expect(page.getByRole("img", { name }).first()).toBeVisible();
  }
});

test("GATE: first launch, Cmd+0, the rail and the palette all resolve to Overview; Subject Info does not exist", async () => {
  // 1. first launch — the app lands here with nothing clicked.
  await connect();
  await expectPage(page, "overview");

  // 2. Cmd+0 — the rail counts from zero (DESIGN.md §9), so the first row is ⌘0.
  await gotoPage(page, "settings");
  await expectPage(page, "settings");
  await page.keyboard.press(`${MOD}+0`);
  await expectPage(page, "overview");

  // 3. the rail's first row.
  await gotoPage(page, "results");
  await expectPage(page, "results");
  const railIds = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="nav-item-"]')).map((el) =>
      (el.getAttribute("data-testid") ?? "").replace(/^nav-item-/, ""),
    ),
  );
  expect(railIds[0]).toBe("overview");
  await page.getByTestId("nav-item-overview").click();
  await expectPage(page, "overview");

  // 4. the palette.
  await gotoPage(page, "jobs");
  await openPalette(page);
  await page.getByTestId("palette-input").fill("overview");
  await page.getByRole("dialog").getByRole("option", { name: /Overview/ }).first().click();
  await expectPage(page, "overview");

  // 5. no Subject Info anywhere: not in the rail, not in the palette, not in Settings' panel list.
  // (`/panel-subject-info` itself falls through App's catch-all to the landing page, which is this
  // one — no page claims that id any more; `tests/unit/shell-registry.test.ts` holds that rule.)
  //
  // Briefly reinstated on 2026-09-06 and removed again the same day — maintainer: *"Remove the
  // subject info extension. We absolutely do not need that, this is redundant."*
  expect(railIds).not.toContain("panel-subject-info");
  await openPalette(page);
  await page.getByTestId("palette-input").fill("subject info");
  await expect(page.getByRole("dialog").getByRole("option", { name: /Subject info/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await gotoPage(page, "settings");
  await expect(page.getByRole("checkbox", { name: "Subject info" })).toHaveCount(0);
});

test("the detail pane exists only when a row is selected, and links into Results", async () => {
  await connect();
  await loaded();

  let panes = await paneWidths(page);
  expect(panes.right).toBe(0);
  expect(panes.work).toBe(panes.content);

  await page.getByTestId("overview-row-ernie").click();
  await expect(page.getByTestId("overview-detail")).toBeVisible();
  panes = await paneWidths(page);
  expect(panes.right).toBe(360);
  expect(panes.work).toBeGreaterThanOrEqual(704);

  // Q3: counts and a link, never a tree or a preview — Results is the outputs browser.
  await expect(page.getByTestId("overview-detail")).toContainText("GSN-HydroCel-185");
  await expect(page.getByTestId("overview-counts")).toContainText("3");
  await expect(page.getByTestId("overview-detail").locator(".outputs-tree")).toHaveCount(0);

  await page.getByTestId("overview-open-results").click();
  await expectPage(page, "results");
  await expect(page.getByTestId("results-subject-ernie")).toHaveAttribute("aria-selected", "true");
});

test("the filter and the scope segments narrow the table", async () => {
  await connect();
  await loaded();

  await page.getByTestId("overview-filter").fill("mni");
  await expect(page.getByTestId("overview-table").getByRole("row")).toHaveCount(2); // header + MNI152
  await page.getByTestId("overview-filter").fill("");

  await page.getByRole("radiogroup", { name: "Subject scope" }).getByRole("radio", { name: "Ready", exact: true }).click();
  await expect(page.getByTestId("overview-row-ernie")).toBeVisible();
  await expect(page.getByTestId("overview-row-MNI152")).toHaveCount(0);
});

test("a run verb navigates, scoped to the selected subject", async () => {
  await connect();
  await loaded();

  await page.getByTestId("overview-row-101").click();
  // 101 has no leadfield, so Optimize is disabled with the reason as its tooltip, never silently.
  await expect(page.getByTestId("overview-verb-optimizer")).toBeDisabled();
  await expect(page.getByTestId("overview-verb-optimizer")).toHaveAttribute("title", "no leadfield");

  await page.getByTestId("overview-verb-simulator").click();
  await expectPage(page, "simulator");
  await expectSubject(page, "101");
});

/**
 * Measured on the 30-subject project, not the 3-subject one.
 *
 * The page is a table now that the readiness board is gone, so what "uses the real estate" means
 * here is that the matrix fills the pane — which is a claim about a project, not about a fixture.
 * Three rows leave three quarters of any pane empty no matter how the page is built, and the four
 * stage cards that used to cover that space were exactly what the maintainer asked to remove.
 */
test("hits its §12.3 numbers at 1280x800 and 1440x900, light and dark", async () => {
  test.setTimeout(180_000);
  await app.close();
  await useProject(30);
  await launchApp();
  await connect();
  await loaded30();

  const rows: PageMetrics[] = [];
  for (const selection of [null, "S001"] as const) {
    if (selection) await page.getByTestId(`overview-row-${selection}`).click();
    for (const size of [
      { width: 1280, height: 800 },
      { width: 1440, height: 900 },
    ]) {
      for (const theme of ["light", "dark"] as const) {
        const row = await captureScreen(page, {
          runId: RUN_ID,
          pageId: `overview-lane-${selection ?? "unselected"}-${theme}`,
          theme,
          width: size.width,
          height: size.height,
          waitFor: loaded30,
        });
        rows.push({ ...row, width: size.width, height: size.height, page: selection ? "populated" : "unselected" });
        expect(row.pageHeaderHeight).toBe(0);
        expect(row.panes.right).toBe(selection ? 360 : 0);
        expect(row.panes.work).toBeGreaterThanOrEqual(704);
      }
    }
  }

  const parts = {
    table: (await deadSpaceRatio(page, '[data-testid="overview-table"]')).ratio,
    detail: (await deadSpaceRatio(page, '[data-testid="overview-detail"]')).ratio,
  };
  console.log("overview parts:", Object.entries(parts).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`).join(" · "));
  console.log(
    "overview dead space:",
    rows.map((r) => `${r.page} ${r.theme} ${r.width}x${r.height} ${(r.deadSpaceRatio * 100).toFixed(1)}%`).join(" · "),
  );
  // A presence matrix is sparse by construction: eight of a row's eleven columns hold one 10 px
  // dot each, and spreading those columns out is the readability fix this pass was asked for, so
  // the sampler counts more of the row as empty than it did when four cards of chips covered the
  // lower half of the page. The numbers below are the measured floor of the page as it now is,
  // held so a regression that empties it further still fails.
  //
  // The detail ceiling moved 0.50 -> 0.53 when DESIGN.md §11's 24 px status bar was deleted: the
  // pane grew 24 px taller against the same content, so the same page measures ~1.8 points emptier
  // without anything about it having changed.
  expect(parts.table, "presence matrix").toBeLessThanOrEqual(0.36);
  expect(parts.detail, "detail pane").toBeLessThanOrEqual(0.53);

  const populated = rows.filter((r) => r.page === "populated");
  const unselected = rows.filter((r) => r.page === "unselected");
  expect(Math.max(...populated.map((r) => r.deadSpaceRatio))).toBeLessThanOrEqual(0.44);
  expect(Math.max(...unselected.map((r) => r.deadSpaceRatio))).toBeLessThanOrEqual(0.45);
});
