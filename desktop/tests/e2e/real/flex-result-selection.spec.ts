/**
 * The maintainer's report, against the real server and a real subject's real flex-search runs:
 * *"the flex mode in the simulator is not working properly — when I select the Flex result mode it
 * opens up the table selection very nicely, but it does not allow me to click or select any of the
 * options."*
 *
 * Why this needs the real project and not the mock: the failure was in the *shape of the data*.
 * Every one of `sub-ernie`'s flex runs writes a `flex_meta.json` with no electrodes in it at all —
 * so the tab's `manifest.electrodes` read came back empty for every row and disabled every
 * checkbox. A fixture can be written to have any shape; only the real derivatives prove the page
 * reads what flex-search actually produces.
 *
 * Since the 2026-09-06 jobs rework there is no flex *tab* and no checkbox: a job row picks
 * `Flex result` in its own Source cell and the run in its Montage cell. The claim is the same —
 * every real run must be offered and must resolve to electrodes — so it is asserted on the run
 * options the cell lists and on the row each of them makes runnable.
 *
 * Reads and plans only — no job is submitted, so nothing is written to the project.
 */
import { expect, test } from "@playwright/test";
import { connectReal, gotoPage, launchElectronApp, selectSubject } from "../_helpers";
import { jobRows, setJobMappedNet, setJobMontage, setJobPlacement, setJobSource, setJobSubject } from "../_jobs";

test("every real flex-search run is selectable, and a ticked one plans a job", async () => {
  test.setTimeout(120_000);
  const app = await launchElectronApp();
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1440, height: 900 });
    await connectReal(page);
    await selectSubject(page, process.env.TIT_E2E_SUBJECT ?? "ernie");
    await gotoPage(page, "simulator");

    const row = jobRows(page).first();
    await setJobSubject(page, row, process.env.TIT_E2E_SUBJECT ?? "ernie");
    await setJobSource(page, row, "Flex result");

    // Every run the catalog knows is offered in the row's Montage cell.
    await row.locator('td[data-cell="montage"]').getByRole("combobox").click();
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible({ timeout: 30_000 });
    const runs = await options.allTextContents();
    expect(runs.length, "sub-ernie has flex-search runs under derivatives/SimNIBS").toBeGreaterThan(0);
    await page.keyboard.press("Escape");

    // The defect, stated as an assertion: not one run resolved to electrodes, so no row could ever
    // become a job. Each is checked in turn, in the one row.
    for (const name of runs) {
      await setJobMontage(page, row, name);
      await expect(row, `run ${name} must resolve to electrodes`).toHaveAttribute("data-runnable", "true");
    }

    // Both placements of the last run, against the real project: the optimiser's own coordinates,
    // and *any* net the subject has — including one the run was never mapped onto, which the
    // server maps on demand (`GET /api/catalog/flex-runs/{run}/mapping`). Nothing is submitted.
    await setJobPlacement(page, row, "Optimised");
    await expect(row.locator('td[data-cell="pairs"]')).toHaveText(/XYZ coordinates$/);
    await setJobPlacement(page, row, "Map to net");
    const netCell = row.locator('td[data-cell="net"]');
    await netCell.getByRole("combobox").click();
    const nets = await page.getByRole("option").allTextContents();
    expect(nets.length, "the subject has EEG nets to map onto").toBeGreaterThan(0);
    await page.keyboard.press("Escape");
    for (const net of nets) {
      await setJobMappedNet(page, row, net);
      await expect(row.locator('td[data-cell="pairs"]'), `mapping onto ${net} must resolve to labels`).toHaveText(/–/, {
        timeout: 30_000,
      });
      await expect(row).toHaveAttribute("data-runnable", "true");
    }

    // And the last one reaches the plan as exactly one job — the server resolving the run a second
    // time from `montage_sources` used to make it two.
    await expect(page.locator('[data-testid^="plan-cell-"]').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · /, { timeout: 30_000 });
    await expect(page.getByTestId("run-button")).toBeEnabled();
    const count = runs.length;

    console.log(`REAL-FLEX: ${count} flex runs, all resolvable, one selected run plans one job`);
  } finally {
    await app.close();
  }
});
