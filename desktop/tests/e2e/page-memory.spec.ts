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
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { activePage as activePageOf, fingerprint, settle, useThePage } from "./_pageMemory";
import { waitForScene } from "./_runPane";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECT = "ernie";
const ALL_PANELS = ["source", "cluster-permutation", "nifti-group-average", "nilearn-visuals", "quick-notes"];

/** The four pages built on the run skeleton (plan of record §4 L1). */
const RUN_PAGES = ["preprocess", "simulator", "optimizer", "analyzer"] as const;

/** The neutral page every round bounces off: it owns no run-page state of its own. */
const AWAY = "jobs";

let app: ElectronApplication;
let page: Page;

/** The shared helper takes its page explicitly; this file's call sites predate that. */
function activePage(target: Page = page) {
  return activePageOf(target);
}

// Deliberately NOT `mode: "serial"`, unlike the other specs that share one app: one round of this
// gate must report every page that forgot something, not stop at the first — the same reason
// `layout.spec.ts` reports all four run pages' numbers before it fails.

test.beforeAll(async () => {
  // V4 (dev/notes/v3-native-panes-external-viewer-plan.md): the embed, its protocol range and the
  // install/activate dance this suite used to perform around itself are gone. The run panes draw
  // with the app's own renderer and need nothing installed.
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
});

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
    expect(after.checks, `${id}: checkbox state`).toEqual(before.checks);
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
  // R5: selectors draft, Open commands. V1: what Open commands is the external Tetravox app, so
  // the page remembers a *selection*, which is all it ever had to remember.
  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await page.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "MNI", exact: true }).click();
  // VM2: the edited file list is part of the draft too — removing a row is a choice someone made,
  // and losing it on a tab switch is the same defect as losing the subject.
  await expect(page.getByTestId("viewer-preview-files")).toBeVisible({ timeout: 15_000 });
  const rows = await page.getByTestId("viewer-preview-files").locator("li .viewer-file-name").allTextContents();
  await page.getByTestId(`viewer-file-remove-${rows[0]!}`).click();
  await expect
    .poll(() => page.getByTestId("viewer-preview-files").locator("li .viewer-file-name").allTextContents())
    .toEqual(rows.slice(1));
  await awayAndBack("viewer");
  await expect(page.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "MNI", exact: true })).toBeChecked();
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("Thalamus");
  await expect
    .poll(() => page.getByTestId("viewer-preview-files").locator("li .viewer-file-name").allTextContents())
    .toEqual(rows.slice(1));
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
  /*
   * The rule under test belongs to the fill controller, but it needs a *collapsible* fill section
   * to aim at, and as of 2026-09-06 no run page has one on the page any more: the Simulator's last
   * one went with the free-hand section (the editor is a footer button now), and the Optimizer's
   * live inside its per-row dialog. Rather than assert against a page that cannot show the
   * behaviour, the test states its precondition and skips with a reason — it comes back by itself
   * the day a run page gets a collapsible section again.
   */
  const collapsibleCount = await activePage().locator("[data-fill-section][data-fill-collapsible]").count();
  test.skip(collapsibleCount === 0, "no run page currently renders a page-level collapsible fill section");
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
  await page.getByRole("option", { name: "Subject anatomy", exact: true }).click();
  await expect(page.getByTestId("viewer-source-bar").getByRole("combobox")).toHaveCount(3);
  const viewerSource = await page.getByTestId("viewer-source-bar").getByRole("combobox").allTextContents();
  const viewerNode = await viewer.elementHandle();

  await gotoPage(page, "simulator");
  await expect(viewer).toBeHidden();
  await expect(viewer).toHaveAttribute("inert", "");
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
  expect(await viewer.evaluate((current, previous) => current === previous, viewerNode)).toBe(true);
  expect(await page.getByTestId("viewer-source-bar").getByRole("combobox").allTextContents()).toEqual(viewerSource);
  await settle(page);
  expect(errors).toEqual([]);
  page.off("pageerror", recordError);
});

