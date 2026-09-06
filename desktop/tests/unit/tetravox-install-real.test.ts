/**
 * The managed install against the **real** Tetravox releases on GitHub
 * (V6, `dev/notes/v3-native-panes-external-viewer/TI.md`).
 *
 * Two gates, because the two halves cost very different things:
 *
 * - `TIT_TETRAVOX_REAL=1` — resolve the real release index and its real `latest*.yml`, and assert
 *   that the asset this platform would install exists and that its digest is stated. Two small
 *   HTTPS requests, no download. This is the test that fails the day Tetravox renames an asset or
 *   stops publishing a manifest — the one contract with another project that the loopback tests
 *   in `tetravox-install.test.ts` cannot cover, because they serve the shape this code expects.
 * - `TIT_E2E_ALLOW_DOWNLOAD=1` — additionally perform one real install into a temp directory:
 *   ~130 MB, `ditto`, and `codesign --verify` against a bundle Apple has actually notarised.
 *
 * Neither runs by default, so `npx vitest run` stays offline and fast, and CI never downloads a
 * third-party binary it did not ask for. Tetravox has **no `--version` flag** — its CLI
 * (`packages/app/src/main/cli.ts`) takes file paths and `--job`/`--out`/`--tvx-search`, and every
 * other invocation opens a window — so the installed copy is asserted by its bundle structure and
 * its signature, never by launching it. A test must not put another application's window on the
 * screen of the machine running it.
 */
import { describe, expect, it } from "vitest";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  assetNameFor,
  createManagedTetravox,
  detectTarget,
  executableIn,
  installedVersions,
  manifestNameFor,
  readState,
  resolveLatestRelease,
  runCommand,
  sha512FromManifest,
} from "../../src/main/tetravoxInstall";

const REAL = process.env.TIT_TETRAVOX_REAL === "1";
const ALLOW_DOWNLOAD = process.env.TIT_E2E_ALLOW_DOWNLOAD === "1";

describe.skipIf(!REAL)("the real Tetravox release index", () => {
  it("publishes the asset and the manifest this platform installs", { timeout: 60_000 }, async () => {
    const target = detectTarget(process.platform, process.arch);
    expect(target, `no Tetravox build for ${process.platform}/${process.arch}`).not.toBeNull();

    const release = await resolveLatestRelease();
    expect(release, "could not reach the Tetravox release index").not.toBeNull();
    // 0.3.11 was the newest release when this lane was written; anything older means the resolver
    // picked a stale or prerelease tag.
    expect(release!.version.split(".").map(Number)[1]).toBeGreaterThanOrEqual(3);

    const assetName = assetNameFor(target!, release!.version);
    const manifestName = manifestNameFor(target!);
    const asset = release!.assets.find((a) => a.name === assetName);
    const manifest = release!.assets.find((a) => a.name === manifestName);
    expect(asset, `${release!.tag} publishes no ${assetName}`).toBeDefined();
    expect(manifest, `${release!.tag} publishes no ${manifestName}`).toBeDefined();

    const yaml = await (await fetch(manifest!.url, { redirect: "follow" })).text();
    const digest = sha512FromManifest(yaml, assetName);
    expect(digest, `${manifestName} does not state a sha512 for ${assetName}`).toBeTruthy();
    // electron-updater writes base64 SHA-512 — 88 characters ending in `==`.
    expect(digest).toHaveLength(88);
    console.log(`real: ${release!.tag} → ${assetName} (${manifestName}, sha512 ${digest!.slice(0, 12)}…)`);
  });
});

describe.skipIf(!REAL || !ALLOW_DOWNLOAD)("one real install", () => {
  it("verifies, unpacks, and produces a bundle that passes codesign", { timeout: 900_000 }, async () => {
    const root = mkdtempSync(join(tmpdir(), "tvx-real-"));
    const managed = createManagedTetravox({ root, platform: process.platform, arch: process.arch });
    const outcome = await managed.ensureInstalled();

    expect(outcome.pending).toBe(false);
    expect(existsSync(outcome.path)).toBe(true);
    expect(await installedVersions(root)).toEqual([outcome.version]);
    expect((await readState(root)).version).toBe(outcome.version);
    expect(managed.location()?.path).toBe(executableIn(join(root, outcome.version), managed.target!));

    if (process.platform === "darwin") {
      // The bundle structure Tetravox's own launcher needs, and Apple's verdict on it. Nothing is
      // launched: there is no headless invocation, and a window would be a test stealing focus.
      expect(existsSync(join(outcome.path, "Contents", "MacOS", "Tetravox"))).toBe(true);
      expect(existsSync(join(outcome.path, "Contents", "Info.plist"))).toBe(true);
      const verified = await runCommand("/usr/bin/codesign", ["--verify", "--deep", "--strict", outcome.path]);
      expect(verified.ok, `codesign said: ${verified.stderr}`).toBe(true);
      // and, because it verified, the quarantine attribute was removed rather than left to
      // Gatekeeper — this is the assertion that the ordering in `installRelease` actually held.
      const attrs = await runCommand("/usr/bin/xattr", ["-p", "com.apple.quarantine", outcome.path]);
      expect(attrs.ok).toBe(false);
    }
    console.log(`real install: ${outcome.version} → ${outcome.path}`);
  });
});
