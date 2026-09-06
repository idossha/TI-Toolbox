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
import { closeOptEditor, openOptEditor, optRowSummary, optRows, setOptCell } from "../_jobs";

/**
 * Optimizer / Ex, against the shared dev container. Fixture matrix row: `sub-ernie`, its existing
 * `EEG10-10_UI_Jurak_2007` leadfield, a small candidate set — started -> cancel.
 *
 * Re-pointed 2026-09-06 (lane OJ) at the jobs table. Two changes worth naming:
 *
 *  * the method, the leadfield, the target and the electrode buckets are all cells or sections of a
 *    job ROW, so the whole configuration happens in that row's editor;
 *  * the submission is `POST /api/jobs/groups` (R3), which this spec still asserted as
 *    `POST /api/jobs` and would have missed.
 *
 * It is also **started -> cancel** now rather than run-to-completion: this container is shared and
 * emulated, an ex search holds a ~3.3 GB leadfield in memory, and what this row is here to prove is
 * the *shape* that reaches the runner and that the runner accepts it. Completion is covered by the
 * container-side pipeline tests, not by a UI spec holding the machine for ten minutes.
 *
 * The ROI picker's Ex/mEx modes are `["saved", "subcortical"]` (no cortical mode — that is
 * Flex-only), and the real project has no saved ROI presets, so this uses Subcortical
 * (`aparc.DKTatlas+aseg.mgz` · Left-Hippocampus).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const RUN_NAME = `smoke-ui-${RUN_ID}-ex`;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Page | Locator = page): Locator {
  return root.locator(".field", { hasText: label }).first();
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
});

test.afterAll(async () => {
  // A cancelled ex search writes no completed run directory; nothing of ours to clean up.
  await app?.close();
});

test("subcortical ROI, bucketed electrodes: accepted, started, cancelled", async () => {
  test.setTimeout(300_000);

  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-subject", "ernie");
  await setOptCell(page, row, "method", "Ex");

  // The Leadfield cell states what ernie actually has — one net, with its size. The page-level
  // strip this replaces could not say whose leadfield it meant once rows named different subjects.
  const netCell = row.locator('td[data-cell="net"]').getByRole("combobox");
  await netCell.click();
  const ready = page.getByRole("option", { name: /EEG10-10_UI_Jurak_2007 · [\d.]+ [MG]B/ });
  await expect(ready).toBeVisible({ timeout: 20_000 });
  console.log(`real/ex: leadfield option = ${await ready.textContent()}`);
  await ready.click();
  await expect(row).toHaveAttribute("data-net", "EEG10-10_UI_Jurak_2007");

  const dialog = await openOptEditor(page, row);
  await field("Run name", dialog).getByRole("textbox").fill(RUN_NAME);

  await dialog.getByRole("radio", { name: "Subcortical", exact: true }).click();
  await field("Volume atlas", dialog).getByRole("button").click();
  await page.getByPlaceholder("Search atlases…").fill("DKTatlas");
  await page.getByRole("option", { name: /DKTatlas/ }).first().click();
  await field("Region(s)", dialog).getByRole("combobox").click();
  await page.getByPlaceholder(/Filter regions…|Search…/).fill("Hippocampus");
  await page.getByRole("option", { name: "Left-Hippocampus", exact: true }).click();
  await page.getByTestId("roi-region-done").click();

  for (const [bucket, electrode] of [
    ["E1+", "Fp1"],
    ["E1-", "Fp2"],
    ["E2+", "F3"],
    ["E2-", "F4"],
  ] as const) {
    await field(bucket, dialog).getByRole("combobox").click();
    // The bucket's own list dialog, named by its heading: "Filter electrodes…" is a *placeholder*,
    // not text content, so `hasText` never matches it.
    const list = page.getByRole("dialog").filter({ hasText: `${bucket} — choose electrodes` });
    await list.getByPlaceholder("Filter electrodes…").fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
    await list.getByRole("button", { name: "Done" }).click();
  }
  await closeOptEditor(page);

  // What the row promises, before anything is queued.
  console.log(`real/ex: row summary = ${await optRowSummary(row).textContent()}`);
  await expect(optRowSummary(row)).toHaveText(/buckets: 4 · 2 mA total/);

  const cell = page.locator('[data-testid^="plan-cell-ernie-"]').first();
  await expect(cell).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  const groupResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs/groups") && r.request().method() === "POST");
  const groupRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs/groups") && r.method() === "POST");
  await page.getByTestId("run-button").click();

  const body = (await groupRequest).postDataJSON() as {
    kind: string;
    subject_ids: string[];
    subject_configs: { subject_id: string; config: { run_name: string; leadfield_hdf: string; roi_atlas: unknown; electrodes: Record<string, unknown> } }[];
  };
  expect(body.kind).toBe("ex");
  expect(body.subject_ids).toEqual(["ernie"]);
  expect(body.subject_configs).toHaveLength(1);
  const config = body.subject_configs[0]!.config;
  expect(config.run_name).toBe(RUN_NAME);
  // The per-subject fact the row now owns: the leadfield path is ernie's own.
  expect(config.leadfield_hdf).toContain("sub-ernie");
  expect(config.electrodes).toMatchObject({
    _type: "BucketElectrodes",
    e1_plus: ["Fp1"],
    e1_minus: ["Fp2"],
    e2_plus: ["F3"],
    e2_minus: ["F4"],
  });
  recordPayload("ex", body);

  const group = (await (await groupResponse).json()) as { group_id: string; jobs: { id: string }[] };
  const jobId = group.jobs[0]!.id;
  const job = await waitForJobRunningOrTerminal(page, { url: SERVER_URL, token: TOKEN, jobId, timeoutMs: 180_000 });
  console.log(`real/ex: job ${jobId} state=${job.state} run=${RUN_ID}`);
  expect(job.state, `ex did not reach running: ${JSON.stringify(job.error?.last_lines?.slice(-3) ?? [])}`).toBe("running");

  await expect(page.getByTestId("job-terminal").getByTestId("job-terminal-identity")).toContainText("ex", { timeout: 60_000 });
  await cancelJobFromRail(page, "ex", { timeoutMs: 60_000 });
});

/**
 * The subject grammar (J3) inside the row, on real data: every project subject is listed, and one
 * that cannot run THIS row is listed **with its reason** and cannot be picked.
 *
 * Deliberately no second job is submitted: two ex runs would hold two ~3.3 GB leadfields in memory
 * at once on this shared emulated container. The multi-row submission path is measured in
 * `tests/unit/optimizer-subjects.test.ts` and end-to-end in the mock `tests/e2e/optimizer.spec.ts`.
 */
test("the row's Subject picker lists every subject, and refuses one with no leadfield by name", async () => {
  const row = optRows(page).first();
  await expect(row).toHaveAttribute("data-method", "ex");

  await row.locator('td[data-cell="subject"]').getByRole("combobox").click();
  const picker = page.getByRole("dialog");
  // Dataset 000 lists five subjects (101, 102, ernie, MNI152, test) — a subject that cannot run is
  // explained, never hidden.
  const options = picker.getByRole("option");
  await expect(options).toHaveCount(5);
  const rendered = await options.allTextContents();
  console.log(`real/ex: subject options = ${JSON.stringify(rendered)}`);
  // At least one of them has no leadfield on this project, and says so rather than failing later.
  expect(rendered.some((t) => /no leadfield — create one first|no head model/.test(t))).toBe(true);
  await picker.getByRole("button", { name: "Done", exact: true }).click();
});
