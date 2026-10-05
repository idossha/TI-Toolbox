/**
 * Host <-> container path rules (`src/shared/paths.ts`).
 *
 * The cross-language cases come from `tests/fixtures/host_paths.json` (groundTruth: authored),
 * which `tests/test_host_path_table.py` reads for `tit/host_path.py` too, so the two cannot drift.
 * Below the table: TS-only behaviour (case folding per host platform, WSL shares, unknown root).
 * CI runs this file on windows-latest as well as Linux and macOS.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  containerToHostPath,
  hasDotSegment,
  hostToContainerPath,
  projectDirName,
  type HostPlatform,
} from "../../src/shared/paths";

interface Table {
  to_host: { why: string; container: string; container_root: string; host_root: string; platform: HostPlatform; expected: string | null }[];
  to_container: { why: string; host: string; host_root: string; container_root: string; platform: HostPlatform; expected: string | null }[];
  project_dir_name: { host_dir: string; expected: string | null }[];
}

const table = JSON.parse(
  readFileSync(new URL("../../../tests/fixtures/host_paths.json", import.meta.url), "utf-8"),
) as Table;

describe("shared host path table", () => {
  it("has cases to check", () => {
    expect(table.to_host.length && table.to_container.length && table.project_dir_name.length).toBeTruthy();
  });

  it.each(table.to_host)("containerToHostPath: $why", (c) => {
    expect(containerToHostPath(c.container, c.container_root, c.host_root, c.platform)).toBe(c.expected);
  });

  it.each(table.to_container)("hostToContainerPath: $why", (c) => {
    expect(hostToContainerPath(c.host, c.host_root, c.container_root, c.platform)).toBe(c.expected);
  });

  it.each(table.project_dir_name)("projectDirName($host_dir)", (c) => {
    if (c.expected === null) expect(() => projectDirName(c.host_dir)).toThrow(/no name/);
    else expect(projectDirName(c.host_dir)).toBe(c.expected);
  });
});

describe("platform case folding", () => {
  it("folds case on macOS (APFS default) and keeps the root's own casing on the way back", () => {
    expect(hostToContainerPath("/users/ido/DATASETS/000/a.txt", "/Users/Ido/datasets/000", "/mnt/000", "darwin")).toBe("/mnt/000/a.txt");
    expect(containerToHostPath("/mnt/000/a.txt", "/mnt/000", "/Users/Ido/datasets/000", "darwin")).toBe("/Users/Ido/datasets/000/a.txt");
  });

  it("is case-sensitive on Linux", () => {
    expect(hostToContainerPath("/home/ido/DATASETS/000/a.txt", "/home/ido/datasets/000", "/mnt/000", "linux")).toBeNull();
  });
});

describe("WSL UNC roots", () => {
  const root = "\\\\wsl.localhost\\Ubuntu\\home\\ido\\datasets\\000";

  it("round-trips through the UNC form", () => {
    expect(hostToContainerPath(`${root}\\sub\\a.txt`, root, "/mnt/000", "win32")).toBe("/mnt/000/sub/a.txt");
    expect(containerToHostPath("/mnt/000/sub/a.txt", "/mnt/000", root, "win32")).toBe(`${root}\\sub\\a.txt`);
  });

  it("treats a different distro (different share) as outside", () => {
    expect(hostToContainerPath("\\\\wsl.localhost\\Debian\\home\\ido\\datasets\\000\\a.txt", root, "/mnt/000", "win32")).toBeNull();
  });
});

describe("unknown host root (Project.host_path was null)", () => {
  it("maps nothing", () => {
    expect(containerToHostPath("/data/project/a.txt", "/data/project", null, "darwin")).toBeNull();
    expect(hostToContainerPath("/Users/ido/000/a.txt", null, "/data/project", "darwin")).toBeNull();
  });
});

describe("hasDotSegment (ra_14 finding 3)", () => {
  it.each([
    ["/mnt/proj/../etc/passwd"],
    ["/mnt/proj/./secret"],
    ["..\\..\\Windows\\System32"],
    [".\\config"],
    ["/mnt/proj/a/../../outside"],
    [".."],
    ["."],
    ["/mnt/proj/a/..\\b"], // mixed separators
  ])("flags %s", (path) => {
    expect(hasDotSegment(path)).toBe(true);
  });

  it.each([
    ["/mnt/proj/derivatives/x.nii.gz"],
    ["/mnt/proj/a..b/file.txt"], // a dot *inside* a segment, not the whole segment
    ["/mnt/proj/..hidden/file"], // dotfile-style prefix, not a literal ".." segment
    ["/mnt/proj"],
    [""],
  ])("does not flag %s", (path) => {
    expect(hasDotSegment(path)).toBe(false);
  });
});
