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
  await cell(row, "net").getByRole("radio", { name: mode, exact: true }).click();
}

/** The net a flex row is mapped onto — only present once "Map to net" is chosen. */
export async function setJobMappedNet(page: Page, row: Locator, net: string): Promise<void> {
  await cell(row, "net").getByRole("combobox").click();
  await page.getByRole("option", { name: net, exact: true }).click();
}

/** Sets a row's montage / flex run / free-hand set — the fourth column, whatever the source. */
export async function setJobMontage(page: Page, row: Locator, option: string): Promise<void> {
  await cell(row, "montage").getByRole("combobox").click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** The row's current (mA) inputs — the count follows its polarity. */
export function jobCurrents(row: Locator): Locator {
  return cell(row, "currents").getByRole("spinbutton");
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

/** The Analyzer's Jobs table rows. */
export function analysisRows(page: Page): Locator {
  return page.locator("tr[data-analysis-row]");
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
