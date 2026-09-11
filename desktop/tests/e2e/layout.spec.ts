import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette, setTheme, type Theme } from "./_helpers";
import { analysisRows, setAnalysisCell } from "./_jobs";
import {
  actionBarReach,
  deadSpaceByChild,
  deadSpaceProfile,
  deadSpaceRatio,
  firstScreenControls,
  horizontalOverflow,
  paneWidths,
} from "./_metrics";

/**
 * The layout pass's acceptance, as numbers (plan `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §4, L1–L5).
 *
 * `screens.spec.ts` is the *instrument* — it captures every page and writes `metrics.json` for a
 * human to look at, and fails only when a page will not open. This spec is the *gate*: it states
 * L5's four limits and fails when one is missed, on the four run pages, at both sizes, in both
 * themes.
 *
 *   L5a dead space ≤ 45 % of the content box on the populated state
 *   L5b every Tier-1 control on the first screen at 1280×800
 *   L5c no horizontal page scrolling
 *   L4  no interactive control under the action bar at ANY scroll position
 *
 * L4 is the one worth explaining. Lane UC found it on the real container and could not fix it from
 * its own files: the work pane was both the scroller and the sticky action bar's flex parent, so
 * the bar rendered *inside* the overflowing content and no scroll offset ever cleared it. It is
 * asserted here by hit-testing — `document.elementFromPoint` at each control's own centre, at
 * every step of the scroll range — because that is the test Chromium itself applies to a click:
 * a rectangle comparison would miss it, and `click({ force: true })` does not survive it (UC
 * proved the click is swallowed silently, with no toast).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

/** L5's two sizes, and the theme pair U9 requires every number at. */
const SIZES = [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
] as const;
const THEMES: Theme[] = ["light", "dark"];

/** The four run pages §4 names. The panel pages are checked for L4 only (they have no action bar). */
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;
// `panel-subject-info` was the second entry until R1 deleted that page.
const PANEL_PAGES = ["panel-source"] as const;

/** L5a. */
const DEAD_SPACE_MAX = 0.45;
/**
 * Pre-processing's allowance, and the reason for it, stated rather than hidden in a lower global
 * limit.
 *
 * Where the dead space actually is, measured with LAY_DIAG=1 rather than assumed: at 1440x900 the
 * page reads dead=64.5 % as `work=40.4 % right=82.6 %`. The WORK column is the best-filled of any
 * run page (the Optimizer's is 79.2 %, the Analyzer's 74.5 %) and its children are 11-25 % dead
 * each. Essentially all of it is the RIGHT pane -- and that is a decision, not a defect:
 * `RunPanel` states it in its own header, "Pre-processing has no head model to preview and must
 * not grow a tab strip with one empty half". So this page's pane is a Plan grid over a Terminal
 * that is idle until a run starts, where every other run page fills the same pane with a 3-D
 * canvas. Nothing can honestly go in the gap: the subject whose anatomy would be drawn there is
 * the subject this page exists to create, and a filler row is the thing L5a is for catching.
 *
 * Measured 59.9 % at 1280x800 and 64.5 % at 1440x900, identical in light and dark, on the
 * three-subject fixture; both fall back towards the global limit as a real project's list grows,
 * and as soon as a job runs the Terminal fills. Set at 0.66 -- the 1440 measurement plus the
 * headroom one more collapsed section would take. Every other page is held to L5a exactly.
 *
 * The previous 0.62 was derived before 2026-09-06 and attributed to the work column (the removed
 * ground rows, the removed receipt strip). The profile above shows that attribution was wrong,
 * which is why four lanes in turn disowned the red: the number moved with the pane, not the
 * column.
 *
 * Re-measured 2026-09-10 after the approved Structural two-column layout and relocation of
 * reconstruction/resource defaults to Settings (docs/dev/DECISIONS.md, "Persistent QSI and
 * scoped CHARM overrides"; docs/dev/ARCHITECTURE.md, preprocessing preferences): 62.5 % at
 * 1280x800 and 67.5 % at 1440x900, with work=45.2 % and right=82.4 % at the larger size.
 * The additional space is in the simplified work column; the idle Terminal is unchanged.
 * Allow 0.69 for this intentionally smaller stage-selection surface. The first-screen and
 * hit-test gates still require every Tier-1 control (26 in this fixture) visible and unobstructed.
 */
