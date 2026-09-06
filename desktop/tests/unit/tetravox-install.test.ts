/**
 * `src/main/tetravoxInstall.ts` — the managed Tetravox install
 * (V6, `dev/notes/v3-native-panes-external-viewer/TI.md`).
 *
 * Everything here runs against a **real loopback HTTP server** serving a real release index, a
 * real `latest-linux.yml` and a real asset, because the property under test is a chain — resolve,
 * download, hash, compare, materialise, rename — and a mocked `fetch` would prove the shape of the
 * calls rather than the outcome on disk. The digests are computed from the served bytes, so a
 * change to the hashing or to the manifest parser fails here rather than at a user's first launch.
 *
 * The Linux AppImage target is the one exercised end to end: it is the only platform whose
 * materialise step is pure Node (rename + chmod), so these tests need no `ditto`, no `codesign`
 * and no NSIS, and they pass identically on a CI Linux box and on a developer's Mac. The
 * macOS-specific steps are asserted through the injected `run`, which records the exact argv.
 */
import { afterEach, describe, expect, it } from "vitest";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  activatePending,
  assetNameFor,
  checkIsDue,
  compareVersions,
  createManagedTetravox,
  detectTarget,
  executableIn,
  installRelease,
  installedVersions,
  manifestNameFor,
  pickRelease,
  pruneVersions,
  readState,
  releaseIndexUrl,
  runCommand,
  sha512FromManifest,
  versionFromTag,
  type ResolvedRelease,
} from "../../src/main/tetravoxInstall";

// ── a fake releases API, standing in for GitHub ──────────────────────────────────────────────

interface FakeRelease {
  version: string;
  bytes: Buffer;
  /** Overrides the digest written into the manifest, to test the mismatch path. */
  manifestDigest?: string;
}

const servers: Server[] = [];

afterEach(() => {
  for (const server of servers.splice(0)) server.close();
});

function base64Sha512(bytes: Buffer): string {
  return createHash("sha512").update(bytes).digest("base64");
}

/**
 * Serve `/releases`, `/download/<version>/<asset>` and `/download/<version>/latest-linux.yml`.
 *
 * `extra` lets a test add a draft or a prerelease to the index without changing what is
 * downloadable, which is exactly the situation the resolver has to survive.
 */
async function startFakeApi(releases: FakeRelease[], extra: Record<string, unknown>[] = []): Promise<string> {
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    if (url.pathname === "/releases") {
      const body = [
        ...releases.map((release) => ({
          tag_name: `v${release.version}`,
          draft: false,
          prerelease: false,
          assets: [
            {
              name: assetNameFor("linux-x64", release.version),
              browser_download_url: `${base}/download/${release.version}/${assetNameFor("linux-x64", release.version)}`,
            },
            { name: "latest-linux.yml", browser_download_url: `${base}/download/${release.version}/latest-linux.yml` },
          ],
        })),
        ...extra,
      ];
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
      return;
    }
    const match = /^\/download\/([^/]+)\/(.+)$/.exec(url.pathname);
    const release = match ? releases.find((r) => r.version === match[1]) : undefined;
    if (!match || !release) {
      res.writeHead(404).end();
      return;
    }
    if (match[2] === "latest-linux.yml") {
      const asset = assetNameFor("linux-x64", release.version);
      const digest = release.manifestDigest ?? base64Sha512(release.bytes);
      res.writeHead(200, { "content-type": "text/yaml" });
      res.end(
        `version: ${release.version}\nfiles:\n  - url: ${asset}\n    sha512: ${digest}\n    size: ${release.bytes.length}\n` +
          `path: ${asset}\nsha512: ${digest}\n`,
      );
      return;
    }
    res.writeHead(200, { "content-type": "application/octet-stream", "content-length": String(release.bytes.length) });
    res.end(release.bytes);
  });
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}/releases`;
}

function fakeAsset(version: string): Buffer {
  // Deliberately not a real AppImage: the AppImage path never opens the file, it renames and
  // chmods it, so the bytes only have to be stable and hashable.
  return Buffer.from(`#!/bin/sh\n# fake Tetravox ${version}\nexit 0\n`);
}

function tempRoot(): string {
  return mkdtempSync(join(tmpdir(), "tvx-managed-"));
}

