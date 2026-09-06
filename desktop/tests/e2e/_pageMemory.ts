/**
 * The shared machinery behind the two page-memory gates: `tests/e2e/page-memory.spec.ts` (mock)
 * and `tests/e2e/real/page-memory.spec.ts` (live container). Both ask the same question — does a
 * run page come back exactly as the user left it — so the fingerprint and the "use the page" pass
 * live here once. The real spec drifted from the mock's when the Existing-outputs disclosure was
 * removed from Pre-processing (2026-09-06) and its "a run page with no collapsible section proves
 * nothing" precondition became false; sharing the code is what stops that happening again.
 */
import { expect, type Locator, type Page } from "@playwright/test";

export interface Fingerprint {
  /** Collapsible section id → open?; a non-collapsible section is not listed. */
  sections: Record<string, boolean>;
  /** Section id → whose decision its state is (`data-fill-user`: "open"/"closed"/""). */
  owned: Record<string, string>;
  /** The right pane's Terminal · Scene host, or `null` on a page that has none. */
  tab: string | null;
  /** Work-pane scroll offset, in px. */
  scrollTop: number;
  /** Segmented control (by `aria-label`) → the label of the chosen segment. */
  segments: Record<string, string>;
  /** Text input (by id, or by its label) → its value. */
  texts: Record<string, string>;
  /** Real (non-ground) table rows in the work pane. */
  rows: number;
  /**
   * Checkbox (by id, or by its accessible name) → ticked?. Pre-processing's whole form is
   * checkboxes and it has no collapsible section, no segmented control and no text field, so
   * without this its fingerprint was constant and remembering it proved nothing.
   */
  checks: Record<string, boolean>;
}

export function activePage(target: Page): Locator {
  return target.locator('[data-page-active="true"]');
}

/** The fill controller works over rAF passes; nothing is read until it has stopped moving. */
export async function settle(target: Page, opts: { skeletonMs?: number; quietMs?: number } = {}): Promise<void> {
  await target
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, {
      timeout: opts.skeletonMs ?? 5_000,
    })
    .catch(() => undefined);
  await target.waitForTimeout(opts.quietMs ?? 500);
}

export async function fingerprint(target: Page): Promise<Fingerprint> {
  return activePage(target).evaluate((root) => {
    const sections: Record<string, boolean> = {};
    const owned: Record<string, string> = {};
    root.querySelectorAll<HTMLElement>("[data-fill-section]").forEach((el) => {
      const trigger = el.querySelector<HTMLElement>("button.form-section-header-trigger");
      if (!trigger) return; // not collapsible — it has no state to remember
      const id = el.dataset.fillSection ?? "";
      sections[id] = trigger.getAttribute("aria-expanded") === "true";
      owned[id] = el.dataset.fillUser ?? "";
    });
    const host = root.querySelector<HTMLElement>('[data-testid="run-pane-tabs"]');
    const scroller = root.querySelector<HTMLElement>("[data-page-work-scroll]");
    const segments: Record<string, string> = {};
    root.querySelectorAll<HTMLElement>(".segmented[aria-label]").forEach((group) => {
      const on = group.querySelector<HTMLElement>('.segmented-item[data-state="on"]');
      segments[group.getAttribute("aria-label") ?? ""] = on?.textContent?.trim() ?? "";
    });
    const texts: Record<string, string> = {};
    root.querySelectorAll<HTMLInputElement>('input[type="text"], input:not([type])').forEach((input) => {
      const key = input.id || input.getAttribute("aria-label") || "";
      if (key) texts[key] = input.value;
    });
    // Ground rows (`tr.run-table-filler`, `tr.data-table-filler`) are `aria-hidden` padding drawn
    // to the bottom of a `fill` table and are not data — counting them would make this number a
    // function of the window height rather than of what the page holds.
    const rows = scroller ? scroller.querySelectorAll("table tbody tr:not([aria-hidden='true'])").length : 0;
    const checks: Record<string, boolean> = {};
    root.querySelectorAll<HTMLElement>('[role="checkbox"], input[type="checkbox"]').forEach((box) => {
      const key = box.id || box.getAttribute("aria-label") || box.closest("label")?.textContent?.trim() || "";
      if (!key || key in checks) return;
      checks[key] = box instanceof HTMLInputElement ? box.checked : box.getAttribute("aria-checked") === "true";
    });
    return { sections, owned, checks, tab: host?.dataset.tab ?? null, scrollTop: Math.round(scroller?.scrollTop ?? 0), segments, texts, rows };
  });
}

