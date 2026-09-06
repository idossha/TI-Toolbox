/**
 * Finding and launching the **host-installed Tetravox desktop app** (V2/V3,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * The embed is gone. Viewing a subject, a simulation or an analysis means opening a scene file in
 * an application that lives on the host, signs and notarises itself, and auto-updates through
 * electron-updater — none of which this app has to do, know about, or ship. Everything here is
 * the small amount of glue that costs: where that app is, and how to hand it a file.
 *
 * ## The launch contract, as measured in the Tetravox repo at 0.3.11 (2026-09-06)
 *
 * 1. **A scene is a `*.tetravox.json`.** `packages/app/src/main/menu.ts::isScenePath` is
 *    `/\.tetravox\.json$/i` and nothing else; `packages/app/src/main/scene-io.ts` exports
 *    `SCENE_EXTENSION = 'tetravox.json'`; `electron-builder.yml` registers that compound
 *    extension `role: Editor, rank: Owner`, so a double-click reaches the app on every platform.
 *    A file with any other suffix is classified as *data* (`splitScenes`) and the app tries to
 *    read the JSON as a volume. `tit/server/routes/viewers.py` writes the right suffix; this
 *    module refuses anything else rather than launch a failure.
 * 2. **Argv opens files.** `packages/app/src/main/cli.ts::collectCliPaths` takes every argv entry
 *    that is not `argv[0]`, not `-`-prefixed, not the value of `--job`/`--out`/`--tvx-search`/
 *    `--user-data-dir`, and not the app path itself, resolves it against cwd, and opens it. So
 *    `Tetravox <scene>` is the whole interface, and an absolute path is what to pass.
 * 3. **A second launch reuses the running window.** `packages/app/src/main/index.ts` takes
 *    `app.requestSingleInstanceLock()` (except under `--job`); a second process quits immediately
 *    and the first receives `second-instance`, which restores/focuses the window and routes the
 *    argv through `sendOpened` → `sendOpenScene`. So "Open" twice is two spawns and one window,
 *    and this module needs no notion of a running instance at all.
 * 4. **macOS also has `open-file`, and it is not enough on its own.** Launching by document
 *    (`open -a Tetravox <scene>`, or the Finder) fires `open-file`, handled before *and* after
 *    ready. `open -a` is still the right call — it hands the file to LaunchServices rather than
 *    starting a second copy of the binary — but there is a third state besides "not running" and
 *    "running with a window": **running with no window**, which is the normal state of a macOS
 *    app whose window you closed with ⌘W. In that state Tetravox's `open-file` handler finds
 *    `mainWindow === null` and *stores* the scene in its `startupScene` slot
 *    (`packages/app/src/main/index.ts`) without creating a window to drain it — so `open` exits 0,
 *    we report success, and nothing appears on screen. That was measured, not guessed
 *    (`dev/notes/v3-native-panes-external-viewer/TI.md` §7).
 *
 *    The fix is one more LaunchServices call: a plain `open -a Tetravox`, with no document, right
 *    after the one carrying the scene. That is an *activation*, which fires Electron's `activate`
 *    — and Tetravox's `activate` handler does create a window when there are none, which then
 *    pulls the `startupScene` the first call just set. With a window already open the second call
 *    only brings the app forward, which is what a person pressing "Open in Tetravox" wants
 *    anyway. Both orders were tried; this one is the one that works from all three states.
 * 5. **8 MB cap.** `MAX_SCENE_BYTES = 8 * 1024 * 1024` in `scene-io.ts`. Our scenes are a few KB
 *    of paths and windows — the volumes are referenced, never inlined — so this is headroom, not
 *    a constraint, but it is the number to remember if a scene ever grows a payload.
 *
 * ## Discovery
 *
 * **Managed install → user override → system locations.** The managed copy
 * (`./tetravoxInstall.ts`, `<userData>/tetravox/<version>/`) comes first because it is the one
 * TI-Toolbox is responsible for: it exists without the user doing anything, and it is the version
 * this app knows how to update. A Settings override still beats every *discovery* below it — a
 * user who names a path means it — and a system-installed copy is honoured last, so someone who
 * already had Tetravox before installing the managed one is not surprised by which opens.
 */
import { spawn } from "node:child_process";
import { runCommand } from "./tetravoxInstall";
import { accessSync, constants, existsSync, readFileSync } from "node:fs";
import { delimiter, join } from "node:path";
import { homedir } from "node:os";