async function managedFor(root: string, indexUrl: string) {
  return createManagedTetravox({ root, platform: "linux", arch: "x64", env: { TIT_TETRAVOX_RELEASE_INDEX: indexUrl } });
}

// ── the pure half ────────────────────────────────────────────────────────────────────────────

describe("platform targeting", () => {
  it("names the one asset each supported platform installs", () => {
    expect(assetNameFor("mac-arm64", "0.3.11")).toBe("Tetravox-0.3.11-mac-arm64.zip");
    expect(assetNameFor("mac-x64", "0.3.11")).toBe("Tetravox-0.3.11-mac-x64.zip");
    expect(assetNameFor("win-x64", "0.3.11")).toBe("Tetravox-0.3.11-win-x64.exe");
    expect(assetNameFor("linux-x64", "0.3.11")).toBe("Tetravox-0.3.11-linux-x86_64.AppImage");
  });

  it("points each platform at the electron-updater manifest that carries its digest", () => {
    expect(manifestNameFor("mac-arm64")).toBe("latest-mac.yml");
    expect(manifestNameFor("mac-x64")).toBe("latest-mac.yml");
    expect(manifestNameFor("win-x64")).toBe("latest.yml");
    expect(manifestNameFor("linux-x64")).toBe("latest-linux.yml");
  });

  it("answers null where Tetravox publishes no build, rather than guessing an asset name", () => {
    expect(detectTarget("darwin", "arm64")).toBe("mac-arm64");
    expect(detectTarget("linux", "x64")).toBe("linux-x64");
    expect(detectTarget("linux", "arm64")).toBeNull();
    expect(detectTarget("win32", "ia32")).toBeNull();
    expect(detectTarget("freebsd", "x64")).toBeNull();
  });
});

describe("the release index", () => {
  it("skips drafts and prereleases — nobody opted into a release candidate of a viewer", () => {
    const index = [
      { tag_name: "v0.4.0", draft: true, assets: [] },
      { tag_name: "v0.4.0-rc.1", prerelease: true, assets: [] },
      { tag_name: "v0.3.11", draft: false, prerelease: false, assets: [] },
    ];
    expect(pickRelease(index)?.version).toBe("0.3.11");
  });

  it("takes the newest by version, not by position — the index is ordered by date", () => {
    const index = [
      { tag_name: "v0.3.9", assets: [] },
      { tag_name: "v0.3.11", assets: [] },
      { tag_name: "v0.3.10", assets: [] },
    ];
    expect(pickRelease(index)?.version).toBe("0.3.11");
    expect(compareVersions("0.3.11", "0.3.9")).toBeGreaterThan(0);
    expect(compareVersions("0.3.11", "0.3.11")).toBe(0);
  });

  it("ignores a tag that is not a version, and an index that is not a list", () => {
    expect(versionFromTag("nightly")).toBeNull();
    expect(versionFromTag("v1.2.3")).toBe("1.2.3");
    expect(pickRelease({ message: "Not Found" })).toBeNull();
    expect(pickRelease([{ tag_name: "nightly", assets: [] }])).toBeNull();
  });

  it("is overridable, so a mirror or a test can stand in for GitHub", () => {
    expect(releaseIndexUrl({})).toContain("api.github.com/repos/idossha/tetravox/releases");
    expect(releaseIndexUrl({ TIT_TETRAVOX_RELEASE_INDEX: "http://127.0.0.1:1/r" })).toBe("http://127.0.0.1:1/r");
  });
});

