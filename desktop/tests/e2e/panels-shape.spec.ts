import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, setTheme, type Theme } from "./_helpers";
import { deadSpaceByChild, deadSpaceProfile, deadSpaceRatio, horizontalOverflow } from "./_metrics";

/**
 * The pages §4 of the plan never reached: the four job-submitting panels, Subject info, and Jobs
 * (fix round, lane FIX-D, defects 3 and 4).
 *
 * **Defect 3 — a fourth idiom.** `nifti-group-average`, `cluster-permutation` and
 * `nilearn-visuals` do not take a *set* of subjects: each row is a `(subject, simulation, role)`
 * tuple and the same subject may legitimately repeat (`cluster-permutation`'s paired test,
 * `nifti-group-average`'s diff pairs), which is why lane SUB deliberately left them on
 * `SubjectsField` (its §4). They were left on three hand-rolled `<div style="display:grid">` row
 * lists instead — a fourth vocabulary. `pages/panels/_participants` gives them the *grammar* of
 * `SubjectsField` (header band, one-line summary stating what will run, a real table with column
 * headers, a per-row "Why not" reason) over a row list rather than a set.
 *
 * **Defect 4 — the empty state is a sentence in the top-left of a 1224x704 box.** Lane LAY
 * measured `panel-source` 82.5-84.4 %, the since-deleted `panel-subject-info` 85.8-86.6 % and Jobs **99.1 %** dead
 * and gated only the run pages (its §8 item 1). The rule these pages now follow is DESIGN.md
 * §4.4's *table* row, not its whole-page row: when the populated state is a table, the empty state
 * is that same table with its column headers and the message inside the body — the shape of what
 * will appear, rather than a centred sentence and 700 px of ground.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ALL_PANELS = ["source", "cluster-permutation", "nifti-group-average", "nilearn-visuals", "quick-notes"];

/** The idle terminal intentionally reserves room for live output. For run panels assert
 * bounded plan / dominant terminal geometry, not the old whole-page ink-density target.
 * Jobs retains its established table-fill metric. */
const DEAD_SPACE_MAX = 0.45;

const SIZES = [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
] as const;
const THEMES: Theme[] = ["light", "dark"];

/** Every page this lane owns that renders no action bar, in nav order. */
const PAGES = [
  { id: "panel-source", label: "Source" },
  { id: "panel-cluster-permutation", label: "Cluster permutation" },
  { id: "panel-nifti-group-average", label: "NIfTI group averaging" },
  { id: "panel-nilearn-visuals", label: "Nilearn visuals" },
  { id: "jobs", label: "Jobs" },
] as const;

/** The three row-list panels defect 3 unifies. */
const PARTICIPANT_PAGES = [
  { id: "panel-cluster-permutation", label: "Cluster permutation", note: "one job over all subjects" },
  { id: "panel-nifti-group-average", label: "NIfTI group averaging", note: "one job over all subjects" },
  { id: "panel-nilearn-visuals", label: "Nilearn visuals", note: "one job over all subjects" },
] as const;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-panels-shape-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  // The nav rail gates a panel on the server's `settings.panels`; the mock's seed enables only
  // three of the six (same reason `panels-forms.spec.ts` routes around it).
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
});

test.afterAll(async () => {
  await app?.close();
});

async function settle(): Promise<void> {
  await page
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, { timeout: 5_000 })
    .catch(() => undefined);
  await page.waitForTimeout(350);
}

