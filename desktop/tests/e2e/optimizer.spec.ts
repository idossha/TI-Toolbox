import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page, type Request } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, deadSpaceRatio, firstScreenControls, type PageMetrics } from "./_metrics";
import {
  addOptRow,
  optRowDetail,
  clearOptRows,
  closeOptEditor,
  openOptEditor,
  optRowSummary,
  optRows,
  setOptCell,
  setOptSubject,
} from "./_jobs";

/**
 * Optimizer — the **jobs table** page (lane OJ, 2026-09-06, DESIGN.md §4.7).
 *
 * Maintainer, on a screenshot of the page still showing a global Subjects list and "No subjects
 * selected": *"create something similar logically to the Simulator and Analyzer: choose a subject,
 * then an optimisation approach (Flex, Ex, mEx…) and configure each job exactly how they want, so
 * users create a list of jobs and run them."*
 *
 * So what is asserted here is the row: that it owns its subject, its method, its net or leadfield,
 * its goal and its whole form; that the page has no global copy of any of those; and that a table
 * of rows reaches the wire as the jobs it promised — one `POST /api/jobs/groups` per job KIND,
 * which is the one thing `GROUP_KINDS` will not let be a single request.
 *
 * Asserts DOM state and measured geometry, never pixels (§8.1).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "optimizer";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

/** The `.field` whose label matches — scoped to a root, because every form now lives in a dialog. */
function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
}

/** Picks a cortical DK40 region inside an open row editor — the flex target gesture. */
async function pickCorticalTarget(dialog: Locator, region = "L · bankssts"): Promise<void> {
  await field("Atlas", dialog).getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: /Desikan-Killiany/i }).click();
  await field("Region(s)", dialog).getByRole("combobox").click();
  await page.getByPlaceholder("Filter regions…").fill("bankssts");
  await page.getByRole("option", { name: region, exact: true }).click();
  await page.getByTestId("roi-region-done").click();
}

/** Ticks a saved ROI inside an open row editor — the ex/mEx target gesture. */
async function pickSavedTarget(dialog: Locator, name: string): Promise<void> {
  await dialog.getByText(name, { exact: true }).locator("xpath=ancestor::label[1]").getByRole("checkbox").click();
}

/** Fills the four Ex buckets with one electrode each. */
async function fillExBuckets(dialog: Locator): Promise<void> {
  for (const [bucket, electrode] of [
    ["E1+", "E1"],
    ["E1-", "E2"],
    ["E2+", "E3"],
    ["E2-", "E4"],
  ] as const) {
    await field(bucket, dialog).getByRole("combobox").click();
    // The bucket's own list dialog, named by its heading: "Filter electrodes…" is a *placeholder*,
    // not text content, so `hasText` never matches it.
    const list = page.getByRole("dialog").filter({ hasText: `${bucket} — choose electrodes` });
    await list.getByPlaceholder("Filter electrodes…").fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
    await list.getByRole("button", { name: "Done" }).click();
    await expect(field(bucket, dialog).getByRole("combobox")).toHaveText(electrode);
  }
}

/**
 * Presses Run, answering the existing-outputs question (C3) with "Replace" when it appears —
 * ernie's ex/mEx runs already exist in the fixture catalog, so the plan is an overwrite and the
 * page asks before it queues anything. Unchanged behaviour; the specs just have to answer it.
 */
async function pressRun(): Promise<void> {
  await page.getByTestId("run-button").click();
  const replace = page.getByTestId("existing-outputs-replace");
  if (await replace.isVisible().catch(() => false)) await replace.click();
}

/** Collects every job submission the next gesture makes. */
function collectGroups(): { bodies: Record<string, unknown>[]; stop: () => void } {
  const bodies: Record<string, unknown>[] = [];
  const collect = (request: Request) => {
    if (/[/]api[/]jobs([/]groups)?$/.test(new URL(request.url()).pathname) && request.method() === "POST") {
      bodies.push(request.postDataJSON() as Record<string, unknown>);
    }
  };
  page.on("request", collect);
  return { bodies, stop: () => page.off("request", collect) };
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  // The shell's subject seeds the table's first row; after that the row owns it.
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });

  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
});

test.afterAll(async () => {
  await app?.close();
});

