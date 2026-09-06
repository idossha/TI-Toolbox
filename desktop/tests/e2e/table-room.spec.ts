import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { deadSpaceRatio, firstScreenControls } from "./_metrics";

/**
 * A table takes the room its pane gives it, and where a table still draws ground rows they belong
 * to the table (cleanup round, lane CL2, item 3 — lane FIX-D's cross-lane requests 1 and 3).
 *
 * The subject list is the one table that draws NONE: it ends after the last subject ("just a
 * simple list of subjects"). `fill` still decides how much room its box may take; it never pads
 * the list out to that room.
 *
 * Two defects, both "the same thing written twice":
 *
 * 1. **`.run-subject-scroll`'s `max-height: 176px` was a ceiling, not a default.** The Source
 *    panel — a page whose whole job is choosing subjects — could not use a 900 px window, so
 *    `pages/panels/panels.css` overrode the cap *and painted its own ground rows behind the
 *    table*, because the rows belonged to `SubjectsField`. Pre-processing pinned `minRows={5}`
 *    for the same reason: a constant, chosen by hand, instead of however many rows fit.
 * 2. **Two pages painted a CSS gradient behind `ui/DataTable`** (`jobs-page.css::.jobs-page-filler`,
 *    `panels.css::.panel-table-filler`) because the table owned its own `<tr>`s and would not draw
 *    ground rows. One rule, written twice, in two files that do not know about each other.
 *
 * Both are now one mechanism: a table that grounds draws its own `<tr>`s, and the page says
 * `fill` for the room. The numbers here are the ones that made the case — the room a
 * table actually takes, and the dead-space ratio the pages must stay inside (L5a, 45 %).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ALL_PANELS = ["source", "cluster-permutation", "nifti-group-average", "nilearn-visuals", "quick-notes"];
/** L5a. The same limit every other page in this programme is held to. */
const DEAD_SPACE_MAX = 0.45;
/** The cap `.run-subject-scroll` used to enforce on every page, whatever the window. */
const OLD_CAP = 176;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-table-room-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: {
        telemetry: { consented: true, enabled: false },
        panels: ALL_PANELS,
        image_tag: "idossha/simnibs:v2.3.1",
        allow_unsafe_overrides: false,
        theme: "system",
      },
    });
  });
  await page.addInitScript((panels: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(panels));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, ALL_PANELS);

  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  // A subject, for `layout.spec.ts`'s reason: a page measured with nothing chosen is measuring its
  // empty state, and L5a's 45 % is stated against the populated one.
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

async function settle(): Promise<void> {
  await page
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, { timeout: 5_000 })
    .catch(() => undefined);
  await page.waitForTimeout(400);
}

/** Height of a box, and how much of the room below it is left unused. */
async function boxRoom(selector: string): Promise<{ height: number; slackBelow: number; painted: boolean }> {
  return page.evaluate((sel) => {
    const active = document.querySelector('[data-page-active="true"]');
    const el = active?.querySelector<HTMLElement>(sel);
    if (!el) throw new Error(`no element for ${sel}`);
    const work = active!.querySelector('[data-testid="page-work"]') as HTMLElement;
    const rect = el.getBoundingClientRect();
    return {
      height: Math.round(rect.height),
      slackBelow: Math.round(work.getBoundingClientRect().bottom - rect.bottom),
      painted: getComputedStyle(el).backgroundImage !== "none",
    };
  }, selector);
}