test("defect 3: the three row-list panels speak one grammar", async () => {
  test.setTimeout(180_000);
  for (const { id, label, note } of PARTICIPANT_PAGES) {
    await gotoPage(page, id, label);
    await expectPage(page, id);
    await settle();

    const control = page.locator('[data-page-active="true"]').getByTestId("participants-field");
    await expect(control, `${id}: no participants control`).toHaveCount(1);

    // With nothing chosen the line says exactly that and nothing else — `SubjectsField`'s own
    // rule, kept: a semantics phrase attached to an empty selection promises a run that cannot
    // happen.
    await expect(control.getByTestId("participants-summary"), `${id}: empty summary`).toHaveText("No subjects chosen yet");

    // A real table with real column headers, not a bare grid of selects. Every one of these
    // panels starts with "Subject" and "Simulation" and adds its own role columns after.
    const headers = await control.locator("thead th").allTextContents();
    // The leading empty heading is the selection checkbox column the one grammar puts on every
    // list (plan C1); the panels' own columns follow it unchanged.
    expect(headers.slice(0, 4), `${id}: leading columns`).toEqual(["", "#", "Subject", "Simulation"]);

    // The blocked reason is a per-row cell, in the same place and the same words as
    // `SubjectsField`'s — not a Callout list at the bottom of the page.
    const rows = control.locator("[data-testid^='participant-row-']");
    expect(await rows.count(), `${id}: rows`).toBeGreaterThan(0);
    const firstRow = rows.first();
    const rowId = ((await firstRow.getAttribute("data-testid")) ?? "").replace("participant-row-", "");
    await expect(firstRow, `${id}: a fresh row is not runnable`).toHaveAttribute("data-eligible", "false");
    await expect(control.getByTestId(`participant-reason-${rowId}`), `${id}: reason`).toHaveText("no subject chosen");

    // Choose a subject in the first row: the summary states what will run (J4, in J4's words) and
    // the row's reason moves on to the next thing it needs.
    await firstRow.getByRole("combobox").first().click();
    await page.getByRole("option", { name: "ernie", exact: true }).click();
    await expect(control.getByTestId("participants-summary"), `${id}: summary`).toHaveText(`ernie · ${note}`);
    await expect(control.getByTestId(`participant-reason-${rowId}`), `${id}: reason`).toHaveText("no simulation chosen");
  }
});

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`defect 4: panels and Jobs — ${theme} at ${size.width}x${size.height}`, async () => {
      test.setTimeout(240_000);
      await page.setViewportSize(size);
      await setTheme(page, theme);

      for (const { id, label } of PAGES) {
        await gotoPage(page, id, label);
        await expectPage(page, id);
        await settle();

        const dead = await deadSpaceRatio(page);
        const profile = await deadSpaceProfile(page);
        console.log(
          `FIXD ${id} ${theme} ${size.width}x${size.height} dead=${(dead.ratio * 100).toFixed(1)}% ` +
            `work=${(profile.work * 100).toFixed(1)}% bands=[${profile.bands.map((b) => (b.ratio * 100).toFixed(0)).join(" ")}]`,
        );
        if (process.env.FIXD_DIAG === "1") {
          const t = await page.evaluate(() => {
            const h = (sel: string) => {
              const el = document.querySelector(sel) as HTMLElement | null;
              return el ? Math.round(el.getBoundingClientRect().height) : null;
            };
            const heights = {
              work: h('[data-testid="page-work"]'),
              scroll: h("[data-page-work-scroll]"),
              page: h(".panel-page"),
              cols: h(".panel-page-columns"),
              jobsWork: h(".jobs-page-work"),
              jobsFiller: h(".jobs-page-filler"),
              panelFiller: h(".panel-table-filler"),
            };
            const box = document.querySelector('[data-testid="participants-field-table"]') as HTMLElement | null;
            const tbl = box?.querySelector("table") as HTMLElement | null;
            const row = box?.querySelector("tbody tr") as HTMLElement | null;
            return box === null
              ? { heights }
              : {
                  heights,
                  boxH: box.clientHeight,
                  tableH: tbl?.getBoundingClientRect().height,
                  rowH: row?.getBoundingClientRect().height,
                  rows: box.querySelectorAll("tbody tr").length,
                  fillers: box.querySelectorAll(".participants-filler").length,
                  fill: box.getAttribute("data-fill"),
                };
          });
          console.log(`FIXD-TABLE ${id} ${JSON.stringify(t)}`);
          for (const c of await deadSpaceByChild(page, '[data-testid="page-work"]', process.env.FIXD_SEL ?? undefined)) {
            console.log(`FIXD-CHILD ${id} ${theme} ${size.width} ${c.label} h=${c.height} dead=${(c.ratio * 100).toFixed(0)}%`);
          }
        }

        const overflow = await horizontalOverflow(page);
        expect.soft(overflow.page, `${id} ${theme} ${size.width}: the page scrolls horizontally`).toBe(0);
        if (id === "jobs") {
          expect.soft(dead.ratio, "Jobs table fills its work area").toBeLessThanOrEqual(DEAD_SPACE_MAX);
        } else {
          const active = page.locator('[data-page-active="true"]');
          const work = await active.getByTestId("page-work").boundingBox();
          const right = await active.getByTestId("page-right-pane").boundingBox();
          const plan = await active.getByTestId("extension-plan").boundingBox();
          const terminal = await active.getByTestId("job-terminal").boundingBox();
          expect(work).not.toBeNull(); expect(right).not.toBeNull();
          expect(plan).not.toBeNull(); expect(terminal).not.toBeNull();
          expect(right!.x).toBeGreaterThanOrEqual(work!.x + work!.width);
          expect(terminal!.height).toBeGreaterThan(right!.height * 0.45);
          expect(plan!.height).toBeLessThanOrEqual(right!.height * 0.46);
          expect(terminal!.y).toBeGreaterThanOrEqual(plan!.y + plan!.height);
        }
      }
    });
  }
}

test("defect 4: an empty table shows its own column headers", async () => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await setTheme(page, "light");

  // Jobs, filtered to a state nothing is in: the table stays, with its eight headers and the
  // message in its body. The whole-page "Nothing has run yet." state renders the same shape.
  await gotoPage(page, "jobs", "Jobs");
  await expectPage(page, "jobs");
  await settle();
  const table = page.getByTestId("jobs-table");
  await expect(table).toBeVisible();
  const headers = await table.locator("thead th").allTextContents();
  // The first heading is the selection column (plan C4).
  expect(headers.slice(0, 4)).toEqual(["", "State", "Kind", "Subjects"]);
  await expect(table.locator("tbody tr")).not.toHaveCount(0);
});