test("one page, one jobs table: no page-level subject set and no global search form", async () => {
  // U7: two nav entries copied from the PyQt tab strip became one page.
  await expect(page.getByTestId("nav-item-optimizer")).toHaveCount(1);
  await expect(page.getByTestId("nav-item-optimizer-flex")).toHaveCount(0);
  await expect(page.getByTestId("nav-item-optimizer-ex")).toHaveCount(0);

  // §4.7 rule 1: the row owns its subject, so the page has no subject control at all — this is the
  // "No subjects selected" list the maintainer's screenshot was of.
  await expect(page.getByTestId("subjects-field")).toHaveCount(0);
  // …and rule 5's converse: nothing on this page is a property of the *run*, so the global method
  // segment, TARGET section and cost read-out are gone with it.
  await expect(page.getByRole("radiogroup", { name: "Method" })).toHaveCount(0);
  await expect(page.getByTestId("page-work").locator(".roi-picker")).toHaveCount(0);
  await expect(page.getByTestId("page-work").locator(".form-section-title", { hasText: "Target" })).toHaveCount(0);

  const table = page.getByTestId("opt-jobs-table");
  await expect(table).toBeVisible();
  await expect(table.locator("thead th")).toHaveText(["Subject", "Method", "Net / leadfield", "Goal", ""]);
  // One row on first visit, already on the shell's subject: the page's first act is choosing what
  // to search for, not discovering a control.
  await expect(optRows(page)).toHaveCount(1);
  await expect(optRows(page).first()).toHaveAttribute("data-subject", "ernie");
  await expect(optRows(page).first()).toHaveAttribute("data-method", "flex");
  // Two methods, not five: the kind a row submits as is derived from its editor, never picked here.
  await optRows(page).first().locator('td[data-cell="method"]').getByRole("combobox").click();
  await expect(page.getByRole("option")).toHaveText(["Flex", "Ex"]);
  await page.keyboard.press("Escape");

  // §2.3 / §8: no page header; shape A is work pane + run panel + action bar.
  await expect(page.locator(".page-header")).toHaveCount(0);
  const pane = page.getByTestId("page-right-pane");
  await expect(pane.getByTestId("run-panel")).toBeVisible();
  await expect(pane.getByTestId("plan-grid")).toBeVisible();
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(pane.getByTestId("job-terminal")).toBeVisible();
  await expect(page.getByTestId("page-work").locator(".action-bar")).toBeVisible();
});

test("adding a row does not open the editor, and neither does clicking one", async () => {
  // Coordinator, 2026-09-06: adding a job and configuring it are two acts, and a single click on a
  // row only moves the active-row focus. A dialog that opens itself takes the keyboard away from
  // someone assembling three rows, and a click-to-edit row cannot be *selected* at all.
  await clearOptRows(page);
  await page.getByRole("button", { name: "Add job", exact: true }).click();
  await expect(optRows(page)).toHaveCount(1);
  await expect(page.getByTestId("opt-row-editor")).toHaveCount(0);
  const first = optRows(page).first();
  // The new row is the ACTIVE one — the wash and the 3-D pane follow it.
  await expect(first).toHaveAttribute("data-active", "true");

  const second = await addOptRow(page);
  await expect(page.getByTestId("opt-row-editor")).toHaveCount(0);
  await expect(second).toHaveAttribute("data-active", "true");

  // A single click moves focus back, and opens nothing.
  await first.locator('td[data-cell="method"]').click({ position: { x: 2, y: 2 } });
  await expect(first).toHaveAttribute("data-active", "true");
  await expect(second).not.toHaveAttribute("data-active", "true");
  await expect(page.getByTestId("opt-row-editor")).toHaveCount(0);

  // The three ways IN: the pencil, the target line, and a double-click on the row.
  await openOptEditor(page, first, "settings");
  await closeOptEditor(page);
  await openOptEditor(page, first);
  await closeOptEditor(page);
  await first.locator('td[data-cell="method"]').dblclick({ position: { x: 2, y: 2 } });
  await expect(page.getByTestId("opt-row-editor")).toBeVisible();
  await closeOptEditor(page);

  // Keyboard: the arrows move the active row, Enter opens its editor.
  await first.locator("tr.opt-job-line1").focus();
  await page.keyboard.press("ArrowDown");
  await expect(second).toHaveAttribute("data-active", "true");
  await page.keyboard.press("ArrowUp");
  await expect(first).toHaveAttribute("data-active", "true");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("opt-row-editor")).toHaveAttribute("data-row", await first.getAttribute("data-opt-row") as string);
  await closeOptEditor(page);

  await second.locator('td[data-cell="actions"]').getByRole("button", { name: /^Remove job/ }).click();
  await expect(optRows(page)).toHaveCount(1);
});

