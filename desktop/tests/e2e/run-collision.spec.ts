import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page, type Request } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import {
  addJobRow,
  addOptRow,
  analysisRows,
  clearJobRows,
  clearOptRows,
  closeOptEditor,
  configureMontageJob,
  jobCurrents,
  jobRows,
  openOptEditor,
  optRows,
  setAnalysisCell,
  setAnalysisSphere,
  setJobSubject,
  setOptCell,
  setOptSubject,
} from "./_jobs";

/**
 * Two jobs of one Run press that resolve to one output folder block Run, and the Run button says
 * which folder (p19, 2026-10-22; bugs sim:batch-duplicate-output-dir, desktop-run-pages:
 * batch-output-collision, ex:multi-target-run-name) — on the Simulator, the Analyzer and the
 * Optimizer.
 *
 * The repro: "Duplicate job" copies the montage name, the copy gets other currents, and Run put
 * both into one `POST /api/jobs/groups`; the scheduler ran them one after another into
 * `sub-ernie/Simulations/F3_F4`, so only the second configuration's results remained. The same
 * gesture on an Analyzer row (one simulation, one sphere) or an Ex row (one run name) is two jobs
 * into one analysis or `ex-search/<run>` folder. The folders the tests expect are the server's
 * rules as the mock server mirrors them (`plan.py::_plan_sim`: `pm.simulation(sid, montage.name)`;
 * the analysis folder `<simulation>_sphere_x<x>_y<y>_z<z>_r<r>_<field>`, `server.mjs::
 * analyzerAnalysisName`; `pm.ex_search_run(sid, run_name)`), typed here from those rules, not read
 * from the page. Changing what makes the copy its own job (subject, radius, run name) is two
 * folders, and Run comes back. The Run shortcut is the button's own code path: pressed over a
 * blocked page it says why in a toast, opens no dialog and posts nothing.
 *
 * Run: `cd desktop && npm run pree2e && TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/run-collision.spec.ts` (mock server, offscreen).
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await app?.close();
});

test("a duplicated row with other currents blocks Run, naming the folder both would write", async () => {
  await expect(jobRows(page)).toHaveCount(1, { timeout: 15_000 });
  await clearJobRows(page);
  const first = await addJobRow(page);
  await configureMontageJob(page, first, { subject: "ernie", net: "GSN-HydroCel-185", montage: "F3_F4 · TI" });
  await first.getByRole("button", { name: "Duplicate job 1" }).click();
  await expect(jobRows(page)).toHaveCount(2);
  const copy = jobRows(page).nth(1);
  // The copy is a different simulation (2 mA on channel 1) under the same montage name.
  await jobCurrents(copy).first().fill("2");
  await jobCurrents(copy).first().press("Tab");
  await expect(copy).toHaveAttribute("data-runnable", "true");

  const posted: string[] = [];
  const collect = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) posted.push(r.url());
  };
  page.on("request", collect);
  const run = page.getByTestId("run-button");
  await expect(run).toHaveAttribute("title", /^2 jobs of ernie · F3_F4 both write sub-ernie\/Simulations\/F3_F4;/, { timeout: 20_000 });
  await expect(run).toBeDisabled();
  // The bar's blocked state: no job count that could contradict the refusal (ui/Chrome.tsx).
  await expect(page.locator(".action-bar-digest")).toHaveCount(0);
  // The keyboard shortcut is the button's own code path: it says why and must not submit either.
  await pressRunShortcut();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "2 jobs of ernie · F3_F4 both write sub-ernie/Simulations/F3_F4" })).toBeVisible();
  page.off("request", collect);
  expect(posted).toEqual([]);

  // Two subjects are two folders: Run comes back and counts both jobs.
  await setJobSubject(page, copy, "101");
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator(".action-bar-digest")).toHaveText(/^2 jobs$/, { timeout: 15_000 });
});

const SHORTCUT = process.platform === "darwin" ? "Meta+Enter" : "Control+Enter";
/** The sentence `collisionReason` ends every collision with. */
const TAIL = "; the last to run would replace the others' results. Rename or remove one.";

/** Visited pages stay mounted (hidden) for page memory, so the CURRENT page's Run is the visible one. */
function visibleRun(): Locator {
  return page.locator('[data-testid="run-button"]:visible');
}

/** Presses the Run shortcut with focus on no control: inside a jobs table, Enter (with or without
 *  a modifier) is the table's own "open this row's editor" key, so the press starts from the page. */
async function pressRunShortcut(): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press(SHORTCUT);
}

/** Every job submission (`POST /api/jobs` or `/api/jobs/groups`) made until `stop()`. */
function collectPosts(): { urls: string[]; stop: () => void } {
  const urls: string[] = [];
  const collect = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) urls.push(r.url());
  };
  page.on("request", collect);
  return { urls, stop: () => page.off("request", collect) };
}