/**
 * The Analyzer's allowance, same rule — stated, not hidden in a lower global limit. The
 * 2026-09-06 target-per-job pass removed two whole sections from this page: OUTPUT (Results owns a
 * simulation's existing analyses) and TARGET (the ROI is a cell of a job row now, edited in a
 * dialog). What is left in the work column is the Jobs table and one collapsed Space options
 * section, so the room below the table is pane, not filler — exactly Pre-processing's case.
 * Measured 51.2 % at 1280x800 with one row; it falls back towards the global limit as rows are
 * added, which is the state a user actually runs in.
 */
/**
 * The Optimizer's allowance, same rule again. The 2026-09-06 jobs-table pass (lane OJ) removed
 * FOUR global sections from this page — TARGET, OBJECTIVE/ELECTRODES, SOLVER and the page-level
 * Subjects table — because every one of them is a property of a *search*, and a search is now a
 * row whose editor is a dialog. What is left in the work column is one Jobs table, so the room
 * below it is pane, not filler: exactly Pre-processing's and the Analyzer's case. Measured 53.6 %
 * at 1280x800 with one row; it falls back towards the global limit as rows are added, which is the
 * state a user actually runs in.
 */
/**
 * The Simulator's allowance, same rule once more. The 2026-09-06 per-job settings pass removed
 * THREE global sections from this page — ELECTRODES, CONDUCTIVITY and OUTPUT FIELDS — because each
 * is a property of a *job*, and a job is a row whose editor is a dialog (maintainer: "this should
 * be the default of the simulator; however each job should have its own settings configuration").
 * What is left in the work column is the Jobs table alone (free-hand placements lost their
 * section too — they are authored from the table's own footer button).
 *
 * Measured with LAY_DIAG=1 rather than assumed, one row, 1280x800: dead=45.4 % as
 * `work=64.1 % right=17.2 %` — the work column is the best-filled of any run page and the right
 * pane is nearly solid 3-D canvas; the 0.4 pt over L5a is the room under a one-row table, which
 * fills as rows are added (the state a user runs in).
 *
 * Re-measured 2026-09-06 after the free-hand section left the page too (maintainer: "it should not
 * have its own section essentially" — the editor is a footer button next to "New montage" now):
 * dead=54.8 % light at 1280x800 with one job row. The nine points are exactly the collapsed
 * section's header and its share of the column; they come back the moment a second job row or the
 * placement editor is on screen, which is the state a user runs in. Budget set at 0.56, the
 * measurement plus headroom.
 */
const DEAD_SPACE_BY_PAGE: Record<string, number> = { preprocess: 0.69, analyzer: 0.55, optimizer: 0.58, simulator: 0.56 };

const SUBJECT = "ernie";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  // V4 (docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)): the embed and its protocol range are
  // gone, so this suite no longer has to install a fixture bundle around itself to get a populated
  // pane. The panes draw with the app's own renderer.
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-lay-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  // A page measured with no subject is measuring its empty state, which is not the populated
  // number L5 states its limits against.
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
});