test("the entry is two lines of a fixed 63px, and the table never scrolls sideways", async () => {
  const row = optRows(page).first();
  const box = (await row.boundingBox())!;
  const parts = await row.evaluate((el) => [...el.querySelectorAll("tr")].map((tr) => tr.getBoundingClientRect().height));
  console.log(`OJ-GEOM entry=${box.height} lines=${JSON.stringify(parts)}`);
  // The Analyzer's own band for a two-line entry (`analyzer.spec.ts`: 56-64), and this table
  // measures 63.5 inside it — one rhythm across the three run pages, asserted the same way rather
  // than as a pixel this page alone would own.
  expect(box.height).toBeGreaterThanOrEqual(56);
  expect(box.height).toBeLessThanOrEqual(64);
  // The two lines are one block: line 2 starts where line 1 ends.
  const [line1, line2] = await row.evaluate((el) => [...el.querySelectorAll("tr")].map((tr) => tr.getBoundingClientRect().y));
  expect(Math.abs((line2 as number) - ((line1 as number) + parts[0]!))).toBeLessThan(2);

  const container = page.getByTestId("opt-jobs-table-container");
  const overflow = await container.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow, "the jobs table must not scroll sideways").toBeLessThanOrEqual(1);

  // Nothing a row does to itself moves a column: the widths come from the colgroup resolver, and
  // only a deliberate drag of a header boundary changes one.
  const before = await container.evaluate((el) => [...el.querySelectorAll("thead th")].map((th) => Math.round(th.getBoundingClientRect().width)));
  await setOptCell(page, row, "method", "Ex");
  await expect(row).toHaveAttribute("data-method", "ex");
  const after = await container.evaluate((el) => [...el.querySelectorAll("thead th")].map((th) => Math.round(th.getBoundingClientRect().width)));
  expect(after).toEqual(before);
  await setOptCell(page, row, "method", "Flex");
});

test("Flex: the row's editor holds the target and the form, and one flex job reaches the wire", async () => {
  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-target-ready", "false");
  await expect(optRowSummary(row)).toHaveText("Choose a target…");

  const dialog = await openOptEditor(page, row);
  // The one shared picker, in the flex family's three modes — the same control the Analyzer's
  // target dialog holds, only scoped to this row.
  await expect(dialog.locator(".roi-picker")).toHaveCount(1);
  await expect(dialog.getByRole("radio", { name: "Cortical", exact: true })).toBeVisible();
  // Every section the page used to carry globally is here, scoped to the row.
  for (const section of ["Objective", "Electrodes", "Solver", "After the search"]) {
    await expect(dialog.locator(".form-section-title", { hasText: section }).first()).toHaveCount(1);
  }
  // The header line is the same structure as the Ex editor's — the two dialogs match: the subject
  // and the run name on one line under the title, and no Run name row in the body.
  const meta = dialog.locator(".optimizer-dialog-meta");
  await expect(meta.locator(".optimizer-dialog-subject")).toHaveText("ernie");
  await expect(meta.getByRole("textbox")).toHaveAttribute("placeholder", "auto (timestamp)");
  await expect(dialog.getByTestId("opt-row-editor").locator(".field", { hasText: "Run name" })).toHaveCount(0);
  const subjectBox = (await meta.locator(".optimizer-dialog-subject").boundingBox())!;
  const runBox = (await meta.getByRole("textbox").boundingBox())!;
  expect(Math.abs(runBox.y + runBox.height / 2 - (subjectBox.y + subjectBox.height / 2))).toBeLessThan(6);
  expect(runBox.x).toBeGreaterThan(subjectBox.x + subjectBox.width);

  await pickCorticalTarget(dialog);
  await closeOptEditor(page);

  // Line 2 states the target AND what the search will cost, from the same `cost.ts` the digest
  // reads — the two cannot disagree.
  await expect(row).toHaveAttribute("data-target-ready", "true");
  // Line 2 is an efficient summary: the target first, then only the essentials — no repetition of
  // the method (line 1 says it), no bucket bookkeeping, no solve estimate.
  await expect(optRowSummary(row)).toHaveText("lh.bankssts · DK40");
  await expect(optRowDetail(row)).toHaveText("goal mean · 2 pairs · 1 mA · ratio 1:1");

  await expect(page.getByTestId("plan-grid").getByTestId("plan-stat-jobs")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run search");

  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await pressRun();
  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    parallel_subjects: number;
    subject_configs: { subject_id: string; config: { goal: string; roi: { _type: string; label: number[] } } }[];
  };
  expect(body.kind).toBe("flex");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.parallel_subjects).toBe(1);
  expect(body.subject_configs.map((e) => e.subject_id)).toEqual(["ernie"]);
  expect(body.subject_configs[0]!.config.roi._type).toBe("AtlasROI");
  expect(body.subject_configs[0]!.config.roi.label).toEqual([1]); // tests/fixtures/atlas_regions.json

  // §4.6 rule 2: the terminal names the job this page started.
  await expect(page.getByTestId("job-terminal").getByTestId("job-terminal-identity")).toContainText("flex", { timeout: 15_000 });
});

