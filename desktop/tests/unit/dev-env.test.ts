/**
 * `.env.dev` parsing and validation (`scripts/devEnv.ts`).
 *
 * Every case here is a way `npm run dev` could otherwise start against the wrong thing without
 * saying so: a missing project directory (the one variable with no safe default), a typo'd port
 * that `Number()` turns into `NaN`, a `TIT_DEV_MOUNT_REPO=maybe` silently read as false — which
 * would run the image's baked-in `tit` while the developer edits the worktree — and the
 * shell-beats-file precedence that makes `TIT_DEV_PORT=8766 npm run dev` mean what it says.
 */
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DevConfigError, loadDevConfig, mergeDevEnv, parseDotenv, resolveDevConfig } from "../../scripts/devEnv";

const projectDir = mkdtempSync(join(tmpdir(), "tit-devenv-project-"));

describe("parseDotenv", () => {
  it("reads KEY=value, skipping blanks, comments and lines with no '='", () => {
    expect(
      parseDotenv(["# a comment", "", "TIT_DEV_PORT=8766", "not a setting", "  TIT_DEV_IMAGE_TAG = v3.0.0-dev  "].join("\n")),
    ).toEqual({ TIT_DEV_PORT: "8766", TIT_DEV_IMAGE_TAG: "v3.0.0-dev" });
  });

  it("removes one layer of matching quotes so a path with spaces can be written", () => {
    expect(parseDotenv('TIT_DEV_PROJECT_DIR="/Users/me/my data/000"')).toEqual({ TIT_DEV_PROJECT_DIR: "/Users/me/my data/000" });
    expect(parseDotenv("TIT_DEV_PROJECT_DIR='/tmp/x'")).toEqual({ TIT_DEV_PROJECT_DIR: "/tmp/x" });
  });

  it("keeps '=' inside a value (a token or a URL is not two settings)", () => {
    expect(parseDotenv("K=a=b=c")).toEqual({ K: "a=b=c" });
  });
});

describe("mergeDevEnv — the shell wins over the file", () => {
  it("lets a one-off shell value override the file", () => {
    expect(mergeDevEnv({ TIT_DEV_PORT: "8765" }, { TIT_DEV_PORT: "8766" }).TIT_DEV_PORT).toBe("8766");
  });

  it("ignores an exported-but-empty shell variable rather than blanking the file's value", () => {
    expect(mergeDevEnv({ TIT_DEV_IMAGE_TAG: "dev" }, { TIT_DEV_IMAGE_TAG: "" }).TIT_DEV_IMAGE_TAG).toBe("dev");
  });

  it("takes a variable the file never mentioned from the shell", () => {
    expect(mergeDevEnv({}, { TIT_DEV_PROJECT_DIR: "/tmp/000" }).TIT_DEV_PROJECT_DIR).toBe("/tmp/000");
  });
});

describe("resolveDevConfig", () => {
  it("fills in every default around the one required variable", () => {
    expect(resolveDevConfig({ TIT_DEV_PROJECT_DIR: projectDir }, "/desktop")).toEqual({
      projectDir,
      imageTag: "dev",
      port: 8765,
      mountRepo: true,
    });
  });

  it("names the fix when TIT_DEV_PROJECT_DIR is missing", () => {
    expect(() => resolveDevConfig({}, "/desktop")).toThrow(DevConfigError);
    expect(() => resolveDevConfig({}, "/desktop")).toThrow(/\.env\.dev\.example/);
  });

  it("refuses a project directory that does not exist, rather than letting Docker create it", () => {
    // A bind mount whose source is missing is created by Docker as an empty root-owned directory;
    // the server then reports a project with no subjects and nothing says the path was wrong.
    expect(() => resolveDevConfig({ TIT_DEV_PROJECT_DIR: join(projectDir, "nope") }, "/desktop")).toThrow(/does not exist/);
  });

  it("resolves a relative project directory against desktop/", () => {
    const parent = mkdtempSync(join(tmpdir(), "tit-devenv-rel-"));
    mkdirSync(join(parent, "desktop"));
    mkdirSync(join(parent, "data"));
    expect(resolveDevConfig({ TIT_DEV_PROJECT_DIR: "../data" }, join(parent, "desktop")).projectDir).toBe(join(parent, "data"));
  });

  it("rejects a port that is not a port", () => {
    for (const bad of ["eight", "0", "70000", "8765.5"]) {
      expect(() => resolveDevConfig({ TIT_DEV_PROJECT_DIR: projectDir, TIT_DEV_PORT: bad }, "/d")).toThrow(/TIT_DEV_PORT/);
    }
    expect(resolveDevConfig({ TIT_DEV_PROJECT_DIR: projectDir, TIT_DEV_PORT: "8766" }, "/d").port).toBe(8766);
  });

  it("reads the documented spellings of TIT_DEV_MOUNT_REPO and rejects the rest", () => {
    const of = (v: string): boolean => resolveDevConfig({ TIT_DEV_PROJECT_DIR: projectDir, TIT_DEV_MOUNT_REPO: v }, "/d").mountRepo;
    expect([of("1"), of("true"), of("YES"), of("on")]).toEqual([true, true, true, true]);
    expect([of("0"), of("false"), of("no"), of("off")]).toEqual([false, false, false, false]);
    expect(() => of("maybe")).toThrow(/TIT_DEV_MOUNT_REPO must be 1 or 0/);
  });
});

describe("loadDevConfig", () => {
  it("reads desktop/.env.dev, and works with no file at all when the shell carries the values", () => {
    const desktop = mkdtempSync(join(tmpdir(), "tit-devenv-desktop-"));
    expect(loadDevConfig(desktop, { TIT_DEV_PROJECT_DIR: projectDir }).imageTag).toBe("dev");
    writeFileSync(join(desktop, ".env.dev"), `TIT_DEV_PROJECT_DIR=${projectDir}\nTIT_DEV_IMAGE_TAG=v3.0.0-dev\nTIT_DEV_PORT=8790\n`);
    expect(loadDevConfig(desktop, {})).toEqual({ projectDir, imageTag: "v3.0.0-dev", port: 8790, mountRepo: true });
    expect(loadDevConfig(desktop, { TIT_DEV_PORT: "8766" }).port).toBe(8766);
  });
});