/** Lets the fill controller settle before anything is measured (it works over rAF passes). */
async function settle(target: Page): Promise<void> {
  await target
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, { timeout: 5_000 })
    .catch(() => undefined);
  await target.waitForTimeout(350);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`run pages — ${theme} at ${size.width}x${size.height}`, async () => {
      test.setTimeout(180_000);
      await page.setViewportSize(size);
      await setTheme(page, theme);

      for (const id of RUN_PAGES) {
        await gotoPage(page, id);
        await expectPage(page, id);
        await settle(page);
        if (id !== "preprocess") {
          const active = page.locator('[data-page-active="true"]');
          await expect(active.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
          await expect(active.getByTestId("scene-canvas")).toBeVisible();
        }

        // Soft, all four of them: one round of this spec should report every number that is out
        // of limits, not the first. A fail-fast gate makes a layout pass N runs long for N
        // findings.

        // L4 — nothing under the action bar, at any scroll position.
        const reach = await actionBarReach(page);
        if (reach.obstructed.length > 0) {
          console.log(`LAY-OBSTRUCTED ${id} ${theme} ${size.width}: ${JSON.stringify(reach.obstructed.slice(0, 8))}`);
          const rects = await page.evaluate(() => {
            const active = document.querySelector('[data-page-active="true"]');
            const r = (sel: string) => {
              const el = active?.querySelector(sel);
              if (!el) return null;
              const b = el.getBoundingClientRect();
              return { top: Math.round(b.top), bottom: Math.round(b.bottom), h: Math.round(b.height) };
            };
            const sc = active?.querySelector<HTMLElement>("[data-page-work-scroll]");
            return {
              main: r(".page-layout-main"),
              scroll: r("[data-page-work-scroll]"),
              bar: r(".action-bar"),
              scrollHeight: sc?.scrollHeight,
              clientHeight: sc?.clientHeight,
            };
          });
          console.log(`LAY-RECTS ${id}: ${JSON.stringify(rects)}`);
        }
        expect
          .soft(
            reach.obstructed,
            `${id} ${theme} ${size.width}: ${reach.obstructed.length} of ${reach.controls} controls (over ${reach.steps} scroll steps) hit-test to something else`,
          )
          .toEqual([]);

        // L5c — the page never scrolls sideways.
        const overflow = await horizontalOverflow(page);
        expect.soft(overflow.page, `${id} ${theme} ${size.width}: the page scrolls horizontally`).toBe(0);

        // L5b — every Tier-1 control on the first screen.
        const first = await firstScreenControls(page);
        expect
          .soft(first.total, `${id}: no Tier-1 controls found — the page lost its data-tier="1" marks`)
          .toBeGreaterThan(0);
        expect.soft(first.hidden, `${id} ${theme} ${size.width}: Tier-1 controls below the fold`).toEqual([]);

        // U1 — a right pane exists on a run page and the work pane takes the rest.
        const panes = await paneWidths(page);
        // work + handle(6) + right + 2 x --page-pad (16 below 1440, 24 at or above) = content box.
        const pad = size.width >= 1440 ? 24 : 16;
        expect
          .soft(
            panes.work + panes.right + panes.gap + 2 * pad,
            `${id}: panes do not fill the content box (work ${panes.work} + gap ${panes.gap} + right ${panes.right} vs ${panes.content})`,
          )
          .toBe(panes.content);

        // L5a — dead space, with the profile that says WHERE it is when it is over.
        const dead = await deadSpaceRatio(page);
        const profile = await deadSpaceProfile(page);
        console.log(
          `LAY ${id} ${theme} ${size.width}x${size.height} dead=${(dead.ratio * 100).toFixed(1)}% ` +
            `work=${(profile.work * 100).toFixed(1)}% right=${(profile.right * 100).toFixed(1)}% ` +
            `bands=[${profile.bands.map((b) => (b.ratio * 100).toFixed(0)).join(" ")}] ` +
            `tier1=${first.visible}/${first.total} obstructed=${reach.obstructed.length}`,
        );
        if (process.env.LAY_DIAG === "1") {
          const byChild = await deadSpaceByChild(page, '[data-testid="page-work"]', process.env.LAY_SEL ?? undefined);
          for (const c of byChild) {
            console.log(`LAY-CHILD ${id} ${theme} ${size.width} ${c.label} h=${c.height} dead=${(c.ratio * 100).toFixed(0)}%`);
          }
        }
        expect
          .soft(
            dead.ratio,
            `${id} ${theme} ${size.width}x${size.height}: dead space ${(dead.ratio * 100).toFixed(1)} % of ${dead.samples} samples`,
          )
          .toBeLessThanOrEqual(DEAD_SPACE_BY_PAGE[id] ?? DEAD_SPACE_MAX);
      }
    });
  }
}

/**
 * Lane UC's second finding, made a test: `RunWork`'s fill controller observed the **pane** and
 * nothing else, so a page whose content grew after mount kept the answer it had computed for a
 * page that no longer existed — and the naive fix (observe the content too) is what UC actually
 * measured going wrong: the sections "oscillated open/closed live while a later test filled in the
 * Analyzer form", and a `locator.click()` inside one raced "element detached from the DOM" for a
 * full 30 s.
 *
 * The Analyzer is the page UC found it on, and picking a simulation is the growth: `ResultsPanel`
 * goes from an empty table to a populated one. This asserts both halves — the controller reacts
 * (it is allowed to change its answer once) and then STOPS (two samples 600 ms apart agree, and
 * nothing is left under the action bar).
 */
