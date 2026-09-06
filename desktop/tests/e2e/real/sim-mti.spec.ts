import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { cancelJobFromRail, cleanupSmokeOutputs, connectReal, expectPage, gotoPage, launchElectronApp, recordPayload, selectSubject, waitForJobTrace } from "../_helpers";
import { createAndSelectMontage, deleteMontage } from "./_simMontage";

/**
 * Simulator, multi-channel mTI (4-pair multi-polar montage) — see `sim.spec.ts`'s file header for
 * the shared rationale (long kind, started -> cancel). There is no separate "mTI" control in the
 * UI: `Montage.simulation_mode` is derived server-side from the pair count (`MontageManager.tsx`'s
 * `isValidPairCount`: exactly 2 = TI, 4+ = mTI), so this spec's only difference from `sim.spec.ts`
 * is the montage it creates.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const SUBJECT = "101";
const MONTAGE_NAME = `smoke-ui-${RUN_ID}-mti`;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, SUBJECT);
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await deleteMontage(page, MONTAGE_NAME).catch(() => undefined);
  cleanupSmokeOutputs([`derivatives/SimNIBS/sub-101/Simulations/${MONTAGE_NAME}`]);
  await app?.close();
});

test("mTI montage: accepted, started, and cancelled cleanly", async () => {
  test.setTimeout(180_000);

  await createAndSelectMontage(page, {
    subject: SUBJECT,
    net: "BioSemi-128-A1.csv",
    name: MONTAGE_NAME,
    pairs: [
      ["A1", "A2"],
      ["B1", "B2"],
      ["C1", "C2"],
      ["D1", "D2"],
    ],
  });

  // The Simulator's plan grid has one column per montage *source* ("montage"/"flex"/"freehand"),
  // not one per simulation name — see `RunControls.tsx`'s `stageFor: sourceOfJob`.
  const cell = page.getByTestId("plan-cell-101-montage");
  await expect(cell).toBeVisible({ timeout: 15_000 });
  await expect(cell).toHaveText(/^1 (new|overwrite)$/);

  // Every run page submits its whole batch as ONE `POST /api/jobs/groups` (R3) — never a loop of
  // per-job `POST /api/jobs`. The per-subject config lives in `subject_configs`.
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await page.getByTestId("run-button").click();
  type SimConfig = { subject_id: string; montages: { name: string; mode: string; electrode_pairs: [string, string][] }[] };
  const body = (await jobRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    config: SimConfig;
    subject_configs?: { subject_id: string; config: SimConfig }[];
  };
  expect(body.kind).toBe("sim");
  expect(body.subject_ids).toEqual(["101"]);
  const configs = body.subject_configs?.length ? body.subject_configs.map((e) => e.config) : [body.config];
  expect(configs).toHaveLength(1);
  const config = configs[0]!;
  expect(config.subject_id).toBe("101");
  expect(config.montages[0]?.name).toBe(MONTAGE_NAME);
  expect(config.montages[0]?.electrode_pairs).toHaveLength(4);
  recordPayload("sim-mti", { kind: body.kind, subject_ids: body.subject_ids, config });

  await waitForJobTrace(page, "sim", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("sim", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  await cancelJobFromRail(page, "sim", { timeoutMs: 30_000 });

  console.log(`real/sim (mTI): subject=101 montage=${MONTAGE_NAME} outcome=cancelled run=${RUN_ID}`);
});
