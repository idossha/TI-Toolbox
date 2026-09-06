/**
 * One helper for the one subject control (plan §3, J1-J4).
 *
 * Pre-processing, Simulator, Optimizer, Analyzer and the Source panel all render
 * `pages/_shared/subjects/SubjectsField`, so every spec drives it through these functions rather
 * than through page-local selectors. If a page ever diverges — a different testid, a different
 * disclosure, a second way to pick a subject — `expectSubjectsGrammar` fails on that page and
 * nowhere else, which is exactly the regression J1 exists to prevent.
 *
 * The row class `.subject-picker-row` is deliberately kept from the pre-J1 controls: it is the
 * vocabulary the existing mock and real specs already locate a subject row by.
 */
import { expect, type Locator, type Page } from "@playwright/test";

export type SubjectsMode = "per-subject" | "grouped" | "single";

/** The control itself. Scope every other query to it — a page may show subjects elsewhere too. */
export function subjectsField(page: Page): Locator {
  return page.locator('[data-page-active="true"]').getByTestId("subjects-field");
}

/**
 * Every row of the control, scoped to it. NOT a bare `.subject-picker-row`: `_shared/roi`'s saved-
 * ROI list borrows that same class, so an unscoped count on the Optimizer picks up the target
 * list's rows too (measured on the real project: 5 subjects + 1 saved ROI = 6).
 */
export function subjectRows(page: Page): Locator {
  return subjectsField(page).locator(".subject-picker-row");
}

/** One subject's row. Only exists while the disclosure is open. */
export function subjectRow(page: Page, id: string): Locator {
  return subjectsField(page).getByTestId(`subject-row-${id}`);
}

/** The one-line summary: `ernie · one job per subject`. */
export function subjectsSummary(page: Page): Locator {
  return subjectsField(page).getByTestId("subjects-summary");
}

/** Opens the table if it is closed (Pre-processing and the Source panel start open). */
export async function openSubjects(page: Page): Promise<void> {
  if ((await subjectsField(page).getAttribute("data-open")) !== "true") {
    await subjectsField(page).getByTestId("subjects-change").click();
  }
  await expect(subjectsField(page).getByTestId("subjects-field-table")).toBeVisible();
}

/** Closes it again — the same control, which reads "Done" while open. */
export async function closeSubjects(page: Page): Promise<void> {
  if ((await subjectsField(page).getAttribute("data-open")) === "true") {
    await subjectsField(page).getByTestId("subjects-change").click();
  }
  await expect(subjectsField(page).getByTestId("subjects-field-table")).toHaveCount(0);
}

/** Ticks / unticks one subject, opening the table first if needed. */
export async function setSubjectChecked(page: Page, id: string, on: boolean): Promise<void> {
  await openSubjects(page);
  const box = subjectRow(page, id).getByRole("checkbox");
  if ((await box.isChecked()) !== on) await box.click();
  await expect(subjectRow(page, id)).toHaveAttribute("data-selected", on ? "true" : "false");
}

/** The exact set, in order, leaving the table as it found it. */
export async function selectSubjects(page: Page, ids: string[]): Promise<void> {
  await openSubjects(page);
  const rows = await subjectRows(page).all();
  for (const row of rows) {
    const id = ((await row.getAttribute("data-testid")) ?? "").replace("subject-row-", "");
    const box = row.getByRole("checkbox");
    const want = ids.includes(id);
    if ((await box.isChecked()) !== want) await box.click();
  }
  await expect(subjectsField(page)).toHaveAttribute("data-selected", String(ids.length));
}

/** The `N of M selected` badge. */
export function subjectsCount(page: Page): Locator {
  return subjectsField(page).getByTestId("subject-count");
}

/** Types into the control's own filter box. */
export async function filterSubjects(page: Page, query: string): Promise<void> {
  await openSubjects(page);
  await subjectsField(page).getByTestId("subjects-filter").fill(query);
}

/**
 * The shared shape, asserted identically on every page that takes subjects: the field with its
 * mode and selection count, the summary line, the disclosure — and, once open, the filter, the
 * select-all (except in `single` mode, where there is nothing to select all of) and one row per
 * subject carrying its own eligibility.
 */
export async function expectSubjectsGrammar(
  page: Page,
  opts: { mode: SubjectsMode; selected: string[]; rows: number; blocked?: Record<string, string> },
): Promise<void> {
  const field = subjectsField(page);
  await expect(field).toHaveCount(1);
  await expect(field).toHaveAttribute("data-mode", opts.mode);
  await expect(field).toHaveAttribute("data-selected", String(opts.selected.length));
  const note =
    opts.mode === "per-subject" ? "one job per subject" : opts.mode === "grouped" ? "one job over all subjects" : "one job";
  if (opts.selected.length === 0) {
    await expect(subjectsSummary(page)).toHaveText("No subjects selected");
  } else {
    const lead = opts.selected.length > 1 ? `${opts.selected.length} subjects · ` : "";
    await expect(subjectsSummary(page)).toHaveText(`${lead}${opts.selected.join(", ")} · ${note}`);
  }

  const wasOpen = (await field.getAttribute("data-open")) === "true";
  await openSubjects(page);
  await expect(field.getByTestId("subjects-filter")).toBeVisible();
  // `All · None` — the only two bulk buttons, and the same pair every other list in the app draws
  // (plan C1). `single` mode has nothing to select all of, so it draws neither.
  await expect(field.getByTestId("subject-select-all")).toHaveCount(opts.mode === "single" ? 0 : 1);
  await expect(field.getByTestId("subject-select-none")).toHaveCount(opts.mode === "single" ? 0 : 1);
  await expect(field.getByTestId("subject-count")).toHaveCount(1);
  await expect(subjectRows(page)).toHaveCount(opts.rows);
  for (const id of opts.selected) {
    await expect(subjectRow(page, id)).toHaveAttribute("data-selected", "true");
  }
  for (const [id, reason] of Object.entries(opts.blocked ?? {})) {
    await expect(subjectRow(page, id)).toHaveAttribute("data-eligible", "false");
    await expect(field.getByTestId(`subject-reason-${id}`)).toHaveText(reason);
  }
  if (!wasOpen) await closeSubjects(page);
}
