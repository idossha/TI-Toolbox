import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { analysisRows, setAnalysisCell, setAnalysisSphere } from "./_jobs";

/**
 * A job you started here stays in this page's Terminal after it finishes (maintainer, 2026-09-07).
 *
 * The defect: the Analyzer's terminal followed the run it had just started only while that run was
 * *running*. The instant the job succeeded the follow rule (which pins nothing finished) dropped
 * it, and the pane the user was reading became "TERMINAL · No job — No job running." — the log and
 * the final status line gone, with nothing having been clicked.
 *
 * Driven against the mock server, whose jobs finish in ~6-10 s.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });

  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
});

test.afterAll(async () => {
  await app?.close();
});

const terminal = () => page.locator('[data-page-active="true"]').getByTestId("job-terminal");

test("the analyzer job you ran is still in the terminal after it succeeds", async () => {
  // A page that has run nothing follows nothing: the rule the earlier screenshot forced is intact.
  await expectRunPaneTab(page, "scene");
  await showRunPaneTab(page, "terminal");
  await expect(terminal()).toHaveAttribute("data-source", "empty");

  const row = analysisRows(page).first();
  await setAnalysisCell(page, row, "simulation", "Thalamus");
  await setAnalysisSphere(page, row, { x: -10, y: -18, z: 9, radius: 10 });
  await expect(page.getByTestId("run-button")).toHaveText("Run analysis", { timeout: 15_000 });
  await page.getByTestId("run-button").click();
  await expect(page.getByText(/Queued: analysis/)).toBeVisible({ timeout: 10_000 });

  // While it runs, the terminal names it and prints its log.
  const identity = terminal().getByTestId("job-terminal-identity");
  await expect(identity).toContainText("analyzer", { timeout: 20_000 });
  await expect(terminal()).toHaveAttribute("data-source", "live", { timeout: 20_000 });
  await expect(terminal().locator(".job-console-line").first()).toBeVisible({ timeout: 30_000 });

  // And when it ends, it stays — with its final status line.
  await expect(identity).toContainText("succeeded", { timeout: 60_000 });
  const lines = await terminal().locator(".job-console-line").count();
  expect(lines).toBeGreaterThan(0);

  // Five seconds later — well past the poll and the socket's job-list refresh — it is still there.
  // This is the exact window in which the pane used to empty itself.
  await page.waitForTimeout(5_000);
  await expect(terminal()).toHaveAttribute("data-source", "live");
  await expect(identity).toContainText("analyzer");
  await expect(identity).toContainText("succeeded");
  await expect(terminal().getByTestId("job-terminal-empty")).toHaveCount(0);
  expect(await terminal().locator(".job-console-line").count()).toBeGreaterThan(0);
});

test("...and it survives a walk to Overview and back — it is page-session state", async () => {
  await gotoPage(page, "overview", "Overview");
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");

  // The pane comes back on the Terminal, not on the Scene: a page that has run something shows
  // what it ran (the tab-level half of the same rule).
  await expectRunPaneTab(page, "terminal");
  const identity = terminal().getByTestId("job-terminal-identity");
  await expect(identity).toContainText("analyzer", { timeout: 20_000 });
  await expect(identity).toContainText("succeeded");
  await expect(terminal().locator(".job-console-line").first()).toBeVisible({ timeout: 30_000 });
});
