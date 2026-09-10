import { expect, type Locator, type Page } from "@playwright/test";

/**
 * The Simulator's Jobs table, as a spec addresses it (2026-09-06 rework): one row is one job and
 * owns its own subject, source, net, montage and currents. Every cell is reached by its
 * `data-cell` attribute rather than by combobox index, so a column added later cannot silently
 * re-point a spec at the wrong control.
 */
export function jobRows(page: Page): Locator {
  return page.locator("tr[data-job-row]");
}

function cell(row: Locator, name: string): Locator {
  return row.locator(`td[data-cell="${name}"]`);
}

/** Picks a row's subject — a `SelectionPicker` dialog (the one selection grammar). */
export async function setJobSubject(page: Page, row: Locator, subject: string): Promise<void> {
  await cell(row, "subject").getByRole("combobox").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("option", { name: subject, exact: true }).click();
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(row).toHaveAttribute("data-subject", subject);
}

/** Sets a row's source: `Montage`, `Flex result` or `Free-hand`. */
export async function setJobSource(page: Page, row: Locator, label: string): Promise<void> {
  await cell(row, "source").getByRole("combobox").click();
  await page.getByRole("option", { name: label, exact: true }).click();
}

/**
 * Sets a row's EEG net — the montage source's net select, whichever column it sits in.
 *
 * Callers pass the net's real filename, because that is its id on the wire everywhere else in the
 * app. Since 2026-09-06 the row's option is *labelled* with the file's stem (`MontageManager`
 * renders `netStem(n)`, so a narrow column reads "BioSemi-128-A1" rather than eliding the name to
 * fit the extension), so the trailing `.csv` is dropped here rather than in every spec.
 */
export async function setJobNet(page: Page, row: Locator, option: string): Promise<void> {
  await pickBy(page, row, "EEG net", option.replace(/\.csv$/i, ""));
}

/**
 * Opens the row's control with this `aria-label` and picks `option`. Addressing controls by what
 * they are rather than by which column they sit in: since the v5 reorder the third column holds
 * the net, the flex run or the free-hand set depending on the row's source.
 */