test("duplicate, then re-point the copy: two subjects, two rows, each with its OWN atlas path", async () => {
  // §4.7 rule 4: repeating a job for another subject is one click on the row — the cross-product a
  // page-level subject set used to force is now something the user asks for.
  const first = optRows(page).first();
  await first.locator('td[data-cell="actions"]').getByRole("button", { name: /^Duplicate job/ }).click();
  await expect(optRows(page)).toHaveCount(2);
  const second = optRows(page).nth(1);
  // The copy is the same search, so it needs nothing but a new subject.
  await expect(optRowSummary(second)).toHaveText("lh.bankssts · DK40");
  await setOptSubject(page, second, "101");

  await expect(page.getByTestId("plan-stat-jobs").locator(".plan-stat-value")).toHaveText("2", { timeout: 15_000 });
  await expect(page.locator('[data-testid^="plan-cell-ernie-"]')).toHaveCount(3); // Flex · Ex · mEx columns
  await expect(page.getByTestId("plan-cell-ernie-flex")).toBeVisible();
  await expect(page.getByTestId("plan-cell-101-flex")).toBeVisible();

  // The three count columns are evenly spaced and the first does not hug the subject id — the same
  // rule and the same measurement as the Simulator's, because it is the same grid (maintainer,
  // 2026-09-06). Measured geometry, not the stylesheet.
  const geometry = await page.locator('[data-page-active="true"] .plan-matrix').evaluate((table) => {
    const head = [...table.querySelectorAll("thead th")];
    const xs = head.slice(1).map((th) => th.getBoundingClientRect().x);
    const subjectText = table.querySelector("tbody th .mono")?.getBoundingClientRect();
    const firstCount = head[1]?.getBoundingClientRect();
    const pad = head[1] ? parseFloat(getComputedStyle(head[1]).paddingLeft) : 0;
    return { xs, gap: (firstCount?.x ?? 0) + pad - (subjectText?.right ?? 0) };
  });
  const [ax, bx, cx] = geometry.xs as [number, number, number];
  expect(Math.abs(bx - ax - (cx - bx)), `column steps ${bx - ax} vs ${cx - bx}`).toBeLessThanOrEqual(2);
  expect(geometry.gap, "subject id sits against the first count").toBeGreaterThanOrEqual(24);
  await expect(page.getByTestId("run-button")).toHaveText("Run 2 searches");

  // Both rows reach the wire in ONE request (R3, one kind), and each job carries ITS OWN subject's
  // resolved atlas path — `sub-101`'s DK40 file, not `sub-ernie`'s repeated.
  const groups = collectGroups();
  await pressRun();
  await expect.poll(() => groups.bodies.length, { timeout: 15_000 }).toBe(1);
  groups.stop();
  const group = groups.bodies[0] as {
    kind: string;
    subject_ids: string[];
    subject_configs: { subject_id: string; config: { subject_id: string; roi: { atlas_path: string[] } } }[];
  };
  expect(group.kind).toBe("flex");
  expect(group.subject_ids).toEqual(["ernie", "101"]);
  expect(group.subject_configs.map((e) => e.config.subject_id)).toEqual(["ernie", "101"]);
  expect(group.subject_configs.map((e) => e.config.roi.atlas_path[0])).toEqual([
    "/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/lh.DK40.annot",
    "/mnt/example/derivatives/SimNIBS/sub-101/m2m_101/segmentation/lh.DK40.annot",
  ]);

  await second.locator('td[data-cell="actions"]').getByRole("button", { name: /^Remove job/ }).click();
  await expect(optRows(page)).toHaveCount(1);
});

