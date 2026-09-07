import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import { answerExistingOutputs, expectPage, gotoPage, launchElectronApp, openPalette, setSectionOpen } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { captureScreen, type PageMetrics } from "./_metrics";
import { addJobRow, clearJobRows, configureMontageJob, jobBlank, jobCurrents, jobDetail, jobPairs, jobRows, setJobMappedNet, setJobMontage, setJobNet, setJobPlacement, setJobSource, setJobSubject } from "./_jobs";

/**
 * Simulator (DESIGN.md v3 §2 shape A, wireframes §3), against the mock server. DOM state and
 * measured geometry only — the screenshots are evidence, not the assertion (§8.1).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "simulator";

let app: ElectronApplication;
let page: Page;

/** The Jobs table's rows — one row is one job (2026-09-06 rework). */
function montageRows() {
  return jobRows(page);
}

/** Empties the table, then leaves one blank row for the test to fill in. */
async function clearMontageRows() {
  await clearJobRows(page);
  await addJobRow(page);
}

test.describe.configure({ mode: "serial" });

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

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });

  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await app?.close();
});

test("shape A, no page header, and one Jobs table instead of a global subject set", async () => {
  await expect(page.locator(".page-header")).toHaveCount(0);
  /*
   * 2026-09-06 rework (maintainer): the page-level Subjects table and the Montage / Flex / Free-hand
   * source tabs are gone. A ROW is a job and owns its subject, its source, its montage and its
   * currents — 2.5.0's job cards — so there is nothing left for a page-wide subject set to decide.
   */
  await expect(page.getByTestId("subjects-field")).toHaveCount(0);
  await expect(page.getByRole("radiogroup", { name: "Montage source" })).toHaveCount(0);
  await expect(page.getByTestId("sim-jobs-table")).toBeVisible();
  await expect(page.locator("table.sim-jobs-table thead th")).toHaveText([
    "Subject",
    "Source",
    "EEG net",
    "Montage",
    "",
  ]);
  // Seeded with one blank row on the context bar's primary subject ("ernie", from beforeAll), so
  // the page's first act is picking a montage rather than discovering an "Add job" button.
  await expect(montageRows()).toHaveCount(1);
  await expect(montageRows().first()).toHaveAttribute("data-subject", "ernie");
  await expect(page.getByRole("heading", { name: /^Selected jobs/ })).toHaveCount(0);

  const pane = page.getByTestId("page-right-pane");
  await expect(pane.getByTestId("run-panel")).toBeVisible();
  await expect(pane.getByTestId("plan-grid")).toBeVisible();
  // S7: the pane's lower half is the Terminal · Scene tab host, and Scene is what a page shows
  // while nothing of its kind is running. The terminal is still there — one click away.
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(pane.getByTestId("job-terminal")).toBeVisible();
  await expect(page.getByTestId("page-work").locator(".action-bar")).toBeVisible();
});

test("with no complete row the primary is disabled, with the reason as its tooltip and no banner", async () => {
  // The disabled button is the ONLY signal: no digest line, no banner (maintainer call). The
  // reason names what is actually empty — the table — rather than the subject set the page no
  // longer has.
  await expect(page.locator(".action-bar-digest")).toHaveCount(0);
  await expect(page.getByTestId("run-receipt")).toHaveCount(0);
  const run = page.getByTestId("run-button");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", "Add a job with a subject and a montage.");
});

test("a row that names a subject and a montage becomes exactly one planned job", async () => {
  // The row's first column is its subject, the second its source, the third the net and the
  // fourth that net's montages — uni-polar and multi-polar in one list, the polarity read off the
  // montage itself and shown as a chip. There are no standalone selectors above the table.
  await expect(page.locator(".field", { hasText: "Polarity" })).toHaveCount(0);
  const row = montageRows().first();
  await configureMontageJob(page, row, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  await expect(row).toHaveAttribute("data-polarity", "uni_polar");
  // The polarity is a quiet label at the start of line 2; the colours there belong to the channels.
  await expect(jobDetail(row).locator(".job-polarity")).toHaveText("TI");

  /*
   * §4.5, as the maintainer redrew it on 2026-09-06: for `kind="sim"` the columns are the three
   * *sources* — Montage · Flex · Free-hand — and a cell is a count with its state breakdown.
   */
  const cell = page.getByTestId("plan-cell-ernie-montage");
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^1 (new|skip|overwrite|blocked|wait)$/);
  await expect(page.locator(".plan-matrix thead th")).toHaveText(["Subject", "Montage", "Flex", "Free-hand"]);
  // No job of the other two kinds, so those cells are em dashes rather than empty.
  await expect(page.getByTestId("plan-cell-ernie-flex")).toHaveText("—");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run simulation");
  // The currents editor lives in the row itself, and the number of fields follows the polarity: a
  // uni-polar (TI) montage takes exactly 2.
  await expect(jobCurrents(row)).toHaveCount(2);
});

