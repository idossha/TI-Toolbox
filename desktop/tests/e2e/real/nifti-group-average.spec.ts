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
  openJobRawLog,
  smokeDirFromArtifactPath,
  waitForJobTerminal,
  waitForJobTrace,
  getServerPanels,
  setServerPanels,
} from "../_helpers";

/**
 * Panel — NIfTI group averaging, against the shared dev container. Fixture matrix row:
 * `L_Insula` across 101/ernie/MNI152 — every one of the three subjects has an `L_Insula`
 * simulation with an MNI-space `TI_max` NIfTI (verified: `GET /api/catalog/simulations` for all
 * three), which is exactly this row's shape.
 *
 * Rows are addressed through the shared participants grammar (`pages/panels/_participants`,
 * lane FIX-D defect 3): `participant-row-<id>` per row, its Subject and Simulation comboboxes in
 * column order, its Group textbox after them. Before that they were counted positionally against
 * a `.card` with the text "Subjects", which broke the moment the card became a table.
 *
 * The default "NIfTI pattern" (`grey_{simulation_name}_...`) does not match this project's actual
 * filenames (`{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`, no `grey_` prefix — verified against the
 * catalog) — the pattern field is overridden below rather than left at its (mock-fixture-shaped)
 * default.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const OUTPUT_NAME = `smoke-ui-${RUN_ID}`;

let app: ElectronApplication;
let page: Page;

let panelsAsFound: string[] = [];

test.describe.configure({ mode: "serial" });

/** One participant row, by index in the table. */
function participantRow(index: number) {
  return page.getByTestId("participants-field").locator("[data-testid^='participant-row-']").nth(index);
}

async function fillRow(index: number, subject: string, simulation: string, group: string): Promise<void> {
  const row = participantRow(index);
  await row.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: subject, exact: true }).click();
  await row.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: simulation, exact: true }).click();
  await row.getByRole("textbox").fill(group);
}

test.beforeAll(async () => {
  // This panel is off in this project's `settings.panels`, and the nav entry is gated on the
  // server's list, not the localStorage mirror — so the link is never rendered until the server
  // says the panel is on. Set it before the app boots, and put the list back in `afterAll`.
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("nifti-group-average")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "nifti-group-average"]);
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await page.getByRole("link", { name: "NIfTI group averaging", exact: true }).click();
  await expectPage(page, "panel-nifti-group-average");
});

/** The real output directory, discovered from the finished job's own artifacts rather than a
 *  guessed convention (this page reports no output path anywhere in its request body). */
let cleanupPath: string | null = null;

test.afterAll(async () => {
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound);
  if (cleanupPath) cleanupSmokeOutputs([cleanupPath]);
  await app?.close();
});

test("average L_Insula across 101/ernie/MNI152: accepted, started, and completed", async () => {
  test.setTimeout(360_000);

  await page.getByTestId("participants-add").click(); // 2 rows -> 3

  await fillRow(0, "101", "L_Insula", "Group1");
  await fillRow(1, "ernie", "L_Insula", "Group1");
  await fillRow(2, "MNI152", "L_Insula", "Group1");

  // The grammar's own contract: every row is runnable, and the summary says what will run (J4).
  await expect(page.getByTestId("participants-field")).toHaveAttribute("data-subjects", "3");
  await expect(page.getByTestId("participants-summary")).toHaveText(
    "3 subjects · 101, ernie, MNI152 · one job over all subjects",
  );

  await page.getByLabel("Analysis name").fill(OUTPUT_NAME);
  await page.getByLabel("NIfTI pattern").fill("{simulation_name}_TI_MNI_MNI_TI_max.nii.gz");

  await expect(page.getByText("Enter an analysis name.")).toHaveCount(0);
  await expect(page.getByText(/Add at least 2 subjects/)).toHaveCount(0);
  // L3: the action bar carries the digest of what will run, not a disabled button with no reason.
  await expect(page.locator(".action-bar-digest")).toHaveText(/^1 job · \d+ CPU · \d+ GB$/);

  const jobResponse = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  const jobRequest = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await page.getByTestId("run-button").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Run analysis" }).click();

  const body = (await jobRequest).postDataJSON() as { kind: string; subject_ids: string[]; config: { output_name: string; subjects: unknown[] } };
  expect(body.kind).toBe("nifti_average");
  expect(new Set(body.subject_ids)).toEqual(new Set(["101", "ernie", "MNI152"]));
  expect(body.config.output_name).toBe(OUTPUT_NAME);
  expect(body.config.subjects).toHaveLength(3);
  recordPayload("nifti_average", body);

  const created = (await (await jobResponse).json()) as { id: string };
  // Click the trace (not just wait for it): the detail pane's Raw log renders the *selected*
  // job's log — the pane's `job` prop is `undefined` (empty state, no `.job-console-line` ever)
  // until something calls `select(job.id)`, which only the trace's own `onClick` does.
  const trace = await waitForJobTrace(page, "nifti_average", { timeoutMs: 120_000 });
  await trace.click();
  await openJobRawLog(page);
  await expect(page.locator(".job-console-line").first()).toBeVisible({ timeout: 120_000 });

  const finalJob = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: created.id, timeoutMs: 300_000 });
  console.log(`real/nifti-group-average: job ${created.id} state=${finalJob.state} artifacts=${finalJob.artifacts?.length ?? 0} run=${RUN_ID}`);
  expect(finalJob.state, JSON.stringify(finalJob.error)).toBe("succeeded");
  expect(finalJob.artifacts?.length ?? 0).toBeGreaterThan(0);
  cleanupPath = smokeDirFromArtifactPath(finalJob.artifacts?.[0]?.path ?? "", OUTPUT_NAME);
});
