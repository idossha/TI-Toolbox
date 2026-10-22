import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Locator, type Page, type Request } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addOptRow, clearOptRows, closeOptEditor, openOptEditor, setOptCell, setOptSubject } from "./_jobs";

/**
 * Optimizer — Ex/mEx edge flows against the mock server (package p38, 2026-10-22).
 *
 * The expected counts are cases of `tests/fixtures/ex_search_counts.json`, the brute-force table
 * `dev/gen_ex_counts.py` writes (no `tit` import); the mock's `/api/plan/{ex,mex}` is held to the
 * same table by `tests/mock-server/plan-output-dirs.test.ts`. A count is invariant under renaming
 * electrodes, so the fixture's labels (A..D, F3..C4) are mapped one-to-one onto the mock net's
 * E1..E4.
 *   1. Step 0.05 with the Channel limit cleared: the cost line states the fixture's counts and the
 *      submitted config keeps current_step 0.05 and no limit.
 *   2. A channel limit below total / 2 leaves no current split: Run is disabled by a sentence that
 *      names the job, and the line says 0 iterations.
 *   3. mEx with all eight buckets holding the same four electrodes: 0 combinations, Run disabled.
 *   5. Switching the net after filling the buckets: an electrode the new net does not have is
 *      either dropped or named in the disabled sentence -- never submitted.
 * Flow 4 (distinct run folders for uncombined ROIs) is package p19's.
 *
 * Offscreen (`TIT_E2E_OFFSCREEN=1`); asserts DOM state and request bodies, never pixels.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

interface CountCase {
  id: string;
  kind: "ex" | "mex";
  buckets: Record<string, string[]>;
  total_current?: number;
  current_step?: number;
  channel_limit?: number | null;
  splits?: number[][];
  expected_montages: number;
  expected_combinations: number;
}
const COUNTS = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "tests", "fixtures", "ex_search_counts.json"), "utf8")) as { cases: CountCase[] };
const countCase = (id: string): CountCase => COUNTS.cases.find((c) => c.id === id)!;
const BUCKET_LABEL: Record<string, string> = {
  e1_plus: "E1+", e1_minus: "E1-", e2_plus: "E2+", e2_minus: "E2-",
  e3_plus: "E3+", e3_minus: "E3-", e4_plus: "E4+", e4_minus: "E4-",
};

/** The case's distinct labels, renamed onto the mock net in first-seen order. */
function renamer(c: CountCase): (label: string) => string {
  const order: string[] = [];
  for (const labels of Object.values(c.buckets)) for (const l of labels) if (!order.includes(l)) order.push(l);
  return (label) => `E${order.indexOf(label) + 1}`;
}
const n = (v: number) => v.toLocaleString("en-US");

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

function field(label: string, root: Locator): Locator {
  return root.locator(".field", { hasText: label }).first();
}

async function fillBucket(dialog: Locator, bucket: string, electrodes: string[]): Promise<void> {
  await field(bucket, dialog).getByRole("combobox").click();
  const list = page.getByRole("dialog").filter({ hasText: `${bucket} — choose electrodes` });
  for (const electrode of electrodes) {
    await list.getByPlaceholder("Filter electrodes…").fill(electrode);
    await list.getByRole("option", { name: electrode, exact: true }).click();
  }
  await list.getByRole("button", { name: "Done" }).click();
}

async function fillCase(dialog: Locator, c: CountCase): Promise<void> {
  const rename = renamer(c);
  for (const [key, labels] of Object.entries(c.buckets)) await fillBucket(dialog, BUCKET_LABEL[key]!, labels.map(rename));
}

async function setNumber(dialog: Locator, index: number, value: string): Promise<void> {
  const input = dialog.locator(".optimizer-current-row").getByRole("spinbutton").nth(index);
  await input.fill(value);
  await input.press("Tab");
}

async function pickSavedTarget(dialog: Locator, name: string): Promise<void> {
  const saved = dialog.locator(".roi-picker .segmented").first().getByRole("radio", { name: "Saved", exact: true });
  if (!(await saved.isChecked())) await saved.click();
  await dialog.getByText(name, { exact: true }).locator("xpath=ancestor::label[1]").getByRole("checkbox").click();
}

async function freshExRow(): Promise<Locator> {
  await clearOptRows(page);
  const row = await addOptRow(page);
  await setOptSubject(page, row, "ernie");
  await setOptCell(page, row, "method", "Ex");
  await expect(row).toHaveAttribute("data-net", "GSN-HydroCel-185");
  return row;
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-exedges-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "optimizer", "Optimizer");
  await expectPage(page, "optimizer");
});

test.afterAll(async () => {
  await app?.close();
});

