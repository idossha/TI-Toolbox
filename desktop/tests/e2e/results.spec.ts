/**
 * Results — the v3 outputs browser (program U4, DESIGN.md §2 shape B / §12.3, wireframes §6).
 *
 * Every assertion here is DOM state or a measured number, never a picture (§8.1): the tree's rows
 * and their badges, the pane widths `paneWidths()` reads off the layout, the dead-space ratio, and
 * the status cell the page registered. The screenshots this spec writes are evidence for a human.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, expectSubject, gotoPage, launchElectronApp } from "./_helpers";
import { captureScreen, deadSpaceRatio, paneWidths, type PageMetrics } from "./_metrics";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "results";

let app: ElectronApplication;
let page: Page;

async function launchApp(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
}

/** Opens Results and waits for ernie's tree — the page's own populated marker. */
async function openResults(subject = "ernie"): Promise<void> {
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId(`results-subject-${subject}`).click();
  await expect(page.getByTestId("results-tree").getByRole("treeitem").first()).toBeVisible({ timeout: 20_000 });
}

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("is a subject list, an outputs tree and a preview — no header, no subject dropdown", async () => {
  await connect();
  await openResults();

  // U4: the v2 page's two signatures are gone.
  await expect(page.locator(".page-header")).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "Subject" })).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveCount(0);

  // Every subject at once, with its output count, and `Group` pinned last.
  const list = page.getByTestId("results-subjects");
  await expect(list.getByRole("option")).toHaveCount(4);
  await expect(page.getByTestId("results-subject-ernie")).toContainText("12");
  await expect(page.getByTestId("results-subject-MNI152")).toHaveText("MNI1520");
  const options = await list.getByRole("option").allInnerTexts();
  expect(options[options.length - 1]).toContain("Group");

  // The five groups of ernie's outputs, with the counts the tree module computes.
  // `innerText` honours the headings' `text-transform: uppercase`, so compare on the words.
  const headings = await page.getByTestId("results-tree").getByRole("treeitem", { expanded: true }).allInnerTexts();
  expect(headings.map((t) => t.replace(/\s+/g, " ").trim().toLowerCase())).toEqual([
    "simulations 3",
    "flex runs 1",
    "ex / mex runs 2",
    "analyses 3",
    "reports 3",
  ]);

  // Type badges come from the shared vocabulary (checklist item 3).
  await expect(page.getByTestId("results-node-simulation:ernie:Thalamus")).toContainText("TI");
  await expect(page.getByTestId("results-node-simulation:ernie:docs_example")).toContainText("mTI");
  await expect(page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500")).toContainText("flex");

  // §11: no bottom status bar, so nothing on this page registers a cell for one.
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
});

/**
 * U14 — "make sure that in the top right section we are presenting meaningful information rather
 * than just the path". A simulation preview opens with what the run WAS: its mode, its net, its
 * electrode pairs, its currents, its geometry — read from the run's own
 * `documentation/config.json` through `GET /api/files/text` — then its field files, then what it
 * holds, then the rendered report. The container path is one line at the foot.
 */