async function pickBy(page: Page, row: Locator, label: string, option: string): Promise<void> {
  const trigger = row.getByRole("combobox", { name: label, exact: true });
  await expect(trigger).toBeVisible();
  // A real mouse click at the trigger's centre: `locator.click()`'s hit-target check reports the
  // cell's own parent as the hit inside a two-line row, so the pointer is driven directly rather
  // than the actionability assertion being forced off. The option list proves it opened.
  const box = (await trigger.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.getByRole("option", { name: option, exact: true }).click();
}

/**
 * A flex row's placement — the optimiser's own coordinates, or the EEG net to map them onto. One
 * select, in the column after the run it qualifies.
 */
export async function setJobPlacement(page: Page, row: Locator, option: string): Promise<void> {
  await pickBy(page, row, "Placement", option);
}

/** The net a flex row maps its optimised positions onto. */
export async function setJobMappedNet(page: Page, row: Locator, net: string): Promise<void> {
  await setJobPlacement(page, row, net);
}

/** Sets a row's montage, flex run or free-hand set — whichever its source names. */
export async function setJobMontage(page: Page, row: Locator, option: string): Promise<void> {
  for (const label of ["Montage", "Flex run", "Free-hand configuration"]) {
    if ((await row.getByRole("combobox", { name: label, exact: true }).count()) > 0) {
      await pickBy(page, row, label, option);
      return;
    }
  }
  throw new Error(`row has no montage / run / free-hand control to set to ${option}`);
}

/**
 * A job's **second line** — the placement, the electrode pairs in full, and the currents. Since the
 * 2026-09-06 redesign a job is two `<tr>`s: `tr[data-job-row]` (what the job is) and the detail row
 * immediately after it (what it will do).
 */
export function jobDetail(row: Locator): Locator {
  return row.locator("xpath=following-sibling::tr[1]");
}

/** The empty first cell of line 2 — the one place in a job that is not a control, so a test can
 *  click the row itself. */
export function jobBlank(row: Locator): Locator {
  return jobDetail(row).locator('td[data-cell="detail-pad"], td[data-cell="detail"]').first();
}

/** The row's electrode pairs, one locator per channel, on line 2. */
export function jobPairs(row: Locator): Locator {
  return jobDetail(row).locator('[data-cell="pair"]');
}

/** The pairs as one string, the way the old single Pairs cell read: `E1–E2 · E3–E4`. */
export async function jobPairsText(row: Locator): Promise<string> {
  return (await jobPairs(row).allTextContents()).join(" · ");
}

/** The row's current (mA) inputs — the count follows its polarity. */
export function jobCurrents(row: Locator): Locator {
  return jobDetail(row).getByRole("spinbutton");
}

/** Empties the table, so a test's job counts are exact rather than additive. */
export async function clearJobRows(page: Page): Promise<void> {
  const remove = page.getByRole("button", { name: /^Remove job / });
  // Re-resolved each pass: removing a row re-renders the table, so a list captured up front goes
  // stale after the first click.
  for (let i = (await remove.count()) - 1; i >= 0; i--) await remove.first().click();
  await expect(jobRows(page)).toHaveCount(0);
}

/** Adds a fresh row and returns it. */
export async function addJobRow(page: Page): Promise<Locator> {
  const before = await jobRows(page).count();
  await page.getByRole("button", { name: "Add job", exact: true }).click();
  await expect(jobRows(page)).toHaveCount(before + 1);
  return jobRows(page).nth(before);
}

/**
 * The whole "one job" gesture: a row on `subject`, montage `montage` of `net`. Returns the row.
 */
export async function configureMontageJob(
  page: Page,
  row: Locator,
  opts: { subject: string; net: string; montage: string },
): Promise<Locator> {
  await setJobSubject(page, row, opts.subject);
  await setJobNet(page, row, opts.net);
  await setJobMontage(page, row, opts.montage);
  await expect(row).toHaveAttribute("data-runnable", "true");
  return row;
}

/* ----------------------------------------------------------------- Analyzer */

/**
 * The Analyzer's Jobs table rows. One job is one `<tbody>` of two `<tr>`s since the 2026-09-06
 * two-line pass (line 1 `Subject · Simulation · Space · Field`, line 2 the target), so the row a
 * spec addresses is the group, and `td[data-cell=…]` reaches either line from it.
 */
export function analysisRows(page: Page): Locator {
  return page.locator("tbody[data-analysis-row]");
}

/** Line 1 of a row — the controls line, for geometry assertions. */
export function analysisLine1(row: Locator): Locator {
  return row.locator("tr.analysis-job-line1");
}

/** Line 2 of a row — the target line. */
export function analysisLine2(row: Locator): Locator {
  return row.locator("tr.analysis-job-line2");
}

export async function setAnalysisSubject(page: Page, row: Locator, subject: string): Promise<void> {
  await cell(row, "subject").getByRole("combobox").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("option", { name: subject, exact: true }).click();
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(row).toHaveAttribute("data-subject", subject);
}

export async function setAnalysisCell(
  page: Page,
  row: Locator,
  name: "simulation" | "space" | "field",
  option: string,
): Promise<void> {
  await cell(row, name).getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/**
 * The row's tissue — a *setting*, so it lives in the row's Job settings dialog under "Space
 * options" rather than on the row itself (maintainer, 2026-09-06). Opens the dialog, sets it and
 * closes again.
 */
export async function setAnalysisTissue(page: Page, row: Locator, option: string): Promise<void> {
  const dialog = await openAnalysisTarget(page, row);
  await dialog.getByTestId("analysis-space-options").getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
  await closeAnalysisTarget(page);
}

/**
 * Opens a row's Target editor — the dialog holding the shared `RoiPicker`, scoped to that row
 * (maintainer, 2026-09-06: "we can modify our analysis input per job"). Returns the dialog.
 */
export async function openAnalysisTarget(page: Page, row: Locator): Promise<Locator> {
  await cell(row, "target").getByRole("button").click();
  const dialog = page.getByRole("dialog").filter({ has: page.getByTestId("analysis-target-editor") });
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function closeAnalysisTarget(page: Page): Promise<void> {
  await page.getByTestId("analysis-target-done").click();
  await expect(page.getByTestId("analysis-target-editor")).toHaveCount(0);
}

/** The whole spherical-target gesture for one row: open, type the sphere, close. */
export async function setAnalysisSphere(
  page: Page,
  row: Locator,
  s: { x: number; y: number; z: number; radius: number; space?: "Subject" | "MNI" },
): Promise<void> {
  const dialog = await openAnalysisTarget(page, row);
  await dialog.getByRole("radio", { name: "Spherical", exact: true }).click();
  if (s.space) await dialog.getByRole("radio", { name: s.space, exact: true }).click();
  await dialog.getByLabel("Sphere 1 X").fill(String(s.x));
  await dialog.getByLabel("Sphere 1 Y").fill(String(s.y));
  await dialog.getByLabel("Sphere 1 Z").fill(String(s.z));
  await dialog.getByLabel("Sphere 1 radius").fill(String(s.radius));
  await closeAnalysisTarget(page);
  await expect(row).toHaveAttribute("data-target-ready", "true");
}

/** The row's Target cell, as it reads with the dialog closed. */
export function analysisTargetText(row: Locator): Locator {
  return cell(row, "target").locator(".analysis-target-text");
}

/* ---------------------------------------------------------------- Optimizer */

/**
 * The Optimizer's Jobs table rows (lane OJ, 2026-09-06). One search is one `<tbody>` of two
 * `<tr>`s — line 1 `Subject · Method · Net/leadfield · Goal`, line 2 the target and the search
 * summary — so the row a spec addresses is the group, and `td[data-cell=…]` reaches either line.
 */
export function optRows(page: Page): Locator {
  return page.locator("tbody[data-opt-row]");
}

export async function setOptSubject(page: Page, row: Locator, subject: string): Promise<void> {
  await cell(row, "subject").getByRole("combobox").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("option", { name: subject, exact: true }).click();
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(row).toHaveAttribute("data-subject", subject);
}

/** Sets a cell of line 1: the method, the net/leadfield, or the goal. */
export async function setOptCell(page: Page, row: Locator, name: "method" | "net" | "goal", option: string): Promise<void> {
  await cell(row, name).getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** Opens the row's editor — the per-method dialog holding the target picker and the form
 *  sections, scoped to that row. Returns the dialog. */
export async function openOptEditor(page: Page, row: Locator, via: "target" | "settings" = "target"): Promise<Locator> {
  if (via === "settings") await cell(row, "actions").getByRole("button", { name: /^Job settings / }).click();
  else await cell(row, "target").getByRole("button").click();
  const dialog = page.getByRole("dialog").filter({ has: page.getByTestId("opt-row-editor") });
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function closeOptEditor(page: Page): Promise<void> {
  await page.getByTestId("opt-row-done").click();
  await expect(page.getByTestId("opt-row-editor")).toHaveCount(0);
}

/** The row's TARGET, the first half of line 2 — the half that never truncates. */
export function optRowSummary(row: Locator): Locator {
  return cell(row, "target").locator(".opt-target-text");
}

/** The rest of line 2: the search essentials, which is the half that ellipses. */
export function optRowDetail(row: Locator): Locator {
  return cell(row, "target").locator(".opt-row-detail");
}

/** Adds a fresh row. Adding does NOT open the editor — the row is appended and made active, and
 *  configuring it is a separate act (the pencil, the target line, a double-click, or Enter). */
export async function addOptRow(page: Page): Promise<Locator> {
  const before = await optRows(page).count();
  await page.getByRole("button", { name: "Add job", exact: true }).click();
  await expect(optRows(page)).toHaveCount(before + 1);
  await expect(page.getByTestId("opt-row-editor")).toHaveCount(0);
  return optRows(page).nth(before);
}

/** Empties the table, so a spec's job counts are exact rather than additive. */
export async function clearOptRows(page: Page): Promise<void> {
  const remove = page.getByRole("button", { name: /^Remove job / });
  for (let i = (await remove.count()) - 1; i >= 0; i--) await remove.first().click();
  await expect(optRows(page)).toHaveCount(0);
}