test("a multi-polar montage row takes one current per pair", async () => {
  await clearMontageRows();
  const row = montageRows().first();
  await configureMontageJob(page, row, { subject: "ernie", net: "GSN-HydroCel-185", montage: "mTI_F3F4_P3P4 · mTI" });
  await expect(row).toHaveAttribute("data-polarity", "multi_polar");
  await expect(jobDetail(row).locator(".job-polarity")).toHaveText("mTI");
  // 4 pairs -> 4 currents, derived from the montage, not from a control the user has to set.
  await expect(jobCurrents(row)).toHaveCount(4);
  await expect(jobPairs(row)).toHaveText(["E24–E124", "E67–E77", "E36–E104", "E12–E62"]);

  // One uni-polar and one multi-polar row side by side.
  await configureMontageJob(page, await addJobRow(page), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "F3_F4 · TI",
  });
  await expect(montageRows()).toHaveCount(2);
});

/**
 * The defect the rework closes, in the maintainer's words: *"it's hard to separate users, montages,
 * modes in different jobs."* Two rows, two subjects, and the SAME montage — reached by duplicating
 * one row and re-pointing its subject, which is the gesture 2.5.0's job cards had.
 */
test("two rows can name two different subjects, and the plan grows a row for each", async () => {
  await clearMontageRows();
  await expect(page.getByTestId("run-button")).toBeDisabled();

  const first = montageRows().first();
  await configureMontageJob(page, first, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  // Duplicate, then point the copy at 101 — one click each, no page-level subject set involved.
  await first.getByRole("button", { name: "Duplicate job 1" }).click();
  await expect(montageRows()).toHaveCount(2);
  const second = montageRows().nth(1);
  await setJobSubject(page, second, "101");
  await expect(second).toHaveAttribute("data-runnable", "true");

  const ernieCell = page.getByTestId("plan-cell-ernie-montage");
  const cell101 = page.getByTestId("plan-cell-101-montage");
  await expect(ernieCell).toBeVisible({ timeout: 15_000 });
  await expect(cell101).toBeVisible({ timeout: 15_000 });

  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);
  await expect(page.locator('[data-testid="plan-stat-jobs"]')).toContainText("2");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^2 jobs · \d+ CPU · \d+ GB/);
  await expect(page.getByTestId("run-button")).toHaveText("Run 2 simulations");
});

/**
 * The plan grid is a per-subject summary (maintainer, 2026-09-06): three fixed source columns, a
 * cell that counts its jobs and breaks them down by state, and — because a cell now stands for
 * several jobs — a list behind the cell from which one job can be pinned.
 */
