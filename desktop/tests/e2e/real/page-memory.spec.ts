/**
 * **A run page remembers how the user left it — against the real server** (lane N2).
 *
 * `tests/e2e/page-memory.spec.ts` is the same gate against the mock; this one exists because the
 * maintainer reported the defect while driving the real app, and because the real container is the
 * only place the pages are populated with a real catalog: real EEG nets, real atlases, a real
 * simulation list. Those are what make the Analyzer's own tables gain rows on a second mount
 * ("its row count changed 1 to 2"), which the mock's fixture is too small to reproduce.
 *
 * It runs no job and writes nothing to the project — navigation and form state only — so it costs
 * seconds, not the sixteen minutes an emulated `sim` takes.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

const SUBJECT = process.env.TIT_E2E_SUBJECT ?? "ernie";
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;
const AWAY = "jobs";

interface Fingerprint {
  sections: Record<string, boolean>;
  owned: Record<string, string>;
  tab: string | null;
  scrollTop: number;
  segments: Record<string, string>;
  texts: Record<string, string>;
  rows: number;
}

let app: ElectronApplication;
let page: Page;

function activePage(target: Page = page): Locator {
  return target.locator('[data-page-active="true"]');
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-memory-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectReal(page);
  await selectSubject(page, SUBJECT);
});

test.afterAll(async () => {
  await app?.close();
});

async function settle(target: Page): Promise<void> {
  await target
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, { timeout: 15_000 })
    .catch(() => undefined);
  await target.waitForTimeout(700);
}

async function fingerprint(target: Page): Promise<Fingerprint> {
  return activePage(target).evaluate((root) => {
    const sections: Record<string, boolean> = {};
    const owned: Record<string, string> = {};
    root.querySelectorAll<HTMLElement>("[data-fill-section]").forEach((el) => {
      const trigger = el.querySelector<HTMLElement>("button.form-section-header-trigger");
      if (!trigger) return;
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
    const rows = scroller ? scroller.querySelectorAll("table tbody tr:not([aria-hidden='true'])").length : 0;
    return { sections, owned, tab: host?.dataset.tab ?? null, scrollTop: Math.round(scroller?.scrollTop ?? 0), segments, texts, rows };
  });
}

async function toggleSection(target: Page, id: string, want: boolean): Promise<void> {
  const trigger = activePage(target).locator(`[data-fill-section="${id}"] button.form-section-header-trigger`);
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", String(want));
}

for (const id of RUN_PAGES) {
  test(`${id} — comes back exactly as the user left it`, async () => {
    test.setTimeout(180_000);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page);

    const start = await fingerprint(page);
    expect(Object.keys(start.sections).length, "a run page with no collapsible section proves nothing").toBeGreaterThan(0);
    const toClose = Object.entries(start.sections).find(([, open]) => open)?.[0];
    if (toClose) {
      await toggleSection(page, toClose, false);
      await settle(page);
    }
    const mid = await fingerprint(page);
    const toOpen = Object.entries(mid.sections).find(([sid, open]) => !open && sid !== toClose)?.[0];
    if (toOpen) {
      await toggleSection(page, toOpen, true);
      await settle(page);
    }
    if (start.tab !== null) {
      await page.getByRole("radiogroup", { name: "Run pane" }).getByRole("radio", { name: "Terminal", exact: true }).click();
      await expect(activePage().getByTestId("run-pane-tabs")).toHaveAttribute("data-tab", "terminal");
    }
    const runName = activePage().locator("#optimizer-run-name");
    if ((await runName.count()) > 0) await runName.fill("n2-probe");
    await activePage().evaluate((root) => {
      const el = root.querySelector<HTMLElement>("[data-page-work-scroll]");
      if (el) el.scrollTop = el.scrollHeight;
    });
    await settle(page);
    const before = await fingerprint(page);

    await gotoPage(page, AWAY);
    await expectPage(page, AWAY);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page);

    const after = await fingerprint(page);
    console.log(`N2-REAL ${id} before=${JSON.stringify(before)}`);
    console.log(`N2-REAL ${id} after =${JSON.stringify(after)}`);

    expect(after.sections, `${id}: section open/closed state`).toEqual(before.sections);
    expect(after.owned, `${id}: whose decision each section's state is`).toEqual(before.owned);
    expect(after.tab, `${id}: right pane tab`).toEqual(before.tab);
    expect(after.segments, `${id}: segmented choices`).toEqual(before.segments);
    expect(after.texts, `${id}: typed values`).toEqual(before.texts);
    expect(after.rows, `${id}: table row count`).toBe(before.rows);
    expect(after.scrollTop, `${id}: work pane scroll offset`).toBe(before.scrollTop);
  });
}
