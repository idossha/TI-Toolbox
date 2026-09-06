import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import {
  cleanupSmokeOutputs,
  connectReal,
  expectPage,
  launchElectronApp,
  recordPayload,
  selectJobsPanelTab,
  smokeDirFromArtifactPath,
  waitForJobTerminal,
  waitForJobTrace,
} from "../_helpers";

/**
 * Panel — Nilearn visuals, against the shared dev container. Fixture matrix row: "one `L_Insula`
 * NIfTI" — uses `sub-101`'s `L_Insula` simulation (present per the catalog).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const SUBDIR = `smoke-ui-${RUN_ID}`;

let app: ElectronApplication;
let page: Page;
let cleanupPath: string | null = null;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await page.getByRole("link", { name: "Nilearn visuals", exact: true }).click();
  await expectPage(page, "panel-nilearn-visuals");
});

test.afterAll(async () => {
  if (cleanupPath) cleanupSmokeOutputs([cleanupPath]);
  await app?.close();
});

test("visualize sub-101's L_Insula: accepted, started, and completed", async () => {
  test.setTimeout(240_000);

  // The shared participants grammar (`pages/panels/_participants`, lane FIX-D defect 3): one
  // `participant-row-<id>` per pair, Subject then Simulation in column order.
  const row = page.getByTestId("participants-field").locator("[data-testid^='participant-row-']").first();
  await row.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: "101", exact: true }).click();
  await row.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: "L_Insula", exact: true }).click();
  await expect(page.getByTestId("participants-summary")).toHaveText("101 · one job over all subjects");

  await page.getByLabel("Sub-directory name").fill(SUBDIR);
  await expect(page.getByText("Enter a sub-directory name for the output files.")).toHaveCount(0);

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const body = (await jobRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: { subdir_name: string } };
  expect(body.kind).toBe("nilearn");
  expect(body.subject_ids).toEqual(["101"]);
  expect(body.config.subdir_name).toBe(SUBDIR);
  recordPayload("nilearn", body);

  const created = (await (await jobResponse).json()) as { id: string };
  // Click the trace (not just wait for it): the Console tab renders the *selected* job's log —
  // `ConsolePane`'s `job` prop is `undefined` (empty state, no `.job-console-line` ever) until
  // something calls `select(job.id)`, which only the trace's own `onClick` does.
  const trace = await waitForJobTrace(page, "nilearn", { timeoutMs: 120_000 });
  await trace.click();
  await selectJobsPanelTab(page, "Console");
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 120_000 });
  console.log(`real/nilearn-visuals: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);
  cleanupPath = smokeDirFromArtifactPath(finalJob.artifacts?.[0]?.path ?? "", SUBDIR);
});