test("the flex variants are DERIVED from the focality mode, not chosen as methods", async () => {
  // Coordinator, 2026-09-06: the Method column offers two methods, and `flex_adaptive` /
  // `flex_pareto` are what a flex search BECOMES when its thresholds are derived or swept. The
  // kind is read off the editor's own focality options (`jobKindFor`), exactly as in 2.5.0.
  const row = optRows(page).first();
  await expect(row.locator('td[data-cell="method"]').getByRole("combobox")).toHaveText("Flex");
  await expect(row).toHaveAttribute("data-kind", "flex");
  await expect(row.locator('td[data-cell="goal"]').getByRole("combobox")).toHaveText("mean");

  // Goal `focality` in the row, then the mode in the editor.
  await setOptCell(page, row, "goal", "focality");
  const dialog = await openOptEditor(page, row);
  await field("Threshold mode", dialog).getByRole("radio", { name: "Adaptive (single run)", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "flex_adaptive");
  // Line 2 states the variant, so the kind is readable without opening the editor.
  await expect(optRowDetail(row)).toHaveText("goal focality (adaptive) · 2 pairs · 1 mA · ratio 1:1");

  const groups = collectGroups();
  await expect(page.getByTestId("plan-stat-jobs").locator(".plan-stat-value")).toHaveText("1", { timeout: 15_000 });
  await pressRun();
  await expect.poll(() => groups.bodies.length, { timeout: 15_000 }).toBe(1);
  groups.stop();
  expect((groups.bodies[0] as { kind: string }).kind).toBe("flex_adaptive");

  const again = await openOptEditor(page, row);
  await field("Threshold mode", again).getByRole("radio", { name: "Pareto sweep", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "flex_pareto");
  await expect(optRowDetail(row)).toHaveText(/^goal focality \(Pareto\) · /);

  await setOptCell(page, row, "goal", "mean");
  await expect(row).toHaveAttribute("data-kind", "flex");
});

test("Ex: the Leadfield cell lists what a subject has, and names the refusal when it has none", async () => {
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  await setOptCell(page, row, "method", "Ex");

  // The cell states the fact — a 2 GB matrix, from tests/fixtures/leadfields.json — and offers the
  // net that has none as a refusal rather than an option that silently fails.
  const cell = row.locator('td[data-cell="net"]').getByRole("combobox");
  await cell.click();
  await expect(page.getByRole("option", { name: /^GSN-HydroCel-185 · 2\.0 GB$/ })).toBeVisible();
  await expect(page.getByRole("option", { name: "EGI_template — no leadfield" })).toBeDisabled();
  await page.getByRole("option", { name: /^GSN-HydroCel-185 · 2\.0 GB$/ }).click();
  await expect(row).toHaveAttribute("data-net", "GSN-HydroCel-185");

  // …and the subject picker refuses a subject that has no leadfield at all, by name (J3): the
  // fixture gives `101` an entry with `exists: false` and MNI152 none.
  await row.locator('td[data-cell="subject"]').getByRole("combobox").click();
  const picker = page.getByRole("dialog");
  await expect(picker.getByRole("option", { name: "101" })).toContainText("no leadfield — create one first");
  await expect(picker.getByRole("option", { name: "101" })).toBeDisabled();
  await picker.getByRole("button", { name: "Done", exact: true }).click();

  // Two uncombined saved ROIs are two runs — 2.5.0's own expansion, kept.
  const dialog = await openOptEditor(page, row);
  await expect(dialog.getByRole("radio", { name: "Saved", exact: true })).toBeChecked();
  await pickSavedTarget(dialog, "Thalamus_target");
  await pickSavedTarget(dialog, "L_Insula_target");
  await fillExBuckets(dialog);
  // The cost is stated beside the buckets that change it — the same function line 2 reads.
  await expect(dialog.getByTestId("optimizer-cost-ex")).toHaveText("4 electrodes · 7 splits · 7 combinations");
  await closeOptEditor(page);
  await expect(optRowSummary(row)).toHaveText("Thalamus_target + L_Insula_target");
  await expect(optRowDetail(row)).toHaveText("4 electrodes (TI) · 2 mA · 7 splits · 7 combinations");

  await expect(page.getByTestId("plan-cell-ernie-ex")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("run-button")).toHaveText("Run 2 searches");

  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await pressRun();
  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    subject_configs: { subject_id: string; config: { roi_name: string; leadfield_hdf: string; electrodes: Record<string, unknown> } }[];
  };
  expect(body.kind).toBe("ex");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.subject_configs).toHaveLength(2);
  expect(body.subject_configs.map((e) => e.config.roi_name)).toEqual(["Thalamus_target", "L_Insula_target"]);
  expect(body.subject_configs[0]!.config.leadfield_hdf).toBe(
    "/mnt/example/derivatives/SimNIBS/sub-ernie/leadfields/GSN-HydroCel-185/leadfield.hdf5",
  );
  expect(body.subject_configs[0]!.config.electrodes).toEqual({ _type: "BucketElectrodes", e1_plus: ["E1"], e1_minus: ["E2"], e2_plus: ["E3"], e2_minus: ["E4"] });
});

