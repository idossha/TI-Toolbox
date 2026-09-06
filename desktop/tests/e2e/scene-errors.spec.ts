/**
 * A failed guide request stays readable and recovers only on an explicit retry.
 *
 * Rewritten 2026-09-05 for the fixed guide (plan R4). What it used to pin was the *scene* routes'
 * 202/500 build cycle: a subject's surfaces are extracted from a 184 MB mesh, so a cold request
 * answered 202 and a build failure was reported once and then cleared. The guide ships built —
 * there is no build, no 202 and no poll — so what is left to get wrong is the failure itself:
 *
 *  - it must be shown as the server's own sentence, not "failed to load";
 *  - it must NOT retry itself (a silent retry loop hides a broken installation and hammers the
 *    server); and
 *  - it must survive leaving the page and coming back, so the user can actually read it.
 */
import { expect, test, type Page } from "@playwright/test";
import { gotoPage, launchElectronApp, selectSubject } from "./_helpers";

const SERVER = process.env.TIT_E2E_SERVER_URL!;
const TOKEN = process.env.TIT_E2E_TOKEN!;

for (const endpoint of ["manifest", "regions"] as const) {
  test(`a guide ${endpoint} failure is readable and retries only on demand`, async () => {
    test.skip(TOKEN !== "mock-token", "Fault injection is limited to the isolated mock server.");
    const install = await fetch(`${SERVER}/api/tetravox/install`, {
      method: "POST", headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ version: "0.4.0" }),
    });
    expect(install.ok).toBe(true);
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
      // The Optimizer: a `target` pane, which asks for BOTH the manifest and an atlas' regions as
      // it opens — the guide's atlas payloads are packaged, so cortical context is drawn whether or
      // not the form has chosen an atlas yet.
      await gotoPage(page, "optimizer");
      const panel = page.locator('[data-page-panel="optimizer"]');

      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "error", { timeout: 5000 });
      await expect(panel.getByTestId("scene-pane-message")).toHaveText(`Synthetic ${endpoint} read failed`);
      // Longer than the old build-poll interval: an HTTP failure must not retry itself at all.
      await page.waitForTimeout(2250);
      expect(requests).toBe(1);
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "error");

      allowSuccess = true;
      await panel.getByRole("button", { name: "Retry 3D preview" }).click();
      await expect(panel.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout: 10_000 });
      expect(requests).toBe(2);
      await expect(panel.getByRole("slider", { name: "Skin opacity", exact: true })).toBeEnabled();
      await expect(panel.getByRole("slider", { name: "Grey matter opacity", exact: true })).toBeEnabled();
    } finally {
      await page?.unrouteAll({ behavior: "wait" });
      await app.close();
      const headers = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };
      const restore = await fetch(`${SERVER}/api/tetravox/activate`, { method: "POST", headers, body: JSON.stringify({ version: "baked" }) });
      expect(restore.ok).toBe(true);
      const remove = await fetch(`${SERVER}/api/tetravox/0.4.0`, { method: "DELETE", headers });
      expect(remove.ok).toBe(true);
    }
  });
}
