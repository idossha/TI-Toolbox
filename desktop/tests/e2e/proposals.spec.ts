import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

// An agent's plan (ARCHITECTURE §6) as the user meets it in the BUILT app against the mock server:
// it arrives over /ws/jobs while the app is open, the nav's Jobs row counts it, the Jobs page shows
// it as a card with its replaced output in a danger callout, Approve queues its root step as an
// `agent` job (badged in the table), and Settings carries the "submit without approval" switch.
// A two-step plan runs to done (the mock queues the dependent step when the first succeeds, as
// `tit.server.proposals._advance`); the inline editor fits at 1024 px; "Open in form" edits a step
// on its run page (Optimizer, Simulator, Pre-processing) and "Save to plan" writes it back; the
// Overview announces a waiting plan. The plan is posted straight to the mock's REST API, as the
// agent plugin would. Screenshots land in TIT_E2E_SHOTS (default TIT_E2E_ARTIFACTS).
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");
const FLEX_DIR = "/mnt/example/derivatives/SimNIBS/sub-ernie/flex-search/thalamus_mean";

let app: ElectronApplication;
let page: Page;

test.beforeAll(() => mkdirSync(ARTIFACTS, { recursive: true }));
test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
});
test.afterEach(async () => {
  await app?.close();
});

const auth = { Authorization: `Bearer ${TOKEN}` };
const OUT = process.env.TIT_E2E_SHOTS ?? ARTIFACTS;

/** The agent's two-step plan; *fresh* drops the existing output (and makes the mock's jobs fast). */
async function propose(fresh = false): Promise<string> {
  const fast = fresh ? { __mock_fast: true } : {};
  const res = await page.request.post(`${SERVER_URL}/api/proposals`, {
    headers: auth,
    data: {
      title: "Maximise the field in the bilateral thalamus",
      rationale: "You asked for the strongest field in both thalami; this optimises, then simulates the winning electrodes.",
      client: "Claude Code",
      steps: [
        {
          id: "opt",
          kind: "flex",
          subject_ids: ["ernie"],
          note: "Target: Left-Thalamus + Right-Thalamus (aseg)",
          config: {
            goal: "mean",
            postproc: "max_TI",
            current_mA: 1,
            output_folder: "l_precuneus_mean_TInormal",
            electrode: { shape: "ellipse", dimensions: [8, 8], gel_thickness: 4 },
            roi: { _type: "SphericalROI", x: [-10], y: [-60], z: [40], radius: [10], use_mni: true, volumetric: false, tissues: "GM" },
            ...fast,
          },
          plan: fresh ? {} : { outputs: [{ subject: "ernie", output_dir: FLEX_DIR, exists: true }], will_overwrite: [FLEX_DIR], eta_minutes: 24 },
        },
        { id: "sim", kind: "sim_from_flex", subject_ids: ["ernie"], config: { flex_step: "opt", conductivity: "scalar", ...fast } },
      ],
    },
  });
  expect(res.status()).toBe(201);
  return (await res.json()).id;
}

async function stored(id: string) {
  return (await page.request.get(`${SERVER_URL}/api/proposals/${id}`, { headers: auth })).json();
}

/** Opens step *stepId*'s inline editor and goes to its run page with "Open in form". */
async function openInForm(stepId: string): Promise<void> {
  await page.getByTestId(`proposal-step-${stepId}`).getByRole("button", { name: "Edit" }).click();
  await page.getByTestId(`proposal-editor-${stepId}`).getByRole("button", { name: "Open in form" }).click();
}

/** The app routes in memory (no URL): the nav rail marks the page that is showing. */
async function onPage(name: string): Promise<void> {
  await expect(page.getByRole("link", { name, exact: true })).toHaveAttribute("aria-current", "page");
}

/** A Select in the row, by its accessible name: a real click at the trigger (see `_jobs.ts`). */
async function pick(label: string, option: string): Promise<void> {
  const trigger = page.getByRole("combobox", { name: label, exact: true }).first();
  await expect(trigger).toBeEnabled();
  const box = (await trigger.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.getByRole("option", { name: option, exact: true }).click();
}

test("a proposed plan is counted, shown as a card, and approving it queues an agent job", async () => {
  await propose(); // arrives live: the app is already open
  const badge = page.getByTestId("nav-proposals-badge");
  await expect(badge).toHaveText("1");
  await page.getByRole("link", { name: "Jobs", exact: true }).click();

  const card = page.getByTestId("proposal-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("from Claude Code");
  await expect(card).toContainText("Mean field in the target");
  await expect(card).toContainText("after step opt");
  await expect(card.getByRole("alert")).toContainText(FLEX_DIR);
  // The card sits above the table, inside the work pane, and never pushes it out of the page.
  const box = (await card.boundingBox())!;
  const work = (await page.locator(".jobs-page-work").boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(work.x - 1);
  expect(box.x + box.width).toBeLessThanOrEqual(work.x + work.width + 1);
  await card.screenshot({ path: join(ARTIFACTS, "proposal-card.png") });

  // Replacing is the user's call: Approve stays off until the step is allowed to replace.
  const approve = card.getByRole("button", { name: "Approve and run" });
  await expect(approve).toBeDisabled();
  await page.getByTestId("proposal-step-opt").getByRole("button", { name: "Edit" }).click();
  const editor = page.getByTestId("proposal-editor-opt");
  await editor.getByRole("checkbox").click();
  await editor.getByRole("button", { name: "Save step" }).click();
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect(card).toHaveAttribute("data-status", "running");
  await expect(badge).toHaveCount(0);
  await expect(page.getByTestId("proposal-step-opt").locator("button.proposal-job-link")).toHaveCount(1);
  await expect(page.getByTestId("proposal-step-sim")).toHaveAttribute("data-state", "waiting");
  await expect(page.locator(".jobs-cell-kind", { hasText: "agent" }).first()).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "proposal-approved.png") });
});