/** Where "Download Tetravox" points when nothing is installed. */
export const TETRAVOX_RELEASES_URL = "https://github.com/idossha/tetravox/releases/latest";

/** The one extension the Tetravox app treats as a scene (see the module comment, point 1). */
export const SCENE_EXTENSION = ".tetravox.json";

export type HostPlatform = "darwin" | "win32" | "linux";

export interface TetravoxLocation {
  /** Absolute path to the `.app` bundle, `.exe` or executable. */
  path: string;
  /** `CFBundleShortVersionString` on macOS; `null` everywhere the platform does not say cheaply. */
  version: string | null;
  /**
   * `"managed"` — installed and maintained by TI-Toolbox itself (`./tetravoxInstall.ts`);
   * `"override"` — the path the user set in Settings; `"discovered"` — a copy the user installed.
   */
  source: "managed" | "override" | "discovered";
}

/**
 * Every place this platform might have put Tetravox, best first — pure, so the ordering is a unit
 * test and not a thing to reason about in front of a real filesystem.
 *
 * `env` is passed rather than read so a test can state a `PATH` and a `LOCALAPPDATA` instead of
 * inheriting the developer's.
 */
export function tetravoxCandidates(platform: HostPlatform, env: NodeJS.ProcessEnv, home: string): string[] {
  if (platform === "darwin") {
    return ["/Applications/Tetravox.app", join(home, "Applications", "Tetravox.app")];
  }
  if (platform === "win32") {
    const local = env.LOCALAPPDATA ?? join(home, "AppData", "Local");
    const programFiles = env.ProgramFiles ?? "C:\\Program Files";
    return [join(local, "Programs", "Tetravox", "Tetravox.exe"), join(programFiles, "Tetravox", "Tetravox.exe")];
  }
  // Linux: a distro package or an AppImage the user put on PATH. An AppImage sitting in
  // ~/Downloads with no PATH entry is exactly what the Settings override exists for.
  const fromPath = (env.PATH ?? "").split(delimiter).filter(Boolean).map((dir) => join(dir, "tetravox"));
  return [...fromPath, join(home, ".local", "bin", "tetravox"), "/usr/bin/tetravox", "/usr/local/bin/tetravox"];
}

