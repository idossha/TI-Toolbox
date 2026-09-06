/**
 * The viewer **launch bridge**, in the real Electron shell (V6 bug fix, 2026-09-06:
 * `dev/notes/v3-native-panes-external-viewer/TI.md` §7).
 *
 * The reported defect was "Open in Tetravox writes the scene, the page says *Opened …*, and no
 * window appears" — a launch reporting success it had not earned. Two things had to become
 * testable as a result, and both are asserted here against the **real** `tit:viewer:*` handlers in
 * main (nothing is stubbed, and nothing is launched):
 *
 * 1. **The bridge is there in the shell.** The renderer is served over HTTP by the toolbox server
 *    in production and by Vite in `pnpm run dev`; if the preload had not attached, the Viewer page
 *    would silently take its browser-mode branch, write the file, and never call main at all —
 *    which looks exactly like the bug. So: `window.tit.viewer` exists and carries every method.
 * 2. **A launch that cannot happen says so.** `open` is asked for a path outside every known
 *    project mount, which main must refuse — with a reason, not with `{ok:true}`.
 *
 * The happy path ends in another application's window and therefore cannot run in an
 * offscreen-by-default suite. It is covered by the argv assertions in
 * `tests/unit/viewer-launch.test.ts` and by one real, manual launch recorded in the note.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
});

test.afterEach(async () => {
  await app?.close();
});

test("the viewer bridge is attached to the server-served page, with every method", async () => {
  const shape = await page.evaluate(() => {
    const viewer = window.tit?.viewer as Record<string, unknown> | undefined;
    return viewer ? Object.keys(viewer).sort() : null;
  });
  // Not "is it truthy": a bridge missing `open` is the browser-mode fallback wearing a costume.
  expect(shape).toEqual(["checkUpdates", "install", "onEvent", "open", "probe", "remove", "setPath"]);
  // and it is still one top-level entry, not seven (the ADR-14 bridge budget)
  const top = await page.evaluate(() => Object.keys(window.tit ?? {}).length);
  expect(top).toBe(14);
});

test("probe answers from main rather than from the page", async () => {
  const info = await page.evaluate(() => window.tit!.viewer.probe());
  // Whatever this machine has, the *shape* is main's and every field is present — a page that
  // could not reach main would have thrown instead.
  expect(info).toHaveProperty("available");
  expect(info).toHaveProperty("managed.supported");
  expect(info).toHaveProperty("downloadUrl");
});

test("a launch that cannot happen reports a reason instead of success", async () => {
  // A path that maps into no known project mount. Main must refuse it: the alternative — spawning
  // an unmapped string and reporting `{ok:true}` — is the shape of the reported bug.
  const outside = await page.evaluate(() => window.tit!.viewer.open("/not/a/project/subject.tetravox.json"));
  expect(outside.ok).toBe(false);
  if (!outside.ok) expect(outside.reason.length).toBeGreaterThan(0);

  // And a path that is not a scene at all is refused before any mapping is attempted.
  const notAScene = await page.evaluate(() => window.tit!.viewer.open("/mnt/project/code/viewer/subject.tvx.json"));
  expect(notAScene.ok).toBe(false);
  if (!notAScene.ok) expect(notAScene.reason).toContain(".tetravox.json");
});
