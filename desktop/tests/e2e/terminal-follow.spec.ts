import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication } from "@playwright/test";
import { connectLauncher, gotoPage, launchElectronApp } from "./_helpers";

let app: ElectronApplication;
test.afterEach(async () => { await app?.close(); });

test("enabling Follow restores the actual log viewport and renders its final row", async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-follow-")) });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  const server = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
  await connectLauncher(page, server, process.env.TIT_E2E_TOKEN ?? "mock-token");
  await expect(page).toHaveURL(new URL("/", server).href);
  await gotoPage(page, "dev", "Gallery");
  const console_ = page.getByTestId("gallery-job-console");
  await console_.scrollIntoViewIfNeeded();
  const viewport = console_.locator(".job-console-lines");
  const follow = console_.getByRole("switch", { name: "Follow tail" });
  await follow.click();
  await expect(follow).toHaveAttribute("aria-checked", "false");
  await viewport.evaluate((el) => { el.scrollTop = 36; });
  await expect.poll(() => viewport.evaluate((el) => el.scrollTop)).toBe(36);
  await follow.click();
  await expect(follow).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => viewport.evaluate((el) =>
    Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop),
  )).toBeLessThanOrEqual(1);
  // Offset alone is insufficient: the virtualizer must mount the last row at the tail.
  await expect.poll(() => viewport.evaluate((el) => {
    const rows = el.querySelectorAll(".job-console-line");
    const tail = rows[rows.length - 1];
    if (!tail) return false;
    const box = tail.getBoundingClientRect();
    const frame = el.getBoundingClientRect();
    return tail.textContent?.startsWith("long command") === true &&
      box.top >= frame.top && box.bottom <= frame.bottom + 1;
  })).toBe(true);
});
