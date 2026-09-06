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
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject } from "../_helpers";
import { fingerprint, settle, useThePage } from "../_pageMemory";

const SUBJECT = process.env.TIT_E2E_SUBJECT ?? "ernie";
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;
const AWAY = "jobs";

/** The real container's pages populate from a real catalog, so give the fill controller longer to
 *  stop moving than the mock's fixtures need. */
const SETTLE = { skeletonMs: 15_000, quietMs: 700 };

let app: ElectronApplication;
let page: Page;

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

for (const id of RUN_PAGES) {
  test(`${id} — comes back exactly as the user left it`, async () => {
    test.setTimeout(180_000);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page, SETTLE);

    const before = await useThePage(page, SETTLE);

    await gotoPage(page, AWAY);
    await expectPage(page, AWAY);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page, SETTLE);

    const after = await fingerprint(page);
    console.log(`N2-REAL ${id} before=${JSON.stringify(before)}`);
    console.log(`N2-REAL ${id} after =${JSON.stringify(after)}`);

    expect(after.sections, `${id}: section open/closed state`).toEqual(before.sections);
    expect(after.owned, `${id}: whose decision each section's state is`).toEqual(before.owned);
    expect(after.tab, `${id}: right pane tab`).toEqual(before.tab);
    expect(after.segments, `${id}: segmented choices`).toEqual(before.segments);
    expect(after.texts, `${id}: typed values`).toEqual(before.texts);
    expect(after.rows, `${id}: table row count`).toBe(before.rows);
    expect(after.checks, `${id}: checkbox state`).toEqual(before.checks);
    expect(after.scrollTop, `${id}: work pane scroll offset`).toBe(before.scrollTop);
  });
}
