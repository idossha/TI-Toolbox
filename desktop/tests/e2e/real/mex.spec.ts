import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { cleanupSmokeOutputs, connectReal, expectPage, gotoPage, launchElectronApp, recordPayload, selectSubject, waitForJobTerminal, waitForJobTrace } from "../_helpers";

/**
 * Optimizer / mEx, against the shared dev container. Same rationale as `ex.spec.ts` (not a §3 P4
 * "long kind" — runs to completion within its 600 s budget) and the same subcortical ROI
 * substitution for the mock's "saved" fixture targets, which do not exist on this project. mEx has
 * eight buckets (E1+..E4-) instead of Ex's four and no Combine control (`allowCombine` is Ex-only).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const RUN_NAME = `smoke-ui-${RUN_ID}-mex`;

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
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "mEx", exact: true }).click();
});

test.afterAll(async () => {
  cleanupSmokeOutputs([`derivatives/SimNIBS/sub-ernie/m-ex-search/${RUN_NAME}`]);
  await app?.close();
});

test("subcortical ROI, eight electrode buckets: accepted, started, and completed", async () => {
  test.setTimeout(700_000);

  const strip = page.getByTestId("leadfield-strip");
  await expect(strip).toBeVisible();
  await expect(strip.locator(".chip")).toHaveText(/GB|MB/, { timeout: 15_000 });

  await field("Run name").getByRole("textbox").fill(RUN_NAME);

  await page.getByTestId("page-work").getByRole("radio", { name: "Subcortical", exact: true }).click();
  await field("Volume atlas").getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DKTatlas");
  await page.getByRole("option", { name: /DKTatlas/ }).first().click();
  await field("Region(s)").getByRole("combobox").click();
  await page.getByPlaceholder("Search…").fill("Hippocampus");
  await page.getByRole("option", { name: "Left-Hippocampus", exact: true }).click();
  await page.keyboard.press("Escape");

  const buckets = [
    ["E1+", "Fp1"],
    ["E1-", "Fp2"],
    ["E2+", "F3"],
    ["E2-", "F4"],
    ["E3+", "C3"],
    ["E3-", "C4"],
    ["E4+", "P3"],
    ["E4-", "P4"],
  ] as const;
  for (const [bucket, electrode] of buckets) {
    await field(bucket).locator(".multi-select").click();
    await page.getByRole("option", { name: electrode, exact: true }).click();
    await page.keyboard.press("Escape");
  }

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|overwrite)$/);
  await expect(page.getByTestId("run-button")).toBeEnabled();

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const requestBody = (await jobRequest).postDataJSON() as {
    kind: string;
    config: { roi_name: string; electrodes: Record<string, unknown> };
  };
  expect(requestBody.kind).toBe("mex");
  expect(requestBody.config.electrodes).toMatchObject({
    e1_plus: ["Fp1"],
    e1_minus: ["Fp2"],
    e2_plus: ["F3"],
    e2_minus: ["F4"],
    e3_plus: ["C3"],
    e3_minus: ["C4"],
    e4_plus: ["P3"],
    e4_minus: ["P4"],
  });
  recordPayload("mex", requestBody);

  const created = (await (await jobResponse).json()) as { id: string };
  await waitForJobTrace(page, "mex", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("mex", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 600_000 });
  console.log(`real/mex: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);

  // The reload is load-bearing: the Results tree's catalog queries have a 60 s `staleTime` and
  // nothing invalidates them when a job finishes (measured on the sibling `ex.spec.ts` run —
  // the tree served a listing fetched 42 s before the job ended, with no further request). See
  // that spec's comment and this lane's notes; a fresh renderer is what a user is left with.
  await page.reload();
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 30_000 });
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId("results-subject-ernie").click();
  await expect(page.getByTestId(`results-node-mex:ernie:${RUN_NAME}`)).toBeVisible({ timeout: 20_000 });
});