describe("sha512FromManifest", () => {
  // The real 0.3.11 manifests, byte for byte, so a change in electron-updater's writer is caught
  // by this suite rather than by a user whose download silently fails to verify.
  const macYml = [
    "version: 0.3.11",
    "files:",
    "  - url: Tetravox-0.3.11-mac-x64.zip",
    "    sha512: gEZCj7HK1W8zdz5OQgfp8dTpfGXIcDRmCr6zPY2zrfhAUWt04X1lQOwqPWMbyIDDDJXRM3FE2CdIDWCPngNGnw==",
    "    size: 137036668",
    "  - url: Tetravox-0.3.11-mac-arm64.zip",
    "    sha512: Xe2yC01SVdY2o4lE7gWTrTdtHIRu38wmIcLVNR1zrjzg1o4Prd4pVoLELtkojF10YuqbHHsSKDZebFrf8fIGeA==",
    "    size: 131342353",
    "path: Tetravox-0.3.11-mac-x64.zip",
    "sha512: gEZCj7HK1W8zdz5OQgfp8dTpfGXIcDRmCr6zPY2zrfhAUWt04X1lQOwqPWMbyIDDDJXRM3FE2CdIDWCPngNGnw==",
    "releaseDate: '2026-09-04T21:36:45.256Z'",
  ].join("\n");

  it("reads the digest of the asset asked for, not the first one in the file", () => {
    expect(sha512FromManifest(macYml, "Tetravox-0.3.11-mac-arm64.zip")).toBe(
      "Xe2yC01SVdY2o4lE7gWTrTdtHIRu38wmIcLVNR1zrjzg1o4Prd4pVoLELtkojF10YuqbHHsSKDZebFrf8fIGeA==",
    );
    expect(sha512FromManifest(macYml, "Tetravox-0.3.11-mac-x64.zip")).toBe(
      "gEZCj7HK1W8zdz5OQgfp8dTpfGXIcDRmCr6zPY2zrfhAUWt04X1lQOwqPWMbyIDDDJXRM3FE2CdIDWCPngNGnw==",
    );
  });

  it("answers null for an asset the manifest does not list — the install then refuses", () => {
    expect(sha512FromManifest(macYml, "Tetravox-0.3.11-linux-x86_64.AppImage")).toBeNull();
  });

  it("reads a single-file manifest, where the digest is stated at the top level too", () => {
    const winYml = [
      "version: 0.3.11",
      "files:",
      "  - url: Tetravox-0.3.11-win-x64.exe",
      "    sha512: vJ0k+5PBUVjRW1VMtTx7mc3vd0N+bHQgRtbwqa1i7STBOnsg196a8nj66MT55Pn3JM+qoMPcPdf5/0eGDa0R2w==",
      "    size: 114295520",
      "path: Tetravox-0.3.11-win-x64.exe",
      "sha512: vJ0k+5PBUVjRW1VMtTx7mc3vd0N+bHQgRtbwqa1i7STBOnsg196a8nj66MT55Pn3JM+qoMPcPdf5/0eGDa0R2w==",
    ].join("\n");
    expect(sha512FromManifest(winYml, "Tetravox-0.3.11-win-x64.exe")).toBe(
      "vJ0k+5PBUVjRW1VMtTx7mc3vd0N+bHQgRtbwqa1i7STBOnsg196a8nj66MT55Pn3JM+qoMPcPdf5/0eGDa0R2w==",
    );
  });
});

// ── the whole chain, over loopback ───────────────────────────────────────────────────────────

describe("a fresh install", () => {
  it("downloads, verifies and lands one runnable version with current.json pointing at it", async () => {
    const bytes = fakeAsset("0.3.11");
    const index = await startFakeApi([{ version: "0.3.11", bytes }]);
    const root = tempRoot();
    const managed = await managedFor(root, index);

    const outcome = await managed.ensureInstalled();

    expect(outcome.version).toBe("0.3.11");
    expect(outcome.pending).toBe(false);
    const binary = executableIn(join(root, "0.3.11"), "linux-x64");
    expect(existsSync(binary)).toBe(true);
    expect(readFileSync(binary, "utf8")).toBe(bytes.toString());
    // An AppImage that is not executable is an install that silently cannot launch.
    expect(statSync(binary).mode & 0o111).not.toBe(0);
    const state = await readState(root);
    expect(state.version).toBe("0.3.11");
    expect(state.pending).toBeNull();
    expect(state.lastCheckedAt).not.toBeNull();
    expect(managed.location()?.path).toBe(binary);
  });

  it("reports progress it can be shown by, and leaves no staging directory behind", async () => {
    const index = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    const root = tempRoot();
    const phases: string[] = [];
    const managed = createManagedTetravox({
      root,
      platform: "linux",
      arch: "x64",
      env: { TIT_TETRAVOX_RELEASE_INDEX: index },
      onProgress: (event) => phases.push(event.phase),
    });
    await managed.ensureInstalled();
    expect(phases).toContain("downloading");
    expect(phases).toContain("verifying");
    expect(phases).toContain("installing");
    expect(phases.at(-1)).toBe("done");
    expect(await installedVersions(root)).toEqual(["0.3.11"]);
  });

  it("joins an install already in flight rather than starting a second download", async () => {
    const index = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    const managed = await managedFor(tempRoot(), index);
    const [a, b] = await Promise.all([managed.ensureInstalled(), managed.ensureInstalled()]);
    expect(a).toBe(b);
  });
});

