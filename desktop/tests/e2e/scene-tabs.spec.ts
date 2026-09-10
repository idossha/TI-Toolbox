/**
 * The run pane's Terminal · Scene rule (plan of record S7), against the mock server (lane SCC).
 *
 * Two clauses, both asserted here because a description of them is not a test:
 *
 *  1. **Scene while configuring, Terminal from the moment a job of this page's kind is running.**
 *     A 3D pane left on screen while a run produces output hides the only place that output is
 *     visible on the page.
 *  2. **A tab the user chose is never taken away.** The switch is automatic only while nobody has
 *     picked; one click pins it. Without this, watching the scene during a batch is impossible.
 *
 * The mock server's jobs finish in seconds, so this is the cheap place to prove it — the real
 * container's own `sim` job takes sixteen minutes under emulation.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { expectRunPaneTab, showRunPaneTab } from "./_runPane";
import { configureMontageJob, jobRows, setJobMontage } from "./_jobs";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-tabs-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await app?.close();
});

test("Scene while configuring; Terminal the moment a job of this kind runs", async () => {
  await expectRunPaneTab(page, "scene");
  await expect(page.getByTestId("run-pane-tabs")).toHaveAttribute("data-active-job", "0");
  // The terminal is mounted the whole time — a tab switch must not drop a live log tail.
  await expect(page.getByTestId("job-terminal")).toHaveCount(1);

  // A complete job in the Jobs table's one seeded row is what makes this page runnable.
  await configureMontageJob(page, jobRows(page).first(), {
    subject: "ernie",
    net: "GSN-HydroCel-185",
    montage: "F3_F4 · TI",
  });
  await expect(page.getByTestId("run-button")).toHaveText("Run simulation");
  await page.getByTestId("run-button").click();

  await expect(page.getByTestId("run-pane-tabs")).toHaveAttribute("data-active-job", "1", { timeout: 20_000 });
  await expectRunPaneTab(page, "terminal");
  await expect(page.getByTestId("job-terminal")).toBeVisible();
});

test("a tab the user chose is not taken away by the next job", async () => {
  // Pick Scene by hand while a job is (or has just been) running.
  await showRunPaneTab(page, "scene");
  await expect(page.getByTestId("run-pane-tabs")).toHaveAttribute("data-chosen", "scene");

  // A different montage in the same row, so Run submits a genuinely new job. (The table keeps its
  // rows after a run — 2.5.0's job cards did too.)
  await setJobMontage(page, jobRows(page).first(), "Thalamus_target · TI");
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-pane-tabs")).toHaveAttribute("data-active-job", "1", { timeout: 20_000 });
  // ...and the pane stays where the user put it.
  await expectRunPaneTab(page, "scene");
});