test("mEx is Ex with eight electrodes: the count decides the kind", async () => {
  // Coordinator, 2026-09-06: `mex` is what an exhaustive search BECOMES when it is given four
  // pairs instead of two — the same inference the Simulator makes from a montage's pairs. There is
  // no "mEx" method to pick.
  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-method", "ex");
  await expect(row).toHaveAttribute("data-kind", "ex");
  // Ex/mEx rank every montage by the ROI field: the Goal cell says so rather than holding a dead
  // control (and there is no goal on the wire to disagree with).
  await expect(row.locator('td[data-cell="goal"]')).toHaveText("—");

  let dialog = await openOptEditor(page, row);
  await field("Electrodes", dialog).getByRole("radio", { name: "8 electrodes (mTI)", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "mex");
  await expect(optRowDetail(row)).toHaveText(/^8 electrodes \(mTI\) · 2 mA · /);

  dialog = await openOptEditor(page, row);
  // The mTI run path has no combined mode, so the control does not exist rather than existing dead.
  await expect(dialog.getByLabel("Combine selected ROIs into one target")).toHaveCount(0);
  for (const bucket of ["E1+", "E1-", "E2+", "E2-", "E3+", "E3-", "E4+", "E4-"]) {
    await expect(field(bucket, dialog)).toBeVisible();
  }
  await expect(dialog.getByTestId("optimizer-cost-mex")).toHaveText(/0 electrodes · 4 pairs · 0 combinations/);
  await expect(dialog.locator(".form-section-title", { hasText: "Carriers" })).toBeVisible();
  await closeOptEditor(page);

  // An incomplete row is shown and is not planned; the disabled sentence names WHICH job (§4.7
  // rule 3), which a page-level form could never do.
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /Job 1: Fill in all eight electrode buckets\./);

  // Back to four electrodes, and the row is an `ex` search again — with the buckets it already had.
  dialog = await openOptEditor(page, row);
  await field("Electrodes", dialog).getByRole("radio", { name: "4 electrodes (TI)", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "ex");
});

test("the row editor's header carries the run name, and Current is one line", async () => {
  // Coordinator, 2026-09-06, on two screenshots of the Ex editor: the run name is one short string
  // naming the whole run, so it belongs on the header line beside the subject rather than as the
  // first row of a body that is otherwise all search parameters; and `Total current · Step ·
  // Channel limit` are three numbers about one thing, so they are one line.
  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-kind", "ex");
  const dialog = await openOptEditor(page, row);

  // The header: the subject and the run-name input on ONE line, under the title, and the body has
  // no Run name field left.
  const meta = dialog.locator(".optimizer-dialog-meta");
  const subject = meta.locator(".optimizer-dialog-subject");
  const runName = meta.getByRole("textbox");
  await expect(subject).toHaveText("ernie");
  await expect(runName).toHaveAttribute("placeholder", "auto (timestamp)");
  await expect(dialog.getByTestId("opt-row-editor").locator(".field", { hasText: "Run name" })).toHaveCount(0);
  const subjectBox = (await subject.boundingBox())!;
  const runBox = (await runName.boundingBox())!;
  const titleBox = (await dialog.locator(".dialog-title").boundingBox())!;
  // Same line as the subject, to its right; below the title.
  expect(Math.abs(runBox.y + runBox.height / 2 - (subjectBox.y + subjectBox.height / 2))).toBeLessThan(6);
  expect(runBox.x).toBeGreaterThan(subjectBox.x + subjectBox.width);
  expect(runBox.y).toBeGreaterThan(titleBox.y + titleBox.height - 4);
  // …and clear of the dialog's own close button.
  const closeBox = (await dialog.getByRole("button", { name: "Close dialog" }).boundingBox())!;
  expect(runBox.x + runBox.width).toBeLessThanOrEqual(closeBox.x);
  // It is the row's run name, and it reaches the config.
  await runName.fill("header-run");
  await closeOptEditor(page);
  await expect(dialog).toHaveCount(0);

  // CURRENT: three fields, one line, content-sized inputs.
  const again = await openOptEditor(page, row);
  const current = again.locator(".optimizer-current-row");
  const boxes = await current.locator(".field").evaluateAll((els) => els.map((el) => el.getBoundingClientRect()).map((r) => ({ x: r.x, y: r.y, w: r.width })));
  expect(boxes).toHaveLength(3);
  console.log(`OJ-CURRENT ${JSON.stringify(boxes)}`);
  // One line: every field shares the first one's top, and each starts right of the last.
  for (const b of boxes) expect(Math.abs(b.y - boxes[0]!.y), "Current is one line").toBeLessThan(4);
  expect(boxes[1]!.x).toBeGreaterThan(boxes[0]!.x);
  expect(boxes[2]!.x).toBeGreaterThan(boxes[1]!.x);
  // Content-sized controls, not one filling half the dialog — and wide enough to PRINT their
  // value: an 88px wrapper that also squeezed the inner input left 37px for the number, which
  // rendered 0.2 as "0" and 1.6 as "1".
  const inputs = await current.locator(".number-input").evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().width)));
  console.log(`OJ-CURRENT-INPUTS ${JSON.stringify(inputs)}`);
  for (const w of inputs) expect(w, "a current control is content-sized").toBeLessThanOrEqual(120);
  await expect(current.getByRole("spinbutton").nth(1)).toHaveValue("0.2");
  await expect(current.getByRole("spinbutton").nth(2)).toHaveValue("1.6");
  await closeOptEditor(page);
});

