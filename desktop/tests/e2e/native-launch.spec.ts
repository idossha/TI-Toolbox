/**
 * N0.4 packaging spike: proves the PACKAGED app (not the dev tree `launchElectronApp` in every
 * other spec here points at) spawns the bundled native Python runtime, connects the shell to it,
 * and leaves no orphan process behind on quit.
 *
 * Prerequisite, run once before this spec (not part of `npm run e2e`'s own build step):
 *   TIT_RUNTIME_DIR=<a python-build-standalone tree with tit.server's deps + tit installed>
 *   npm run package:dir
 * (docs/dev/SPIKES.md builds a runtime tree that satisfies this.) Without
 * that prior `--dir` build this spec SKIPS itself with a clear message — it deliberately never
 * builds the package inline, to keep `npm run e2e`'s normal ~15-spec run fast and to keep this spec
 * runnable standalone (`npx playwright test tests/e2e/native-launch.spec.ts`) once the app exists.
 *
 * `TIT_NATIVE_RUNTIME_DIR` is explicitly UNSET for this spec's launch (deleted from the child env
 * even if the invoking shell happens to have it) — the whole point is exercising the PACKAGED
 * `resourcesPath/runtime/darwin-arm64` resolution branch in `resolveRuntime()`
 * (`src/main/nativeRuntime.ts`), not the dev/env-override one.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { offscreenEnv } from "./_helpers";

const APP_ROOT = join(__dirname, "..", "..");

/**
 * `release/<electron-builder appOutDir>/TI-Toolbox.app/Contents/MacOS/TI-Toolbox` — only the
 * `mac-arm64` leg exists (this spike built and measured macOS arm64 only, REPORT.md); the other
 * candidates are here so this spec degrades to a clear skip rather than a confusing "no such file"
 * on a platform/arch this spike never packaged, not because they were built or tested.
 */
function resolvePackagedAppBinary(): string | null {
  const candidates =
    process.platform === "darwin"
      ? [
          join(APP_ROOT, "release", "mac-arm64", "TI-Toolbox.app", "Contents", "MacOS", "TI-Toolbox"),
          join(APP_ROOT, "release", "mac", "TI-Toolbox.app", "Contents", "MacOS", "TI-Toolbox"),
        ]
      : process.platform === "win32"
        ? [join(APP_ROOT, "release", "win-unpacked", "TI-Toolbox.exe")]
        : [join(APP_ROOT, "release", "linux-unpacked", "ti-toolbox")];
  return candidates.find((c) => existsSync(c)) ?? null;
}

/** `pgrep -f` — empty match is a normal "not running" outcome, not a test infra error. */
function pgrepServerPids(): string[] {
  try {
    return execFileSync("pgrep", ["-f", "runtime/darwin-arm64/bin/python3.11 -m tit.server"], { encoding: "utf8" })
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

const APP_BIN = resolvePackagedAppBinary();

test.describe("native launch (packaged app, N0.4 spike)", () => {
  test.skip(APP_BIN === null, "no packaged app under release/ — run `TIT_RUNTIME_DIR=<runtime tree> npm run package:dir` first");

  let app: ElectronApplication | undefined;
  let page: Page;

  test.afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  test("spawns the bundled runtime, connects, and leaves no python process behind on quit", async () => {
    const projectDir = mkdtempSync(join(tmpdir(), "tit-native-e2e-"));
    const userDataDir = mkdtempSync(join(tmpdir(), "tit-native-e2e-userdata-"));

    const beforeLaunch = pgrepServerPids();
    expect(beforeLaunch, "no leftover native server from an earlier run").toHaveLength(0);

    // Destructured out, not `delete`d: forces the packaged-mode resolution branch (see file doc)
    // even if the invoking shell happens to have this set, without fighting ProcessEnv's optional
    // (`string | undefined`) index signature under electron.launch()'s stricter `{[k: string]: string}`.
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- destructured only to omit it below
    const { TIT_NATIVE_RUNTIME_DIR: _unused, ...restEnv } = process.env;

    app = await electron.launch({
      executablePath: APP_BIN as string,
      env: { ...restEnv, ...offscreenEnv(), TIT_USER_DATA_DIR: userDataDir, TIT_NATIVE_PROJECT_DIR: projectDir },
    });
    page = await app.firstWindow();

    // The launcher form is bypassed entirely: the window navigates straight to the natively-spawned
    // server's own origin, never app://launcher.
    await expect(page).not.toHaveURL(/^app:\/\/launcher/, { timeout: 20_000 });
    await expect(page.getByTestId("shell-content")).toBeVisible({ timeout: 20_000 });

    // "the shell connects (subjects table or the empty-project state)" — a fresh temp dir has no
    // subjects, so the empty state is the expected branch, but either is accepted (a leftover
    // `~/.local/state`-style cache is not this spec's concern).
    await expect(page.getByTestId("overview-table").or(page.getByText("No subjects found in this project yet."))).toBeVisible({
      timeout: 20_000,
    });

    // Independently verified against the spawned server itself, not only the page's own fetch of
    // it — the page origin *is* the native server's origin in this mode (no dev proxy involved).
    const origin = new URL(page.url()).origin;
    const health = await page.request.get(`${origin}/api/health`);
    expect(health.ok()).toBe(true);
    expect((await health.json()).status).toBe("ok");

    const version = await page.request.get(`${origin}/api/version`);
    expect(version.ok()).toBe(true);
    const versionBody = await version.json();
    expect(versionBody.tit_version).toBeTruthy();

    const running = pgrepServerPids();
    expect(running.length, "the native tit.server child is actually running while the app is open").toBeGreaterThan(0);

    await app.close();
    app = undefined;
    // The process tree kill (nativeRuntime.ts `stop()`) is async relative to the window closing;
    // give it the same grace window `stop()` itself budgets before escalating to SIGKILL.
    await new Promise((resolve) => setTimeout(resolve, 2000));

    const afterQuit = pgrepServerPids();
    expect(afterQuit, "no orphaned native server process after the app quits").toHaveLength(0);
  });
});