test("rejecting sends the note, folds the plan into Finished plans, and Settings has the approval switch", async () => {
  const id = await propose();
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  const card = page.getByTestId("proposal-card");
  await card.getByRole("button", { name: "Reject…" }).click();
  await card.getByLabel("Rejection note").fill("use the left thalamus only");
  await card.getByRole("button", { name: "Reject plan" }).click();
  // A decided plan is no card any more: it folds into the collapsed "Finished plans" disclosure.
  await expect(card).toHaveCount(0);
  const finished = page.getByTestId("finished-plans");
  await expect(finished).toContainText("Finished plans (1)");
  await expect(page.getByTestId("finished-plan")).toHaveCount(0);
  await page.screenshot({ path: join(ARTIFACTS, "finished-plans-collapsed.png") });
  await finished.getByRole("button", { name: /Finished plans/ }).click();
  const row = page.getByTestId("finished-plan");
  await expect(row).toContainText("Maximise the field in the bilateral thalamus");
  await expect(row).toContainText("rejected");
  await expect(row).toContainText("from Claude Code");
  await page.screenshot({ path: join(ARTIFACTS, "finished-plans-expanded.png") });
  const stored = await (await page.request.get(`${SERVER_URL}/api/proposals/${id}`, { headers: { Authorization: `Bearer ${TOKEN}` } })).json();
  expect(stored.decision).toMatchObject({ state: "rejected", note: "use the left thalamus only" });

  // Dismiss persists on the server: gone from the list and from the default listing.
  await row.getByRole("button", { name: /^Dismiss/ }).click();
  await expect(finished).toHaveCount(0);
  const listed = await (await page.request.get(`${SERVER_URL}/api/proposals`, { headers: { Authorization: `Bearer ${TOKEN}` } })).json();
  expect((listed as { id: string }[]).map((p) => p.id)).not.toContain(id);

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const toggle = page.getByRole("switch", { name: "Agent may submit without approval" });
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
});

test("an approved two-step plan runs its dependent step when the first succeeds, then is done", async () => {
  const id = await propose(true);
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await page.getByTestId("proposal-card").getByRole("button", { name: "Approve and run" }).click();
  await expect(page.getByTestId("proposal-step-sim")).toHaveAttribute("data-state", "waiting");
  // The flex job finishes, the server-side advance queues the simulation, and it finishes too.
  await expect(page.getByTestId("proposal-step-opt")).toHaveAttribute("data-state", "succeeded", { timeout: 20_000 });
  await expect(page.getByTestId("proposal-step-sim").locator("button.proposal-job-link")).toHaveCount(1, { timeout: 20_000 });
  // Done folds the card into Finished plans.
  await expect(page.getByTestId("proposal-card")).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByTestId("finished-plans")).toContainText("Finished plans (1)");
  const record = await stored(id);
  expect(record.status).toBe("succeeded");
  expect(record.steps.map((s: { id: string; state: string; job_ids: string[] }) => [s.id, s.state, s.job_ids.length])).toEqual([
    ["opt", "succeeded", 1],
    ["sim", "succeeded", 1],
  ]);
});

