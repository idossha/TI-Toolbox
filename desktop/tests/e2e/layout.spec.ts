import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { setSectionOpen, expectPage, gotoPage, launchElectronApp, openPalette, setTheme, type Theme } from "./_helpers";
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
 * The layout pass's acceptance, as numbers (plan `dev/notes/v3-scene-ia-plan.md` §4, L1–L5).
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
 * limit: the subject list no longer pads itself out with ground rows (the maintainer's "just a
 * simple list of subjects" — they are the same horizontal lines a user read as a broken pane), so
 * on a 3-subject fixture the work column ends after the last subject and the room below it is
 * pane, not filler. This page also drops the run receipt (2026-09-06): its plan grid and the
 * action-bar digest already state the batch, so the ~80px strip the receipt held at the bottom of
 * the work column is now empty too. Measured 53.8 % at 1280x800 and 59.8 % at 1440x900 with three
 * subjects; both fall back towards the global limit as a real project's list grows. Every other
 * page is held to L5a exactly.
 */
const DEAD_SPACE_BY_PAGE: Record<string, number> = { preprocess: 0.62 };

const SUBJECT = "ernie";

let app: ElectronApplication;
let page: Page;
let restoreMockEmbed: { version: string; removeProtocol2: boolean } | undefined;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  if (TOKEN === "mock-token") {
    // The baked mock bundle speaks protocol 1: it shows the missing-camera error instead of a
    // populated ScenePane. The density gate must measure a ready viewport, not that failure box.
    const headers = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };
    const before = await fetch(`${SERVER_URL}/api/tetravox`, { headers });
    expect(before.ok, "read the mock viewer state before the layout fixture").toBe(true);
    const state = await before.json() as { active: { source: string; version: string }; installed: { version: string }[] };
    const installed = await fetch(`${SERVER_URL}/api/tetravox/install`, {
      method: "POST", headers, body: JSON.stringify({ version: "0.4.0" }),
    });
    expect(installed.ok, "activate the mock protocol-2 scene fixture").toBe(true);
    restoreMockEmbed = {
      version: state.active.source === "baked" ? "baked" : state.active.version,
      removeProtocol2: !state.installed.some((release) => release.version === "0.4.0"),
    };
  }
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-lay-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
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
  try {
    await app?.close();
  } finally {
    if (restoreMockEmbed) {
      const headers = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };
      const restored = await fetch(`${SERVER_URL}/api/tetravox/activate`, {
        method: "POST", headers, body: JSON.stringify({ version: restoreMockEmbed.version }),
      });
      expect(restored.ok, "restore the mock viewer active before the layout fixture").toBe(true);
      if (restoreMockEmbed.removeProtocol2) {
        const removed = await fetch(`${SERVER_URL}/api/tetravox/0.4.0`, { method: "DELETE", headers });
        expect(removed.ok, "remove the layout-only mock viewer installation").toBe(true);
      }
    }
  }
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
          await expect(active.getByTestId("scene-pane-tetravox-frame")).toBeVisible();
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

  await page.locator("#analyzer-simulation").click();
  await page.getByRole("option", { name: "Thalamus" }).first().click();
  // Open "Output" by hand rather than waiting for the fill controller to open it: since the run
  // receipt (plan C3) took its ~80px at the bottom of the work column, the Analyzer at 1280x800
  // no longer has the 96px of slack the controller needs to open a fifth section on its own. The
  // growth this test is about — `ResultsPanel` going from an empty table to a populated one — is
  // the same either way, and the assertions below (react once, then STOP) are unchanged.
  await setSectionOpen(page, "Output", true);
  await expect(page.getByTestId("analyses-table")).toBeVisible({ timeout: 15_000 });
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
