/**
 * `src/main/viewer.ts` — the pure half of finding and launching the Tetravox desktop app
 * (V2/V3, `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * Everything asserted here is a *contract with another program*, read out of the Tetravox repo at
 * 0.3.11 and written down so a change on either side fails a test rather than a user's Open:
 *
 * - the scene extension (`packages/app/src/main/menu.ts::isScenePath`, `scene-io.ts`'s
 *   `SCENE_EXTENSION`, and the `fileAssociations` entry in `electron-builder.yml`),
 * - the argv shape (`packages/app/src/main/cli.ts::collectCliPaths`),
 * - `open -a` on macOS, so LaunchServices routes the document into the running instance's
 *   `open-file` handler rather than starting a second copy of the binary.
 *
 * `launchTetravox` itself is exercised only through its *refusal* path. Spawning a GUI app in a
 * unit test would steal focus on the machine running it, which this suite never does.
 */
import { describe, expect, it } from "vitest";
import {
  SCENE_EXTENSION,
  findTetravox,
  launchTetravox,
  readMacBundleVersion,
  tetravoxCandidates,
  tetravoxSpawnPlan,
} from "../../src/main/viewer";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("the scene extension", () => {
  it("is the compound extension the Tetravox app actually claims", () => {
    // `isScenePath` in the app is /\.tetravox\.json$/i and nothing else. `.tvx.json` — the working
    // name in the plan — is classified as *data* and read as a volume: a failure with no error.
    expect(SCENE_EXTENSION).toBe(".tetravox.json");
  });
});

describe("tetravoxCandidates", () => {
  it("looks in /Applications first on macOS, then the user's own", () => {
    expect(tetravoxCandidates("darwin", {}, "/Users/me")).toEqual([
      "/Applications/Tetravox.app",
      "/Users/me/Applications/Tetravox.app",
    ]);
  });

  it("uses LOCALAPPDATA on Windows, and falls back to the profile when it is unset", () => {
    expect(tetravoxCandidates("win32", { LOCALAPPDATA: "D:\\Local" }, "C:\\Users\\me")[0]).toBe(
      join("D:\\Local", "Programs", "Tetravox", "Tetravox.exe"),
    );
    expect(tetravoxCandidates("win32", {}, "C:\\Users\\me")[0]).toBe(
      join("C:\\Users\\me", "AppData", "Local", "Programs", "Tetravox", "Tetravox.exe"),
    );
  });

  it("walks PATH in order on Linux before the conventional locations", () => {
    const candidates = tetravoxCandidates("linux", { PATH: "/opt/bin:/usr/bin" }, "/home/me");
    expect(candidates.slice(0, 2)).toEqual(["/opt/bin/tetravox", "/usr/bin/tetravox"]);
    expect(candidates).toContain("/home/me/.local/bin/tetravox");
  });

  it("does not crash without a PATH — an empty environment is a normal one", () => {
    expect(() => tetravoxCandidates("linux", {}, "/home/me")).not.toThrow();
  });
});

describe("findTetravox", () => {
  it("prefers a usable override, and labels it as one", () => {
    const dir = mkdtempSync(join(tmpdir(), "tvx-"));
    const app = join(dir, "Tetravox.app");
    mkdirSync(join(app, "Contents"), { recursive: true });
    const found = findTetravox("darwin", {}, "/Users/nobody", app);
    expect(found).not.toBeNull();
    expect(found?.path).toBe(app);
    expect(found?.source).toBe("override");
  });

  it("never reports a stale override as the app it found", () => {
    // Trusting the string would spawn a path that does not exist and report success, so the user
    // sees a button that does nothing and a Settings card saying it is installed. A stale override
    // falls through to discovery instead of disabling the feature: the app may well still be in
    // /Applications, and refusing to look would punish the user for an old setting.
    const found = findTetravox("darwin", {}, "/Users/nobody", "/nope/Tetravox.app");
    expect(found?.path).not.toBe("/nope/Tetravox.app");
    expect(found?.source).not.toBe("override");
  });

  it("finds nothing when nothing is installed, rather than guessing", () => {
    expect(findTetravox("linux", { PATH: "/nowhere" }, "/home/nobody", null)).toBeNull();
  });
});

describe("readMacBundleVersion", () => {
  it("reads CFBundleShortVersionString out of Info.plist", () => {
    const dir = mkdtempSync(join(tmpdir(), "tvx-plist-"));
    const app = join(dir, "Tetravox.app");
    mkdirSync(join(app, "Contents"), { recursive: true });
    writeFileSync(
      join(app, "Contents", "Info.plist"),
      "<plist><dict><key>CFBundleShortVersionString</key><string>0.3.11</string></dict></plist>",
    );
    expect(readMacBundleVersion(app)).toBe("0.3.11");
  });

  it("answers null rather than throwing when there is no plist", () => {
    expect(readMacBundleVersion("/definitely/not/here.app")).toBeNull();
  });
});

describe("tetravoxSpawnPlan", () => {
  it("goes through LaunchServices on macOS, so a second Open reuses the running window", () => {
    // `open -a` fires the app's `open-file` handler; running the binary directly relies on the
    // single-instance lock instead. Both work, but only this one is what the app is written for.
    expect(tetravoxSpawnPlan("darwin", "/Applications/Tetravox.app", "/data/x.tetravox.json")).toEqual({
      command: "/usr/bin/open",
      args: ["-a", "/Applications/Tetravox.app", "/data/x.tetravox.json"],
    });
  });

  it("passes the scene as the only argument elsewhere — `collectCliPaths` takes it from argv", () => {
    expect(tetravoxSpawnPlan("linux", "/usr/bin/tetravox", "/data/x.tetravox.json")).toEqual({
      command: "/usr/bin/tetravox",
      args: ["/data/x.tetravox.json"],
    });
    expect(tetravoxSpawnPlan("win32", "C:\\Tetravox.exe", "D:\\x.tetravox.json").args).toEqual(["D:\\x.tetravox.json"]);
  });

  it("never passes the scene as something option-shaped", () => {
    // `collectCliPaths` drops every argv entry starting with `-`, so a scene path that looked like
    // a switch would be silently ignored and the app would open empty. Our scene paths are always
    // absolute, but the last argument is the one to hold to it. (`-a` on macOS is ours, and is
    // consumed by `open`, not by Tetravox.)
    for (const platform of ["darwin", "linux", "win32"] as const) {
      const plan = tetravoxSpawnPlan(platform, "/Applications/Tetravox.app", "/data/x.tetravox.json");
      expect(plan.args.at(-1)).toBe("/data/x.tetravox.json");
      expect(plan.args.at(-1)?.startsWith("-")).toBe(false);
    }
  });
});

describe("launchTetravox", () => {
  it("refuses a file the app would not treat as a scene, without spawning anything", () => {
    const result = launchTetravox("darwin", "/Applications/Tetravox.app", "/data/x.tvx.json");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toContain(".tetravox.json");
  });
});