describe("an update", () => {
  it("keeps two versions, does not disturb the running one, and activates on the next launch", async () => {
    const root = tempRoot();
    const first = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    await (await managedFor(root, first)).ensureInstalled();

    const second = await startFakeApi([
      { version: "0.3.11", bytes: fakeAsset("0.3.11") },
      { version: "0.3.12", bytes: fakeAsset("0.3.12") },
    ]);
    const managed = await managedFor(root, second);
    const result = await managed.checkNow();

    expect(result).toEqual({ checked: true, installed: "0.3.12" });
    // The new one is on disk but not active: whoever has 0.3.11 open keeps it.
    let state = await readState(root);
    expect(state.version).toBe("0.3.11");
    expect(state.pending).toBe("0.3.12");
    expect(managed.location()?.version).toBe("0.3.11");

    // The next launch of TI-Toolbox promotes it — one JSON write, no network.
    state = await activatePending(root, "linux-x64");
    expect(state.version).toBe("0.3.12");
    expect(state.pending).toBeNull();
    expect((await installedVersions(root)).sort()).toEqual(["0.3.11", "0.3.12"]);
  });

  it("prunes to the current version and the one before it", async () => {
    const root = tempRoot();
    for (const version of ["0.3.9", "0.3.10", "0.3.11", "0.3.12"]) {
      mkdirSync(join(root, version), { recursive: true });
      writeFileSync(executableIn(join(root, version), "linux-x64"), "x");
    }
    const removed = await pruneVersions(root, "0.3.12", 2);
    expect(removed.sort()).toEqual(["0.3.10", "0.3.9"]);
    expect(await installedVersions(root)).toEqual(["0.3.12", "0.3.11"]);
  });

  it("does nothing when the newest release is the one already installed", async () => {
    const root = tempRoot();
    const index = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    const managed = await managedFor(root, index);
    await managed.ensureInstalled();
    expect(await managed.checkNow()).toEqual({ checked: true, installed: null });
    expect(await installedVersions(root)).toEqual(["0.3.11"]);
  });

  it("checks at most once a day", () => {
    expect(checkIsDue(null)).toBe(true);
    expect(checkIsDue(new Date(Date.now() - 60_000).toISOString())).toBe(false);
    expect(checkIsDue(new Date(Date.now() - 25 * 3600_000).toISOString())).toBe(true);
    expect(checkIsDue("not a date")).toBe(true);
  });
});

describe("a download that does not match its digest", () => {
  it("installs nothing and replaces nothing", async () => {
    const root = tempRoot();
    const good = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    await (await managedFor(root, good)).ensureInstalled();

    const tampered = await startFakeApi([
      { version: "0.3.12", bytes: Buffer.from("tampered"), manifestDigest: base64Sha512(Buffer.from("what was published")) },
    ]);
    const managed = await managedFor(root, tampered);
    await expect(managed.ensureInstalled()).rejects.toThrow(/SHA-512/);

    expect(existsSync(join(root, "0.3.12"))).toBe(false);
    expect(await installedVersions(root)).toEqual(["0.3.11"]);
    expect((await readState(root)).version).toBe("0.3.11");
    // and nothing half-unpacked was left where a later run could mistake it for an install
    expect((await installedVersions(root)).every((v) => !v.startsWith("."))).toBe(true);
  });

  it("refuses a release whose manifest does not list this platform's asset", async () => {
    const release: ResolvedRelease = {
      version: "0.3.11",
      tag: "v0.3.11",
      assets: [{ name: "latest-linux.yml", url: "http://127.0.0.1:1/latest-linux.yml" }],
    };
    await expect(installRelease(tempRoot(), "linux-x64", release, {})).rejects.toThrow(/no build for this platform/);
  });
});