/** Clicks a section header by its `data-fill-section` id and waits for the new `aria-expanded`. */
export async function toggleSection(target: Page, id: string, want: boolean): Promise<void> {
  const trigger = activePage(target).locator(`[data-fill-section="${id}"] button.form-section-header-trigger`);
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", String(want));
}

/**
 * Everything a user would change on a run page in one visit, in one pass:
 * close an open section, open a closed one, pick Terminal, tick a checkbox, scroll, type.
 * Returns the settled state that navigating away and back must reproduce exactly.
 */
export async function useThePage(target: Page, settleOpts: { skeletonMs?: number; quietMs?: number } = {}): Promise<Fingerprint> {
  const start = await fingerprint(target);
  // Collapsible sections are the richest thing to remember, but they are not universal:
  // Pre-processing lost its only collapsible section when the Existing-outputs disclosure was
  // removed (2026-09-06), and its two FormSections are plain. So the guard at the end is that this
  // pass changed SOMETHING — sections, or the tab, or a checkbox, or a typed value, or the scroll
  // offset — rather than that sections exist. A page where nothing at all is changeable would
  // still prove nothing, and is still caught.

  // Close one and open a DIFFERENT one, so both directions are on the page at once: the fill
  // controller's natural drift is to open, so a section left closed is the harder half.
  // Re-read between the two clicks: closing a section frees height, and the controller is entitled
  // to spend it on a section the user has never touched.
  const toClose = Object.entries(start.sections).find(([, open]) => open)?.[0];
  if (toClose) {
    await toggleSection(target, toClose, false);
    await settle(target, settleOpts);
  }
  const mid = await fingerprint(target);
  const toOpen = Object.entries(mid.sections).find(([id, open]) => !open && id !== toClose)?.[0];
  if (toOpen) {
    await toggleSection(target, toOpen, true);
    await settle(target, settleOpts);
  }

  // The right pane's tab: Scene is the default while nothing runs, so Terminal is always a change.
  if (start.tab !== null) {
    await target.getByRole("radiogroup", { name: "Run pane" }).getByRole("radio", { name: "Terminal", exact: true }).click();
    await expect(activePage(target).getByTestId("run-pane-tabs")).toHaveAttribute("data-tab", "terminal");
  }

  // A checkbox, where the page has one — Pre-processing's only changeable state.
  const firstCheck = activePage(target).locator('[role="checkbox"], input[type="checkbox"]').first();
  if ((await firstCheck.count()) > 0 && (await firstCheck.isEnabled())) {
    await firstCheck.click();
    await settle(target, settleOpts);
  }

  // Something typed, where the page has a free-text field of its own.
  const runName = activePage(target).locator("#optimizer-run-name");
  if ((await runName.count()) > 0) await runName.fill("n2-probe");

  // Scroll the work pane as far as it goes; 0 would not be a change.
  await activePage(target).evaluate((root) => {
    const el = root.querySelector<HTMLElement>("[data-page-work-scroll]");
    if (el) el.scrollTop = el.scrollHeight;
  });

  await settle(target, settleOpts);
  const end = await fingerprint(target);
  const changeable = (f: Fingerprint) => JSON.stringify({ s: f.sections, t: f.tab, x: f.texts, o: f.scrollTop, c: f.checks });
  expect(changeable(end) !== changeable(start), "this page offered nothing to change, so remembering it proves nothing").toBe(true);
  return end;
}
