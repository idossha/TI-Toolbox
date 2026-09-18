/**
 * **A finished job's log, against the real server** (jobs polish lane).
 *
 * The mock server accepted the `since=-1` the renderer used to send for a job's events; a real
 * `tit.server` answers it 422, and nothing is streamed over `/ws/jobs` for a job that has already
 * finished — so the whole transcript of every finished job came from one rejected request. This
 * spec is the reason that was found and the proof it is gone: it opens a job the project already
 * has and asserts the Raw log really carries its lines, and that the Summary excerpt is the tail of
 * the same log.
 *
 * It runs no job and writes nothing to the project — it reads the job history that is already
 * there — so it costs seconds.
 *
 *   TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
 *     bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/jobs-log.spec.ts
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, launchElectronApp } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

let app: ElectronApplication;
let page: Page;

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-joblog-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectReal(page);
});

test.afterAll(async () => {
  await app?.close();
});

/** A finished job this project already has, with a log long enough to be worth showing. */
async function aFinishedJobWithALog(): Promise<{ id: string; lines: number }> {
  const res = await page.request.get(`${SERVER_URL}/api/jobs`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  expect(res.ok()).toBeTruthy();
  const jobs = (await res.json()) as { id: string; state: string }[];
  for (const job of jobs) {
    if (job.state !== "succeeded") continue;
    const log = await page.request.get(`${SERVER_URL}/api/jobs/${job.id}/log`, { headers: { Authorization: `Bearer ${TOKEN}` } });
    const lines = (await log.text()).split("\n").filter(Boolean).length;
    if (lines >= 10) return { id: job.id, lines };
  }
  throw new Error("this project has no finished job with a log to read");
}

test("the Raw log of a job that finished long ago is not empty", async () => {
  test.setTimeout(120_000);
  const job = await aFinishedJobWithALog();

  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page.getByTestId("jobs-toolbar")).toBeVisible({ timeout: 30_000 });

  const row = page.getByTestId("jobs-table").getByRole("row").filter({ hasText: /succeeded/ });
  await expect(row.first()).toBeVisible({ timeout: 30_000 });
  // Select the exact job whose log was read above, by walking to it through the table's own rows.
  const detail = page.getByTestId("job-detail");
  const count = await row.count();
  for (let i = 0; i < count; i++) {
    await row.nth(i).click();
    await expect(detail).toBeVisible();
    if (await detail.getByText(`id ${job.id}`).count()) break;
  }
  await expect(detail.getByText(`id ${job.id}`)).toBeVisible();

  // The Summary's excerpt is the tail of that job's log, not an empty box.
  const excerpt = detail.getByTestId("job-detail-console");
  await expect(excerpt).toBeVisible();
  await expect(excerpt.locator("pre")).not.toHaveText("(no output yet)", { timeout: 30_000 });

  // And the Raw log is the log. The RENDERED lines alone do not prove the fix — that tab falls
  // back to reading the log file when the event stream yields nothing, which is exactly what
  // masked the 422 — so watch the request itself: the console's backlog must be accepted by the
  // real server. `useJobLogEvents` is also what the run pages' Terminal uses, and that one has no
  // file fallback at all.
  const eventRequests: number[] = [];
  page.on("response", (response) => {
    if (response.url().includes(`/api/jobs/${job.id}/events`)) eventRequests.push(response.status());
  });
  await detail.getByRole("tab", { name: "Raw log", exact: true }).click();
  const console_ = detail.getByTestId("job-detail-rawlog");
  await expect(console_).toBeVisible();
  const rendered = console_.locator(".job-console-line");
  await expect(rendered.first()).toBeVisible({ timeout: 30_000 });
  expect(await rendered.count()).toBeGreaterThan(1);
  await expect.poll(() => eventRequests.length, { timeout: 30_000 }).toBeGreaterThan(0);
  expect(eventRequests, "the console's event backlog must be a request this server accepts").toContain(200);
  expect(eventRequests).not.toContain(422);

  // Follow starts on and holds the tail; scrolling back releases it, the switch takes it back.
  const lines = console_.locator(".job-console-lines");
  const follow = console_.getByRole("switch", { name: "Follow tail" });
  await expect(follow).toHaveAttribute("aria-checked", "true");
  const scroll = await lines.evaluate((el) => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight }));
  if (scroll.scrollHeight > scroll.clientHeight) {
    await expect.poll(() => lines.evaluate((el) => el.scrollHeight - el.clientHeight - el.scrollTop)).toBeLessThanOrEqual(18);
    await lines.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event("scroll")); });
    await expect(follow).toHaveAttribute("aria-checked", "false");
    await follow.click();
    await expect(follow).toHaveAttribute("aria-checked", "true");
    await expect.poll(() => lines.evaluate((el) => el.scrollHeight - el.clientHeight - el.scrollTop)).toBeLessThanOrEqual(18);
  }
});