describe("offline", () => {
  it("keeps launching the version that is already installed", async () => {
    const root = tempRoot();
    const index = await startFakeApi([{ version: "0.3.11", bytes: fakeAsset("0.3.11") }]);
    const managed = await managedFor(root, index);
    await managed.ensureInstalled();

    // The whole world goes away — a closed port is the honest local stand-in for no network.
    const offline = createManagedTetravox({
      root,
      platform: "linux",
      arch: "x64",
      env: { TIT_TETRAVOX_RELEASE_INDEX: "http://127.0.0.1:1/releases" },
    });
    await offline.activate();
    expect(offline.location()?.version).toBe("0.3.11");
    expect(await offline.checkNow()).toEqual({ checked: false, installed: null });
    // still there, and still the one that launches
    expect(offline.location()?.path).toBe(executableIn(join(root, "0.3.11"), "linux-x64"));
    expect((await offline.summary()).version).toBe("0.3.11");
  });

  it("says so, once, when there is nothing installed and nothing reachable", async () => {
    const managed = createManagedTetravox({
      root: tempRoot(),
      platform: "linux",
      arch: "x64",
      env: { TIT_TETRAVOX_RELEASE_INDEX: "http://127.0.0.1:1/releases" },
    });
    await expect(managed.ensureInstalled()).rejects.toThrow(/could not reach the Tetravox release index/);
    expect(managed.location()).toBeNull();
  });
});

describe("an unsupported platform", () => {
  it("is a stated fact, not a silent no-op", async () => {
    const managed = createManagedTetravox({ root: tempRoot(), platform: "linux", arch: "arm64" });
    expect(managed.target).toBeNull();
    expect((await managed.summary()).supported).toBe(false);
    await expect(managed.ensureInstalled()).rejects.toThrow(/no build for this platform/);
    expect(await managed.checkNow()).toEqual({ checked: false, installed: null });
    // and `activate` is a no-op rather than a crash on a machine that can never have an install
    await expect(managed.activate()).resolves.toBeUndefined();
  });
});

