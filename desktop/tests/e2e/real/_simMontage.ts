import { expect, type Page } from "@playwright/test";

/** The `.field` whose label matches — `MontageManager`'s "EEG net"/"Polarity"/"Montage name"
 *  fields pass no `htmlFor`/`id` (program `optimizer.spec.ts`'s own `field()` convention, reused
 *  here since `getByLabel` cannot resolve an unassociated `<Field>`). */
function field(page: Page, label: string) {
  return page.locator(".field", { hasText: label }).first();
}

/**
 * Creates a brand-new montage through the real Simulator UI (`MontageManager.tsx`) and ticks it
 * for the currently-selected subject(s), so `sim.spec.ts` / `sim-mti.spec.ts` never touch a
 * pre-existing montage (program P6 — nothing here can collide with a subject's real montages).
 *
 * `pairs` must be exactly 2 (TI, uni-polar) or 4+ (mTI, multi-polar) — `MontageManager`'s own
 * `isValidPairCount` rule.
 */
export async function createAndSelectMontage(
  page: Page,
  opts: { net: string; name: string; pairs: [string, string][] },
): Promise<void> {
  const { net, name, pairs } = opts;
  const kind: "uni_polar" | "multi_polar" = pairs.length === 2 ? "uni_polar" : "multi_polar";

  await field(page, "EEG net").getByRole("combobox").click();
  await page.getByRole("option", { name: net, exact: true }).click();
  await field(page, "Polarity").getByRole("combobox").click();
  await page.getByRole("option", { name: kind === "uni_polar" ? "Uni-polar (TI, 2 pairs)" : "Multi-polar (mTI, 4+ pairs)" }).click();

  // `.first()`: when this (net, polarity) has zero existing montages, `EmptyState` renders its own
  // "New montage" call-to-action button *in addition to* the toolbar's — two same-named buttons,
  // and the toolbar's is always first in DOM order (montage-table.spec territory none of the mock
  // specs hit, since their fixtures always seed at least one uni-polar montage; this real project
  // has zero multi-polar ones for BioSemi-128, so `sim-mti.spec.ts` is what surfaces it).
  await page.getByRole("button", { name: "New montage" }).first().click();
  await field(page, "Montage name").getByRole("textbox").fill(name);

  const editor = page.locator(".electrode-pairs");
  // A fresh uni-polar montage starts with 2 empty pair rows, multi-polar with 4 — exactly `pairs`'
  // own length in both cases this file is used for, so no "Add pair" clicks are needed.
  for (let i = 0; i < pairs.length; i++) {
    const row = editor.locator(".electrode-pair-row").nth(i);
    const [a, b] = pairs[i] as [string, string];
    await row.getByRole("combobox").nth(0).click();
    await page.getByRole("option", { name: a, exact: true }).click();
    await row.getByRole("combobox").nth(1).click();
    await page.getByRole("option", { name: b, exact: true }).click();
  }

  // A real DOM `.click()` via `evaluate`, not `locator.click()`: a full 4-pair mTI editor on a
  // net with zero pre-existing montages (this file's own `.first()` case, above) pushes "Save
  // montage" low enough that it sits under the page's sticky `.action-bar` — genuinely reachable
  // in the DOM (never `disabled`) but geometrically unclickable no matter the scroll position
  // (`.page-layout-main` doesn't reserve the action bar's own height in its scrollable content, a
  // pre-existing gap in `ui/Layout.tsx`'s pane primitive — reported in this lane's notes, proven
  // with a scratch spec that scanned every scroll position and found none where the two don't
  // overlap). `locator.click({ force: true })` does not help: Chromium's own hit-testing at that
  // screen point still resolves to the action bar, not the button, so the click is silently lost.
  // A same-node `HTMLElement.click()` fires React's listener directly, bypassing hit-testing
  // entirely — confirmed against the real button (not merely "no error thrown") by the toast
  // assertion right below.
  await page.getByRole("button", { name: "Save montage" }).evaluate((el) => (el as HTMLButtonElement).click());
  await expect(page.getByText(`Saved montage "${name}".`)).toBeVisible({ timeout: 10_000 });

  const row = page.locator(".data-table tbody tr", { hasText: name });
  await row.getByRole("checkbox").click();
}

/** Deletes the montage this spec created, through the UI, at teardown. */
export async function deleteMontage(page: Page, name: string): Promise<void> {
  const row = page.locator(".data-table tbody tr", { hasText: name });
  if ((await row.count()) === 0) return;
  await row.getByRole("button", { name: `Delete ${name}` }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete montage" }).click();
  await expect(page.getByText(`Deleted montage "${name}".`)).toBeVisible({ timeout: 10_000 });
}
