/**
 * **A run page remembers how the user left it** (lane N2, the maintainer's report: "the state of
 * the tabs is not persistent: jumping between tabs resets them").
 *
 * The failure this gate prevents, measured before the fix on 2026-09-04 against the mock server:
 * open a run page, close a section, open another, pick the Terminal tab, scroll the work pane,
 * type a run name — then go to Jobs and come back, and the page is a fresh page. Simulator's
 * `Electrodes`/`Conductivity` came back open after being closed by hand, Optimizer's "After the
 * search" came back closed after being opened, Analyzer's `Output` came back open, the right pane
 * fell back to Scene, the scroll offset went to 0 and the Optimizer's run name was empty. None of
 * that is a redraw: the page component unmounts on navigation (`app/App.tsx` renders one route
 * element), every page keeps its state in `useState`, and `RunWork`'s fill controller then
 * re-derives the section layout from whatever it measures on the new mount.
 *
 * The model this spec encodes (`dev/notes/v3-scene-ia/n2-notes.md` §1):
 *
 *   - **The user's state is theirs for the session.** A section they opened or closed, the
 *     Terminal/Scene tab they picked, where they scrolled, the segment they chose, what they
 *     typed. Nothing may recompute it while the app is running.
 *   - **Derived state may be recomputed** — but only for a section the user has *never* touched on
 *     this page in this session. That is the fill controller's whole remit.
 *
 * It asserts *state as data*, never a screenshot: a fingerprint object per page (section →
 * `aria-expanded`, the run pane's `data-tab`, the scroll offset, each segmented control's chosen
 * label, each text input's value) captured before navigating away and compared after coming back.
 * A picture cannot tell you that `Conductivity` was closed and is now open; this can.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { waitForScene } from "./_runPane";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const ALL_PANELS = ["source", "cluster-permutation", "nifti-group-average", "nilearn-visuals", "quick-notes"];

/** The four pages built on the run skeleton (plan of record §4 L1). */
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;

/** The neutral page every round bounces off: it owns no run-page state of its own. */
const AWAY = "jobs";

interface Fingerprint {
  /** Collapsible section id → open?; a non-collapsible section is not listed. */
  sections: Record<string, boolean>;
  /** The right pane's Terminal · Scene host, or `null` on a page that has none. */
  tab: string | null;
  /** Work-pane scroll offset, in px. */
  scrollTop: number;
  /** Segmented control (by `aria-label`) → the label of the chosen segment. */
  segments: Record<string, string>;
  /** Text input (by id, or by its label) → its value. */
  texts: Record<string, string>;
  /** Real (non-ground) table rows in the work pane — the maintainer's "row count changed 1 to 2". */
  rows: number;
}

let app: ElectronApplication;
let page: Page;

function activePage(target: Page = page): Locator {
  return target.locator('[data-page-active="true"]');
}

// Deliberately NOT `mode: "serial"`, unlike the other specs that share one app: one round of this
// gate must report every page that forgot something, not stop at the first — the same reason
// `layout.spec.ts` reports all four run pages' numbers before it fails.