test("a cell counts its subject's jobs per source, and lists them for pinning", async () => {
  // Two subjects are still in the table from the test above; add a second montage row for ernie,
  // so ernie's Montage cell holds two jobs rather than one.
  await configureMontageJob(page, await addJobRow(page), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "Thalamus_target · TI",
  });

  // And a flex source, so the plan is genuinely mixed: 2 montage jobs for ernie + 1 flex job.
  const flexRow = await addJobRow(page);
  await setJobSubject(page, flexRow, "ernie");
  await setJobSource(page, flexRow, "Flex result");
  await setJobMontage(page, flexRow, "flex_Thalamus_20260810_101500");
  await expect(flexRow).toHaveAttribute("data-runnable", "true");

  const montageCell = page.getByTestId("plan-cell-ernie-montage");
  await expect(montageCell).toHaveText("2 new", { timeout: 15_000 });
  await expect(page.getByTestId("plan-cell-ernie-flex")).toHaveText("1 new");
  await expect(page.getByTestId("plan-cell-ernie-freehand")).toHaveText("—");
  // Still three columns and one row per subject, however many jobs are in the table.
  await expect(page.locator(".plan-matrix thead th")).toHaveText(["Subject", "Montage", "Flex", "Free-hand"]);
  await expect(page.locator(".plan-matrix tbody tr")).toHaveCount(2);
  // The footer keeps counting jobs, and it counts the folded ones.
  await expect(page.getByTestId("plan-legend")).toContainText("new — 4 jobs in this plan");
  await expect(page.locator('[data-testid="plan-stat-jobs"]')).toContainText("4");

  // The three count columns are evenly spaced, and the first does not hug the subject id
  // (maintainer, 2026-09-06). Measured, not asserted from the CSS: `table-layout: fixed` with only
  // the subject column sized is what divides the rest equally, and this is the proof.
  const geometry = await page.locator('[data-testid="plan-grid"] .plan-matrix').evaluate((table) => {
    const head = [...table.querySelectorAll("thead th")];
    const xs = head.slice(1).map((th) => th.getBoundingClientRect().x);
    const subjectText = table.querySelector("tbody th .mono")?.getBoundingClientRect();
    const firstCount = head[1]?.getBoundingClientRect();
    const pad = head[1] ? parseFloat(getComputedStyle(head[1]).paddingLeft) : 0;
    return { xs, gap: (firstCount?.x ?? 0) + pad - (subjectText?.right ?? 0) };
  });
  expect(geometry.xs).toHaveLength(3);
  // Equidistant to within 2px: the two steps between the three columns are the same.
  const [a, b, c] = geometry.xs as [number, number, number];
  expect(Math.abs(b - a - (c - b)), `column steps ${b - a} vs ${c - b}`).toBeLessThanOrEqual(2);
  expect(geometry.gap, "subject id sits against the first count").toBeGreaterThanOrEqual(24);

  // Evidence (§8.1): two subjects, mixed sources.
  await page.locator('[data-testid="plan-grid"]').screenshot({ path: "tests/e2e/artifacts/sim-plan-summary.png" });

  // A cell of several jobs opens the list; picking one pins the terminal to that subject.
  await montageCell.getByRole("button").click();
  const jobs = page.getByTestId("plan-cell-jobs-ernie-montage");
  await expect(jobs.locator("li")).toHaveCount(2);
  await jobs.locator("li button").first().click();
  await expect(jobs).toHaveCount(0);
});

