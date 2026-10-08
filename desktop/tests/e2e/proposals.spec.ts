import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

// An agent's plan (ARCHITECTURE §6) as the user meets it in the BUILT app against the mock server:
// it arrives over /ws/jobs while the app is open, the nav's Jobs row counts it, the Jobs page shows
// it as a card with its replaced output in a danger callout, Approve queues its root step as an
// `agent` job (badged in the table), and Settings carries the "submit without approval" switch.
// The plan is posted straight to the mock's REST API, as the agent plugin would. The card's
// screenshot lands in TIT_E2E_ARTIFACTS/proposal-card.png.
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

async function propose(): Promise<string> {
  const res = await page.request.post(`${SERVER_URL}/api/proposals`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
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
            output_folder: "thalamus_mean",
            electrode: { shape: "ellipse", dimensions: [8, 8], gel_thickness: 4 },
            roi: { _type: "SubcorticalROI", atlas_path: ["/mnt/example/aseg.nii.gz"], label: [10, 49], tissues: "GM" },
          },
          plan: { outputs: [{ subject: "ernie", output_dir: FLEX_DIR, exists: true }], will_overwrite: [FLEX_DIR], eta_minutes: 24 },
        },
        { id: "sim", kind: "sim_from_flex", subject_ids: ["ernie"], config: { flex_step: "opt", conductivity: "scalar" } },
      ],
    },
  });
  expect(res.status()).toBe(201);
  return (await res.json()).id;
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
