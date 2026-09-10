/**
 * Results — the group-statistics pane and the analyzer pane, against the shared dev container and
 * Dataset 000's real outputs.
 *
 * The maintainer's third note was *"please make sure that we actually run an end-to-end on the
 * group analysis to make sure we produce good results and not just the .log file"*. Every earlier
 * `smoke-ui-*` run on this project had left exactly one 1.5 kB log:
 * `tit.stats.engine.ttest_ind` built the pooled variance as `(n - 1) * np.var(x, ddof=1)`, which
 * for the lone Non-Responder is `0 * nan`, so every one of the 1 383 362 voxels came back `nan`,
 * was excluded as "zero within-group variance", and `ttest_voxelwise` raised on an empty mask
 * before a single map was written. Fixed at the source; this spec runs the design and refuses to
 * pass on a directory that holds only a log.
 *
 * What it does NOT assert is a significant cluster. Three subjects give the permutation null three
 * distinct relabellings, so the smallest cluster p reachable is 1/3 — no cluster can clear
 * alpha = 0.05 at this N, and a run that reported one would be the bug. "Real results" here means
 * the maps, the plots and the summary, with an honest zero in the significance column.
 *
 * Bounded on purpose: `n_permutations: 100` on 2 cores is ~20 s of the ~25 s run.
 */
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import {
  cleanupSmokeOutputs,
  connectReal,
  expectPage,
  gotoPage,
  launchElectronApp,
  PROJECT_HOST_ROOT,
  waitForJobTerminal,
} from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const ANALYSIS_NAME = `smoke-results-${RUN_ID}`;
const OUT_REL = `derivatives/ti-toolbox/stats/group_comparison/${ANALYSIS_NAME}`;

/** The maps, plots and summaries a completed MNI group comparison writes (`tit/stats/permutation.py`). */
const EXPECTED_OUTPUTS = [
  "average_responders.nii.gz",
  "average_non_responders.nii.gz",
  "difference_map.nii.gz",
  "pvalues_map.nii.gz",
  "significant_voxels_mask.nii.gz",
  "permutation_null_distribution.pdf",
  "cluster_size_mass_correlation.pdf",
  "analysis_summary.txt",
  "permutation_details.txt",
];

let app: ElectronApplication;
let page: Page;
let cleanupPath: string | null = null;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  // The run is ~90 MB of MNI-grid volumes; it is reproducible in 25 s and is not kept as a fixture.
  if (cleanupPath) cleanupSmokeOutputs([cleanupPath]);
  await app?.close();
});

async function api(path: string, init?: RequestInit): Promise<Response> {
  return fetch(new URL(path, SERVER_URL).href, {
    ...init,
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json", ...init?.headers },
  });
}

test("a 2-vs-1 group comparison writes real maps, plots and a summary — not just a log", async () => {
  test.setTimeout(300_000);

  const submitted = await api("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      kind: "stats",
      subject_ids: ["101", "ernie", "MNI152"],
      config: {
        analysis_name: ANALYSIS_NAME,
        subjects: [
          { subject_id: "101", simulation_name: "L_Insula", response: 1 },
          { subject_id: "MNI152", simulation_name: "L_Insula", response: 1 },
          { subject_id: "ernie", simulation_name: "L_Insula", response: 0 },
        ],
        test_type: "unpaired",
        alternative: "two-sided",
        cluster_threshold: 0.05,
        cluster_stat: "mass",
        n_permutations: 100,
        alpha: 0.05,
        n_jobs: 2,
        tissue_type: "grey",
        nifti_file_pattern: null,
        space: "mni",
        fsaverage_field: "TI_max",
        fsaverage_spacing: 5,
        atlas_files: [],
        group1_name: "Responders",
        group2_name: "Non-Responders",
        value_metric: "Current intensity",
      },
    }),
  });
  expect(submitted.ok, `POST /api/jobs -> ${submitted.status}`).toBe(true);
  const created = (await submitted.json()) as { id: string };
  cleanupPath = OUT_REL;

  const finalJob = await waitForJobTerminal(page, {
    url: SERVER_URL,
    token: TOKEN,
    jobId: created.id,
    timeoutMs: 240_000,
  });
  expect(finalJob.state, `job error: ${JSON.stringify(finalJob.error)}`).toBe("succeeded");

  // On disk: every map, both plots, both text reports — and more than the log.
  const files = readdirSync(join(PROJECT_HOST_ROOT, OUT_REL));
  console.log(`real/results-group: ${files.length} files: ${files.join(", ")}`);
  for (const name of EXPECTED_OUTPUTS) expect(files, `${name} written`).toContain(name);
  expect(files.filter((f) => !f.endsWith(".log")).length).toBeGreaterThan(1);

  // And through the endpoint the Results pane reads: a complete run, its inputs and its outcome.
  const detail = (await (await api(`/api/catalog/group/stats/${ANALYSIS_NAME}?type=group_comparison`)).json()) as {
    status: string;
    reason: string | null;
    groups: { name: string; n: number; subjects: string[] }[];
    results: { label: string; value: string }[];
    artifacts: { kind: string }[];
  };
  expect(detail.status).toBe("ok");
  expect(detail.reason).toBeNull();
  expect(detail.groups.map((g) => g.n)).toEqual([2, 1]);
  const results = Object.fromEntries(detail.results.map((r) => [r.label, r.value]));
  // A real test happened: voxels were testable and some of them cleared the uncorrected threshold.
  expect(Number(results["Testable voxels"])).toBeGreaterThan(1_000_000);
  expect(Number(results["Voxels at p < 0.05"])).toBeGreaterThan(0);
  // And the honest zero: three subjects cannot produce a cluster p below 1/3.
  expect(results["Significant clusters"]).toBe("0");
  expect(detail.artifacts.some((a) => a.kind === "pdf")).toBe(true);
});

