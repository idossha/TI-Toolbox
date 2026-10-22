import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { setSubjectChecked } from "./_subjects";

/**
 * Pre-processing's existing-outputs question decides the policy the group is submitted with
 * (2026-10-22, p27), against the mock server, offscreen.
 *
 * What it pins: the contract written at `pages/preprocess/index.tsx`'s `submit` — pressing
 * "Replace and rerun" in the shared dialog submits `replace_existing_outputs: true,
 * skip_existing_outputs: false` even though the page's own policy control still says skip, and
 * the skip answer submits the reverse. The dialog's "N of M" is checked against the plan response
 * the page received (`POST /api/plan/pre`: jobs with `exists`), not against the page's own count.
 *
 * The group POST is answered here (`page.route`) so nothing is queued in the mock: each answer
 * starts from the same plan and the same existing outputs. `preprocess.spec.ts` covers the real
 * queueing path. Run: `TIT_E2E_OFFSCREEN=1 npx playwright test --project=default
 * tests/e2e/preprocess-replace.spec.ts` after `npm run pree2e`.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SUBJECTS = ["ernie", "101"];

interface PlanSeen {
  subjects: string[];
  jobs: number;
  exists: number;
}
interface GroupBody {
  kind: string;
  subject_ids: string[];
  config: { skip_existing_outputs: boolean; replace_existing_outputs: boolean; subject_ids: string[] };
}

let app: ElectronApplication;
let page: Page;
const plans: PlanSeen[] = [];
const submitted: GroupBody[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });

  page.on("response", async (response) => {
    const request = response.request();
    if (request.method() !== "POST" || !response.url().endsWith("/api/plan/pre") || !response.ok()) return;
    const sent = request.postDataJSON() as { subject_ids: string[] };
    const body = (await response.json()) as { jobs: { exists: boolean }[] };
    plans.push({ subjects: sent.subject_ids, jobs: body.jobs.length, exists: body.jobs.filter((j) => j.exists).length });
  });
  await page.route("**/api/jobs/groups", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted.push(route.request().postDataJSON() as GroupBody);
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ group_id: "e2e-replace", jobs: [] }) });
  });

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "preprocess", "Pre-processing");
  await expectPage(page, "preprocess");
  await setSubjectChecked(page, "101", true);
  // The first plan covers ernie alone; wait for the one for both, and for the page to show it.
  await expect.poll(() => plans.some((p) => sameSubjects(p.subjects)), { timeout: 15_000 }).toBe(true);
  await expect(page.getByTestId("run-button")).toHaveText(`Queue ${lastPlan().jobs} jobs`, { timeout: 15_000 });
});

test.afterAll(async () => {
  await app?.close();
});

function sameSubjects(subjects: string[]): boolean {
  return JSON.stringify(subjects) === JSON.stringify(SUBJECTS);
}

/** The last plan the page received for both subjects: what the dialog must describe. */
function lastPlan(): PlanSeen {
  const seen = plans.filter((p) => sameSubjects(p.subjects));
  const last = seen[seen.length - 1];
  if (!last) throw new Error("the page never planned both subjects");
  return last;
}

async function answer(testId: string): Promise<GroupBody> {
  const before = submitted.length;
  await page.getByTestId("run-button").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const plan = lastPlan();
  // Some outputs exist and some do not, or the question would not be worth asking.
  expect(plan.exists).toBeGreaterThan(0);
  expect(plan.exists).toBeLessThan(plan.jobs);
  await expect(dialog).toContainText(
    `${plan.exists} of ${plan.jobs} planned jobs already ${plan.exists === 1 ? "has" : "have"} pre-processing output on disk.`,
  );
  await page.getByTestId(testId).click();
  await expect.poll(() => submitted.length).toBe(before + 1);
  await expect(dialog).toBeHidden();
  const body = submitted[submitted.length - 1];
  if (!body) throw new Error("no group was submitted");
  return body;
}

test("'Replace and rerun' submits replace, not the page's skip", async () => {
  const body = await answer("existing-outputs-replace");
  expect(body.kind).toBe("pre");
  expect(body.subject_ids).toEqual(SUBJECTS);
  expect(body.config.subject_ids).toEqual(SUBJECTS);
  expect(body.config.replace_existing_outputs).toBe(true);
  expect(body.config.skip_existing_outputs).toBe(false);
});

test("'Skip' submits skip", async () => {
  const body = await answer("existing-outputs-skip");
  expect(body.subject_ids).toEqual(SUBJECTS);
  expect(body.config.skip_existing_outputs).toBe(true);
  expect(body.config.replace_existing_outputs).toBe(false);
});

test("'Cancel' submits nothing", async () => {
  const before = submitted.length;
  await page.getByTestId("run-button").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByTestId("existing-outputs-cancel").click();
  await expect(page.getByRole("dialog")).toBeHidden();
  // No sleep to prove a negative: the next answer's request comes after anything Cancel might
  // have sent, so exactly one new submission, and that one the skip, means Cancel sent none.
  const body = await answer("existing-outputs-skip");
  expect(submitted.length).toBe(before + 1);
  expect(body.config.skip_existing_outputs).toBe(true);
});
