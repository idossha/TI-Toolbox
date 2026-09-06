import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { cancelJobFromRail, cleanupSmokeOutputs, connectReal, expectPage, gotoPage, launchElectronApp, recordPayload, selectSubject, waitForJobTrace } from "../_helpers";
import { createAndSelectMontage, deleteMontage } from "./_simMontage";

/**
 * Simulator, standard TI (2-pair uni-polar montage), against the shared dev container. `sim` is a
 * program §3 "long kind" (started -> cancel, DESIGN.md/plan §3 P4): the maintainer's own earlier
 * run of this exact (subject, net) pair took 16 minutes under emulation, so this spec proves the
 * submit is accepted and the runner actually starts, then cancels rather than waiting it out —
 * completion is `--full`/S1's job.
 *
 * Subject and net match the fixture matrix's "sim (TI)" row: `sub-101`, `BioSemi-128-A1.csv` — the
 * maintainer's own succeeded config (`dev/notes/v3-pipelines-program.md` §0).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const MONTAGE_NAME = `smoke-ui-${RUN_ID}-ti`;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "101");
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  // Teardown even if the test body threw partway through, so a failed assertion never leaves the
  // montage (or a partially-written Simulations/ dir) behind for the next run.
  await deleteMontage(page, MONTAGE_NAME).catch(() => undefined);
  cleanupSmokeOutputs([`derivatives/SimNIBS/sub-101/Simulations/${MONTAGE_NAME}`]);
  await app?.close();
});

test("TI montage: accepted, started, and cancelled cleanly", async () => {
  test.setTimeout(180_000);

  await createAndSelectMontage(page, {
    net: "BioSemi-128-A1.csv",
    name: MONTAGE_NAME,
    pairs: [
      ["A1", "A2"],
      ["B1", "B2"],
    ],
  });

  const cell = page.getByTestId(`plan-cell-101-${MONTAGE_NAME}`);
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^(new|overwrite)$/);
  await expect(page.getByTestId("run-button")).toHaveText("Run simulation");

  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();
  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    config: { montages: { name: string; mode: string; electrode_pairs: [string, string][] }[] };
  };
  expect(body.kind).toBe("sim");
  expect(body.subject_ids).toEqual(["101"]);
  expect(body.config.montages).toHaveLength(1);
  expect(body.config.montages[0]?.name).toBe(MONTAGE_NAME);
  expect(body.config.montages[0]?.electrode_pairs).toHaveLength(2);
  recordPayload("sim", body);

  // Jobs rail + in-page terminal within the 120 s "started" budget (P4).
  await waitForJobTrace(page, "sim", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("sim", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  await cancelJobFromRail(page, "sim", { timeoutMs: 30_000 });

  console.log(`real/sim (TI): subject=101 montage=${MONTAGE_NAME} outcome=cancelled run=${RUN_ID}`);
});