test("a simulation previews its configuration, its files and its report — not its path", async () => {
  await connect();
  await openResults();

  // The summary, from the real `config.json` this mock serves (tests/fixtures/preview/).
  const summary = page.getByTestId("results-summary-rows");
  await expect(summary).toBeVisible();
  const rows = summary.locator("dt");
  await expect(rows.filter({ hasText: "Mode" })).toBeVisible();
  await expect(summary).toContainText("TI");
  await expect(summary).toContainText("EEG10-10_Cutini_2011");
  await expect(summary).toContainText("1 / 1 mA");
  await expect(summary).toContainText("ellipse · 8 × 8 mm · gel 4 mm · rubber 2 mm");
  await expect(summary).toContainText("surface, fsaverage");
  // The electrode pairs are chips, one per stimulation channel.
  const chips = page.getByTestId("results-pair-chips");
  await expect(chips.getByText("F7 → P7")).toBeVisible();
  await expect(chips.getByText("F8 → P8")).toBeVisible();

  // The field files, from the catalog, with their kind badges.
  const fields = page.getByTestId("results-files");
  await expect(fields).toContainText("TI_max · subject");
  await expect(fields).toContainText("NIfTI");
  await expect(fields).toContainText("mesh");

  // What this simulation holds: its analyses and its report, each a jump to that node.
  const holds = page.getByTestId("results-holds");
  await expect(holds.getByRole("button", { name: /Thalamus_DK40_TI_max/ })).toBeVisible();
  await holds.getByRole("button", { name: /Thalamus simulation report/ }).first().click();
  await expect(page.getByTestId("results-preview")).toContainText("Thalamus simulation report");

  // Back on the simulation, the report is inline under the numbers and still sandboxed.
  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();
  const frame = page.getByTestId("results-report-frame");
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  await expect(frame).toHaveAttribute("src", /\/api\/files\/report\/ernie-thalamus-2026-08-01$/);
  await expect(page.frameLocator('[data-testid="results-report-frame"]').getByRole("heading", { name: /Thalamus simulation/ })).toBeVisible({
    timeout: 10_000,
  });

  // The path is one mono line at the FOOT with a copy control — never the headline (U14).
  const pathLine = page.getByTestId("results-preview-path");
  await expect(pathLine).toContainText("/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus");
  await expect(page.getByTestId("results-copy-path")).toBeVisible();
  const foot = (await page.getByTestId("results-preview-path").boundingBox())!;
  const head = (await page.getByTestId("results-preview").boundingBox())!;
  expect(foot.y, "the path sits in the bottom third of the pane").toBeGreaterThan(head.y + head.height * 0.66);

  // D3: no Freeview, no Gmsh, no "Open externally ▾".
  await expect(page.getByRole("button", { name: /Freeview|Gmsh|Open externally ▾/ })).toHaveCount(0);
});

test("a flex run previews its goal, its best value and its final electrode positions", async () => {
  await connect();
  await openResults();
  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();

  // From `flex_meta.json`, which the catalog already inlines as `FlexRun.manifest`.
  const summary = page.getByTestId("results-summary-rows");
  await expect(summary).toContainText("focality_tf · max_TI");
  await expect(summary).toContainText("2 · 2 multistart");
  await expect(summary).toContainText("-91.5567");
  // From `summary.txt`, read through the files route.
  await expect(summary).toContainText("differential_evolution");
  await expect(summary).toContainText("710");
  await expect(summary).toContainText("1057 s");

  // From `electrode_positions.json`: four electrodes, each with its channel and array index.
  const positions = page.getByTestId("results-flex-positions");
  await expect(positions.getByRole("table")).toContainText("Channel");
  await expect(positions.getByRole("row")).toHaveCount(5); // header + 4 electrodes

  // The run's PNGs are thumbnails, its other files are rows.
  await expect(page.getByTestId("results-figures")).toBeVisible();
  await expect(page.getByText("Convergence plot")).toBeVisible();
  await expect(page.getByText("Run manifest")).toBeVisible();
});

test("an ex run previews its search config and the ten best montages", async () => {
  await connect();
  await openResults();
  await page.getByTestId("results-node-ex:ernie:ex_L_Insula_20260812_090000").click();

  // From `run_config.json`, read through the files route.
  const summary = page.getByTestId("results-summary-rows");
  await expect(summary).toContainText("L_Insula_MNI.csv · r 5 mm");
  await expect(summary).toContainText("EEG10-10_UI_Jurak_2007");
  await expect(summary).toContainText("bucket · symmetric (within pairs)");
  await expect(summary).toContainText("343");
  await expect(summary).toContainText("2 mA · step 0.25 mA");
  // Its four electrode buckets.
  await expect(page.getByTestId("results-summary-ex")).toContainText("F7 FT7 T7 F5 FC5 AF7 F3");

  // The ranked table: ten rows, best composite index first, projected onto the columns that matter.
  const table = page.getByTestId("results-ex-table");
  await expect(table.getByRole("table")).toContainText("TImax_ROI");
  await expect(table.getByRole("table")).not.toContainText("TImean_GM");
  await expect(table.getByRole("row")).toHaveCount(11); // header + 10
});

