import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, PROJECT_HOST_ROOT, recordPayload, selectSubject, waitForJobTerminal, waitForJobTrace } from "../_helpers";
import { removeNewEntriesSince, snapshotDir } from "./_dirDiff";

/**
 * Analyzer, mesh space — against the shared dev container. Fixture matrix row: `sub-ernie`,
 * simulation `Thalamus`, spherical target — the mock's own fixture coordinates
 * (`analyzer.spec.ts`), which turn out to be real Thalamus coordinates on this project too.
 *
 * `AnalyzerConfig.output_dir` is always `null` from this page (`buildConfig.ts`) — the server
 * names the analysis directory, so there is no field to stamp `smoke-ui-<runid>` into. Cleanup
 * here is a verified before/after directory diff (`_dirDiff.ts`) instead of a naming convention.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const ANALYSES_DIR = join(PROJECT_HOST_ROOT, "derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses");

let app: ElectronApplication;
let page: Page;
let before: Set<string>;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  before = snapshotDir(ANALYSES_DIR);
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "ernie");
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
});

test.afterAll(async () => {
  const removed = removeNewEntriesSince(ANALYSES_DIR, before);
  console.log(`real/analyzer-mesh: cleaned up new Analyses entries: ${JSON.stringify(removed)}`);
  await app?.close();
});

test("spherical target, mesh space: accepted, started, and completed", async () => {
  test.setTimeout(360_000);

  await page.locator("#analyzer-simulation").click();
  await page.getByRole("option", { name: "Thalamus" }).first().click();

  // Mesh is the page's own default (`space` state starts "mesh") — asserted, not re-selected, so
  // this spec fails loudly if that default ever changes instead of silently testing voxel twice.
  await expect(page.getByRole("radiogroup", { name: "Analysis space" }).getByRole("radio", { name: "Mesh", exact: true })).toBeChecked();

  await page.getByLabel("Sphere 1 X").fill("-10");
  await page.getByLabel("Sphere 1 Y").fill("-18");
  await page.getByLabel("Sphere 1 Z").fill("9");
  await page.getByLabel("Sphere 1 radius").fill("10");

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|overwrite)$/);

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  // The output already exists from an earlier real run (this project's own Analyses/ directory
  // carries a prior `smoke-*-mesh` entry at these coordinates) — handle the overwrite confirm if
  // the server reports it as existing, same as every other real spec that can hit it.
  const confirm = page.getByRole("alertdialog").getByRole("button", { name: "Overwrite and run" });
  if (await confirm.isVisible({ timeout: 3_000 }).catch(() => false)) await confirm.click();

  const body = (await jobRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: { space: string; simulation: string } };
  expect(body.kind).toBe("analyzer");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.config.space).toBe("mesh");
  expect(body.config.simulation).toBe("Thalamus");
  recordPayload("analyzer", body);

  const created = (await (await jobResponse).json()) as { id: string };
  await waitForJobTrace(page, "analyzer", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("analyzer", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 300_000 });
  console.log(`real/analyzer-mesh: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);
});