describe("the macOS materialise step", () => {
  // `ditto`, `codesign` and `xattr` exist only on macOS, so the real chain runs there and the
  // argv is asserted everywhere.
  const onMac = process.platform === "darwin";

  it("uses ditto to unpack, codesign to decide, and xattr only after codesign passed", async () => {
    const root = tempRoot();
    // A fake .app with the structure the module looks for, zipped the way the release is.
    const staging = mkdtempSync(join(tmpdir(), "tvx-app-"));
    mkdirSync(join(staging, "Tetravox.app", "Contents", "MacOS"), { recursive: true });
    writeFileSync(join(staging, "Tetravox.app", "Contents", "Info.plist"), "<plist/>");
    const zip = join(staging, "asset.zip");
    if (onMac) {
      const { execFileSync } = await import("node:child_process");
      execFileSync("/usr/bin/ditto", ["-c", "-k", "--keepParent", join(staging, "Tetravox.app"), zip]);
    } else {
      writeFileSync(zip, "not a real zip");
    }
    const bytes = readFileSync(zip);

    const server = createServer((req, res) => {
      if ((req.url ?? "").endsWith("latest-mac.yml")) {
        res.writeHead(200, { "content-type": "text/yaml" });
        res.end(
          `version: 0.3.11\nfiles:\n  - url: Tetravox-0.3.11-mac-arm64.zip\n    sha512: ${base64Sha512(bytes)}\n    size: ${bytes.length}\n`,
        );
        return;
      }
      res.writeHead(200, { "content-length": String(bytes.length) }).end(bytes);
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const release: ResolvedRelease = {
      version: "0.3.11",
      tag: "v0.3.11",
      assets: [
        { name: "Tetravox-0.3.11-mac-arm64.zip", url: `${origin}/a.zip` },
        { name: "latest-mac.yml", url: `${origin}/latest-mac.yml` },
      ],
    };

    const calls: string[][] = [];
    const outcome = await installRelease(root, "mac-arm64", release, {
      run: async (command, args) => {
        calls.push([command, ...args]);
        if (command.endsWith("ditto")) {
          if (onMac) return runCommand(command, args);
          // Off macOS, stand in for ditto by creating what it would have produced.
          mkdirSync(join(args[3]!, "Tetravox.app", "Contents"), { recursive: true });
          return { ok: true, stderr: "" };
        }
        // An unsigned bundle: codesign says no, which is the interesting case.
        return { ok: false, stderr: "code object is not signed at all" };
      },
    });

    expect(outcome.path).toBe(join(root, "0.3.11", "Tetravox.app"));
    expect(existsSync(outcome.path)).toBe(true);
    expect(calls[0]?.[0]).toBe("/usr/bin/ditto");
    expect(calls[0]?.slice(1, 3)).toEqual(["-x", "-k"]);
    expect(calls[1]?.slice(0, 4)).toEqual(["/usr/bin/codesign", "--verify", "--deep", "--strict"]);
    // The property: quarantine is NOT stripped from a bundle whose signature did not verify.
    expect(calls.some((call) => call[0]?.endsWith("xattr"))).toBe(false);
  });

  it("strips quarantine once, and only once codesign has passed", async () => {
    const root = tempRoot();
    const bytes = Buffer.from("zip-ish");
    const server = createServer((req, res) => {
      if ((req.url ?? "").endsWith("latest-mac.yml")) {
        res.writeHead(200).end(`files:\n  - url: Tetravox-0.3.11-mac-arm64.zip\n    sha512: ${base64Sha512(bytes)}\n`);
        return;
      }
      res.writeHead(200).end(bytes);
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const calls: string[][] = [];
    await installRelease(
      root,
      "mac-arm64",
      {
        version: "0.3.11",
        tag: "v0.3.11",
        assets: [
          { name: "Tetravox-0.3.11-mac-arm64.zip", url: `${origin}/a.zip` },
          { name: "latest-mac.yml", url: `${origin}/latest-mac.yml` },
        ],
      },
      {
        run: async (command, args) => {
          calls.push([command, ...args]);
          if (command.endsWith("ditto")) mkdirSync(join(args[3]!, "Tetravox.app", "Contents"), { recursive: true });
          return { ok: true, stderr: "" };
        },
      },
    );
    // Both run against the *staged* bundle, before the rename into place: the extended attribute
    // travels with the directory, and a bundle is never moved into the versions tree until it has
    // been through both steps.
    expect(calls.at(-1)?.slice(0, 3)).toEqual(["/usr/bin/xattr", "-dr", "com.apple.quarantine"]);
    expect(calls.at(-1)?.[3]).toMatch(/\.staging-.*Tetravox\.app$/);
    expect(calls.filter((call) => call[0]?.endsWith("xattr"))).toHaveLength(1);
  });

  it("names the executable each platform's launcher will spawn", () => {
    expect(executableIn("/root/0.3.11", "mac-arm64")).toBe("/root/0.3.11/Tetravox.app");
    expect(executableIn("/root/0.3.11", "win-x64")).toBe("/root/0.3.11/Tetravox.exe");
    expect(executableIn("/root/0.3.11", "linux-x64")).toBe("/root/0.3.11/Tetravox.AppImage");
  });
});

describe("the Windows materialise step", () => {
  it("runs the NSIS installer silently into the managed directory, /D last and unquoted", async () => {
    const root = tempRoot();
    const bytes = Buffer.from("an installer");
    const server = createServer((req, res) => {
      if ((req.url ?? "").endsWith("latest.yml")) {
        res.writeHead(200).end(`files:\n  - url: Tetravox-0.3.11-win-x64.exe\n    sha512: ${base64Sha512(bytes)}\n`);
        return;
      }
      res.writeHead(200).end(bytes);
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const calls: string[][] = [];
    await installRelease(
      root,
      "win-x64",
      {
        version: "0.3.11",
        tag: "v0.3.11",
        assets: [
          { name: "Tetravox-0.3.11-win-x64.exe", url: `${origin}/a.exe` },
          { name: "latest.yml", url: `${origin}/latest.yml` },
        ],
      },
      {
        run: async (command, args) => {
          calls.push([command, ...args]);
          // NSIS would put the app there; stand in for it so the state write has something real.
          writeFileSync(executableIn(join(root, "0.3.11"), "win-x64"), "app");
          return { ok: true, stderr: "" };
        },
      },
    );
    expect(calls).toHaveLength(1);
    expect(calls[0]?.slice(1)).toEqual(["/S", `/D=${join(root, "0.3.11")}`]);
    expect((await readState(root)).version).toBe("0.3.11");
  });
});