test("selecting an ex-search run and an analysis swaps the preview for their tables", async () => {
  await connect();
  await openResults();

  await page.getByTestId("results-node-ex:ernie:ex_L_Insula_20260812_090000").click();
  await expect(page.getByTestId("results-ex-table")).toBeVisible();
  // "TImax_ROI" appears only in the per-montage results table this run's preview renders.
  await expect(page.getByTestId("results-ex-table").getByRole("table")).toContainText("TImax_ROI");
  // The run's own artifacts, from the same cached list read the tree was built from.
  await expect(page.getByText("Final output")).toBeVisible();
  await expect(page.getByText("Ranked montages plot")).toBeVisible();

  await page.getByTestId("results-node-analysis:ernie:Thalamus/Thalamus_DK40_TI_max").click();
  await expect(page.getByTestId("results-key-numbers")).toBeVisible();
  await expect(page.getByText("Summary table")).toBeVisible();
  await expect(page.getByText("PDF report")).toBeVisible();
});

test("the filter box and the kind segments narrow the tree", async () => {
  await connect();
  await openResults();

  await page.getByTestId("results-tree-filter").fill("thalamus");
  await expect(page.getByTestId("results-tree").getByRole("treeitem", { level: 2 })).toHaveCount(5);

  await page.getByTestId("results-tree-filter").fill("");
  await page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "Ex", exact: true }).click();
  const rows = page.getByTestId("results-tree").getByRole("treeitem");
  await expect(rows).toHaveCount(3); // one heading + ex + mex
  await expect(page.getByTestId("results-node-mex:ernie:mex_Thalamus_20260814_140000")).toBeVisible();
});

test("the tree is navigable from the keyboard", async () => {
  await connect();
  await openResults();

  await page.getByTestId("results-tree").focus();
  // Home puts the roving focus on the first heading; two rows down is the second simulation.
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("results-node-simulation:ernie:L_Insula")).toHaveAttribute("aria-selected", "true");

  // Left on a heading collapses it, and its nodes leave the tree.
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("results-node-simulation:ernie:Thalamus")).toHaveCount(0);
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("results-node-simulation:ernie:Thalamus")).toBeVisible();
});

test("the Group pseudo-subject holds the project catalog", async () => {
  await connect();
  await openResults();

  await page.getByTestId("results-subject-Group").click();
  const headings = await page.getByTestId("results-tree").getByRole("treeitem", { expanded: true }).allInnerTexts();
  expect(headings.map((t) => t.replace(/\s+/g, " ").trim().toLowerCase())).toEqual([
    "group statistics 1",
    "nilearn visuals 1",
    "group analyses 1",
  ]);
  // A group output has no subject-space field, so it offers no viewer link rather than a broken one.
  await expect(page.getByTestId("results-open-in-viewer")).toHaveCount(0);
});

test("a subject with no outputs drops the preview pane and the tree takes its width", async () => {
  await connect();
  await gotoPage(page, "results", "Results");
  await page.getByTestId("results-subject-MNI152").click();
  await expect(page.getByTestId("results-tree")).toContainText("MNI152 has no outputs yet.");

  const panes = await paneWidths(page);
  expect(panes.right).toBe(0); // U1 in its enforceable form
  expect(panes.work).toBe(panes.content);
});

test("'Open in viewer' opens the scene, it does not park you on the Menu", async () => {
  // Maintainer, 2026-09-07: *"Open in viewer sends me to the Menu but doesn't actually select the
  // correct items. It should automatically open the visualizer with the minimal selection of what
  // makes sense for a quick visualization."* The link now carries `?open=1`, and the Viewer runs
  // the same `open()` its own button runs.
  await connect();
  await openResults();

  await page.getByTestId("results-open-in-viewer").click();
  await expectPage(page, "viewer");
  await expectSubject(page, "ernie");

  // Landed on the Tetravox sub-page with a scene, rather than on the Menu with a form.
  await expect(page.getByTestId("viewer-sub-viewer")).toHaveAttribute("data-active", "true", { timeout: 20_000 });

  // That the Menu behind it is pre-filled with the selection the scene was built from is asserted
  // in `viewer.spec.ts` ("a deep link that asks to open..."), which already has the tree helpers
  // for it. This spec's claim is the navigation.
});

