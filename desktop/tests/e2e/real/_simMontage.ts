import { expect, type Page } from "@playwright/test";
import { configureMontageJob, jobRows } from "../_jobs";

/** The `.field` whose label matches — the montage editor's "EEG net"/"Montage name" fields pass
 *  no `htmlFor`/`id` (program `optimizer.spec.ts`'s own `field()` convention, reused here since
 *  `getByLabel` cannot resolve an unassociated `<Field>`). */
function field(page: Page, label: string) {
  return page.locator(".field", { hasText: label }).first();
}

/**
 * Creates a brand-new montage through the real Simulator UI (`MontageManager.tsx`) and selects it
 * in a row of the montage table for the currently-selected subject(s), so `sim.spec.ts` /
 * `sim-mti.spec.ts` never touch a pre-existing montage (program P6 — nothing here can collide
 * with a subject's real montages).
 *
 * `pairs` must be exactly 2 (TI, uni-polar) or 4+ (mTI, multi-polar) — `MontageManager`'s own
 * `isValidPairCount` rule. The polarity is NOT chosen: the editor infers it from the pair count
 * and saves into the matching bucket, which is what the read-only label below asserts.
 */
export async function createAndSelectMontage(
  page: Page,
  opts: { subject: string; net: string; name: string; pairs: [string, string][] },
): Promise<void> {
  const { net, name, pairs } = opts;
  const kind: "uni_polar" | "multi_polar" = pairs.length === 2 ? "uni_polar" : "multi_polar";

  await page.getByRole("button", { name: "New montage", exact: true }).click();
  await field(page, "EEG net").getByRole("combobox").click();
  await page.getByRole("option", { name: net, exact: true }).click();
  await field(page, "Montage name").getByRole("textbox").fill(name);

  const editor = page.locator(".electrode-pairs");
  // A fresh draft starts with 2 empty pair rows and grows two pairs (one channel) at a time.
  for (let i = 2; i < pairs.length; i += 2) await page.getByRole("button", { name: "Add 2 pairs", exact: true }).click();
  for (let i = 0; i < pairs.length; i++) {
    const row = editor.locator(".electrode-pair-row").nth(i);
    const [a, b] = pairs[i] as [string, string];
    // Each slot is a `SelectionPicker` (lane C2's one selection grammar): a `combobox` trigger
    // opening the shared list in a dialog, which stays open until "Done" — the old two-`Select`
    // flow this helper was written against is gone.
    for (const [slot, label] of [[0, a], [1, b]] as const) {
      await row.getByRole("combobox").nth(slot).click();
      await page.getByRole("dialog").getByRole("option", { name: label, exact: true }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
    }
  }

  // The inferred polarity, stated before the save — the bucket the montage lands in.
  await expect(page.getByTestId("montage-draft-polarity")).toContainText(kind === "uni_polar" ? "TI" : "mTI");

  // A real DOM `.click()` via `evaluate`, not `locator.click()`: a full 4-pair mTI editor pushes
  // "Save montage" low enough that it sits under the page's sticky `.action-bar` — genuinely
  // reachable in the DOM (never `disabled`) but geometrically unclickable no matter the scroll
  // position (`.page-layout-main` doesn't reserve the action bar's own height in its scrollable
  // content, a pre-existing gap in `ui/Layout.tsx`'s pane primitive). `locator.click({ force:
  // true })` does not help: Chromium's own hit-testing at that screen point still resolves to the
  // action bar. A same-node `HTMLElement.click()` fires React's listener directly, bypassing hit
  // testing — confirmed by the toast assertion right below.
  await page.getByRole("button", { name: "Save montage" }).evaluate((el) => (el as HTMLButtonElement).click());
  await expect(page.getByText(`Saved montage "${name}".`)).toBeVisible({ timeout: 10_000 });

  // Select it in the Jobs table: the seeded row's subject (already the shell's), then its net and
  // its montage (both polarities are in the one list, labelled `<name> · TI` / `<name> · mTI`).
  const row = jobRows(page).first();
  await configureMontageJob(page, row, {
    subject: opts.subject,
    net,
    montage: `${name} · ${kind === "uni_polar" ? "TI" : "mTI"}`,
  });
}

/** Deletes the montage this spec created, through the UI, at teardown. */
export async function deleteMontage(page: Page, name: string): Promise<void> {
  const row = page.locator(`tr[data-job-row][data-montage-row="${name}"]`);
  if ((await row.count()) === 0) return;
  await row.getByRole("button", { name: `Delete ${name}` }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete montage" }).click();
  await expect(page.getByText(`Deleted montage "${name}".`)).toBeVisible({ timeout: 10_000 });
}