test("the Source panel's subject table may use the room a 900px window gives it", async () => {
  await gotoPage(page, "panel-source", "Source");
  await expectPage(page, "panel-source");
  await settle();

  const scroll = await boxRoom('[data-testid="subjects-field-table"]');
  if (process.env.CL2_DIAG === "1") {
    console.log(
      "CL2-DIAG " +
        JSON.stringify(
          await page.evaluate(() => {
            const active = document.querySelector('[data-page-active="true"]')!;
            const box = active.querySelector('[data-testid="subjects-field-table"]') as HTMLElement;
            const sc = box.closest("[data-page-work-scroll]") as HTMLElement;
            const work = active.querySelector('[data-testid="page-work"]') as HTMLElement;
            return {
              boxH: box.clientHeight,
              boxScrollH: box.scrollHeight,
              scClientH: sc?.clientHeight ?? null,
              scScrollH: sc?.scrollHeight ?? null,
              scBottom: Math.round(sc?.getBoundingClientRect().bottom ?? 0),
              boxBottom: Math.round(box.getBoundingClientRect().bottom),
              workBottom: Math.round(work.getBoundingClientRect().bottom),
            };
          }),
        ),
    );
  }
  const fillers = await page.locator('[data-page-active="true"] [data-testid="subjects-field-table"] .run-table-filler').count();
  console.log(`CL2-ROOM panel-source scroll=${scroll.height}px slackBelow=${scroll.slackBelow}px fillers=${fillers} painted=${scroll.painted}`);

  // The cap is LIFTED, not swapped for a stretch: `max-height` is the measured room (far past the
  // 176px this page used to be pinned to by `pages/_shared/run/run.css`), while the box itself is
  // as tall as its rows — three subjects are three rows, not a 684px empty box.
  const cap = await page.evaluate(() => {
    const el = document.querySelector('[data-page-active="true"] [data-testid="subjects-field-table"]') as HTMLElement;
    const mh = getComputedStyle(el).maxHeight;
    return { maxHeight: mh === "none" ? Number.POSITIVE_INFINITY : parseFloat(mh), content: el.scrollHeight };
  });
  expect(cap.maxHeight).toBeGreaterThan(OLD_CAP);
  expect(scroll.height).toBeLessThanOrEqual(cap.content + 2);
  // And nothing pads it out: no ground rows in the table, and no gradient painted behind it.
  expect(fillers).toBe(0);
  expect(scroll.painted).toBe(false);
  // Dead space on this panel is `layout.spec.ts`'s gate (`panel-source`); reported, not re-asserted
  // here — a list that ends after its last subject leaves the pane below it to the page.
  const dead = await deadSpaceRatio(page);
  console.log(`CL2-DEAD panel-source ${(dead.ratio * 100).toFixed(1)}%`);
});

test("Pre-processing's subject list ends after the last subject", async () => {
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
  await settle();

  const scroll = await boxRoom('[data-testid="subjects-field-table"]');
  const rows = await page.locator('[data-page-active="true"] [data-testid="subjects-field-table"] tbody tr').count();
  const fillers = await page.locator('[data-page-active="true"] [data-testid="subjects-field-table"] .run-table-filler').count();
  const subjects = await page.locator('[data-page-active="true"] [data-testid="subjects-field-table"] tbody tr.subject-picker-row').count();
  console.log(`CL2-ROOM preprocess 1440x900 scroll=${scroll.height}px rows=${rows} fillers=${fillers}`);

  // Just the subjects: `minRows={5}` and the measured ground rows are both gone, so the list is
  // exactly as long as the project is. The box may still be given more room than that (`fill`) —
  // it simply is not padded out to it.
  expect(subjects).toBeGreaterThan(0);
  expect(fillers).toBe(0);
  expect(rows).toBe(subjects);
  expect(scroll.painted).toBe(false);

  // The rest of the page still fits: every Tier-1 control is on the first screen.
  const first = await firstScreenControls(page);
  expect(first.hidden).toEqual([]);
  // Dead space is `layout.spec.ts`'s gate and it owns Pre-processing's stated allowance (the
  // pane below a 3-subject list is pane now, not filler rows); reported here, not re-asserted.
  const dead = await deadSpaceRatio(page);
  console.log(`CL2-DEAD preprocess ${(dead.ratio * 100).toFixed(1)}%`);
});

test("Jobs draws the ground rows in the table, not behind it", async () => {
  // Paired with `panel-subject-info` until R1 deleted that page; Jobs is the remaining table
  // that paints its own filler rows.
  for (const { id, label, painter } of [
    { id: "jobs", label: "Jobs", painter: ".jobs-page-filler" },
  ] as const) {
    await gotoPage(page, id, label);
    await expectPage(page, id);
    await settle();

    const active = page.locator('[data-page-active="true"]');
    // Either vocabulary: `ui/DataTable`'s own filler rows, or `ui/SelectionList`'s (the Jobs list
    // is the selection list now — plan C4 — and it draws the same `.run-table-filler` rows the run
    // pages' tables draw).
    const fillers = await active.locator(".data-table-filler, .run-table-filler").count();
    const painted = await active.locator(painter).count();
    const dead = await deadSpaceRatio(page);
    console.log(`CL2-GROUND ${id} dataTableFillers=${fillers} painter(${painter})=${painted} dead=${(dead.ratio * 100).toFixed(1)}%`);

    expect(fillers, `${id}: the table draws its own ground rows`).toBeGreaterThan(0);
    expect(painted, `${id}: the duplicate gradient is gone`).toBe(0);
    expect(dead.ratio, `${id}: L5a`).toBeLessThanOrEqual(DEAD_SPACE_MAX);
  }
});
