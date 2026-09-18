import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

/**
 * The Jobs page's Raw log, end to end: it follows the tail, a reader who scrolls back keeps their
 * place, the Follow switch takes them back to the tail, and a finished job's transcript is complete
 * again after a reload (the pane has no live socket for a terminal job — everything it shows comes
 * from `GET /api/jobs/{id}/events`, whose `since` the renderer used to send as `-1`; a real server
 * answers that with HTTP 422 and the console came up empty).
 *
 * `terminal-follow.spec.ts` covers the same switch on the Gallery's console fixture; this one is
 * the real Jobs pane, over a real (mock-server) job's log.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.afterEach(async () => {
  await app?.close();
});

async function submitJob(body: Record<string, unknown>): Promise<{ id: string }> {
  const res = await page.request.post(`${SERVER_URL}/api/jobs`, { headers: { Authorization: `Bearer ${TOKEN}` }, data: body });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

/** The window has to exist before `page.request` can seed a job, so launching and connecting are
 *  two steps: seed in between and the job is already in the list when the app loads it. */
async function launchApp(): Promise<void> {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-joblog-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
}

async function connect(): Promise<void> {
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
}

async function openRawLog(subject: string): Promise<{ lines: ReturnType<Page["locator"]>; follow: ReturnType<Page["locator"]> }> {
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page.getByTestId("jobs-toolbar")).toBeVisible();
  const row = page.getByTestId("jobs-table").getByRole("row", { name: new RegExp(subject) });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.click();
  const detail = page.getByTestId("job-detail");
  await detail.getByRole("tab", { name: "Raw log", exact: true }).click();
  const console_ = detail.getByTestId("job-detail-rawlog");
  await expect(console_).toBeVisible();
  return { lines: console_.locator(".job-console-lines"), follow: console_.getByRole("switch", { name: "Follow tail" }) };
}

const atBottom = (el: Element): number => el.scrollHeight - el.clientHeight - el.scrollTop;

test("Follow holds the tail, scrolling back releases it, and the switch takes it back", async () => {
  // A log taller than the pane, still running, so output keeps arriving while we read it.
  await launchApp();
  await submitJob({ kind: "sim", config: { __mock_log_lines: 400, __mock_hold: true }, subject_ids: ["followers"], tags: ["e2e-follow"] });
  await connect();
  const { lines, follow } = await openRawLog("followers");

  await expect(lines.getByText(/filler line \d+ of 400/).first()).toBeVisible({ timeout: 20_000 });
  await expect(follow).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => lines.evaluate(atBottom)).toBeLessThanOrEqual(18);

  // Scrolling back to read something releases Follow — otherwise the next chunk of a running job's
  // output snaps the view to the bottom and the line being read is unreachable.
  await lines.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event("scroll")); });
  await expect(follow).toHaveAttribute("aria-checked", "false");

  // And the reading position survives the output that arrives next.
  const resting = await lines.evaluate((el) => el.scrollTop);
  await page.waitForTimeout(2_500);
  expect(await lines.evaluate((el) => el.scrollTop)).toBe(resting);
  await expect(follow).toHaveAttribute("aria-checked", "false");

  await follow.click();
  await expect(follow).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => lines.evaluate(atBottom)).toBeLessThanOrEqual(18);
});

test("a finished job's whole log is there again after a reload", async () => {
  await launchApp();
  await submitJob({ kind: "sim", config: { __mock_fast: true, __mock_log_lines: 400 }, subject_ids: ["reloaded"], tags: ["e2e-follow"] });
  await connect();

  const first = await openRawLog("reloaded");
  await expect(page.getByTestId("job-detail").getByText("succeeded", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(first.lines.getByText(/filler line \d+ of 400/).first()).toBeVisible({ timeout: 20_000 });

  // Nothing is streamed for a terminal job, so this is the REST backlog on its own.
  await page.reload();
  const again = await openRawLog("reloaded");
  await expect(again.lines.getByText(/filler line \d+ of 400/).first()).toBeVisible({ timeout: 20_000 });
  // The whole file, not a tail of it: the log scrolls, and its last line is the job's last line.
  const scroll = await again.lines.evaluate((el) => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight }));
  expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
  await expect(again.lines.locator(".job-console-line").last()).toContainText(/complete for reloaded/);
});