test("the Results pane renders that run's inputs, numbers, clusters and files", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "results", "Results");
  await expectPage(page, "results");
  // The subject list re-renders as each subject's catalog lands, so the `Group` row can be
  // detached mid-click on a real project; wait for the last subject's own count first.
  await expect(page.getByTestId("results-subject-Group")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("results-subject-MNI152").locator(".results-subject-count")).toBeVisible({
    timeout: 30_000,
  });
  await page.getByTestId("results-subject-Group").click();
  const node = page.getByTestId(`results-node-analysis:Group:stats/${ANALYSIS_NAME}`);
  await expect(node).toBeVisible({ timeout: 30_000 });
  await node.click();

  const header = page.getByTestId("results-header-block");
  await expect(header).toContainText("group comparison");
  await expect(header).toContainText("101, MNI152");
  await expect(header).toContainText("ernie");
  await expect(header).toContainText("(182, 218, 182)");

  const numbers = page.getByTestId("results-key-numbers");
  await expect(numbers).toContainText("Significant clusters");
  await expect(numbers).toContainText("Testable voxels");
  await expect(numbers).toContainText("100"); // permutations

  // Its two PDF plots are figures, drawn as bitmaps — no PDF viewer chrome anywhere.
  const figures = page.getByTestId("results-figures");
  await expect(figures.locator("button")).toHaveCount(2);
  await expect(page.locator('[data-testid="results-preview"] embed')).toHaveCount(0);
  await expect(page.getByTestId("results-pdf-page").first()).toHaveAttribute("data-state", "ready", {
    timeout: 30_000,
  });

  // Its maps and text reports, each with exactly one action.
  const files = page.getByTestId("results-files");
  await expect(files).toContainText("p-value map (−log10 p)");
  await expect(files).toContainText("Analysis summary");
  await expect(files.getByRole("button", { name: /^(View|Open)$/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open externally" })).toHaveCount(0);
});

test("an existing Thalamus analysis reads as key numbers, not a 22-row metric dump", async () => {
  test.setTimeout(120_000);
  await gotoPage(page, "results", "Results");
  await expect(page.getByTestId("results-subject-ernie").locator(".results-subject-count")).toBeVisible({
    timeout: 30_000,
  });
  await page.getByTestId("results-subject-ernie").click();
  const node = page
    .getByTestId("results-tree")
    .locator('[data-testid^="results-node-analysis:ernie:Thalamus/"]')
    .first();
  await expect(node).toBeVisible({ timeout: 30_000 });
  await node.click();

  const header = page.getByTestId("results-header-block");
  await expect(header).toContainText("ernie");
  await expect(header).toContainText("Thalamus");
  await expect(header).toContainText("TI_max");

  const numbers = page.getByTestId("results-key-numbers");
  await expect(numbers).toContainText("V/m");
  // SCI-03: the focality group names its own unit, and it is not the same one in both spaces.
  await expect(numbers).toContainText(/Focality extent · cm[²³]/);
  // No sixteen-digit float survives anywhere in the pane.
  const text = (await page.getByTestId("results-preview").innerText()).replace(/\s+/g, " ");
  expect(text).not.toMatch(/\d\.\d{8,}/);
});