test("the fill controller settles after the content grows (lane UC's second finding)", async () => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await setTheme(page, "light");
  await gotoPage(page, "analyzer");
  await expectPage(page, "analyzer");
  await settle(page);

  const openState = async (): Promise<string> =>
    page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>('[data-page-active="true"] [data-fill-section]'))
        .map((el) => `${el.dataset.fillSection}:${el.querySelector(".form-section-body") ? "open" : "closed"}`)
        .join(","),
    );

  // Since the 2026-09-06 jobs rework the Analyzer's simulation is a *row* cell, not a page-level
  // combobox, and (second pass) the Output section that used to be the growth is gone — Results
  // owns a simulation's existing analyses. The Jobs table is what grows now: three more rows are
  // three more rows of content appearing after mount, which is the same shape of growth the
  // controller must react to once and then stop reacting to.
  const analysisRow = analysisRows(page).first();
  await expect(analysisRow).toBeVisible();
  await setAnalysisCell(page, analysisRow, "simulation", "Thalamus");
  const addRow = page.getByTestId("analysis-jobs-footer").getByRole("button", { name: "Add row", exact: true });
  for (let i = 0; i < 3; i++) await addRow.click();
  await expect(analysisRows(page)).toHaveCount(4);
  await page.waitForTimeout(1_200);

  const first = await openState();
  // Not vacuous: the page must actually have sections the controller can act on.
  expect(first.split(",").filter(Boolean).length, "no [data-fill-section] on the Analyzer").toBeGreaterThan(0);
  await page.waitForTimeout(600);
  const second = await openState();
  expect(second, "the fill controller is still toggling sections after the content grew").toBe(first);

  const reach = await actionBarReach(page);
  expect(reach.obstructed, "controls obstructed after the content grew").toEqual([]);
});

test("the panel pages are reachable end to end at 1280x800", async () => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await setTheme(page, "light");
  for (const id of PANEL_PAGES) {
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page);
    const reach = await actionBarReach(page);
    expect(reach.obstructed, `${id}: obstructed controls`).toEqual([]);
    const overflow = await horizontalOverflow(page);
    expect(overflow.page, `${id}: the page scrolls horizontally`).toBe(0);
  }
});

/**
 * The run pane's range, in the one form that catches the defect the maintainer reported: a DRAG,
 * measured.
 *
 * What he saw was "the pane cannot be widened past its default". The cause was not the CSS default
 * but the divider: Pre-processing and Source pass no `paneController`, so they got the legacy
 * `InspectorHandle`, whose ceiling was a flat 560 px — *below* the run pane's own default on a
 * 2000 px screen, so dragging wider snapped it narrower. A test that only reads the default width
 * cannot see that; this one drags to both ends and reads what the pane measures.
 */
test("the run pane opens at 45 vw and drags between 36 vw and 70 vw", async () => {
  test.setTimeout(180_000);
  await setTheme(page, "light");
  const dragHandleBy = async (dx: number): Promise<number> => {
    const box = (await page.locator(String.raw`[data-page-active="true"]`).getByTestId("inspector-handle").boundingBox())!;
    await page.mouse.move(box.x + 3, box.y + Math.min(300, box.height / 2));
    await page.mouse.down();
    // Dragging LEFT widens the pane, so a negative dx is the "stretch" gesture.
    await page.mouse.move(box.x + 3 + dx, box.y + Math.min(300, box.height / 2), { steps: 20 });
    await page.mouse.up();
    await page.waitForTimeout(300);
    return (await paneWidths(page)).right;
  };

  for (const width of [1280, 1440, 2000]) {
    await page.setViewportSize({ width, height: 1250 });
    // A width stored by an earlier step would hide the default this asserts.
    await page.evaluate(() => {
      Object.keys(localStorage)
        .filter((k) => k.startsWith("tit-pane"))
        .forEach((k) => localStorage.removeItem(k));
    });
    await page.reload();
    await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
    await gotoPage(page, "preprocess", "Pre-processing");
    await expectPage(page, "preprocess");
    await settle(page);

    // Default: 45 vw, ceilinged at `100% - 566px` so the work pane keeps its >=560 px floor. That
    // ceiling binds at 1440 and only at 1440 (the labelled nav rail costs 216 px there).
    const panes = await paneWidths(page);
    const expected = width === 1440 ? 610 : Math.round(width * 0.45);
    expect(panes.right, `default pane width at ${width}`).toBe(expected);
    expect(panes.work, `work pane at ${width}`).toBeGreaterThanOrEqual(560);

    // Stretch: 70 vw, reached by dragging further than the ceiling so the clamp is what stops it.
    expect(await dragHandleBy(-1200), `stretched pane at ${width}`).toBe(Math.round(width * 0.7));
    // Pull back: 36 vw is the FLOOR now, not the default — the pane never gets narrow again.
    expect(await dragHandleBy(1600), `narrowed pane at ${width}`).toBe(Math.round(width * 0.36));
  }
});
