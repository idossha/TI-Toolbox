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
 * 4. **macOS also has `open-file`.** Launching by document (`open -a Tetravox <scene>`, or the
 *    Finder) fires `open-file`, handled before *and* after ready — before, it fills the startup
 *    scene slot; after, it goes down the same `sendOpened` path. `open -a` is preferred on macOS
 *    because it hands the file to LaunchServices rather than starting a second copy of the
 *    binary, which is what the app's own single-instance handling expects of a GUI app.
 * 5. **8 MB cap.** `MAX_SCENE_BYTES = 8 * 1024 * 1024` in `scene-io.ts`. Our scenes are a few KB
 *    of paths and windows — the volumes are referenced, never inlined — so this is headroom, not
 *    a constraint, but it is the number to remember if a scene ever grows a payload.
 *
 * ## Discovery
 *
 * A path the user set in Settings wins; then the platform's conventional install locations. There
 * is deliberately no download, no bundling and no version pin: the app updates itself, and this
 * one has no business deciding when.
 */
import { spawn } from "node:child_process";
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
  /** `"override"` when it came from the user's own setting, else `"discovered"`. */
  source: "override" | "discovered";
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
): TetravoxLocation | null {
  if (override && isUsable(override, platform)) {
    return { path: override, version: platform === "darwin" ? readMacBundleVersion(override) : null, source: "override" };
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

export type LaunchResult = { ok: true; command: string; args: string[] } | { ok: false; reason: string };

/**
 * Spawn detached and forget.
 *
 * Detached with stdio ignored and `unref()` because Tetravox outlives this app: a user who quits
 * TI-Toolbox with a scene open should keep the scene open, and an inherited stdio pipe would tie
 * the two processes' lifetimes together for no benefit. Errors after the spawn call are therefore
 * not observable here — which is correct, since a GUI app that fails to start says so on screen.
 */
export function launchTetravox(platform: HostPlatform, appPath: string, scenePath: string): LaunchResult {
  if (!scenePath.endsWith(SCENE_EXTENSION)) {
    return { ok: false, reason: `a Tetravox scene must end in ${SCENE_EXTENSION}` };
  }
  const plan = tetravoxSpawnPlan(platform, appPath, scenePath);
  try {
    const child = spawn(plan.command, plan.args, { detached: true, stdio: "ignore" });
    child.unref();
    return { ok: true, command: plan.command, args: plan.args };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** `findTetravox` against the live host. */
export function probeTetravox(platform: HostPlatform, override: string | null): TetravoxLocation | null {
  return findTetravox(platform, process.env, homedir(), override);
}
