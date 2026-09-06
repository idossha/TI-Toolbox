import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page } from "@playwright/test";
import { cleanupSmokeOutputs, connectReal, expectPage, gotoPage, launchElectronApp, recordPayload, selectSubject, waitForJobTerminal, waitForJobTrace } from "../_helpers";
import { closeSubjects, expectSubjectsGrammar, setSubjectChecked, subjectsSummary } from "../_subjects";

/**
 * Optimizer / Ex, against the shared dev container. `ex` is not one of program §3 P4's "long
 * kinds" (sim, flex, leadfield, charm, fastsurfer, qsiprep/qsirecon, blender) so this spec runs it
 * to completion within its 600 s budget (fixture matrix), rather than started -> cancel.
 *
 * Fixture matrix row: `sub-ernie`, existing `EEG10-10_UI_Jurak_2007` leadfield, small candidate
 * set. The ROI picker's Ex/mEx modes are `["saved", "subcortical"]` (no cortical mode — that is
 * Flex-only), and the real project has no pre-existing "saved" ROI presets, so this uses
 * Subcortical (`aparc.DKTatlas+aseg.mgz` · Left-Hippocampus) rather than the mock's "saved" fixture
 * targets, which do not exist on this project.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const RUN_NAME = `smoke-ui-${RUN_ID}-ex`;

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
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "Ex", exact: true }).click();
});

test.afterAll(async () => {
  cleanupSmokeOutputs([`derivatives/SimNIBS/sub-ernie/ex-search/${RUN_NAME}`]);
  await app?.close();
});

test("subcortical ROI, bucketed electrodes: accepted, started, and completed", async () => {
  test.setTimeout(700_000);

  // The leadfield strip auto-selects `EEG10-10_UI_Jurak_2007` (the one net ernie already has a
  // leadfield for), so this run never needs "Generate (≈40 min)".
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

  for (const [bucket, electrode] of [
    ["E1+", "Fp1"],
    ["E1-", "Fp2"],
    ["E2+", "F3"],
    ["E2-", "F4"],
  ] as const) {
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
  expect(requestBody.kind).toBe("ex");
  expect(requestBody.config.electrodes).toMatchObject({
    _type: "BucketElectrodes",
    e1_plus: ["Fp1"],
    e1_minus: ["Fp2"],
    e2_plus: ["F3"],
    e2_minus: ["F4"],
  });
  recordPayload("ex", requestBody);

  const created = (await (await jobResponse).json()) as { id: string };
  await waitForJobTrace(page, "ex", { timeoutMs: 120_000 });
  const identity = page.getByTestId("job-terminal").getByTestId("job-terminal-identity");
  await expect(identity).toContainText("ex", { timeout: 120_000 });
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 600_000 });
  console.log(`real/ex: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);

  // Results lists the run under ernie's ex/mEx tree (results.spec.ts's own node-id convention:
  // "ex:<subject>:<run>").
  //
  // The reload is load-bearing, not defensive: the Results tree reads the catalog through
  // react-query with a 60 s `staleTime` (`src/renderer/main.tsx`) and NOTHING invalidates those
  // queries when a job finishes — the page has no refresh control either. Measured on this very
  // run: `GET /api/catalog/ex-runs?subject=ernie&kind=ex` was served at 01:10:18, the job finished
  // at 01:11:00, and the page rendered the 01:10:18 answer for the whole 20 s assertion without
  // one further request (container access log). A fresh renderer is the only thing that shows a
  // just-finished run inside that minute; reported as an open issue against the Results page.
  await page.reload();
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 30_000 });
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  await page.getByTestId("results-subject-ernie").click();
  await expect(page.getByTestId(`results-node-ex:ernie:${RUN_NAME}`)).toBeVisible({ timeout: 20_000 });
});

/**
 * U16 on real data: the subject set is the page's, and a second subject that this project cannot
 * actually run is named rather than silently dropped.
 *
 * `sub-101` is the honest second subject here — it HAS its own `EEG10-10_UI_Jurak_2007` leadfield
 * (3.4 GB, `GET /api/catalog/leadfields?subject=101`) but NOT the FreeSurfer atlas the target above
 * comes from (`GET /api/catalog/atlases?subject=101&kind=subcortical` returns only SimNIBS's
 * `labeling.nii.gz`). So the plan resolves for both subjects — the server plans one job per id it
 * is given — while only one of them can be built into a real config. Deliberately no second job is
 * submitted here: two ex runs would hold two ~3.3 GB leadfields in memory at once on this shared
 * emulated container. The two-subject *submission* path is measured in `tests/unit/
 * optimizer-subjects.test.ts` and end-to-end in the mock `tests/e2e/optimizer.spec.ts`.
 */
test("a second subject is planned as its own row, and blocks the run by name when it cannot run", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await page.getByRole("radiogroup", { name: "Method" }).getByRole("radio", { name: "Ex", exact: true }).click();

  // The shared subject grammar (J1) on real data: the same control, testids and words as the
  // other three run pages. Dataset 000 lists five subjects (101, 102, ernie, MNI152, test), and
  // the control shows every one of them — a subject that cannot run is explained, never hidden.
  await expectSubjectsGrammar(page, { mode: "per-subject", selected: ["ernie"], rows: 5 });

  // Re-pick the same target as the run above (a fresh renderer after the reload).
  await page.getByTestId("page-work").getByRole("radio", { name: "Subcortical", exact: true }).click();
  await field("Volume atlas").getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DKTatlas");
  await page.getByRole("option", { name: /DKTatlas/ }).first().click();
  await field("Region(s)").getByRole("combobox").click();
  await page.getByPlaceholder("Search…").fill("Hippocampus");
  await page.getByRole("option", { name: "Left-Hippocampus", exact: true }).click();
  await page.keyboard.press("Escape");
  for (const [bucket, electrode] of [
    ["E1+", "Fp1"],
    ["E1-", "Fp2"],
    ["E2+", "F3"],
    ["E2-", "F4"],
  ] as const) {
    await field(bucket).locator(".multi-select").click();
    await page.getByRole("option", { name: electrode, exact: true }).click();
    await page.keyboard.press("Escape");
  }
  await expect(page.locator('[data-testid^="plan-cell-ernie-"]').first()).toBeVisible({ timeout: 20_000 });

  // 101 HAS its own leadfield for this net, so it is tickable — what it does not have is the
  // FreeSurfer atlas this target comes from, which is the row's own reason once it is ticked.
  await setSubjectChecked(page, "101", true);
  await expect(subjectsSummary(page)).toHaveText("2 subjects · ernie, 101 · one job per subject");
  await expect(page.getByTestId("subject-reason-101")).toHaveText("this target does not exist for it");
  await closeSubjects(page);

  // One row per chosen subject, from the page's own set (U16's measured acceptance).
  await expect(page.locator('[data-testid^="plan-cell-101-"]').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-testid^="plan-cell-ernie-"]').first()).toBeVisible();

  // …and the run is blocked: the primary is disabled, its tooltip naming the subject that cannot run.
  await expect(page.getByTestId("run-button")).toBeDisabled({ timeout: 15_000 });
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /101/);
});
