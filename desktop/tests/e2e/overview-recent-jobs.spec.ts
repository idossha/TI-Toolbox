/**
 * Overview → "Recent jobs": the project's own history on its front door, and the click that leads
 * from a job to what it produced.
 *
 * Maintainer, Sep 2026: *"in the Overview page, users should see the jobs they performed and get
 * to the results by clicking there."* So the two claims worth an e2e are exactly those: the rows
 * are there, newest first, and one click on a finished simulation lands on Results with its
 * subject selected, while a job still running lands on the Jobs page instead.
 *
 * Jobs are seeded straight through the mock's REST API, the way `jobs.spec.ts` does it (the
 * "Submit test job" button is DEV-only). File order matters in a `workers: 1` run: this file sorts
 * after `jobs.spec.ts`, whose first test needs the job registry to still be empty.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

/** The minimal config `POST /api/jobs` accepts for a `sim` (see `jobs.spec.ts::seedConfig`). */
function simConfig(subject: string): Record<string, unknown> {
  return {
    subject_id: subject,
    montages: [
      {
        _type: "Montage",
        name: "recent_montage",
        mode: "net",
        electrode_pairs: [
          ["E010", "E011"],
          ["E012", "E013"],
        ],
        eeg_net: "GSN-HydroCel-185.csv",
      },
    ],
  };
}

async function submitSim(subject: string): Promise<{ id: string }> {
  const res = await page.request.post(`${SERVER_URL}/api/jobs`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: { kind: "sim", config: simConfig(subject), subject_ids: [subject], tags: ["e2e-recent"] },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

async function jobState(id: string): Promise<string> {
  const res = await page.request.get(`${SERVER_URL}/api/jobs/${id}`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { status?: { state: string }; state?: string };
  return body.status?.state ?? body.state ?? "unknown";
}

test.beforeEach(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
});
test.afterEach(async () => {
  await app?.close();
});

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
}

test("lists the jobs this project ran, newest first, and a click lands where that job's outputs are", async () => {
  test.setTimeout(120_000);
  const older = await submitSim("ernie");
  await expect.poll(() => jobState(older.id), { timeout: 60_000 }).toBe("succeeded");
  const newer = await submitSim("101");

  await connect();
  const section = page.getByTestId("overview-recent");
  await expect(section).toBeVisible();

  const finished = page.getByTestId(`overview-recent-${older.id}`);
  const running = page.getByTestId(`overview-recent-${newer.id}`);
  await expect(finished).toBeVisible({ timeout: 20_000 });
  await expect(running).toBeVisible({ timeout: 20_000 });

  // Newest first: the job submitted second is drawn above the one submitted first.
  const rows = section.locator(".overview-recent-row");
  const ids = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));
  expect(ids.indexOf(`overview-recent-${newer.id}`)).toBeLessThan(ids.indexOf(`overview-recent-${older.id}`));
  expect(ids.length, "eight rows at most").toBeLessThanOrEqual(8);

  // What a row says: kind, subject, run, a state chip, when it started and how long it took.
  await expect(finished).toContainText("sim");
  await expect(finished).toContainText("ernie");
  await expect(finished).toContainText("succeeded");
  await expect(finished).toContainText(/ago|just now/);

  // A finished simulation goes to its outputs.
  await expect(finished).toHaveAttribute("data-destination", "results");
  await finished.click();
  await expectPage(page, "results");
  await expect(page.getByTestId("results-subject-ernie")).toHaveAttribute("aria-selected", "true");
});

test("a job that has not finished opens the Jobs page on that job, and the row takes the keyboard", async () => {
  test.setTimeout(120_000);
  const job = await submitSim("keyboard-recent");

  await connect();
  const row = page.getByTestId(`overview-recent-${job.id}`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await expect(row).toHaveAttribute("data-destination", "jobs");

  // Enter on the focused row is the same gesture as the click (it is a button, not a div).
  await row.focus();
  await page.keyboard.press("Enter");
  await expectPage(page, "jobs");
  await expect(page.getByTestId("job-detail")).toContainText("keyboard-recent", { timeout: 20_000 });

  // "See all" is the way to the rest of them.
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByTestId("overview-recent-see-all").click();
  await expectPage(page, "jobs");
});