test("a mixed table submits one group per kind, and says so", async () => {
  // `POST /api/jobs/groups` takes ONE kind (`tit/jobs/plans.py::GROUP_KINDS`), so a table holding a
  // Flex row and an Ex row cannot be one request. The page does not pretend otherwise: two groups,
  // named in the toast.
  const exRow = optRows(page).first();
  await expect(exRow).toHaveAttribute("data-method", "ex");

  const flexRow = await addOptRow(page);
  await setOptSubject(page, flexRow, "ernie");
  await setOptCell(page, flexRow, "method", "Flex");
  const dialog = await openOptEditor(page, flexRow);
  await pickCorticalTarget(dialog);
  await closeOptEditor(page);

  await expect(page.getByTestId("plan-stat-jobs").locator(".plan-stat-value")).toHaveText("3", { timeout: 15_000 });
  // The plan grid's columns are the three families, counted per subject (`cellDetail="counts"`).
  await expect(page.getByTestId("plan-grid").locator("thead th")).toContainText(["Flex", "Ex", "mEx"]);
  await expect(page.getByTestId("plan-cell-ernie-ex")).toContainText("2");
  await expect(page.getByTestId("plan-cell-ernie-flex")).toBeVisible();

  const groups = collectGroups();
  await pressRun();
  await expect.poll(() => groups.bodies.length, { timeout: 15_000 }).toBe(2);
  groups.stop();
  expect(groups.bodies.map((b) => b.kind).sort()).toEqual(["ex", "flex"]);
  expect((groups.bodies.find((b) => b.kind === "ex") as { subject_configs: unknown[] }).subject_configs).toHaveLength(2);
  expect((groups.bodies.find((b) => b.kind === "flex") as { subject_configs: unknown[] }).subject_configs).toHaveLength(1);

  // §4.7 rule 7: the table survives the run — the rows are what the user built.
  await expect(optRows(page)).toHaveCount(2);
});