test.beforeAll(async () => {
  if (TOKEN === "mock-token") {
    // Live run-pane continuity needs protocol 2 (meshes/camera), not the mock's protocol-1 floor.
    const installed = await fetch(`${SERVER_URL}/api/tetravox/install`, {
      method: "POST",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ version: "0.4.0" }),
    });
    expect(installed.ok, "mock activates the protocol-2 scene fixture").toBe(true);
  }
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-memory-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  if (TOKEN === "mock-token") {
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
    await page.evaluate((panels) => {
      window.localStorage.setItem("tit-enabled-panels", JSON.stringify(panels));
      window.localStorage.setItem("tit-enabled-panels-synced", "1");
    }, ALL_PANELS);
  }
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  // A page measured with no subject is measuring its empty state, which has no sections to
  // remember — the same reason `layout.spec.ts` picks a subject before it measures anything.
  await openPalette(page);
  await page.getByTestId("palette-input").fill(SUBJECT);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${SUBJECT}`) }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", SUBJECT, { timeout: 10_000 });
});

test.afterAll(async () => {
  await app?.close();
  if (TOKEN === "mock-token") {
    const activated = await fetch(`${SERVER_URL}/api/tetravox/activate`, {
      method: "POST",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ version: "baked" }),
    });
    expect(activated.ok, "restore the mock's original embed after this suite").toBe(true);
    const removed = await fetch(`${SERVER_URL}/api/tetravox/0.4.0`, {
      method: "DELETE", headers: { authorization: `Bearer ${TOKEN}` },
    });
    expect(removed.ok, "remove this suite's mock embed fixture").toBe(true);
  }
});

/** The fill controller works over rAF passes; nothing is read until it has stopped moving. */
async function settle(target: Page): Promise<void> {
  await target
    .waitForFunction(() => document.querySelectorAll('[data-page-active="true"] .skeleton').length === 0, undefined, { timeout: 5_000 })
    .catch(() => undefined);
  await target.waitForTimeout(500);
}

async function fingerprint(target: Page): Promise<Fingerprint> {
  return activePage(target).evaluate((root) => {
    const sections: Record<string, boolean> = {};
    root.querySelectorAll<HTMLElement>("[data-fill-section]").forEach((el) => {
      const trigger = el.querySelector<HTMLElement>("button.form-section-header-trigger");
      if (!trigger) return; // not collapsible — it has no state to remember
      sections[el.dataset.fillSection ?? ""] = trigger.getAttribute("aria-expanded") === "true";
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
    const rows = scroller
      ? scroller.querySelectorAll("table tbody tr:not([aria-hidden='true'])").length
      : 0;
    return {
      sections,
      tab: host?.dataset.tab ?? null,
      scrollTop: Math.round(scroller?.scrollTop ?? 0),
      segments,
      texts,
      rows,
    };
  });
}

/** Clicks a section header by its `data-fill-section` id and waits for the new `aria-expanded`. */
async function toggleSection(target: Page, id: string, want: boolean): Promise<void> {
  const trigger = activePage(target).locator(`[data-fill-section="${id}"] button.form-section-header-trigger`);
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", String(want));
}

/**
 * Everything a user would change on a run page in one visit, in one pass:
 * close an open section, open a closed one, pick Terminal, scroll, type.
 * Returns the settled state that navigating away and back must reproduce exactly.
 */
async function useThePage(target: Page): Promise<Fingerprint> {
  const start = await fingerprint(target);
  expect(Object.keys(start.sections).length, "a run page with no collapsible section proves nothing").toBeGreaterThan(0);

  // Close one and open a DIFFERENT one, so both directions are on the page at once: the fill
  // controller's natural drift is to open, so a section left closed is the harder half, and a
  // page that only ever re-opens what it closed would prove half the rule.
  //
  // Re-read between the two clicks: closing a section frees height, and the controller is entitled
  // to spend it on a section the user has never touched, so `start` no longer describes the page
  // by the time of the second click.
  const toClose = Object.entries(start.sections).find(([, open]) => open)?.[0];
  if (toClose) {
    await toggleSection(target, toClose, false);
    await settle(target);
  }
  const mid = await fingerprint(target);
  const toOpen = Object.entries(mid.sections).find(([id, open]) => !open && id !== toClose)?.[0];
  if (toOpen) {
    await toggleSection(target, toOpen, true);
    await settle(target);
  }

  // The right pane's tab: Scene is the default while nothing runs, so Terminal is always a change.
  if (start.tab !== null) {
    await target.getByRole("radiogroup", { name: "Run pane" }).getByRole("radio", { name: "Terminal", exact: true }).click();
    await expect(activePage(target).getByTestId("run-pane-tabs")).toHaveAttribute("data-tab", "terminal");
  }

  // Something typed, where the page has a free-text field of its own.
  const runName = activePage(target).locator("#optimizer-run-name");
  if ((await runName.count()) > 0) await runName.fill("n2-probe");

  // Scroll the work pane as far as it goes; 0 would not be a change.
  await activePage(target).evaluate((root) => {
    const el = root.querySelector<HTMLElement>("[data-page-work-scroll]");
    if (el) el.scrollTop = el.scrollHeight;
  });

  await settle(target);
  return fingerprint(target);
}

for (const id of RUN_PAGES) {
  test(`${id} — comes back exactly as the user left it`, async () => {
    test.setTimeout(120_000);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page);

    const before = await useThePage(page);

    await gotoPage(page, AWAY);
    await expectPage(page, AWAY);
    await gotoPage(page, id);
    await expectPage(page, id);
    await settle(page);

    const after = await fingerprint(page);
    console.log(`N2-MEMORY ${id} before=${JSON.stringify(before)}`);
    console.log(`N2-MEMORY ${id} after =${JSON.stringify(after)}`);

    expect(after.sections, `${id}: section open/closed state`).toEqual(before.sections);
    expect(after.tab, `${id}: right pane tab`).toEqual(before.tab);
    expect(after.segments, `${id}: segmented choices`).toEqual(before.segments);
    expect(after.texts, `${id}: typed values`).toEqual(before.texts);
    expect(after.rows, `${id}: table row count`).toBe(before.rows);
    expect(after.scrollTop, `${id}: work pane scroll offset`).toBe(before.scrollTop);
  });
}

async function awayAndBack(id: string): Promise<void> {
  await gotoPage(page, AWAY);
  await expectPage(page, AWAY);
  await gotoPage(page, id);
  await expectPage(page, id);
  await settle(page);
}

async function chooseSelectByLabel(label: string, option: string): Promise<void> {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function submitMockJob(kind: string, subject = SUBJECT): Promise<{ id: string }> {
  const res = await page.request.post(`${SERVER_URL}/api/jobs`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: { kind, config: { __mock_fast: true }, subject_ids: [subject], tags: ["memory"] },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

test("settings, results, jobs and viewer keep session-only page state beyond the run pages", async () => {
  test.setTimeout(180_000);
  test.skip(TOKEN !== "mock-token", "extended page-memory coverage uses the mock server fixtures");

  await gotoPage(page, "settings");
  await expectPage(page, "settings");
  await expect(page.locator("#settings-image-tag")).toBeVisible({ timeout: 20_000 });
  await page.locator("#settings-image-tag").fill("idossha/session-memory:round1");
  const unsafe = page.getByRole("switch", { name: "Allow unsafe overrides" });
  if (!(await unsafe.isChecked())) await unsafe.click();
  await awayAndBack("settings");
  await expect(page.locator("#settings-image-tag")).toHaveValue("idossha/session-memory:round1");
  await expect(page.getByRole("switch", { name: "Allow unsafe overrides" })).toBeChecked();

  await gotoPage(page, "results");
  await expectPage(page, "results");
  await page.getByTestId("results-subject-ernie").click();
  await expect(page.getByTestId("results-tree").getByRole("treeitem").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("results-subject-filter").fill("ern");
  await page.getByTestId("results-tree-filter").fill("flex");
  await page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "Flex", exact: true }).click();
  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();
  await awayAndBack("results");
  await expect(page.getByTestId("results-subject-filter")).toHaveValue("ern");
  await expect(page.getByTestId("results-tree-filter")).toHaveValue("flex");
  await expect(page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "Flex", exact: true })).toHaveAttribute("data-state", "on");
  await expect(page.getByTestId("results-preview")).toContainText("flex_Thalamus_20260810_101500");

  await submitMockJob("sim");
  await submitMockJob("analyzer");
  await gotoPage(page, "jobs");
  await expectPage(page, "jobs");
  await expect(page.getByTestId("jobs-table").getByText("analyzer", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  await chooseSelectByLabel("Kind", "analyzer");
  await page.getByRole("radiogroup", { name: "Grouping" }).getByRole("radio", { name: "Groups", exact: true }).click();
  await awayAndBack("jobs");
  await expect(page.locator("#jobs-filter-kind")).toContainText("analyzer");
  await expect(page.getByTestId("jobs-groups")).toBeVisible();
  await expect(page.getByTestId("jobs-table")).toHaveCount(0);

  await gotoPage(page, "viewer");
  await expectPage(page, "viewer");
  // R5: selectors draft, Load commands. The status bar's `space` cell reports the LOADED space,
  // so MNI has to be drafted and then loaded before it can read "mni".
  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await page.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "MNI", exact: true }).click();
  await page.getByTestId("viewer-load").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 15_000 });
  await expect(page.getByTestId("status-space")).toHaveText("mni", { timeout: 10_000 });
  await awayAndBack("viewer");
  await expect(page.getByTestId("status-space")).toHaveText("mni", { timeout: 10_000 });
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("Thalamus");
});

test("optional panel pages keep their drafts and selections while navigating", async () => {
  test.setTimeout(180_000);
  test.skip(TOKEN !== "mock-token", "panel page-memory coverage needs the mock server's all-panel fixture");

  await gotoPage(page, "panel-source");
  await expectPage(page, "panel-source");
  await activePage().locator(".subject-picker-row", { hasText: SUBJECT }).click();
  await activePage().getByTestId("subjects-filter").fill("ern");
  await page.locator("#source-fwd-spacing").click();
  await page.getByRole("option", { name: "6", exact: true }).click();
  await awayAndBack("panel-source");
  await expect(activePage().getByTestId("subjects-filter")).toHaveValue("ern");
  await expect(activePage().getByTestId(`subject-row-${SUBJECT}`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator("#source-fwd-spacing")).toContainText("6");

  await gotoPage(page, "panel-cluster-permutation");
  await expectPage(page, "panel-cluster-permutation");
  await page.getByRole("radio", { name: "Correlation" }).click();
  await activePage().getByLabel("Analysis name").fill("memory_cluster");
  await awayAndBack("panel-cluster-permutation");
  await expect(page.getByText("Correlation type")).toBeVisible();
  await expect(activePage().getByLabel("Analysis name")).toHaveValue("memory_cluster");

  await gotoPage(page, "panel-nifti-group-average");
  await expectPage(page, "panel-nifti-group-average");
  await activePage().getByLabel("Analysis name").fill("memory_average");
  await page.getByLabel("Group differences").fill("Group1-Group2");
  await awayAndBack("panel-nifti-group-average");
  await expect(activePage().getByLabel("Analysis name")).toHaveValue("memory_average");
  await expect(page.getByLabel("Group differences")).toHaveValue("Group1-Group2");

  await gotoPage(page, "panel-nilearn-visuals");
  await expectPage(page, "panel-nilearn-visuals");
  await page.getByLabel("Sub-directory name").fill("memory_visuals");
  const percentiles = page.getByRole("checkbox", { name: /Use percentile cutoffs/ });
  if (!(await percentiles.isChecked())) await percentiles.click();
  await awayAndBack("panel-nilearn-visuals");
  await expect(page.getByLabel("Sub-directory name")).toHaveValue("memory_visuals");
  await expect(page.getByRole("checkbox", { name: /Use percentile cutoffs/ })).toBeChecked();

  // (The `panel-subject-info` row-selection case that closed this test lived on a page R1
  // deleted; the Overview page's own selection memory is covered in `overview.spec.ts`.)
});

test("a deliberate pointer click is not inverted by the fill controller", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  await activePage().locator("[data-fill-section][data-fill-collapsible] button.form-section-header-trigger").first().waitFor({ timeout: 20_000 });
  const id = await activePage().evaluate((root) => {
    const sections = Array.from(root.querySelectorAll<HTMLElement>("[data-fill-section][data-fill-collapsible]"));
    const closed = sections.find((section) => section.querySelector("button.form-section-header-trigger")?.getAttribute("aria-expanded") === "false");
    return closed?.dataset.fillSection ?? sections[0]?.dataset.fillSection ?? "";
  });
  expect(id, "need a collapsible section to aim at").not.toBe("");
  const section = activePage().locator(`[data-fill-section="${id}"]`).first();
  const trigger = section.locator("button.form-section-header-trigger");
  const box = await trigger.boundingBox();
  expect(box, `section ${id} has a clickable header`).not.toBeNull();
  await page.mouse.move((box?.x ?? 0) + (box?.width ?? 0) / 2, (box?.y ?? 0) + (box?.height ?? 0) / 2);
  // This wait is longer than the fill controller's initial rAF passes. Before the guard, a section
  // could auto-open during this window and the click below would close it — then persist the wrong
  // user decision for the rest of the session.
  await page.waitForTimeout(350);
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(section).toHaveAttribute("data-fill-user", "open");
});

test("changing another tab's subject preserves preprocessing and the live viewer session", async () => {
  test.setTimeout(120_000); // Three populated tabs, each waiting for its API and embed handshake.
  test.skip(TOKEN !== "mock-token", "the cursor and message counters use the deterministic fake embed");
  const errors: string[] = [];
  const recordError = (error: Error) => errors.push(error.message);
  page.on("pageerror", recordError);

  await gotoPage(page, "preprocess");
  await settle(page);
  const preprocess = page.locator('[data-page-panel="preprocess"]');
  const preprocessingSubject = await preprocess.getByTestId("subjects-summary").textContent();
  const preprocessNode = await preprocess.elementHandle();

  await gotoPage(page, "viewer");
  const viewer = page.locator('[data-page-panel="viewer"]');
  await expectPage(page, "viewer");
  await expect(page.getByTestId("viewer-source-bar")).toBeVisible();
  // Pin the bar's shape rather than inheriting whatever type the draft happened to hold: R5 makes
  // the number of selectors a function of the view type (`subject` → type, subject, atlas).
  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Subject", exact: true }).click();
  await expect(page.getByTestId("viewer-source-bar").getByRole("combobox")).toHaveCount(3);
  await page.getByTestId("viewer-load").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 15_000 });
  const viewerSource = await page.getByTestId("viewer-source-bar").getByRole("combobox").allTextContents();
  const frameNode = await page.getByTestId("tetravox-frame").elementHandle();
  const embed = await frameNode!.contentFrame();
  expect(embed).not.toBeNull();
  await embed!.locator("body").click();
  await expect(page.getByTestId("status-ras")).toHaveText("12.0  -18.0  9.0");
  const messages = await embed!.evaluateHandle(() => {
    const counts = { load: 0, reset: 0, hello: 0 };
    window.addEventListener("message", (event) => {
      const type = event.data?.type as keyof typeof counts;
      if (event.source === window.parent && event.data?.tvx === 1 && type in counts) counts[type]++;
    });
    return counts;
  });

  await gotoPage(page, "simulator");
  await expect(viewer).toBeHidden();
  await expect(viewer).toHaveAttribute("inert", "");
  await expect(page.getByTestId("status-ras")).toHaveCount(0);
  await openPalette(page);
  await page.getByTestId("palette-input").fill("101");
  await page.getByRole("dialog").getByRole("option", { name: /^101/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "101");
  await expect(preprocess.getByTestId("subjects-summary")).toHaveText(preprocessingSubject ?? "");

  await gotoPage(page, "preprocess");
  expect(await preprocess.evaluate((current, previous) => current === previous, preprocessNode)).toBe(true);
  await expect(preprocess.getByTestId("subjects-summary")).toHaveText(preprocessingSubject ?? "");
  await gotoPage(page, "viewer");
  await expectPage(page, "viewer");
  await expect(viewer).toBeVisible();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie");
  expect(await page.getByTestId("tetravox-frame").evaluate((current, previous) => current === previous, frameNode)).toBe(true);
  expect(await page.getByTestId("viewer-source-bar").getByRole("combobox").allTextContents()).toEqual(viewerSource);
  await expect(page.getByTestId("status-ras")).toHaveText("12.0  -18.0  9.0");
  await settle(page);
  expect(await messages.jsonValue()).toEqual({ load: 0, reset: 0, hello: 0 });
  expect(errors).toEqual([]);
  page.off("pageerror", recordError);
});

test("Results deep links replace the retained viewer selection without replacing its iframe", async () => {
  test.skip(TOKEN !== "mock-token", "the named simulations come from the mock catalog");
  await gotoPage(page, "viewer");
  await page.getByTestId("viewer-load").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 15_000 });
  const frame = await page.getByTestId("tetravox-frame").elementHandle();
  await gotoPage(page, "results");
  await page.getByTestId("results-subject-filter").fill("");
  await page.getByTestId("results-subject-ernie").click();
  await page.getByTestId("results-tree-filter").fill("");
  await page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "All", exact: true }).click();
  await page.getByTestId("results-node-simulation:ernie:docs_example").click();
  await page.getByTestId("results-open-in-viewer").click();
  await expectPage(page, "viewer");
  // A deep link prefills the draft and loads nothing (R5); Load is what replaces the scene.
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("docs_example");
  await page.getByTestId("viewer-load").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 15_000 });
  expect(await page.getByTestId("tetravox-frame").evaluate((current, previous) => current === previous, frame)).toBe(true);
  await awayAndBack("viewer");
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("docs_example");
});

test("a subject's Results action updates an already visited Results tab", async () => {
  test.skip(TOKEN !== "mock-token", "the named subjects come from the mock catalog");
  await gotoPage(page, "results");
  await page.getByTestId("results-subject-filter").fill("");
  await page.getByTestId("results-subject-101").click();
  await expect(page.getByTestId("results-subject-101")).toHaveAttribute("aria-selected", "true");
  await gotoPage(page, "overview");
  await page.getByTestId("overview-row-ernie").click();
  await page.getByTestId("overview-open-results").click();
  await expectPage(page, "results");
  await expect(page.getByTestId("results-subject-ernie")).toHaveAttribute("aria-selected", "true");
});

test("hidden tabs cannot take focus or respond to the active pane's shortcut", async () => {
  await gotoPage(page, "optimizer");
  await expectPage(page, "optimizer");
  const optimizer = page.locator('[data-page-panel="optimizer"]');
  const hiddenPane = optimizer.locator(".page-layout-body");
  const optimizerMode = await hiddenPane.getAttribute("data-pane-mode");
  expect(optimizerMode).not.toBeNull();
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");

  const nav = page.getByTestId("nav-item-simulator");
  await nav.focus();
  await optimizer.locator("#optimizer-run-name").evaluate((input: HTMLInputElement) => input.focus());
  await expect(nav).toBeFocused();

  const currentPane = activePage().locator(".page-layout-body");
  const simulatorMode = await currentPane.getAttribute("data-pane-mode");
  const chord = process.platform === "darwin" ? "Meta+Shift+i" : "Control+Shift+i";
  await page.keyboard.press(chord);
  await expect(currentPane).toHaveAttribute("data-pane-mode", simulatorMode === "collapsed" ? "normal" : "collapsed");
  await expect(hiddenPane).toHaveAttribute("data-pane-mode", optimizerMode!);
  await page.keyboard.press(chord);
  await expect(currentPane).toHaveAttribute("data-pane-mode", simulatorMode!);

  await activePage().getByTestId("subjects-change").focus();
  const focusStates: (string | null)[] = [];
  for (let index = 0; index < 20; index++) {
    await page.keyboard.press("Tab");
    focusStates.push(await page.evaluate(() => document.activeElement?.closest("[data-page-panel]")?.getAttribute("data-page-active") ?? null));
  }
  expect(focusStates).toContain("true");
  expect(focusStates).not.toContain("false");
});

test("pane collapse and expansion retain the live iframe, work DOM and a scrolled draft", async () => {
  test.setTimeout(90_000); // The first Simulator scene includes its API build and iframe handshake.
  test.skip(TOKEN !== "mock-token", "the message counters inspect the deterministic fake embed");
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  const current = activePage();
  await current.getByRole("radiogroup", { name: "Montage source" }).getByRole("radio", { name: "Free-hand", exact: true }).click();
  await current.getByPlaceholder("e.g. custom_4electrode", { exact: true }).fill("pane_draft");
  await current.getByLabel("Position 1 X", { exact: true }).fill("12.5");
  await current.getByRole("button", { name: "Add position", exact: true }).click();
  await waitForScene(page);
  await current.getByRole("spinbutton", { name: "Skin opacity value" }).fill("31");
  await current.getByRole("spinbutton", { name: "Grey matter opacity value" }).fill("46");
  await settle(page);

  const pane = current.getByTestId("page-right-pane");
  const frameLocator = current.getByTestId("scene-pane-tetravox-frame");
  const frameNode = await frameLocator.elementHandle();
  const embed = await frameNode!.contentFrame();
  expect(embed).not.toBeNull();
  const messages = await embed!.evaluateHandle(() => {
    const counts = { load: 0, reset: 0, hello: 0 };
    window.addEventListener("message", (event) => {
      const type = event.data?.type as keyof typeof counts;
      if (event.source === window.parent && event.data?.tvx === 1 && type in counts) counts[type]++;
    });
    return counts;
  });
  const work = current.getByTestId("page-work");
  const workNode = await work.elementHandle();
  const input = current.getByPlaceholder("e.g. custom_4electrode", { exact: true });
  const inputNode = await input.elementHandle();
  const scroller = current.locator("[data-page-work-scroll]");
  const scrollBefore = await scroller.evaluate((el) => {
    el.scrollTop = Math.min(80, el.scrollHeight - el.clientHeight);
    return el.scrollTop;
  });
  expect(scrollBefore, "the expanded work test must start at a nonzero scroll offset").toBeGreaterThan(0);

  await current.getByTestId("pane-collapse").click();
  await expect(pane).toBeHidden();
  await expect(pane).toHaveAttribute("inert", "");
  expect(await pane.evaluate((el) => el.getBoundingClientRect().width)).toBe(0);
  expect(await frameNode!.evaluate((el) => el.isConnected)).toBe(true);
  await current.getByTestId("pane-collapsed-rail").click();
  await expect(pane).toBeVisible();
  expect(await frameLocator.evaluate((currentFrame, previous) => currentFrame === previous, frameNode)).toBe(true);

  await current.getByTestId("pane-expand").click();
  await expect(work).toBeHidden();
  await expect(work).toHaveAttribute("inert", "");
  expect(await work.evaluate((el) => el.getBoundingClientRect().width)).toBe(0);
  expect(await workNode!.evaluate((el) => el.isConnected)).toBe(true);
  // Even an explicit focus request cannot pull focus into the retained, expanded-away work.
  await current.getByTestId("pane-expand").focus();
  await inputNode!.evaluate((el: HTMLInputElement) => el.focus());
  await expect(current.getByTestId("pane-expand")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(work).toBeVisible();
  expect(await work.evaluate((currentWork, previous) => currentWork === previous, workNode)).toBe(true);
  expect(await input.evaluate((currentInput, previous) => currentInput === previous, inputNode)).toBe(true);
  await expect(input).toHaveValue("pane_draft");
  await expect(current.getByLabel("Position 1 X", { exact: true })).toHaveValue("12.5");
  await expect.poll(() => scroller.evaluate((el) => el.scrollTop)).toBe(scrollBefore);
  await expect(current.getByRole("spinbutton", { name: "Skin opacity value" })).toHaveValue("31");
  await expect(current.getByRole("spinbutton", { name: "Grey matter opacity value" })).toHaveValue("46");
  await settle(page);
  expect(await frameLocator.evaluate((currentFrame, previous) => currentFrame === previous, frameNode)).toBe(true);
  expect(await messages.jsonValue()).toEqual({ load: 0, reset: 0, hello: 0 });
  console.log(`PANE-MEMORY scroll=${scrollBefore}->${await scroller.evaluate((el) => el.scrollTop)} iframe=same loads=0 resets=0 hellos=0`);
});

test("Free-hand to Montage and back preserves the subject, unfinished positions and validation", async () => {
  test.skip(TOKEN !== "mock-token", "the two named subjects come from the mock catalog");
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  const current = activePage();
  const subjects = current.getByTestId("subjects-field");
  if ((await subjects.getAttribute("data-open")) !== "true") await subjects.getByTestId("subjects-change").click();
  await subjects.getByTestId("subjects-filter").fill("");
  for (const id of ["ernie", "101"]) {
    const box = subjects.getByRole("checkbox", { name: id, exact: true });
    if (!(await box.isChecked())) await box.click();
  }
  await subjects.getByTestId("subjects-change").click();
  const sources = current.getByRole("radiogroup", { name: "Montage source" });
  await sources.getByRole("radio", { name: "Free-hand", exact: true }).click();
  // Change the editor's current subject, rather than merely proving its first-subject default.
  const subject = current.locator(".field", { hasText: /^Subject/ }).getByRole("combobox");
  const draftSubject = (await subject.textContent())?.trim() === "101" ? "ernie" : "101";
  await subject.click();
  await page.getByRole("option", { name: draftSubject, exact: true }).click();
  await current.getByPlaceholder("e.g. custom_4electrode", { exact: true }).fill("unfinished_source_draft");
  await current.getByLabel("Position 1 label", { exact: true }).fill("custom-A");
  await current.getByLabel("Position 1 Y", { exact: true }).fill("-23.5");
  await current.getByLabel("Position 1 Z", { exact: true }).fill("67.5");
  // Five positions are deliberately incomplete; changing source must not silently repair them.
  while (await current.getByRole("button", { name: /^Remove position / }).count() > 4) {
    await current.getByRole("button", { name: /^Remove position / }).last().click();
  }
  await current.getByRole("button", { name: "Add position", exact: true }).click();
  await expect(current.getByRole("button", { name: /^Remove position / })).toHaveCount(5);
  await expect(current.locator(".field-error")).toContainText("Use 4 positions");

  await sources.getByRole("radio", { name: "Montage", exact: true }).click();
  await expect(current.getByPlaceholder("e.g. custom_4electrode", { exact: true })).toHaveCount(0);
  await sources.getByRole("radio", { name: "Free-hand", exact: true }).click();
  await expect(subject).toContainText(draftSubject);
  await expect(current.getByPlaceholder("e.g. custom_4electrode", { exact: true })).toHaveValue("unfinished_source_draft");
  await expect(current.getByLabel("Position 1 label", { exact: true })).toHaveValue("custom-A");
  await expect(current.getByLabel("Position 1 Y", { exact: true })).toHaveValue("-23.5");
  await expect(current.getByLabel("Position 1 Z", { exact: true })).toHaveValue("67.5");
  await expect(current.getByRole("button", { name: /^Remove position / })).toHaveCount(5);
  await expect(current.locator(".field-error")).toContainText("Use 4 positions");
  await expect(current.getByRole("button", { name: "Save configuration", exact: true })).toBeDisabled();
});