test("step 0.05 with no channel limit: the line states the runner's count and the config keeps the step", async () => {
  const c = countCase("bucket_shared_poles");
  expect(c.current_step).toBe(0.05);
  expect(c.channel_limit).toBeNull();
  const row = await freshExRow();
  const dialog = await openOptEditor(page, row);
  await pickSavedTarget(dialog, "Thalamus_target");
  await fillCase(dialog, c);
  await setNumber(dialog, 1, String(c.current_step));
  await setNumber(dialog, 2, "");
  const distinct = new Set(Object.values(c.buckets).flat()).size;
  await expect(dialog.getByTestId("optimizer-cost-ex")).toHaveText(
    `${distinct} electrodes · ${n(c.expected_montages)} montages · ${n(c.splits!.length)} current splits · ${n(c.expected_combinations)} iterations`,
  );
  await closeOptEditor(page);

  const bodies: Record<string, unknown>[] = [];
  const collect = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) bodies.push(r.postDataJSON() as Record<string, unknown>);
  };
  page.on("request", collect);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15_000 });
  await page.getByTestId("run-button").click();
  const replace = page.getByTestId("existing-outputs-replace");
  if (await replace.isVisible().catch(() => false)) await replace.click();
  await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);
  page.off("request", collect);
  const body = bodies[0] as { kind: string; subject_configs: { config: { current_step: number; channel_limit?: number | null; total_current: number } }[] };
  expect(body.kind).toBe("ex");
  const config = body.subject_configs[0]!.config;
  expect(config.current_step).toBe(c.current_step);
  expect(config.channel_limit ?? null).toBeNull();
  expect(config.total_current).toBe(c.total_current);
});

test("a channel limit below half the total leaves no split: Run is disabled by a sentence naming the job", async () => {
  const c = countCase("bucket_limit_below_half");
  expect(c.expected_combinations).toBe(0);
  const row = await freshExRow();
  const dialog = await openOptEditor(page, row);
  await pickSavedTarget(dialog, "Thalamus_target");
  await fillCase(dialog, c);
  await setNumber(dialog, 1, String(c.current_step));
  await setNumber(dialog, 2, String(c.channel_limit));
  await expect(dialog.getByTestId("optimizer-cost-ex")).toContainText(`${n(c.splits!.length)} current splits · ${n(c.expected_combinations)} iterations`);
  await closeOptEditor(page);
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /Job 1: No current split fits/);
});

test("mEx with the same four electrodes in all eight buckets: 0 combinations and Run disabled", async () => {
  const c = countCase("mex_same_four");
  expect(c.expected_combinations).toBe(0);
  const row = await freshExRow();
  let dialog = await openOptEditor(page, row);
  await field("Count", dialog).getByRole("radio", { name: "8 electrodes (mTI)", exact: true }).click();
  await closeOptEditor(page);
  await expect(row).toHaveAttribute("data-kind", "mex");
  dialog = await openOptEditor(page, row);
  await pickSavedTarget(dialog, "Thalamus_target");
  await fillCase(dialog, c);
  const distinct = new Set(Object.values(c.buckets).flat()).size;
  await expect(dialog.getByTestId("optimizer-cost-mex")).toHaveText(new RegExp(`^${distinct} electrodes · 4 pairs · ${n(c.expected_combinations)} combinations`));
  await closeOptEditor(page);
  await expect(page.getByTestId("run-button")).toBeDisabled();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /Job 1: No montage has eight different electrodes/);
});

test("switching the net drops or names an electrode the new net does not have", async () => {
  // KNOWN BUG (found by this spec, 2026-10-22; the fix belongs to the Optimizer page, outside
  // package p38): after the switch E1+ still holds E200, Run is ENABLED with no title, and the job
  // would be submitted with an electrode the GSN-HydroCel-185 leadfield does not have.
  // `test.fail` keeps the flow in the suite and turns red the day the page drops or names it --
  // then delete this line.
  test.fail(true, "Optimizer keeps an electrode the new net lacks and lets the job run");
  // The mock's EGI_template has E1..E256 and GSN-HydroCel-185 E1..E185 (server.mjs NET_SIZES).
  const row = await freshExRow();
  await setOptCell(page, row, "net", "EGI_template — no leadfield");
  await expect(row).toHaveAttribute("data-net", "EGI_template");
  const dialog = await openOptEditor(page, row);
  await pickSavedTarget(dialog, "Thalamus_target");
  await fillBucket(dialog, "E1+", ["E200"]);
  await fillBucket(dialog, "E1-", ["E2"]);
  await fillBucket(dialog, "E2+", ["E3"]);
  await fillBucket(dialog, "E2-", ["E4"]);
  await closeOptEditor(page);
  await setOptCell(page, row, "net", "GSN-HydroCel-185 · 2.0 GB");
  await expect(row).toHaveAttribute("data-net", "GSN-HydroCel-185");

  const again = await openOptEditor(page, row);
  const kept = (await field("E1+", again).getByRole("combobox").innerText()).trim();
  await closeOptEditor(page);
  const run = page.getByTestId("run-button");
  if (kept.includes("E200")) {
    // Kept on screen, so the page must refuse to run it, and say which electrode and which job.
    await expect(run).toBeDisabled();
    await expect(run).toHaveAttribute("title", /Job 1: .*E200/);
  } else {
    // Dropped: the bucket is then empty, which the row gate already refuses by name.
    await expect(run).toBeDisabled();
    await expect(run).toHaveAttribute("title", /Job 1: Fill in every electrode bucket\./);
  }
});
