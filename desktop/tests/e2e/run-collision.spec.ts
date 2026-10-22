import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addJobRow, clearJobRows, configureMontageJob, jobCurrents, jobRows, setJobSubject } from "./_jobs";

/**
 * Two Simulator rows that resolve to one output folder block Run, and the Run button says which
 * folder (p19, 2026-10-22; bug sim:batch-duplicate-output-dir).
 *
 * The repro: "Duplicate job" copies the montage name, the copy gets other currents, and Run put
 * both into one `POST /api/jobs/groups`; the scheduler ran them one after another into
 * `sub-ernie/Simulations/F3_F4`, so only the second configuration's results remained. The folder
 * the test expects is the server's rule (`plan.py::_plan_sim`: `pm.simulation(sid, montage.name)`,
 * which the mock server mirrors), typed here from that rule, not read from the page. Re-pointing
 * the copy at another subject is two folders, and Run comes back.
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
  // The keyboard shortcut is the button's own code path: it must not submit either.
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Enter" : "Control+Enter");
  page.off("request", collect);
  expect(posted).toEqual([]);

  // Two subjects are two folders: Run comes back and counts both jobs.
  await setJobSubject(page, copy, "101");
  await expect(run).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator(".action-bar-digest")).toHaveText(/^2 jobs$/, { timeout: 15_000 });
});