function isUsable(candidate: string, platform: HostPlatform): boolean {
  if (!existsSync(candidate)) return false;
  if (platform === "darwin") return true; // a .app is a directory; existence is the check
  try {
    accessSync(candidate, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * `CFBundleShortVersionString` out of a macOS bundle's `Info.plist`.
 *
 * Read with a regex rather than a plist parser: this is a display string beside a path, it is
 * never compared, and a dependency for one line of one label would be the wrong trade. Any
 * failure — no bundle, no key, unreadable — answers `null`, which the UI renders as just the path.
 */
export function readMacBundleVersion(appPath: string): string | null {
  try {
    const plist = readFileSync(join(appPath, "Contents", "Info.plist"), "utf8");
    const match = /<key>CFBundleShortVersionString<\/key>\s*<string>([^<]+)<\/string>/.exec(plist);
    return match?.[1]?.trim() || null;
  } catch {
    return null;
  }
}

/** The installed app, or `null`. An `override` that does not exist is reported as *not* found. */
export function findTetravox(
  platform: HostPlatform,
  env: NodeJS.ProcessEnv,
  home: string,
  override: string | null,
  managed: { path: string; version: string | null } | null = null,
): TetravoxLocation | null {
  // A user who typed a path meant it, so an override outranks the managed copy; but an override
  // that no longer exists is not allowed to disable the viewer — it falls through, like any other
  // stale candidate.
  if (override && isUsable(override, platform)) {
    return { path: override, version: platform === "darwin" ? readMacBundleVersion(override) : null, source: "override" };
  }
  if (managed && isUsable(managed.path, platform)) {
    return { path: managed.path, version: managed.version, source: "managed" };
  }
  for (const candidate of tetravoxCandidates(platform, env, home)) {
    if (!isUsable(candidate, platform)) continue;
    return { path: candidate, version: platform === "darwin" ? readMacBundleVersion(candidate) : null, source: "discovered" };
  }
  return null;
}

export interface SpawnPlan {
  command: string;
  args: string[];
}

/**
 * What to run to open `scenePath` in the app at `appPath`.
 *
 * Pure and exported so the real-data gate can assert the argv **without launching anything** —
 * starting a GUI app in a test steals focus on the machine the test runs on, which is the one
 * thing an offscreen-by-default suite must never do.
 */
export function tetravoxSpawnPlan(platform: HostPlatform, appPath: string, scenePath: string): SpawnPlan {
  if (platform === "darwin") {
    // LaunchServices, not a second copy of the binary: `open -a` routes the document to the
    // running instance's `open-file` handler, which is the path the app is written for.
    return { command: "/usr/bin/open", args: ["-a", appPath, scenePath] };
  }
  return { command: appPath, args: [scenePath] };
}

/** Bring the app forward (and, with no window, make it create one). See point 4 above. */
export function tetravoxActivatePlan(platform: HostPlatform, appPath: string): SpawnPlan | null {
  return platform === "darwin" ? { command: "/usr/bin/open", args: ["-a", appPath] } : null;
}

export type LaunchResult =
  | { ok: true; command: string; args: string[]; activated: boolean }
  | { ok: false; reason: string };

/** How long a spawn is watched for an immediate failure (ENOENT, EACCES) before it is let go. */
const SPAWN_ERROR_GRACE_MS = 400;

/**
 * Open `scenePath` in the app at `appPath`, and **report what actually happened**.
 *
 * The first version of this spawned and forgot. That is right for the *app* — Tetravox outlives
 * TI-Toolbox, and an inherited stdio pipe would tie their lifetimes together — but it was wrong
 * for the *launcher*: on macOS the thing spawned is `/usr/bin/open`, a short-lived helper whose
 * exit code is the only signal that LaunchServices refused (a moved bundle, a damaged app, a
 * quarantined download). Swallowing it meant reporting "Opened …" for a launch that never
 * happened, which is exactly the bug this lane was sent to fix. So: `open` is awaited, and its
 * exit code and stderr are the result. Elsewhere the binary *is* the app, so it stays detached —
 * but the spawn is watched for `SPAWN_ERROR_GRACE_MS`, which is long enough for the errors that
 * arrive immediately (`ENOENT`, `EACCES`) and short enough not to delay a window.
 *
 * `run` is injectable so a test can assert the exact argv of both calls without launching a GUI
 * application on the machine running the suite.
 */
export async function launchTetravox(
  platform: HostPlatform,
  appPath: string,
  scenePath: string,
  run: (command: string, args: string[]) => Promise<{ ok: boolean; stderr: string }> = runCommand,
): Promise<LaunchResult> {
  if (!scenePath.endsWith(SCENE_EXTENSION)) {
    return { ok: false, reason: `a Tetravox scene must end in ${SCENE_EXTENSION}` };
  }
  const plan = tetravoxSpawnPlan(platform, appPath, scenePath);

  if (platform === "darwin") {
    const opened = await run(plan.command, plan.args);
    if (!opened.ok) {
      return { ok: false, reason: opened.stderr.trim() || `${plan.command} could not open ${appPath}` };
    }
    // The activation kick (point 4). A failure here is not a failed open: the scene has already
    // been handed over, and the worst case is an app that did not come to the front.
    const activate = tetravoxActivatePlan(platform, appPath);
    const activated = activate ? (await run(activate.command, activate.args)).ok : false;
    return { ok: true, command: plan.command, args: plan.args, activated };
  }

  try {
    const child = spawn(plan.command, plan.args, { detached: true, stdio: "ignore" });
    const failure = await new Promise<string | null>((resolve) => {
      const timer = setTimeout(() => resolve(null), SPAWN_ERROR_GRACE_MS);
      child.once("error", (error: Error) => {
        clearTimeout(timer);
        resolve(error.message);
      });
      child.once("spawn", () => {
        clearTimeout(timer);
        resolve(null);
      });
    });
    if (failure !== null) return { ok: false, reason: failure };
    child.unref();
    return { ok: true, command: plan.command, args: plan.args, activated: false };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** `findTetravox` against the live host. */
export function probeTetravox(
  platform: HostPlatform,
  override: string | null,
  managed: { path: string; version: string | null } | null = null,
): TetravoxLocation | null {
  return findTetravox(platform, process.env, homedir(), override, managed);
}