test("the inline step editor fits at 1024 px: whole run name, checkbox beside its label, actions in one footer", async () => {
  await page.setViewportSize({ width: 1024, height: 800 });
  await propose();
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await page.getByTestId("proposal-step-opt").getByRole("button", { name: "Edit" }).click();
  const editor = page.getByTestId("proposal-editor-opt");
  const runName = editor.getByLabel("Run name");
  await expect(runName).toHaveValue("l_precuneus_mean_TInormal");
  const fit = await runName.evaluate((el: HTMLInputElement) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  expect(fit.scroll).toBeLessThanOrEqual(fit.client); // nothing cut off
  const box = (await editor.getByRole("checkbox").boundingBox())!;
  const label = (await editor.getByText("Replace existing output", { exact: true }).boundingBox())!;
  expect(Math.abs(box.y + box.height / 2 - (label.y + label.height / 2))).toBeLessThan(3); // one row
  expect(label.x).toBeGreaterThan(box.x + box.width - 1); // label to the right of the box
  await expect(editor.locator(".proposal-editor-actions button")).toHaveText(["Open in form", "Cancel", "Save step"]);
  await expect(page.getByTestId("proposal-step-opt").getByRole("button", { name: /^(Close|Edit)$/ })).toHaveCount(0);
  await page.getByTestId("proposal-card").screenshot({ path: join(OUT, "inline-editor-after.png") });
  await editor.locator("summary").click();
  const json = (await editor.getByLabel("Step config JSON").boundingBox())!;
  expect(json.height).toBeGreaterThan(150); // ~10 lines, not one
  await page.getByTestId("proposal-card").screenshot({ path: join(OUT, "inline-editor-after-json.png") });
  await editor.getByRole("button", { name: "Cancel" }).click();
  await expect(editor).toHaveCount(0);
});

test("Open in form edits a flex step on the Optimizer and Save to plan writes it back", async () => {
  const id = await propose();
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await openInForm("opt");
  await onPage("Optimizer");
  const banner = page.getByTestId("plan-step-banner");
  await expect(banner).toContainText("Editing plan step: Maximise the field in the bilateral thalamus · step 1");
  await expect(page.getByTestId("run-button")).toHaveCount(0);
  await expect(page.getByTestId("plan-step-save")).toHaveText("Save to plan");
  const optRow = page.locator("[data-opt-row]");
  await expect(optRow).toHaveCount(1);
  await expect(optRow).toHaveAttribute("data-subject", "ernie");
  await expect(optRow).toHaveAttribute("data-kind", "flex");
  await page.screenshot({ path: join(OUT, "open-in-form-optimizer.png") });
  await pick("Goal", "Max TImax (99.9%)");
  await page.getByTestId("plan-step-save").click();
  await onPage("Jobs");
  await expect(page.getByTestId("proposal-step-opt")).toContainText("Peak field in the target");
  const record = await stored(id);
  expect(record.steps[0].config).toMatchObject({ goal: "max", output_folder: "l_precuneus_mean_TInormal", roi: { _type: "SphericalROI", x: [-10], use_mni: true } });
  // Back on the Optimizer the page is its own again: no banner, Run is back.
  await page.getByRole("link", { name: "Optimizer", exact: true }).click();
  await expect(page.getByTestId("plan-step-banner")).toHaveCount(0);
  await expect(page.getByTestId("run-button")).toBeVisible();
});

test("Open in form shows a sim_from_flex step as its flex row on the Simulator; Cancel saves nothing, Save sets the placement", async () => {
  const id = await propose();
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await openInForm("sim");
  await onPage("Simulator");
  await expect(page.getByTestId("plan-step-banner")).toContainText("step 2");
  const row = page.locator("tr[data-job-row]");
  await expect(row).toHaveCount(1);
  await expect(row.locator('td[data-cell="source"]')).toContainText("Flex result");
  await expect(row).toContainText("l_precuneus_mean_TInormal · step opt");
  await page.screenshot({ path: join(OUT, "open-in-form-simulator.png") });
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await onPage("Jobs");
  expect((await stored(id)).steps[1].config.eeg_net).toBeUndefined();

  await openInForm("sim");
  await pick("Placement", "GSN-HydroCel-185");
  await page.getByTestId("plan-step-save").click();
  await onPage("Jobs");
  expect((await stored(id)).steps[1].config).toMatchObject({ flex_step: "opt", eeg_net: "GSN-HydroCel-185", conductivity: "scalar" });
  await expect(page.getByTestId("proposal-step-sim")).toContainText("GSN-HydroCel-185");
});

test("Open in form edits a pre-processing step on Pre-processing", async () => {
  const res = await page.request.post(`${SERVER_URL}/api/proposals`, {
    headers: auth,
    data: { title: "Head model for 101", client: "Claude Code", steps: [{ id: "pre", kind: "pre", subject_ids: ["101"], config: { create_m2m: true, run_freesurfer: false } }] },
  });
  const id = (await res.json()).id;
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await openInForm("pre");
  await onPage("Pre-processing");
  await expect(page.getByTestId("plan-step-banner")).toContainText("Editing plan step: Head model for 101 · step 1");
  const charm = page.getByRole("checkbox", { name: "SimNIBS charm (m2m + subject atlas)" });
  await expect(charm).toBeChecked();
  await page.getByRole("checkbox", { name: "FreeSurfer (optional)" }).click();
  await page.getByTestId("plan-step-save").click();
  await onPage("Jobs");
  const record = await stored(id);
  expect(record.steps[0].subject_ids).toEqual(["101"]);
  expect(record.steps[0].config).toMatchObject({ create_m2m: true, run_freesurfer: true });
});

test("a waiting plan is announced on the Overview, and Review opens its card on Jobs", async () => {
  await propose();
  const notice = page.getByTestId("pending-plans-notice");
  await expect(notice).toContainText("Claude Code proposes Maximise the field in the bilateral thalamus");
  await page.screenshot({ path: join(OUT, "overview-plan-notice.png") });
  await notice.getByRole("button", { name: "Review" }).click();
  await onPage("Jobs");
  await expect(page.getByTestId("proposal-card")).toBeInViewport();
});
