/**
 * Results — the shape of the preview pane, per output kind.
 *
 * The maintainer, on three screenshots: remove `View` and `Open` from every file row and keep only
 * the folder icon; give the analyzer (and every other kind) the Ex-search pane's shape — "the main
 * numerical things on top, then render the images, then a synthesis of the artifacts at the
 * bottom"; and clean up the group's duplicate header icons. This spec is the standing check on all
 * three, across the five kinds, so they cannot drift apart again.
 *
 * DOM state only (§8.1) — control counts, section order read off the live layout, and the actual
 * text of a number, never a picture.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
});
test.afterEach(async () => {
  await app?.close();
});

async function openResults(subject: string): Promise<void> {
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId(`results-subject-${subject}`).click();
  await expect(page.getByTestId("results-tree").getByRole("treeitem").first()).toBeVisible({
    timeout: 20_000,
  });
}

/**
 * The `data-testid`s of the pane's sections, in the order they are painted.
 *
 * Waits for the header block first: every kind builds its header from a manifest read through
 * `GET /api/files/text`, so a pane read the instant it is selected can be one section short.
 */
async function sectionOrder(): Promise<string[]> {
  await expect(page.getByTestId("results-header-block")).toBeVisible({ timeout: 15_000 });
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-testid="results-preview"] .results-preview-section')]
      .map((el) => {
        const marked = el.getAttribute("data-testid");
        if (marked) return marked;
        return el.querySelector(".results-eyebrow")?.textContent?.trim() ?? "(untitled)";
      }),
  );
}

/** Every button inside the pane's own header bar. */
function headerControls(): Locator {
  return page.locator('[data-testid="results-preview"] .results-preview-header button');
}

// ── the file rows ────────────────────────────────────────────────────────────

test("one folder icon per pane, zero per file row, and no View or Open button", async () => {
  await openResults("ernie");
  for (const node of [
    "results-node-simulation:ernie:Thalamus",
    "results-node-flex:ernie:flex_Thalamus_20260810_101500",
    "results-node-ex:ernie:ex_L_Insula_20260812_090000",
    "results-node-analysis:ernie:Thalamus/Thalamus_DK40_TI_max",
  ]) {
    await page.getByTestId(node).click();
    const files = page.getByTestId("results-files");
    await expect(files).toBeVisible();

    // The two buttons the maintainer struck out, gone from every row of every kind.
    await expect(files.getByRole("button", { name: /^View$/ })).toHaveCount(0);
    await expect(files.getByRole("button", { name: /^Open$/ })).toHaveCount(0);

    // And no per-row folder either: eleven buttons that all open the same directory are one
    // button. The row's only control is its own name, for the inline preview.
    const rows = files.locator("li");
    const rowCount = await rows.count();
    expect(rowCount, `${node} has files`).toBeGreaterThan(0);
    for (let i = 0; i < rowCount; i++) {
      const labels = await rows
        .nth(i)
        .locator(".results-file-line button")
        .evaluateAll((els) => els.map((el) => el.getAttribute("aria-label") ?? "name"));
      expect(labels.filter((l) => l !== "name"), `${node} row ${i} actions`).toHaveLength(0);
    }

    // The one that does open it is in the pane header, once.
    expect(await page.getByTestId("results-reveal-node").count(), `${node} header folder`).toBe(1);
    const folders = await page
      .locator('[data-testid="results-preview"] button[aria-label*="folder" i]')
      .count();
    expect(folders, `${node} folder icons in the whole pane`).toBe(1);
  }
});

test("the pane header keeps one folder icon, not a folder and a diagonal arrow", async () => {
  await openResults("ernie");
  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();

  // Screenshot 3: "there are two icons that do the same, both the folder and that diagonal arrow".
  await expect(page.getByRole("button", { name: "Open externally" })).toHaveCount(0);
  await expect(page.getByTestId("results-reveal-node")).toHaveCount(1);

  // What is left is the folder plus the pane's own collapse/expand controls — nothing else.
  const labels = await headerControls().evaluateAll((els) =>
    els.map((el) => el.getAttribute("aria-label") ?? ""),
  );
  expect(labels.filter((l) => /folder/i.test(l))).toHaveLength(1);
  expect(labels.some((l) => /external/i.test(l))).toBe(false);
});