test("Results deep links replace the retained viewer selection without remounting the page", async () => {
  test.skip(TOKEN !== "mock-token", "the named simulations come from the mock catalog");
  await gotoPage(page, "viewer");
  const viewerPanel = page.locator('[data-page-panel="viewer"]');
  const viewerNode = await viewerPanel.elementHandle();
  await gotoPage(page, "results");
  await page.getByTestId("results-subject-filter").fill("");
  await page.getByTestId("results-subject-ernie").click();
  await page.getByTestId("results-tree-filter").fill("");
  await page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "All", exact: true }).click();
  await page.getByTestId("results-node-simulation:ernie:docs_example").click();
  await page.getByTestId("results-open-in-viewer").click();
  await expectPage(page, "viewer");
  // A deep link prefills the draft and opens nothing (R5/V1); Open is what launches Tetravox.
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("docs_example");
  expect(await viewerPanel.evaluate((current, previous) => current === previous, viewerNode)).toBe(true);
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
  // Addressed structurally, not by a named control: the Optimizer's page-level `#optimizer-run-name`
  // became a per-row `#opt-run-name-<row>` inside the 2026-09-06 jobs table's row editor, and what
  // this test measures is that a control in a HIDDEN panel cannot take focus — not which one.
  const hiddenFocusable = optimizer
    .locator('button, input, select, textarea, [tabindex="0"]')
    .first();
  await expect(hiddenFocusable).toHaveCount(1);
  await hiddenFocusable.evaluate((el: HTMLElement) => el.focus());
  await expect(nav).toBeFocused();

  const currentPane = activePage().locator(".page-layout-body");
  const simulatorMode = await currentPane.getAttribute("data-pane-mode");
  const chord = process.platform === "darwin" ? "Meta+Shift+i" : "Control+Shift+i";
  await page.keyboard.press(chord);
  await expect(currentPane).toHaveAttribute("data-pane-mode", simulatorMode === "collapsed" ? "normal" : "collapsed");
  await expect(hiddenPane).toHaveAttribute("data-pane-mode", optimizerMode!);
  await page.keyboard.press(chord);
  await expect(currentPane).toHaveAttribute("data-pane-mode", simulatorMode!);

  // Start the Tab walk from the first focusable in the *active* page's work column. Addressed
  // structurally rather than by a named control: the Simulator lost its page-level SubjectsField
  // to the 2026-09-06 jobs table, and what this test measures is where focus can land, not which
  // control it starts from.
  await activePage().getByTestId("page-work").locator("button, input, select, textarea, [tabindex=\"0\"]").first().focus();
  const focusStates: (string | null)[] = [];
  for (let index = 0; index < 20; index++) {
    await page.keyboard.press("Tab");
    focusStates.push(await page.evaluate(() => document.activeElement?.closest("[data-page-panel]")?.getAttribute("data-page-active") ?? null));
  }
  expect(focusStates).toContain("true");
  expect(focusStates).not.toContain("false");
});

