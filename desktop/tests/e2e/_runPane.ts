/**
 * The run pane's Terminal · Scene tab host (plan of record `docs/dev/HISTORY.md § 2026-09-04 (scene service)` S7),
 * driven identically from every spec so a change to the tab strip's DOM is one edit here.
 *
 * The rule these helpers encode, and why a spec must not just look for the terminal any more:
 * **Scene is the default while nothing of this page's kind is running**, so `job-terminal` is
 * mounted but hidden on a freshly opened run page. A spec that wants the log clicks the tab first.
 */
import { expect, type Page } from "@playwright/test";

export type RunPaneTab = "terminal" | "scene";

/** Asserts which half of the run pane is showing, from the host's own `data-tab`. */
export async function expectRunPaneTab(page: Page, tab: RunPaneTab): Promise<void> {
  const active = page.locator('[data-page-active="true"]');
  await expect(active.getByTestId("run-pane-tabs")).toHaveAttribute("data-tab", tab);
  await expect(active.getByTestId(`run-pane-panel-${tab}`)).toBeVisible();
}

/** Clicks a tab and waits for it to take. A user's choice pins it for the session (S7). */
export async function showRunPaneTab(page: Page, tab: RunPaneTab): Promise<void> {
  const label = tab === "terminal" ? "Terminal" : "Scene";
  await page.getByRole("radiogroup", { name: "Run pane" }).getByRole("radio", { name: label, exact: true }).click();
  await expectRunPaneTab(page, tab);
}

/** The scene pane's own state machine: `no-subject | building | loading | ready | error`. */
export async function scenePaneState(page: Page): Promise<string | null> {
  return page.locator('[data-page-active="true"]').getByTestId("scene-pane-host").getAttribute("data-state");
}

/** Waits for the native scene pane to report its first loaded frame. */
export async function waitForScene(page: Page, timeout = 30_000): Promise<void> {
  await showRunPaneTab(page, "scene");
  const active = page.locator('[data-page-active="true"]');
  await expect(active.getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready", { timeout });
  await expect(active.getByTestId("scene-canvas")).toBeVisible({ timeout });
}
