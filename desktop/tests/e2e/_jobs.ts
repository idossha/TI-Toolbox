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

/** Sets a row's EEG net — the montage source's net select. */
export async function setJobNet(page: Page, row: Locator, option: string): Promise<void> {
  await cell(row, "net").getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** A flex row's placement: the optimiser's own coordinates, or an EEG net's labels. */
export async function setJobPlacement(page: Page, row: Locator, mode: "Optimised" | "Map to net"): Promise<void> {
  const item = jobDetail(row).getByRole("radio", { name: mode, exact: true });
  await expect(item).toBeVisible();
  // A real mouse click at the segment's centre. `locator.click()`'s hit-target check reports the
  // Radix toggle item's own parent as the hit on this control (the item is what
  // `document.elementFromPoint` returns at exactly this point — asserted by the state change
  // below), so the pointer is driven directly rather than the assertion being forced off.
  const box = (await item.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(item).toHaveAttribute("data-state", "on");
}

/** The net a flex row is mapped onto — only present once "Map to net" is chosen. */
export async function setJobMappedNet(page: Page, row: Locator, net: string): Promise<void> {
  const trigger = jobDetail(row).getByRole("combobox");
  await expect(trigger).toBeVisible();
  const box = (await trigger.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.getByRole("option", { name: net, exact: true }).click();
}

/** Sets a row's montage / flex run / free-hand set — the fourth column, whatever the source. */
export async function setJobMontage(page: Page, row: Locator, option: string): Promise<void> {
  await cell(row, "montage").getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/**
 * A job's **second line** — the placement, the electrode pairs in full, and the currents. Since the
 * 2026-09-06 redesign a job is two `<tr>`s: `tr[data-job-row]` (what the job is) and the detail row
 * immediately after it (what it will do).
 */
export function jobDetail(row: Locator): Locator {
  return row.locator("xpath=following-sibling::tr[1]");
}

/** The row's electrode-pairs text, on line 2. */
export function jobPairs(row: Locator): Locator {
  return jobDetail(row).locator('[data-cell="pairs"]');
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

export async function setAnalysisCell(page: Page, row: Locator, name: "simulation" | "space" | "field", option: string): Promise<void> {
  await cell(row, name).getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
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