test("hits its acceptance numbers at both sizes, in both themes (DESIGN.md §12.3)", async () => {
  test.setTimeout(240_000);
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  const dialog = await openOptEditor(page, row);
  await pickCorticalTarget(dialog);
  await closeOptEditor(page);

  const rows: PageMetrics[] = [];
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    for (const theme of ["light", "dark"] as const) {
      rows.push(
        await captureScreen(page, {
          runId: RUN_ID,
          pageId: "optimizer",
          theme,
          width: size.width,
          height: size.height,
          waitFor: async () => {
            await expect(page.getByTestId("plan-grid")).toBeVisible();
          },
        }),
      );
    }
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  const work = await deadSpaceRatio(page, '[data-testid="page-work"]');
  const right = await deadSpaceRatio(page, '[data-testid="page-right-pane"]');
  console.log("optimizer metrics:", JSON.stringify(rows, null, 1));
  console.log(`optimizer pane dead space @1280: work=${work.ratio.toFixed(4)} right=${right.ratio.toFixed(4)}`);

  for (const metrics of rows) {
    // DESIGN.md §12.3 asks for <= 0.22 here, which no form-shaped run page in this build reaches
    // with this instrument (see the note this budget replaced). A jobs table is *sparser* than the
    // form it replaced — a page that is one table plus a plan is mostly the table's own gutters —
    // so the budget is this page's measured value plus headroom, reported rather than papered over.
    expect(metrics.deadSpaceRatio, `${metrics.theme} @${metrics.width}`).toBeLessThanOrEqual(0.9);
    expect(metrics.pageHeaderHeight).toBe(0);
    expect(metrics.panes.nav).toBe(metrics.width >= 1440 ? 216 : 56);
    // DESIGN.md §2.1: the run panel is `clamp(320px, 45vw, calc(100% - 566px))`.
    expect(metrics.panes.right).toBe(metrics.width >= 1440 ? 610 : 576);
    expect(metrics.panes.work).toBeGreaterThanOrEqual(560);
  }

  // Every Tier-1 control the page has is the jobs table, and all of it is on the first screen.
  const first = await firstScreenControls(page);
  console.log("optimizer first screen:", JSON.stringify(first));
  expect(first.total, "the page declares Tier-1 controls").toBeGreaterThan(0);
  expect(first.hidden, "Tier-1 below the fold").toEqual([]);
});

test("the leadfield strip states the fact and estimates THIS net, with no 'required' chip", async () => {
  // Maintainer, 2026-09-06, on a screenshot of the strip: *"Remove that required icon. Just say
  // that the leadfield is not there... for the time prediction, make sure we have a rough estimate
  // based on the number of electrodes in the net."* So: one plain sentence, and a duration read
  // from `PlanCost.eta_minutes` for the SELECTED net (one FEM solve per electrode, on this
  // machine) instead of the "≈40 min" that used to be typed into the label.
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  await setOptCell(page, row, "method", "Ex");
  const dialog = await openOptEditor(page, row);
  const strip = dialog.getByTestId("leadfield-strip");

  // `EGI_template` is the net ernie has no leadfield for (tests/fixtures/leadfields.json).
  await strip.getByRole("combobox", { name: "EEG net" }).click();
  await page.getByRole("option", { name: "EGI_template", exact: true }).click();

  await expect(strip).toContainText("No leadfield for this net yet.");
  await expect(strip.getByText("required")).toHaveCount(0);

  const generate = strip.getByRole("button", { name: /^Generate/ });
  await expect(generate).toHaveAttribute("data-eta-minutes", /\d/);
  // 256 electrodes on the mock's emulated machine: over an hour, not the old flat 40 minutes.
  const minutes = Number(await generate.getAttribute("data-eta-minutes"));
  expect(minutes).toBeGreaterThan(60);
  await expect(generate).toHaveText(/^Generate \(≈ 1 h/);
  await expect(generate).toHaveAttribute("title", /on this machine/);

  await closeOptEditor(page);
});

/**
 * Evidence for a reviewer, not an assertion: the table, and one row editor per family. Written to
 * `tests/e2e/artifacts/` like the other lanes' jobs-table shots.
 */
test("artifacts: the jobs table and its two row editors", async () => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await clearOptRows(page);

  const flexRow = await addOptRow(page);
  await setOptSubject(page, flexRow, "ernie");
  let dialog = await openOptEditor(page, flexRow);
  await pickCorticalTarget(dialog);
  await dialog.screenshot({ path: "tests/e2e/artifacts/optimizer-row-flex.png" });
  await closeOptEditor(page);

  const exRow = await addOptRow(page);
  await setOptSubject(page, exRow, "ernie");
  await setOptCell(page, exRow, "method", "Ex");
  await setOptCell(page, exRow, "net", "GSN-HydroCel-185 · 2.0 GB");
  dialog = await openOptEditor(page, exRow);
  await pickSavedTarget(dialog, "Thalamus_target");
  await fillExBuckets(dialog);
  await dialog.screenshot({ path: "tests/e2e/artifacts/optimizer-row-ex.png" });
  await closeOptEditor(page);

  await expect(page.getByTestId("plan-grid")).toBeVisible();
  await page.locator('[data-page-active="true"]').getByTestId("page-work").screenshot({ path: "tests/e2e/artifacts/optimizer-jobs.png" });
});