test("clicking a previewable file's NAME opens it inline; a NIfTI's name is not a button", async () => {
  await openResults("ernie");
  await page.getByTestId("results-node-analysis:ernie:Thalamus/Thalamus_DK40_TI_max").click();

  // The `View` capability did not disappear with the button — it moved onto the name.
  await expect(page.getByTestId("results-file-preview")).toHaveCount(0);
  await page.getByTestId("results-file-summary.csv").click();
  const preview = page.getByTestId("results-file-preview");
  await expect(preview).toBeVisible();
  await expect(preview.locator("pre")).toContainText("roi_mean");
  // Clicking it again closes it; only one file is open at a time.
  await page.getByTestId("results-file-summary.csv").click();
  await expect(page.getByTestId("results-file-preview")).toHaveCount(0);

  // A file this pane cannot render is a plain row: label, name, folder icon, no name button.
  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();
  const statics = page.getByTestId("results-files").locator(".results-file-static");
  expect(await statics.count()).toBeGreaterThan(0);
  await expect(statics.first()).toContainText("NIfTI");
});

// ── the analyzer pane, reshaped ──────────────────────────────────────────────

test("an analysis reads header · key numbers · figures · files, not a 22-row metric dump", async () => {
  await openResults("ernie");
  await page.getByTestId("results-node-analysis:ernie:Thalamus/Thalamus_DK40_TI_max").click();

  expect(await sectionOrder()).toEqual([
    "results-header-block",
    "results-key-numbers",
    "Figures · 1",
    "results-files-section",
  ]);

  // The header block says what the analysis IS — the four descriptive rows of `results.csv`.
  const header = page.getByTestId("results-header-block");
  await expect(header).toContainText("TI_max");
  await expect(header).toContainText("Mesh (surface)");
  await expect(header).toContainText("Cortical region");
  await expect(header).toContainText("lh.bankssts + rh.bankssts");

  // The numbers are grouped and rounded. `0.07018370126141073` in the file, four digits on screen.
  const numbers = page.getByTestId("results-key-numbers");
  await expect(numbers).toContainText("0.07018 V/m");
  await expect(numbers).toContainText("0.1084 V/m");
  await expect(numbers).not.toContainText("0.07018370126141073");
  // SCI-03: the unit of `focality_*_area` depends on the space, so the label carries it.
  await expect(numbers).toContainText("Focality extent · cm²");
  await expect(numbers).toContainText("119.3 cm²");
  await expect(numbers).toContainText("4,957");

  // The analyzer's only picture is its histogram PDF, and it is a figure, not a file row.
  await expect(page.getByTestId("results-figures")).toBeVisible();
  await expect(page.getByTestId("results-files")).not.toContainText("PDF report");
});

test("a figure opens in a lightbox over the pane and Escape closes it", async () => {
  await openResults("ernie");
  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();
  await page.getByTestId("results-figures").locator("button").first().click();
  await expect(page.getByTestId("results-lightbox")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("results-lightbox")).toHaveCount(0);
});

// ── the other kinds keep the same order ──────────────────────────────────────

test("every kind paints the same section order", async () => {
  await openResults("ernie");
  const canonical = (order: string[]): string[] =>
    order.map((s) =>
      s === "results-header-block" || s === "results-key-numbers" || s === "results-files-section"
        ? s
        : "other",
    );

  await page.getByTestId("results-node-ex:ernie:ex_L_Insula_20260812_090000").click();
  const ex = await sectionOrder();
  expect(ex[0]).toBe("results-header-block");
  expect(ex.at(-1)).toBe("results-files-section");
  expect(ex.indexOf("results-ex-table")).toBeGreaterThan(0);
  expect(ex.indexOf("results-summary-ex")).toBeGreaterThan(ex.indexOf("results-ex-table"));

  await page.getByTestId("results-node-flex:ernie:flex_Thalamus_20260810_101500").click();
  const flex = await sectionOrder();
  expect(flex[0]).toBe("results-header-block");
  expect(flex.at(-1)).toBe("results-files-section");

  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();
  const sim = await sectionOrder();
  expect(sim[0]).toBe("results-header-block");
  // A simulation is the one kind with anything below its files: what it HOLDS (its analyses and
  // reports, as jumps) and the rendered report, which are navigation and a document, not artifacts.
  expect(canonical(sim).indexOf("results-files-section")).toBeGreaterThan(0);
  expect(sim.slice(sim.indexOf("results-files-section") + 1)).toEqual(["results-holds", "results-report-section"]);
});