test("nothing moves while a row is edited — including a change of SOURCE", async () => {
  await clearMontageRows();
  const first = montageRows().first();
  await configureMontageJob(page, first, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  const second = await addJobRow(page);
  await configureMontageJob(page, second, { subject: "ernie", net: "GSN-HydroCel-185", montage: "Thalamus_target · TI" });
  await expect(montageRows()).toHaveCount(2);

  /*
   * Every cell of the table, by COLUMN — x and width, plus the y of the first row, which is what
   * the rule is about: a row's own cells may get taller (an mTI job lists four channels on line 2
   * where a TI job lists two, and four channel groups do not fit on one line at 1280), but no
   * column may move and no row above the edited one may shift.
   */
  const boxes = async () =>
    page.locator("tr[data-job-row]:first-of-type td, tr[data-job-row] td").evaluateAll((cells) =>
      cells.map((cell) => {
        const r = cell.getBoundingClientRect();
        return { x: Math.round(r.x), w: Math.round(r.width) };
      }),
    );

  /** The first row's own geometry, which nothing done to the SECOND row may change. */
  const firstRowBox = async () =>
    page.locator("tr[data-job-row]").first().evaluate((tr) => {
      const r = tr.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    });

  const before = await boxes();
  const firstBefore = await firstRowBox();
  // 1. Change the SECOND row's montage, and with it its polarity (TI -> mTI, 2 -> 4 currents).
  await setJobMontage(page, second, "mTI_F3F4_P3P4 · mTI");
  await expect(second).toHaveAttribute("data-polarity", "multi_polar");
  await expect(jobCurrents(second)).toHaveCount(4);
  expect(await boxes(), "polarity switch moved a cell").toEqual(before);
  expect(await firstRowBox(), "polarity switch moved the row above it").toEqual(firstBefore);

  // 2. Change the second row's NET (which empties its montage back to "choose one").
  await setJobNet(page, second, "EGI_template");
  expect(await boxes(), "net change moved a cell").toEqual(before);
  expect(await firstRowBox(), "net change moved the row above it").toEqual(firstBefore);

  // 3. And back to a montage on the new net.
  await setJobMontage(page, second, "mTI_Cz_Oz_F3_F4 · mTI");
  // Wait for the row to finish becoming multi-polar before measuring, exactly as step 1 does:
  // without it the cells are read mid-render and come back as 0x0 rects, which is a race in the
  // test, not movement in the table.
  await expect(second).toHaveAttribute("data-polarity", "multi_polar");
  await expect(jobCurrents(second)).toHaveCount(4);
  expect(await boxes(), "montage change moved a cell").toEqual(before);
  expect(await firstRowBox(), "montage change moved the row above it").toEqual(firstBefore);

  // 4. And the case the rework adds: the row's SOURCE. Its EEG-net cell becomes a placement
  //    picker and its Montage cell a flex-run picker, inside the columns they already had.
  await setJobSource(page, second, "Flex result");
  await expect(second).toHaveAttribute("data-source", "flex");
  expect(await boxes(), "source switch moved a cell").toEqual(before);
  expect(await firstRowBox(), "source switch moved the row above it").toEqual(firstBefore);
  await setJobSource(page, second, "Free-hand");
  await expect(second).toHaveAttribute("data-source", "freehand");
  expect(await boxes(), "free-hand switch moved a cell").toEqual(before);
});

test("the jobs table never scrolls sideways in the work column", async () => {
  // The columns always sum to the container by construction — this asserts that construction
  // rather than a set of pixel widths that happen to add up.
  for (const width of [1280, 1024]) {
    await page.setViewportSize({ width, height: 800 });
    await expect(page.locator("table.sim-jobs-table")).toBeVisible();
    const box = await page.getByTestId("sim-jobs-table-container").evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(box.clientWidth, `table container collapsed at ${width}`).toBeGreaterThan(300);
    expect(box.scrollWidth, `jobs table scrolls sideways at ${width}`).toBeLessThanOrEqual(box.clientWidth);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
});

test("clicking a row makes it the one the 3-D pane draws, and up/down moves it", async () => {
  // The previous test left row 2 on the Free-hand source; put it back on a montage so both rows
  // are drawable.
  const rows = montageRows();
  await setJobSource(page, rows.nth(1), "Montage");
  await configureMontageJob(page, rows.nth(1), { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });

  await jobBlank(rows.nth(1)).click();
  await expect(rows.nth(1)).toHaveAttribute("data-active", "true");
  await expect(rows.first()).not.toHaveAttribute("data-active", "true");

  await rows.nth(1).press("ArrowUp");
  await expect(rows.first()).toHaveAttribute("data-active", "true");
  await expect(rows.nth(1)).not.toHaveAttribute("data-active", "true");
  await rows.first().press("ArrowDown");
  await expect(rows.nth(1)).toHaveAttribute("data-active", "true");
});

/**
 * The reported defect the flex source once had: every row's checkbox was disabled because the tab
 * looked for the electrodes in `flex_meta.json`, which never records any. Since the jobs rework
 * there is no checkbox at all — a row picks `Flex result` in its own Source cell — so this walks
 * that path instead, all the way to a planned job.
 */
test("a row on the Flex result source becomes a planned job, in either placement", async () => {
  await clearMontageRows();
  const row = montageRows().first();
  await setJobSubject(page, row, "ernie");
  await setJobSource(page, row, "Flex result");
  await setJobMontage(page, row, "flex_Thalamus_20260810_101500");
  await expect(row).toHaveAttribute("data-runnable", "true");
  await expect(jobPairs(row)).toHaveText(["E020–E074", "E101–E133"]);

  // A flex source lands in the Flex column, and the montage column empties — which is the whole
  // point of summarising by source rather than by simulation name.
  const cell = page.getByTestId("plan-cell-ernie-flex");
  await expect(cell).toHaveText("1 new", { timeout: 15_000 });
  await expect(page.getByTestId("plan-cell-ernie-montage")).toHaveText("—");
  // One job, not two: the plan is built from the resolved config alone. Sending `montage_sources`
  // alongside it made the server resolve the same run a second time.
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · /, { timeout: 15_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The optimiser's own coordinates are the other placement a run can be simulated in — and the
  // only one a run that was never mapped onto a net has. It is the row's EEG-net cell, stated as a
  // choice rather than as a truncated option label.
  await setJobPlacement(page, row, "Optimised (XYZ)");
  await expect(jobPairs(row)).toHaveText(["XYZ (2 pts)", "XYZ (2 pts)"]);
  await expect(row).toHaveAttribute("data-runnable", "true");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · /, { timeout: 15_000 });

  // Back to a net — and not only the net the run happens to carry a mapping file for: every net
  // the subject has is offered, and the server maps the optimised positions onto it on demand.
  await setJobMappedNet(page, row, "EGI_template");
  await expect(jobPairs(row).first()).toHaveText(/–/, { timeout: 15_000 });
  await expect(row).toHaveAttribute("data-runnable", "true");
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · /, { timeout: 15_000 });
});

/**
 * Per-job settings (maintainer, 2026-09-06): *"the three sections should be the **default** of the
 * simulator; however each job should have its own settings configuration."* The claim is about the
 * configs that reach the server — one customised job differs from its neighbour, and a changed
 * default reaches only the job that never disagreed with it.
 */
test("a job's own electrodes reach its config, and a changed default reaches only the other job", async () => {
  await clearMontageRows();
  const first = montageRows().first();
  await configureMontageJob(page, first, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  const second = await addJobRow(page);
  await configureMontageJob(page, second, { subject: "ernie", net: "GSN-HydroCel-185", montage: "Thalamus_target · TI" });

  // Customise the FIRST job: rectangle, 10x10, and TI_avg instead of TI_max.
  await first.locator('td[data-cell="actions"]').getByRole("button", { name: /^Job settings/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("job-settings-form")).toBeVisible();
  await expect(dialog).toContainText("ernie");
  await dialog.getByRole("radio", { name: "Rectangle", exact: true }).click();
  await dialog.getByRole("spinbutton", { name: "Electrode width" }).fill("10");
  await dialog.getByRole("spinbutton", { name: "Electrode height" }).fill("10");
  await dialog.getByRole("checkbox", { name: "TI_avg" }).click();
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(dialog).toHaveCount(0);

  // Line 2 says so, on that row only.
  await expect(jobDetail(first).locator('[data-cell="custom"]')).toHaveText(/^custom: rect 10×10/);
  await expect(jobDetail(second).locator('[data-cell="custom"]')).toHaveCount(0);

  // Change a DEFAULT: gel thickness 4 -> 6. The customised row keeps its own 4.
  const electrodes = await setSectionOpen(page, "Electrodes", true);
  await electrodes.getByRole("spinbutton").last().fill("6");
  await electrodes.getByRole("spinbutton").last().blur();

  const bodies: Record<string, unknown>[] = [];
  const collect = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) bodies.push(r.postDataJSON() as Record<string, unknown>);
  };
  page.on("request", collect);
  await page.getByTestId("run-button").click();
  await answerExistingOutputs(page);
  await expect.poll(() => bodies.length, { timeout: 20_000 }).toBeGreaterThan(0);
  page.off("request", collect);

  const group = bodies[0] as { subject_configs?: { config: Record<string, unknown> }[]; config?: Record<string, unknown> };
  const configs = (group.subject_configs ?? []).map((e) => e.config);
  const byMontage = (name: string) =>
    configs.find((c) => ((c.montages as { name: string }[]) ?? []).some((m) => m.name === name))!;
  const custom = byMontage("F3_F4");
  const plain = byMontage("Thalamus_target");

  // The customised job carries its own electrodes and fields...
  expect(custom.electrode_shape).toBe("rect");
  expect(custom.electrode_dimensions).toEqual([10, 10]);
  expect(custom.output_fields).toEqual(["TI_max", "TI_avg"]);
  expect(custom.gel_thickness).toBe(4);
  // ...and the untouched job followed the default that changed after it was created.
  expect(plain.electrode_shape).toBe("ellipse");
  expect(plain.gel_thickness).toBe(6);
  expect(plain.output_fields).toEqual(["TI_max"]);

  // Reset puts the row back on the defaults — including the one that changed meanwhile.
  await first.locator('td[data-cell="actions"]').getByRole("button", { name: /^Job settings/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset to defaults", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  await expect(jobDetail(first).locator('[data-cell="custom"]')).toHaveCount(0);

  // Put the default back: this file is serial, and the next test reads the section's summary.
  const gel = (await setSectionOpen(page, "Electrodes", true)).getByRole("spinbutton").last();
  await gel.fill("4");
  await gel.blur();
});

test("collapsed sections state their own values (§4.2 rule 5)", async () => {
  // FXU1: sections auto-expand to fill the pane, so the summary is asserted on a section the user
  // has collapsed by hand — which is the state the rule is actually about ("a collapsed section
  // still states what it holds"). A hand toggle also takes the section out of the fill
  // controller's reach, so it stays collapsed for the assertion.
  // Converging, not check-then-act: the controller can open the section between the count and the
  // click, and the click would then re-open what this test needs closed (`setSectionOpen`).
  const electrodes = await setSectionOpen(page, "Electrodes", false);
  await expect(electrodes.locator(".form-section-summary")).toHaveText("ellipse · 8×8 mm · gel 4 mm");

  const fields = await setSectionOpen(page, "Output fields", false);
  await expect(fields.locator(".form-section-summary")).toHaveText("TI_max");
});

test("hits its acceptance numbers at both sizes, in both themes (DESIGN.md §12.3)", async () => {
  test.setTimeout(180_000);
  const rows: PageMetrics[] = [];
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    for (const theme of ["light", "dark"] as const) {
      rows.push(
        await captureScreen(page, {
          runId: RUN_ID,
          pageId: "simulator",
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
  console.log("simulator metrics:", JSON.stringify(rows, null, 1));

  for (const row of rows) {
    // See preprocess.spec.ts for why this is not §12.3's 22 %: the DOM instrument measures a
    // strictly smaller quantity than the pixel proxy those limits were set against.
    // Raised from 0.58 when the montage table's six ground rows were removed (the Subjects rule:
    // a list is a list, not a box padded out with empty rows). Those rows were ~200px of
    // `--surface`-backed <td> down the work column, which this instrument scores as content — so
    // deleting them RAISES the number while removing chrome, which is exactly the case where the
    // instrument and the design disagree. Measured after the removal: 0.63 (1280) / 0.69 (1440);
    // +0.02 margin, and still a regression guard on anything that adds real emptiness.
    // Raised again to 0.75 by FXU2: the terminal no longer fills itself with a "What will run"
    // step list when nothing is running, because content in the log pane of a page you merely
    // opened reads as a job in progress. Measured after that change: 0.7076 (1280) / 0.7295 (1440).
    expect(row.deadSpaceRatio, `${row.theme} @${row.width}`).toBeLessThanOrEqual(0.75);
    expect(row.pageHeaderHeight).toBe(0);
    expect(row.panes.nav).toBe(row.width >= 1440 ? 216 : 56);
    // DESIGN.md §2.1: the run panel is `clamp(320px, 45vw, calc(100% - 566px))` — 45 % of the
    // window, ceilinged so the work pane keeps its >=560 px floor. 576 at 1280; at 1440 the
    // ceiling binds, not the 45 %, so 610.
    expect(row.panes.right).toBe(row.width >= 1440 ? 610 : 576);
    expect(row.panes.work).toBeGreaterThanOrEqual(560);
  }

  const first = rows.find((r) => r.width === 1280 && r.theme === "light");
  expect(first?.firstScreenControls.hidden).toEqual([]);
});


/*
 * Evidence only (§8.1), never the assertion — and deliberately last in this serial file: it
 * collapses the run pane and widens the window so the currents column is not clipped by the
 * table's own horizontal scroll, which would move the geometry the acceptance test above measures.
 */
test("records the jobs table (two subjects, mixed sources) as an artifact", async () => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await clearMontageRows();
  await configureMontageJob(page, montageRows().first(), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "mTI_F3F4_P3P4 · mTI",
  });
  const second = await addJobRow(page);
  await configureMontageJob(page, second, { subject: "101", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  const third = await addJobRow(page);
  await setJobSubject(page, third, "ernie");
  await setJobSource(page, third, "Flex result");
  await setJobMontage(page, third, "flex_Thalamus_20260810_101500");
  await expect(montageRows()).toHaveCount(3);

  const chord = process.platform === "darwin" ? "Meta+Shift+i" : "Control+Shift+i";
  await page.setViewportSize({ width: 1800, height: 900 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.keyboard.press(chord);
  await page.getByTestId("sim-jobs-table-container").screenshot({ path: "tests/e2e/artifacts/jobs-table-sim.png" });
});