test("pane collapse and expansion retain the live canvas, work DOM and a scrolled draft", async () => {
  test.setTimeout(90_000); // The first Simulator scene includes the guide fetch and the first GL frame.
  test.skip(TOKEN !== "mock-token", "the guide payloads come from the deterministic mock server");
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  const current = activePage();
  // The free-hand editor is opened from the jobs table's footer, next to "New montage" — it has
  // no section of its own (maintainer, 2026-09-06).
  await current.getByRole("button", { name: "New placement", exact: true }).click();
  await current.getByPlaceholder("e.g. custom_4electrode", { exact: true }).fill("pane_draft");
  await current.getByLabel("Position 1 X", { exact: true }).fill("12.5");
  await current.getByRole("button", { name: "Add position", exact: true }).click();
  await waitForScene(page);
  // The native canvas carries its own opacity chrome: the skin slider alone, no number input (the
  // embed's spinbuttons went with the embed). The grey matter is always opaque and has no control.
  // Nudge the skin off its default with the keyboard and remember what it became — the point of
  // the test is that collapsing the pane does not reset it.
  const skin = current.getByRole("slider", { name: "Skin opacity" });
  await expect(current.getByRole("slider", { name: "GM opacity" })).toHaveCount(0);
  await skin.focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowLeft");
  const skinValue = await skin.getAttribute("aria-valuenow");
  await settle(page);

  const pane = current.getByTestId("page-right-pane");
  // The native renderer's own canvas. Retaining it across a collapse is the whole claim: a
  // remounted canvas is a new WebGL2 context, a re-uploaded guide and a camera back at its
  // default — none of which the user asked for by hiding a pane.
  const frameLocator = current.getByTestId("scene-canvas");
  const frameNode = await frameLocator.elementHandle();
  const guideRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/guide/")) guideRequests.push(request.url());
  });
  const work = current.getByTestId("page-work");
  const workNode = await work.elementHandle();
  const input = current.getByPlaceholder("e.g. custom_4electrode", { exact: true });
  const inputNode = await input.elementHandle();
  const scroller = current.locator("[data-page-work-scroll]");
  // Half the available range, not a fixed 80 px. Collapsing the pane gives the work column the
  // whole window, its content re-flows shorter, and the browser CLAMPS scrollTop to the new
  // maximum on the spot — a loss no app code can undo on the way back. A fixed 80 was inside the
  // range when it was written and is outside it now that the Simulator's page-level sections
  // became a jobs table (max is 66 px here), so the test was measuring the clamp rather than the
  // retention. Half the range is inside both widths' range and still nonzero.
  // The Simulator's work column lost its last three page-level sections to per-job settings
  // (2026-09-06), so with one job row it does not scroll at all. Add rows until it does: what this
  // test is about is the offset surviving a pane collapse, not how the range came to exist.
  for (let i = 0; i < 10; i++) {
    const range = await scroller.evaluate((el) => el.scrollHeight - el.clientHeight);
    // Comfortably more than the 8 px this asked for before the free-hand section left the page: a
    // 26 px range put the half-way offset inside the clamp the collapsed pane applies, and the
    // test then measured the clamp instead of the retention.
    if (range > 80) break;
    await current.getByRole("button", { name: "Add job", exact: true }).click();
  }
  const scrollBefore = await scroller.evaluate((el) => {
    el.scrollTop = Math.floor((el.scrollHeight - el.clientHeight) / 2);
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
  await expect(skin).toHaveAttribute("aria-valuenow", skinValue!);
  await settle(page);
  expect(await frameLocator.evaluate((currentFrame, previous) => currentFrame === previous, frameNode)).toBe(true);
  // The context is live, not lost-and-restored, and nothing was re-fetched to redraw it.
  await expect(current.getByTestId("scene-context-lost")).toHaveCount(0);
  await expect(current.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  expect(guideRequests, `the retained canvas re-fetched the guide: ${guideRequests.join(", ")}`).toEqual([]);
  console.log(`PANE-MEMORY scroll=${scrollBefore}->${await scroller.evaluate((el) => el.scrollTop)} canvas=same opacity=${skinValue} guide-requests=0`);
});

test("the free-hand draft survives a navigation away and back", async () => {
  test.skip(TOKEN !== "mock-token", "the two named subjects come from the mock catalog");
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  const current = activePage();
  /*
   * Since the 2026-09-06 jobs rework the free-hand editor is opened from the jobs table's footer,
   * not a source *tab* — a job row picks a saved set in its own Montage cell. What the memory rule
   * is about is unchanged: an unfinished placement belongs to the project session, so stepping to
   * another page and back must not discard it.
   */
  // The editor may already be open — an earlier test in this file opens it, and the page is
  // retained for the whole file on purpose. Re-pressing the footer button is harmless either way.
  await current.getByRole("button", { name: "New placement", exact: true }).click();
  const subject = current.locator(".field", { hasText: /^Subject/ }).getByRole("combobox");
  const draftSubject = (await subject.textContent())?.trim() === "101" ? "ernie" : "101";
  await subject.click();
  await page.getByRole("option", { name: draftSubject, exact: true }).click();
  await current.getByPlaceholder("e.g. custom_4electrode", { exact: true }).fill("unfinished_source_draft");
  await current.getByLabel("Position 1 label", { exact: true }).fill("custom-A");
  await current.getByLabel("Position 1 Y", { exact: true }).fill("-23.5");
  await current.getByLabel("Position 1 Z", { exact: true }).fill("67.5");
  // Five positions are deliberately incomplete; a navigation must not silently repair them.
  while (await current.getByRole("button", { name: /^Remove position / }).count() > 4) {
    await current.getByRole("button", { name: /^Remove position / }).last().click();
  }
  await current.getByRole("button", { name: "Add position", exact: true }).click();
  await expect(current.getByRole("button", { name: /^Remove position / })).toHaveCount(5);
  // Scoped to *this* field's error: the page carries whatever other validation the earlier tests
  // in this file left behind (an emptied output-field list, say), and an unscoped `.field-error`
  // then resolves to two nodes and fails on strict mode rather than on the rule under test.
  await expect(current.locator(".field-error", { hasText: "Use 4 positions" })).toBeVisible();

  await gotoPage(page, "analyzer");
  await expectPage(page, "analyzer");
  await gotoPage(page, "simulator");
  await expectPage(page, "simulator");
  const back = activePage();
  // Whether the editor is open is page-session state too, so it comes back open with its draft.
  await expect(back.locator(".field", { hasText: /^Subject/ }).getByRole("combobox")).toContainText(draftSubject);
  await expect(back.getByPlaceholder("e.g. custom_4electrode", { exact: true })).toHaveValue("unfinished_source_draft");
  await expect(back.getByLabel("Position 1 label", { exact: true })).toHaveValue("custom-A");
  await expect(back.getByLabel("Position 1 Y", { exact: true })).toHaveValue("-23.5");
  await expect(back.getByLabel("Position 1 Z", { exact: true })).toHaveValue("67.5");
  await expect(back.getByRole("button", { name: /^Remove position / })).toHaveCount(5);
  await expect(back.locator(".field-error", { hasText: "Use 4 positions" })).toBeVisible();
  await expect(back.getByRole("button", { name: "Save placement", exact: true })).toBeDisabled();
});