test("Analyzer: a duplicated analysis blocks Run and the Run shortcut, naming the folder both would write", async () => {
  await gotoPage(page, "analyzer", "Analyzer");
  await expectPage(page, "analyzer");
  const first = analysisRows(page).first();
  await expect(first).toHaveAttribute("data-subject", "ernie");
  await setAnalysisCell(page, first, "simulation", "Thalamus");
  await setAnalysisSphere(page, first, { x: -10, y: -18, z: 9, radius: 5 });
  const run = visibleRun();
  // One row is one folder: nothing to refuse yet.
  await expect(run).toBeEnabled({ timeout: 20_000 });

  await first.getByRole("button", { name: "Duplicate row 1", exact: true }).click();
  await expect(analysisRows(page)).toHaveCount(2);
  // The real plan's folder (`PathManager.analysis_output_dir`, which the mock ports): a mesh
  // sphere in subject space, the default TI_max field adding no suffix.
  const folder = "sub-ernie/Simulations/Thalamus/Analyses/Mesh/sphere_x-10.00_y-18.00_z9.00_r5.0_subject";
  const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await expect(run).toHaveAttribute("title", new RegExp(`^Job 1 and Job 2 both write ${escape(folder)}${escape(TAIL)}$`), { timeout: 20_000 });
  await expect(run).toBeDisabled();
  await expect(page.locator(".action-bar-digest:visible")).toHaveCount(0);

  // The shortcut does not bypass the block: it says why, asks nothing and queues nothing.
  const posts = collectPosts();
  await pressRunShortcut();
  // A toast prints a long sentence's first 77 characters (`ui/Toast.tsx`), which reach "Analyses/".
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Job 1 and Job 2 both write sub-ernie/Simulations/Thalamus/Analyses/" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  posts.stop();
  expect(posts.urls).toEqual([]);

  // Another radius is another analysis folder: Run comes back and queues both.
  await setAnalysisSphere(page, analysisRows(page).nth(1), { x: -10, y: -18, z: 9, radius: 10 });
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(run).toHaveText("Queue 2 jobs");
});

/** The `.field` whose label matches, inside an open row editor. */
function field(label: string, root: Locator): Locator {
  return root.locator(".field", { hasText: label }).first();
}

test("Optimizer: two Ex searches under one run name block Run, naming the run folder", async () => {
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  await setOptCell(page, row, "method", "Ex");
  // Choosing Ex fills the subject's computed leadfield by itself.
  await expect(row).toHaveAttribute("data-net", "GSN-HydroCel-185");

  const dialog = await openOptEditor(page, row);
  const saved = dialog.locator(".roi-picker .segmented").first().getByRole("radio", { name: "Saved", exact: true });
  if (!(await saved.isChecked())) await saved.click();
  await dialog.getByText("Thalamus_target", { exact: true }).locator("xpath=ancestor::label[1]").getByRole("checkbox").click();
  for (const [bucket, electrode] of [
    ["E1+", "E1"],
    ["E1-", "E2"],
    ["E2+", "E3"],
    ["E2-", "E4"],
  ] as const) {
    await field(bucket, dialog).getByRole("combobox").click();
    const list = page.getByRole("dialog").filter({ hasText: `${bucket} — choose electrodes` });
    await list.getByPlaceholder("Filter electrodes…").fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
    await list.getByRole("button", { name: "Done" }).click();
  }
  await dialog.locator(".optimizer-dialog-meta").getByRole("textbox").fill("shared");
  await closeOptEditor(page);
  const run = visibleRun();
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(run).toHaveText("Run search");

  // The copy is the same search under the same run name: one `ex-search/shared` for two runs.
  await row.locator('td[data-cell="actions"]').getByRole("button", { name: "Duplicate job 1", exact: true }).click();
  await expect(optRows(page)).toHaveCount(2);
  await expect(run).toHaveAttribute("title", `Job 1 and Job 2 both write sub-ernie/ex-search/shared${TAIL}`, { timeout: 20_000 });
  await expect(run).toBeDisabled();

  const posts = collectPosts();
  await pressRunShortcut();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Job 1 and Job 2 both write sub-ernie/ex-search/shared" })).toBeVisible();
  posts.stop();
  expect(posts.urls).toEqual([]);

  // Its own run name is its own folder: Run comes back for both searches.
  const copyEditor = await openOptEditor(page, optRows(page).nth(1));
  await copyEditor.locator(".optimizer-dialog-meta").getByRole("textbox").fill("shared_2");
  await closeOptEditor(page);
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(run).toHaveText("Run 2 searches");
});

test("Optimizer: Run validates every search before it queues any — a refusal of the second names Job 2 and nothing is queued", async () => {
  // The two searches the test above left: one Ex config per row, in `ex-search/shared` and
  // `ex-search/shared_2`, and Run enabled for both.
  const run = visibleRun();
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(run).toHaveText("Run 2 searches");

  // The server refuses only the SECOND search's config. Before p19 the page validated one config
  // per kind (`group[0]`), so this one went to the queue unchecked.
  const validated: (string | null)[] = [];
  const pattern = "**/api/validate/ex";
  await page.route(pattern, async (route) => {
    const config = (route.request().postDataJSON() as { config: { run_name?: string | null } }).config;
    validated.push(config.run_name ?? null);
    await route.fulfill({
      json: config.run_name === "shared_2"
        ? { ok: false, errors: [{ path: "roi_radius", message: "must be greater than 0 (e2e refusal)" }] }
        : { ok: true, errors: [] },
    });
  });
  const posts = collectPosts();
  try {
    await run.click();
    const rejected = page.locator(".callout-danger:visible", { hasText: "The server rejected this configuration" });
    await expect(rejected).toContainText("Job 2 · ex: roi_radius: must be greater than 0 (e2e refusal)", { timeout: 15_000 });
    // Job 1 was valid, so it is not listed — and it was not queued on its own either.
    await expect(rejected).not.toContainText("Job 1");
    expect([...validated].sort()).toEqual(["shared", "shared_2"]);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(posts.urls).toEqual([]);
  } finally {
    posts.stop();
    await page.unroute(pattern);
  }
});
