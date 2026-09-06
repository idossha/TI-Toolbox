/**
 * A failed guide request stays readable and recovers only on an explicit retry.
 *
 * The guide ships built — there is no build, no 202 and no poll — so what is left to get wrong is
 * the failure itself:
 *
 *  - it must be shown as the server's own sentence, not "failed to load";
 *  - it must NOT retry itself (a silent retry loop hides a broken installation and hammers the
 *    server); and
 *  - it must survive leaving the page and coming back, so the user can actually read it.
 *
 * The two endpoints below are the two that can empty the pane. A `regions` or `electrodes` failure
 * deliberately is NOT one of them: an atlas or a net the guide does not carry leaves the anatomy
 * worth drawing and the form entirely usable, so it is a sentence under the stage, not a state.
 */
import { expect, test, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp, selectSubject } from "./_helpers";

const SERVER = process.env.TIT_E2E_SERVER_URL!;
const TOKEN = process.env.TIT_E2E_TOKEN!;

for (const endpoint of ["manifest", "surface"] as const) {
  test(`a guide ${endpoint} failure is readable and retries only on demand`, async () => {
    test.skip(TOKEN !== "mock-token", "Fault injection is limited to the isolated mock server.");
    const app = await launchElectronApp();
    let page: Page | undefined;
    try {
      page = await app.firstWindow();
      let requests = 0;
      let allowSuccess = false;
      await page.route(`**/api/guide/${endpoint}*`, async (route) => {
        requests++;
        if (allowSuccess) return route.continue();
        return route.fulfill({ status: 500, json: { detail: `Synthetic ${endpoint} read failed` } });
      });
      await page.fill("#server-url", SERVER);
      await page.fill("#token", TOKEN);
      await page.click("#connect");
      await expect(page.getByTestId("nav-rail")).toBeVisible();
      await selectSubject(page, "ernie");
      await gotoPage(page, "optimizer");
      const panel = page.locator('[data-page-panel="optimizer"]');

      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "error", { timeout: 10_000 });
      await expect(panel.getByTestId("scene-pane-message")).toHaveText(`Synthetic ${endpoint} read failed`);
      // An HTTP failure must not retry itself at all. `surface` is two parts, so the honest
      // assertion is "no request after the first round", not "exactly one request".
      const afterFirstRound = requests;
      await page.waitForTimeout(2250);
      expect(requests).toBe(afterFirstRound);
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "error");

      allowSuccess = true;
      await panel.getByRole("button", { name: "Retry 3D preview" }).click();
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 15_000 });
      expect(requests).toBeGreaterThan(afterFirstRound);
      // The renderer's own per-surface opacity controls — proof the canvas mounted with both parts.
      await expect(panel.getByRole("slider", { name: "Skin opacity", exact: true })).toBeEnabled();
      await expect(panel.getByRole("slider", { name: "Grey matter opacity", exact: true })).toBeEnabled();
    } finally {
      await page?.unrouteAll({ behavior: "wait" });
      await app.close();
    }
  });
}
