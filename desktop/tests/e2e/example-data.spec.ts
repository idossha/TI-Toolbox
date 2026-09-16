/**
 * "Add example data?" — the once-per-project chooser (`app/exampleData/ExampleDataPrompt`).
 *
 * The defect this closes: the chooser was mounted inside Overview and treated a failed
 * `GET /api/project/status` as "do not ask", so a freshly created project — which has no
 * `project_status.json` yet, and whose first route need not be Overview — was never asked.
 * `POST /api/__mock/project-status {"missing": true}` is that fresh project: the mock's GET then
 * 404s exactly as the server does with no status file on disk.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

async function setProjectStatusMissing(missing: boolean): Promise<void> {
  const res = await fetch(`${SERVER_URL}/api/__mock/project-status`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ missing }),
  });
  expect(res.status, "the mock accepted the project-status fixture").toBe(200);
}

async function launchAndConnect(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
}

test.afterEach(async () => {
  await app?.close();
  await setProjectStatusMissing(false);
});

test("a project with no project_status.json is asked, and the four samples are the choices", async () => {
  await setProjectStatusMissing(true);
  await launchAndConnect();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 45_000 });
  await expect(dialog).toContainText("Add example data?");
  await expect(page.getByTestId("example-data-list")).toBeVisible();
  for (const id of ["mni152-t1", "ernie-t1", "ernie-headmodel", "mni152-headmodel"]) {
    await expect(page.getByTestId(`example-data-row-${id}`)).toBeVisible();
  }
  // Default-checked: the only sample that runs the optimizer/simulator/analyzer immediately.
  await expect(page.getByTestId("example-data-check-ernie-headmodel")).toBeChecked();
  await expect(page.getByTestId("example-data-check-ernie-t1")).not.toBeChecked();
  await expect(page.getByTestId("example-data-row-ernie-headmodel")).toContainText("ready to simulate");
  await expect(page.getByTestId("example-data-row-ernie-t1")).toContainText("needs pre-processing");
});

test("Download selected starts a plain fetch per ticked sample and never asks again", async () => {
  await setProjectStatusMissing(true);
  await launchAndConnect();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 45_000 });

  // A plain route, not a job: one POST per sample to /api/example-data/{id}, no job submission.
  const posts: string[] = [];
  const jobPosts: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/api/example-data/")) posts.push(path);
    if (path === "/api/jobs" || path === "/api/project/example-data") jobPosts.push(path);
  });
  await page.getByTestId("example-data-check-mni152-t1").check();
  await page.getByTestId("example-data-download").click();

  await expect(page.getByRole("dialog")).toBeHidden();
  await expect.poll(() => posts.length, { timeout: 15_000 }).toBe(2);
  expect(posts.join("|")).toContain("ernie-headmodel");
  expect(posts.join("|")).toContain("mni152-t1");
  expect(jobPosts, "a download must not go through the jobs system").toEqual([]);

  // The answer was persisted server-side, so a relaunch into the same project is not asked again.
  await app.close();
  await launchAndConnect();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("a project that already holds example data is never asked", async () => {
  await setProjectStatusMissing(false);
  await launchAndConnect();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("Overview's toolbar button opens Help ▸ Example data, the same list with Download buttons", async () => {
  await setProjectStatusMissing(false);
  await launchAndConnect();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });

  await page.getByTestId("add-example-subject").click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-page", "help");
  await expect(page.getByTestId("help-example-data")).toBeVisible();
  await expect(page.getByTestId("example-data-download-ernie-t1")).toBeVisible();
  // The mock project already holds the head model, so that row says so instead of offering it.
  await expect(page.getByTestId("example-data-installed-ernie-headmodel")).toBeVisible();
});

test("Help ▸ Example data shows polled progress and then Installed, with no job rail entry", async () => {
  await setProjectStatusMissing(false);
  await launchAndConnect();
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });

  await page.getByTestId("add-example-subject").click();
  await expect(page.getByTestId("help-example-data")).toBeVisible();

  // The poll is what reports progress: GET /api/example-data repeats while a fetch is in flight.
  let polls = 0;
  page.on("request", (r) => {
    if (r.method() === "GET" && new URL(r.url()).pathname === "/api/example-data") polls += 1;
  });
  const before = polls;
  await page.getByTestId("example-data-download-ernie-t1").click();

  // The mock finishes the download over a few polls, so the row ends as Installed.
  await expect(page.getByTestId("example-data-installed-ernie-t1")).toBeVisible({ timeout: 30_000 });
  expect(polls, "the catalogue was re-polled while the fetch ran").toBeGreaterThan(before + 1);
});