// ── group statistics ─────────────────────────────────────────────────────────

test("a group-statistics run shows its inputs, its outcome, its clusters and its files", async () => {
  await openResults("Group");
  await page
    .getByTestId("results-node-analysis:Group:stats/group_comparison_Thalamus_TI_max_20260815")
    .click();

  // Screenshot 3: this pane used to be the single row "Kind analysis".
  await expect(page.getByTestId("results-preview")).not.toContainText("Kind analysis");

  const header = page.getByTestId("results-header-block");
  await expect(header).toContainText("group comparison");
  await expect(header).toContainText("Responders · 2");
  await expect(header).toContainText("101, MNI152");
  await expect(header).toContainText("Non-Responders · 1");
  await expect(header).toContainText("ernie");
  await expect(header).toContainText("(182, 218, 182)");

  const numbers = page.getByTestId("results-key-numbers");
  await expect(numbers).toContainText("Significant clusters");
  await expect(numbers).toContainText("Permutations");
  await expect(numbers).toContainText("100");
  await expect(numbers).toContainText("2.06e-08");

  const clusters = page.getByTestId("results-cluster-table");
  await expect(clusters.getByRole("table")).toContainText("Size (voxels)");
  await expect(clusters.getByRole("row")).toHaveCount(3); // header + 2

  // Its maps and its log, each with the one folder icon.
  const files = page.getByTestId("results-files");
  await expect(files).toContainText("p-value map (−log10 p)");
  await expect(files).toContainText("Analysis summary");
  await expect(files.getByRole("button", { name: /^View$/ })).toHaveCount(0);

  // One header icon, here as everywhere.
  await expect(page.getByRole("button", { name: "Open externally" })).toHaveCount(0);
  await expect(page.getByTestId("results-reveal-node")).toHaveCount(1);
});

test("a simulation shows channel labels and a single montage figure", async () => {
  await openResults("ernie");
  await page.getByTestId("results-node-simulation:ernie:Thalamus").click();

  const channels = page.getByTestId("results-pair-chips");
  await expect(channels.getByText("F7 → P7")).toBeVisible();
  await expect(channels.locator("img")).toHaveCount(0);
  const montage = page.getByTestId("results-figure-Thalamus_highlighted_visualization.png");
  await expect(montage).toHaveCount(1);
  await expect(page.getByTestId("results-figures").getByTestId("results-figure-Thalamus_highlighted_visualization.png")).toBeVisible();

  // Clicking it opens the same lightbox a flex-run PNG does.
  await montage.click();
  await expect(page.getByTestId("results-lightbox")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("a group-statistics run that wrote only a log says why, instead of showing a bare file", async () => {
  // The mock's `?empty=1` variant is the state of the maintainer's `smoke-ui-51129`: the 2-vs-1
  // comparison died in `ttest_voxelwise` and left one 1.5 kB log behind.
  await page.route("**/api/catalog/group/stats/**", async (route) => {
    const url = new URL(route.request().url());
    url.searchParams.set("empty", "1");
    await route.continue({ url: url.toString() });
  });
  await openResults("Group");
  await page
    .getByTestId("results-node-analysis:Group:stats/group_comparison_Thalamus_TI_max_20260815")
    .click();

  const notice = page.getByTestId("results-notice");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("This run produced no results");
  await expect(notice).toContainText("zero within-group variance");
  await expect(page.getByTestId("results-files")).toContainText("log");
});


test("selecting a result restores its collapsed preview for pointer and keyboard", async () => {
  await openResults("ernie");
  const simulation = page.getByTestId("results-node-simulation:ernie:Thalamus");
  await simulation.click();
  await expect(page.getByTestId("results-preview")).toBeVisible();
  await page.getByRole("button", { name: "Collapse the preview pane", exact: true }).click();
  await expect(page.getByTestId("results-preview")).toBeHidden();
  await simulation.click();
  await expect(page.getByTestId("results-preview")).toBeVisible();
  await page.getByRole("button", { name: "Collapse the preview pane", exact: true }).click();
  await page.getByTestId("results-tree").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("results-preview")).toBeVisible();
});