test("hits its §12.3 numbers at 1280x800 and 1440x900, light and dark", async () => {
  test.setTimeout(180_000);
  await connect();
  await openResults();

  const rows: PageMetrics[] = [];
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    for (const theme of ["light", "dark"] as const) {
      const row = await captureScreen(page, {
        runId: RUN_ID,
        pageId: `results-lane-${theme}`,
        theme,
        width: size.width,
        height: size.height,
        waitFor: async () => {
          await expect(page.getByTestId("results-tree").getByRole("treeitem").first()).toBeVisible();
          await expect(page.getByTestId("results-preview")).toBeVisible();
        },
      });
      rows.push({ ...row, width: size.width, height: size.height });

      // Panes, wireframes §6: list 200 · tree ≥ 400 · preview clamp(380, 40% of the content box, 560).
      const expectedPreview = Math.min(560, Math.max(380, Math.round(row.panes.content * 0.4)));
      expect(Math.abs(row.panes.right - expectedPreview), `preview width at ${size.width}`).toBeLessThanOrEqual(8);
      const list = await page.getByTestId("results-subjects").evaluate((el) => Math.round(el.getBoundingClientRect().width));
      expect(list).toBe(200);
      const tree = await page.getByTestId("results-tree-pane").evaluate((el) => Math.round(el.getBoundingClientRect().width));
      expect(tree, `tree width at ${size.width}`).toBeGreaterThanOrEqual(400);

      // No page header anywhere on this page (checklist item 2).
      expect(row.pageHeaderHeight).toBe(0);
    }
  }

  // §12.3: results ≤ 20 % dead on the populated state. Reported for every capture, and broken down
  // per column, so a regression says which column moved rather than "the page got worse".
  const worst = rows.reduce((a, b) => (a.deadSpaceRatio > b.deadSpaceRatio ? a : b));
  // Two numbers per column: the whole column, and just the region its rows occupy. Both are now
  // meaningful: the list/tree own their row-capacity ground, so a short fixture no longer turns the
  // browser shape into bare app ground below the real rows.
  const columns = {
    list: (await deadSpaceRatio(page, '[data-testid="results-subjects"]')).ratio,
    listRows: (await deadSpaceRatio(page, ".results-subject-list")).ratio,
    tree: (await deadSpaceRatio(page, '[data-testid="results-tree-pane"]')).ratio,
    treeRows: (await deadSpaceRatio(page, '[data-testid="results-tree-rows"]')).ratio,
    preview: (await deadSpaceRatio(page, '[data-testid="results-preview"]')).ratio,
  };
  const geometry = await page.evaluate(() => {
    const r = (sel: string): string => {
      const el = document.querySelector(sel);
      if (!el) return `${sel}: absent`;
      const b = el.getBoundingClientRect();
      return `${sel} ${Math.round(b.width)}x${Math.round(b.height)}@${Math.round(b.left)},${Math.round(b.top)}`;
    };
    return [
      r('[data-testid="shell-content"]'),
      r('[data-testid="page-work"]'),
      r('[data-testid="page-right-pane"]'),
      r('[data-testid="results-subjects"]'),
      r('[data-testid="results-tree-pane"]'),
      r('[data-testid="results-preview"]'),
      r(".results-preview-body"),
      r(".results-report-frame"),
      r('[data-testid="results-files-section"]'),
    ].join(" | ");
  });
  console.log("results geometry:", geometry);
  console.log("results preview dead-space ratio:", columns.preview);
  console.log(
    "results dead space:",
    rows.map((r) => `${r.theme} ${r.width}x${r.height} ${(r.deadSpaceRatio * 100).toFixed(1)}%`).join(" · "),
    "| columns at 1440 dark:",
    Object.entries(columns).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`).join(" · "),
  );
  // Keep the row and whole-page budgets. The preview intentionally lost its duplicate Channels
  // image; assert that content contract instead of requiring the removed image's occupied area.
  expect(columns.treeRows, "outputs tree rows").toBeLessThanOrEqual(0.05);
  expect(columns.listRows, "subject list rows").toBeLessThanOrEqual(0.05);
  await expect(page.getByTestId("results-pair-chips").locator("img")).toHaveCount(0);
  await expect(page.getByTestId("results-figures").locator("img")).toHaveCount(1);

  // DESIGN.md §12.3, restored as the page-level gate: the subject list and tree now draw their own
  // measured ground rows rather than handing their empty tails back to the page background.
  expect(worst.deadSpaceRatio, `worst: ${worst.theme} ${worst.width}x${worst.height}`).toBeLessThanOrEqual(0.2);
});

/**
 * U13 — "the results also look great but similarly … allow to stretch/collapse/expand the right
 * hand side". Same primitive as Jobs (`ui/Layout.tsx`'s `usePaneController`), same measured
 * acceptance: +200 px of drag is +200 px of pane, collapsed is 0, expanded takes the work pane's
 * width, and the width comes back after a reload.
 */
test("the preview pane stretches, collapses, expands and remembers its width", async () => {
  await connect();
  await openResults();

  const before = await paneWidths(page);
  // The design's own default at 1280: clamp(380px, 40% of the 1224px content box, 560px).
  expect(before.right).toBe(490);
  const row = before.work + before.gap + before.right;
  expect(row, "the browse shape spends the whole content box").toBe(before.content);

  // --- stretch.
  const handle = page.getByTestId("inspector-handle");
  await expect(handle).toHaveAttribute("role", "separator");
  await expect(handle).toHaveAttribute("aria-valuenow", "490");
  // 70 vw of the 1280 px window (DESIGN.md §2.1) — the ceiling is window-relative now, not a flat
  // 880, so it can never sit below a pane's own default.
  await expect(handle).toHaveAttribute("aria-valuemax", "896");
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2, { steps: 10 });
  await page.mouse.up();
  const dragged = await paneWidths(page);
  expect(dragged.right - before.right, `dragged: ${JSON.stringify(dragged)}`).toBeGreaterThanOrEqual(196);
  expect(dragged.right - before.right).toBeLessThanOrEqual(204);
  expect(before.work - dragged.work).toBe(dragged.right - before.right);

  // --- collapse: the retained pane is hidden, and the tree takes the width back but for the rail.
  await page.getByTestId("pane-collapse").click();
  await expect(page.locator('[data-page-active="true"]').getByTestId("page-right-pane")).toBeHidden();
  const collapsed = await paneWidths(page);
  expect(collapsed.right).toBe(0);
  expect(collapsed.work).toBe(row - 16);
  const rail = page.getByTestId("pane-collapsed-rail");
  await expect(rail).toHaveAccessibleName("Show the preview pane");
  await rail.click();
  expect((await paneWidths(page)).right).toBe(dragged.right);

  // --- expand: the pane is the page, for reading a report at full width.
  await page.getByTestId("pane-expand").click();
  const expanded = await paneWidths(page);
  expect(expanded.work, "the tree is gone, not merely narrow").toBe(0);
  expect(expanded.right).toBeGreaterThanOrEqual(row - 4);
  await expect(page.getByTestId("results-tree")).toBeHidden();
  await expect(page.getByTestId("results-preview")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("results-tree")).toBeVisible();
  expect((await paneWidths(page)).right).toBe(dragged.right);

  // --- persistence, keyed per page: `tit-pane-results`, not the one Jobs writes.
  await page.reload();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
  await openResults();
  expect((await paneWidths(page)).right).toBe(dragged.right);
  expect(await page.evaluate(() => localStorage.getItem("tit-pane-v3-results"))).toContain(`"width":${dragged.right}`);
  expect(await page.evaluate(() => localStorage.getItem("tit-pane-v3-jobs"))).toBeNull();
});

test("⌘⇧I collapses the preview, and a subject with no outputs does not swallow it", async () => {
  await connect();
  await openResults();
  const chord = process.platform === "darwin" ? "Meta+Shift+i" : "Control+Shift+i";

  await page.keyboard.press(chord);
  await expect(page.locator('[data-page-active="true"]').getByTestId("page-right-pane")).toBeHidden();
  await expect(page.getByTestId("pane-collapsed-rail")).toBeVisible();
  await page.keyboard.press(chord);
  await expect(page.getByTestId("page-right-pane")).toBeVisible();

  // MNI152 has no outputs, so there is no pane to collapse and no rail to show (U1).
  await page.getByTestId("results-subject-MNI152").click();
  await expect(page.getByTestId("results-tree")).toContainText("MNI152 has no outputs yet.");
  await page.keyboard.press(chord);
  await expect(page.getByTestId("pane-collapsed-rail")).toHaveCount(0);
  expect((await paneWidths(page)).work).toBe((await paneWidths(page)).content);
});
