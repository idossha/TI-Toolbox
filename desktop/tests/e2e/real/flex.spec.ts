import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import {
  cancelJobFromRail,
  connectReal,
  expectPage,
  gotoPage,
  launchElectronApp,
  recordPayload,
  selectSubject,
  waitForJobRunningOrTerminal,
} from "../_helpers";

/**
 * Optimizer / Flex, against the shared dev container. Fixture matrix row: `sub-ernie`, atlas ROI
 * (list form), started -> cancel.
 *
 * This row was the program's own §0 failure: the UI emits `atlas_path` as `string[]` (ROI unions,
 * PR #130) while `flex.py`'s `_validate_roi_input` assumed a scalar, so the job died in seconds
 * with `TypeError: expected str, bytes or os.PathLike object, not list`. F0 fixed the runner
 * (2026-09-03) and both branches below are kept deliberately: the "running" branch is what a
 * healthy run takes and what this spec now asserts (measured 2026-09-04, job fb8832a6d4f440d1,
 * reached `running` and cancelled in 3.0 s), and the terminal branch keeps the regression
 * witness — if the list-form ROI ever regresses, the failure is named in the assertion message
 * instead of showing up as a bare timeout.
 *
 * The list form itself is asserted on the payload (`config.roi.atlas_path` is an array) before
 * the job is ever submitted, so the shape is proven even when the container is too busy to start
 * the search.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string): Locator {
  return page.locator(".field", { hasText: label }).first();
}

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "ernie");
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "Flex", exact: true }).click();
});

test.afterAll(async () => {
  // Nothing of ours to remove: a cancelled flex writes no run directory (verified on the host
  // after the 2026-09-04 run — `flex-search/` gained no entry).
  await app?.close();
});

test("cortical ROI (DK40 · bankssts, list form): accepted, started, cancelled", async () => {
  test.setTimeout(180_000);

  // Real catalog names the atlas "DK40" (not the mock fixture's friendlier "Desikan-Killiany").
  await field("Atlas").getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DK40");
  await page.getByRole("option", { name: "DK40", exact: true }).click();
  await field("Region(s)").getByRole("combobox").click();
  await page.getByPlaceholder("Search…").fill("bankssts");
  await page.getByRole("option", { name: "L · bankssts" }).click();
  await page.keyboard.press("Escape");

  await expect(page.getByTestId("plan-grid").getByTestId("plan-stat-jobs")).toBeVisible({ timeout: 15_000 });

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    config: { roi: { _type: string; atlas_path: unknown } };
  };
  expect(body.kind).toBe("flex");
  expect(body.subject_ids).toEqual(["ernie"]);
  recordPayload("flex", body);
  // The shape the §0 failure was about, asserted on the real payload: `atlas_path` is an array.
  expect(Array.isArray(body.config.roi.atlas_path)).toBe(true);
  console.log(`real/flex: config.roi.atlas_path = ${JSON.stringify(body.config.roi.atlas_path)}`);

  const created = (await (await jobResponse).json()) as { id: string };
  const job = await waitForJobRunningOrTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 60_000 });

  if (job.state === "running") {
    await expect(page.getByTestId("job-terminal").getByTestId("job-terminal-identity")).toContainText("flex", { timeout: 15_000 });
    await cancelJobFromRail(page, "flex", { timeoutMs: 30_000 });
    console.log(`real/flex: job ${created.id} reached running and was cancelled. run=${RUN_ID}`);
  } else {
    console.log(`real/flex: job ${created.id} state=${job.state} error=${JSON.stringify(job.error)} run=${RUN_ID}`);
    // Regression witness: since F0's fix the healthy path is "running", so a terminal state here
    // is a report of WHICH failure came back, not an expected outcome.
    expect(
      job.state,
      `flex did not reach running — list-form ROI regression? ${JSON.stringify(job.error?.last_lines?.slice(-3) ?? [])}`,
    ).toBe("running");
  }
});
