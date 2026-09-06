/**
 * The maintainer's report, against the real server and a real subject's real flex-search runs:
 * *"the flex mode in the simulator is not working properly — when I select the Flex result mode it
 * opens up the table selection very nicely, but it does not allow me to click or select any of the
 * options."*
 *
 * Why this needs the real project and not the mock: the failure was in the *shape of the data*.
 * Every one of `sub-ernie`'s flex runs writes a `flex_meta.json` with no electrodes in it at all —
 * so the tab's `manifest.electrodes` read came back empty for every row and disabled every
 * checkbox. A fixture can be written to have any shape; only the real derivatives prove the tab
 * reads what flex-search actually produces.
 *
 * Reads and plans only — no job is submitted, so nothing is written to the project.
 */
import { expect, test } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

test("every real flex-search run is selectable, and a ticked one plans a job", async () => {
  test.setTimeout(120_000);
  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1440, height: 900 });
    await connectReal(page);
    await selectSubject(page, process.env.TIT_E2E_SUBJECT ?? "ernie");
    await gotoPage(page, "simulator");

    await page.getByRole("radiogroup", { name: "Montage source" }).getByRole("radio", { name: "Flex result", exact: true }).click();

    const rows = page.getByTestId("flex-run-row");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const count = await rows.count();
    expect(count, "sub-ernie has flex-search runs under derivatives/SimNIBS").toBeGreaterThan(0);

    // The defect, stated as an assertion: not one row was clickable.
    for (let i = 0; i < count; i++) {
      await expect(rows.nth(i).getByRole("checkbox"), `row ${i} must be selectable`).toBeEnabled();
    }

    const first = rows.first();
    await first.getByRole("checkbox").click();
    await expect(first.getByRole("checkbox")).toBeChecked();

    // It reaches the plan as exactly one job — the server resolving the run a second time from
    // `montage_sources` used to make it two.
    await expect(page.locator('[data-testid^="plan-cell-"]').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · /, { timeout: 30_000 });
    await expect(page.getByTestId("run-button")).toBeEnabled();

    console.log(`REAL-FLEX: ${count} flex runs, all selectable, one ticked run plans one job`);
  } finally {
    await app.close();
  }
});
