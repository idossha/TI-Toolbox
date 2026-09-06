/**
 * **The managed Tetravox install** — TI-Toolbox installs and maintains the viewer itself, on the
 * host, with no user action (V6, `dev/notes/v3-native-panes-external-viewer/TI.md`).
 *
 * ## Why this exists at all
 *
 * V2/V3 made the viewer an ordinary desktop app on the host and `./viewer.ts` learned to find and
 * launch it. That left one sentence in the product that nobody should have to read: *"install
 * Tetravox first."* A user who has TI-Toolbox and a finished simulation should be able to press
 * **Open in Tetravox** and see it. So this module does what a package manager would: resolve the
 * newest release, fetch the one asset for this platform, verify it against the publisher's own
 * `latest*.yml` digest, and keep it in `<userData>/tetravox/<version>/`.
 *
 * ## Why not inside the Docker image (DECISION)
 *
 * The obvious cheaper answer — bake Tetravox into `ti-toolbox` next to SimNIBS — does not work,
 * and it fails at run time rather than at build time. The image has **no display and no GPU**: it
 * is a headless Linux container the user reaches over HTTP. Tetravox is an Electron app whose
 * whole purpose is a WebGL2 canvas, and since Chromium 137 the software-GL fallback (SwiftShader
 * for WebGL) is gone, so `--use-gl=swiftshader` no longer buys a rendering context; a container
 * launch would either fail to open a window at all or open one with no GL. Forwarding X11 back to
 * the host adds a dependency (XQuartz, an X server on Windows) that is strictly worse than the
 * one it replaces, and streams pixels for an interactive 3D viewer over a socket. The viewer must
 * therefore run on the host, on the user's own GPU — and if it must run on the host, *something*
 * must put it there. That something is this module, not the person.
 *
 * ## The five properties that matter
 *
 * 1. **Launch never waits on the network.** `activate()` runs at startup and promotes an already
 *    downloaded version; the update check is fire-and-forget, at most once per 24 h. An offline
 *    machine with an install launches exactly as fast as an online one.
 * 2. **A new version never replaces a running one.** A download lands in `<root>/<version>/` and
 *    is recorded as `pending`; `current.json` flips on the *next* launch. Nobody's open window is
 *    swapped underneath them.
 * 3. **Nothing is trusted that is not verified.** The asset is hashed while it streams and
 *    compared to the base64 SHA-512 in the release's own `latest*.yml` (the manifest
 *    electron-updater publishes). A mismatch deletes the staging directory and leaves every
 *    installed version untouched.
 * 4. **Quarantine is stripped only from a bundle that verifies.** On macOS `codesign --verify` runs
 *    *before* `xattr -d com.apple.quarantine`, and a failure leaves the attribute in place — the
 *    user then gets Gatekeeper's own dialog, which is the correct outcome, rather than this app
 *    silently waving through an unsigned binary it downloaded.
 * 5. **Two versions, no more.** The current one and the one before it, so an update that turns out
 *    badly is a rollback rather than a re-download.
 *
 * ## Per-platform asset and verification path
 *
 * | Platform | Asset | Verify | Materialise |
 * |---|---|---|---|
 * | macOS arm64/x64 | `Tetravox-<v>-mac-{arm64,x64}.zip` | sha512 from `latest-mac.yml` | `ditto -x -k` (preserves symlinks and the signature, which `unzip` does not), then `codesign --verify --deep --strict`, then `xattr -dr com.apple.quarantine` only if that passed |
 * | Windows x64 | `Tetravox-<v>-win-x64.exe` (NSIS; the release publishes no portable or zip build) | sha512 from `latest.yml` | run the installer silently, `/S /D=<dir>` — NSIS requires `/D` last and unquoted |
 * | Linux x64 | `Tetravox-<v>-linux-x86_64.AppImage` | sha512 from `latest-linux.yml` | rename to `Tetravox.AppImage`, `chmod 0755` — an AppImage *is* the install |
 *
 * Everything else — Linux arm64, 32-bit anything — is an honest "no build for this platform", not
 * a silent no-op: the Settings card says so and the download link still works.
 */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createWriteStream } from "node:fs";
import { chmod, mkdir, mkdtemp, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

/** GitHub's release index for Tetravox. Overridable so a test (or a mirror) can stand in. */
export const DEFAULT_RELEASE_INDEX = "https://api.github.com/repos/idossha/tetravox/releases";

export function releaseIndexUrl(env: NodeJS.ProcessEnv = process.env): string {
  return env.TIT_TETRAVOX_RELEASE_INDEX?.trim() || DEFAULT_RELEASE_INDEX;
}

/** How long a check is good for. The viewer is not a security update; once a day is plenty. */
export const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;

/** The platform/arch combinations Tetravox publishes a build for. */
export type InstallTarget = "mac-arm64" | "mac-x64" | "win-x64" | "linux-x64";

export function detectTarget(platform: string, arch: string): InstallTarget | null {
  if (platform === "darwin") return arch === "arm64" ? "mac-arm64" : arch === "x64" ? "mac-x64" : null;
  if (platform === "win32") return arch === "x64" ? "win-x64" : null;
  if (platform === "linux") return arch === "x64" ? "linux-x64" : null;
  return null;
}

/** The one asset name this target installs, for a given version. */
export function assetNameFor(target: InstallTarget, version: string): string {
  switch (target) {
    case "mac-arm64":
      return `Tetravox-${version}-mac-arm64.zip`;
    case "mac-x64":
      return `Tetravox-${version}-mac-x64.zip`;
    case "win-x64":
      return `Tetravox-${version}-win-x64.exe`;
    case "linux-x64":
      return `Tetravox-${version}-linux-x86_64.AppImage`;
  }
}

/** electron-updater's manifest for this target — where the digest to check against is written. */
export function manifestNameFor(target: InstallTarget): string {
  if (target === "mac-arm64" || target === "mac-x64") return "latest-mac.yml";
  if (target === "win-x64") return "latest.yml";
  return "latest-linux.yml";
}

/** Where the installed app lives inside a version directory. */
export function executableIn(versionDir: string, target: InstallTarget): string {
  if (target === "mac-arm64" || target === "mac-x64") return join(versionDir, "Tetravox.app");
  if (target === "win-x64") return join(versionDir, "Tetravox.exe");
  return join(versionDir, "Tetravox.AppImage");
}

// ── the release index ────────────────────────────────────────────────────────────────────────

export interface ReleaseAsset {
  name: string;
  url: string;
}

export interface ResolvedRelease {
  version: string;
  tag: string;
  assets: ReleaseAsset[];
}

/** `1.2.3` from `v1.2.3` / `1.2.3`; `null` for anything that is not three numbers. */
export function versionFromTag(tag: string): string | null {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(tag.trim());
  return m ? `${m[1]}.${m[2]}.${m[3]}` : null;
}

/** Semver ordering on the three numeric fields. Positive when `a` is newer. */
export function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map((n) => Number.parseInt(n, 10) || 0);
  const pb = b.split(".").map((n) => Number.parseInt(n, 10) || 0);
  for (let i = 0; i < 3; i += 1) {
    if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pa[i] ?? 0) - (pb[i] ?? 0);
  }
  return 0;
}

/**
 * The newest published release in GitHub's index.
 *
 * Drafts and prereleases are skipped: a user who never asked for a viewer at all must not be given
 * a release candidate of one. The index is *not* assumed sorted — it is ordered by creation date,
 * which is not version order once a patch is backported.
 */
export function pickRelease(index: unknown): ResolvedRelease | null {
  if (!Array.isArray(index)) return null;
  let best: ResolvedRelease | null = null;
  for (const raw of index) {
    if (!raw || typeof raw !== "object") continue;
    const rel = raw as Record<string, unknown>;
    if (rel.draft === true || rel.prerelease === true) continue;
    const version = versionFromTag(String(rel.tag_name ?? ""));
    if (!version) continue;
    const assets: ReleaseAsset[] = Array.isArray(rel.assets)
      ? rel.assets
          .map((a) => a as Record<string, unknown>)
          .filter((a) => typeof a?.name === "string" && typeof a?.browser_download_url === "string")
          .map((a) => ({ name: String(a.name), url: String(a.browser_download_url) }))
      : [];
    if (!best || compareVersions(version, best.version) > 0) {
      best = { version, tag: String(rel.tag_name), assets };
    }
  }
  return best;
}

/**
 * The base64 SHA-512 electron-updater recorded for `assetName`.
 *
 * Parsed with a line scanner rather than a YAML dependency: the shape is fixed by
 * electron-updater's own writer (`files:` is a list of `url`/`sha512`/`size`), and a whole YAML
 * parser to read one field out of a 512-byte file is a dependency this process does not need.
 * Both the per-file entry and the top-level `path`/`sha512` pair are honoured, because a
 * single-file manifest (`latest.yml`) states the digest in both places.
 */
export function sha512FromManifest(yaml: string, assetName: string): string | null {
  const lines = yaml.split(/\r?\n/);
  let inMatchingEntry = false;
  let topLevelPath: string | null = null;
  let topLevelSha: string | null = null;
  for (const line of lines) {
    const url = /^\s*-?\s*url:\s*(.+?)\s*$/.exec(line);
    if (url) {
      inMatchingEntry = url[1] === assetName;
      continue;
    }
    const sha = /^\s+sha512:\s*(\S+)\s*$/.exec(line);
    if (sha && inMatchingEntry) return sha[1] ?? null;
    const path = /^path:\s*(.+?)\s*$/.exec(line);
    if (path) {
      topLevelPath = path[1] ?? null;
      inMatchingEntry = false;
      continue;
    }
    const flat = /^sha512:\s*(\S+)\s*$/.exec(line);
    if (flat) topLevelSha = flat[1] ?? null;
  }
  return topLevelPath === assetName ? topLevelSha : null;
}

// ── the managed install on disk ──────────────────────────────────────────────────────────────

export interface ManagedState {
  /** The version `launch` uses right now. */
  version: string | null;
  /** Downloaded and verified, waiting for the next launch to become `version`. */
  pending: string | null;
  /** ISO timestamp of the last completed release-index check, successful or not. */
  lastCheckedAt: string | null;
  /** ISO timestamp of the install that produced `version`. */
  installedAt: string | null;
}

const EMPTY_STATE: ManagedState = { version: null, pending: null, lastCheckedAt: null, installedAt: null };

export function stateFile(root: string): string {
  return join(root, "current.json");
}

export async function readState(root: string): Promise<ManagedState> {
  try {
    const raw = JSON.parse(await readFile(stateFile(root), "utf8")) as Record<string, unknown>;
    return {
      version: typeof raw.version === "string" ? raw.version : null,
      pending: typeof raw.pending === "string" ? raw.pending : null,
      lastCheckedAt: typeof raw.lastCheckedAt === "string" ? raw.lastCheckedAt : null,
      installedAt: typeof raw.installedAt === "string" ? raw.installedAt : null,
    };
  } catch {
    return { ...EMPTY_STATE };
  }
}

/** Whole-then-rename: a half-written `current.json` is a viewer that has forgotten its install. */
export async function writeState(root: string, state: ManagedState): Promise<void> {
  await mkdir(root, { recursive: true });
  const tmp = `${stateFile(root)}.partial`;
  await writeFile(tmp, `${JSON.stringify(state, null, 2)}\n`);
  await rename(tmp, stateFile(root));
}

/** Version directories present on disk, newest first. */
export async function installedVersions(root: string): Promise<string[]> {
  let entries: string[];
  try {
    entries = await readdir(root);
  } catch {
    return [];
  }
  return entries.filter((name) => versionFromTag(name) === name).sort((a, b) => compareVersions(b, a));
}

/**
 * Promote a `pending` download, if there is one, and answer the state to launch with.
 *
 * This is the whole of "activating on the next launch": the download already happened, the digest
 * already matched, and the only thing left is one rename of a JSON field.
 */
export async function activatePending(root: string, target: InstallTarget): Promise<ManagedState> {
  const state = await readState(root);
  if (state.pending && existsSync(executableIn(join(root, state.pending), target))) {
    const next: ManagedState = {
      version: state.pending,
      pending: null,
      lastCheckedAt: state.lastCheckedAt,
      installedAt: new Date().toISOString(),
    };
    await writeState(root, next);
    await pruneVersions(root, next.version, 2);
    return next;
  }
  return state;
}

/** Keep `keep` versions (the current one always among them); delete the rest. */
export async function pruneVersions(
  root: string,
  current: string | null,
  keep: number,
  protect: readonly (string | null)[] = [],
): Promise<string[]> {
  const versions = await installedVersions(root);
  const kept = new Set<string>();
  if (current) kept.add(current);
  for (const version of protect) if (version) kept.add(version);
  for (const version of versions) {
    if (kept.size >= keep) break;
    kept.add(version);
  }
  const removed: string[] = [];
  for (const version of versions) {
    if (kept.has(version)) continue;
    await rm(join(root, version), { recursive: true, force: true });
    removed.push(version);
  }
  return removed;
}

/** Bytes on disk under `root`, for the Settings card's "disk usage" row. */
export async function diskUsage(root: string): Promise<number> {
  let total = 0;
  const walk = async (dir: string): Promise<void> => {
    let entries: import("node:fs").Dirent[];
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.isFile()) {
        try {
          total += (await stat(full)).size;
        } catch {
          /* raced with a prune; not worth failing a size label over */
        }
      }
    }
  };
  await walk(root);
  return total;
}

// ── download, verify, materialise ────────────────────────────────────────────────────────────

export type ProgressEvent =
  | { phase: "checking" }
  | { phase: "downloading"; version: string; received: number; total: number }
  | { phase: "verifying"; version: string }
  | { phase: "installing"; version: string }
  | { phase: "done"; version: string; pending: boolean }
  | { phase: "error"; message: string };

export type FetchLike = typeof fetch;

export interface InstallDeps {
  fetch?: FetchLike;
  onProgress?: (event: ProgressEvent) => void;
  /** Injected so the digest and the pruning can be tested without shelling out to `ditto`. */
  run?: (command: string, args: string[]) => Promise<{ ok: boolean; stderr: string }>;
}

/** `spawn` reduced to the two facts a caller here needs: did it succeed, and what did it say. */
export function runCommand(command: string, args: string[]): Promise<{ ok: boolean; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => resolve({ ok: false, stderr: error.message }));
    child.on("close", (code) => resolve({ ok: code === 0, stderr }));
  });
}

/** base64 SHA-512 of a file — the exact form electron-updater writes into `latest*.yml`. */
export async function sha512OfFile(file: string): Promise<string> {
  const hash = createHash("sha512");
  const { createReadStream } = await import("node:fs");
  await pipeline(createReadStream(file), hash);
  return hash.digest("base64");
}

async function download(
  url: string,
  destination: string,
  fetchImpl: FetchLike,
  onChunk?: (received: number, total: number) => void,
): Promise<void> {
  const response = await fetchImpl(url, { redirect: "follow" });
  if (!response.ok || !response.body) throw new Error(`download failed: HTTP ${response.status}`);
  const total = Number.parseInt(response.headers.get("content-length") ?? "0", 10) || 0;
  let received = 0;
  const source = Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0]);
  source.on("data", (chunk: Buffer) => {
    received += chunk.length;
    onChunk?.(received, total);
  });
  await pipeline(source, createWriteStream(destination));
}

export interface InstallOutcome {
  version: string;
  /** true when the install landed as `pending` because another version is already active. */
  pending: boolean;
  path: string;
}

/**
 * Fetch, verify and install one release into `<root>/<version>/`.
 *
 * The order is the safety property: **hash before anything is moved into place.** The download and
 * the unpack both happen in a staging directory beside the versions; only a verified, materialised
 * tree is renamed in. A failure at any step leaves every existing install exactly as it was, which
 * is what "bad digest → nothing replaced" means.
 */
export async function installRelease(
  root: string,
  target: InstallTarget,
  release: ResolvedRelease,
  deps: InstallDeps = {},
): Promise<InstallOutcome> {
  const fetchImpl = deps.fetch ?? fetch;
  const run = deps.run ?? runCommand;
  const progress = deps.onProgress ?? ((): void => undefined);
  const { version } = release;

  const assetName = assetNameFor(target, version);
  const asset = release.assets.find((a) => a.name === assetName);
  const manifestName = manifestNameFor(target);
  const manifest = release.assets.find((a) => a.name === manifestName);
  if (!asset) throw new Error(`Tetravox ${version} publishes no build for this platform (${assetName})`);
  if (!manifest) throw new Error(`Tetravox ${version} has no ${manifestName}, so the download cannot be verified`);

  await mkdir(root, { recursive: true });
  const staging = await mkdtemp(join(root, ".staging-"));
  try {
    const manifestResponse = await fetchImpl(manifest.url, { redirect: "follow" });
    if (!manifestResponse.ok) throw new Error(`could not read ${manifestName}: HTTP ${manifestResponse.status}`);
    const expected = sha512FromManifest(await manifestResponse.text(), assetName);
    if (!expected) throw new Error(`${manifestName} does not list ${assetName}`);

    const downloaded = join(staging, assetName);
    progress({ phase: "downloading", version, received: 0, total: 0 });
    await download(asset.url, downloaded, fetchImpl, (received, total) =>
      progress({ phase: "downloading", version, received, total }),
    );

    progress({ phase: "verifying", version });
    const actual = await sha512OfFile(downloaded);
    if (actual !== expected) {
      throw new Error(`${assetName} failed its SHA-512 check; nothing was installed`);
    }

    progress({ phase: "installing", version });
    const finalDir = join(root, version);
    if (target === "win-x64") {
      // NSIS writes straight into its destination, so there is no staged tree to rename. `/D` must
      // be the last switch and must not be quoted — that is NSIS's rule, not a style choice.
      await rm(finalDir, { recursive: true, force: true });
      await mkdir(finalDir, { recursive: true });
      const result = await run(downloaded, ["/S", `/D=${finalDir}`]);
      if (!result.ok) throw new Error(`the Tetravox installer failed: ${result.stderr.trim() || "no output"}`);
    } else {
      if (target === "linux-x64") {
        await rename(downloaded, join(staging, "Tetravox.AppImage"));
        await chmod(join(staging, "Tetravox.AppImage"), 0o755);
      } else {
        // `ditto -x -k` and not `unzip`: it is the only unpacker on macOS that preserves the
        // symlinks and extended attributes inside an .app, and a bundle unpacked with `unzip`
        // fails its own code signature.
        const extracted = await run("/usr/bin/ditto", ["-x", "-k", downloaded, staging]);
        if (!extracted.ok) throw new Error(`could not unpack ${assetName}: ${extracted.stderr.trim()}`);
        await rm(downloaded, { force: true });
        const bundle = join(staging, "Tetravox.app");
        if (!existsSync(bundle)) throw new Error(`${assetName} did not contain Tetravox.app`);
        // Quarantine comes off only if the signature holds. An unsigned or tampered bundle keeps
        // it and meets Gatekeeper, which is the right authority for that question.
        const verified = await run("/usr/bin/codesign", ["--verify", "--deep", "--strict", bundle]);
        if (verified.ok) await run("/usr/bin/xattr", ["-dr", "com.apple.quarantine", bundle]);
      }
      await rm(finalDir, { recursive: true, force: true });
      await rename(staging, finalDir);
    }

    const state = await readState(root);
    const active = state.version && existsSync(executableIn(join(root, state.version), target)) ? state.version : null;
    const pending = active !== null && active !== version;
    const next: ManagedState = pending
      ? { ...state, pending: version, lastCheckedAt: new Date().toISOString() }
      : { version, pending: null, lastCheckedAt: new Date().toISOString(), installedAt: new Date().toISOString() };
    await writeState(root, next);
    // Two versions: the one in use and the one before it, so a bad update is a rollback.
    await pruneVersions(root, next.version, 2, [next.pending]);
    progress({ phase: "done", version, pending });
    return { version, pending, path: executableIn(join(root, version), target) };
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
}

/** The newest release, or `null` when the network is not there. Never throws. */
export async function resolveLatestRelease(deps: InstallDeps = {}, env: NodeJS.ProcessEnv = process.env): Promise<ResolvedRelease | null> {
  const fetchImpl = deps.fetch ?? fetch;
  try {
    // GitHub answers 403 to a request with no User-Agent, and 403 again once an unauthenticated
    // IP passes 60 requests an hour — both with no hint as to which. A once-a-day check is far
    // under that limit in normal use; `GITHUB_TOKEN`/`GH_TOKEN` is honoured when it happens to be
    // set (a developer's machine, CI) purely so a shared-IP office or a test loop is not the one
    // case that cannot check.
    const token = env.GITHUB_TOKEN?.trim() || env.GH_TOKEN?.trim();
    const response = await fetchImpl(releaseIndexUrl(env), {
      redirect: "follow",
      headers: {
        accept: "application/vnd.github+json",
        "user-agent": "TI-Toolbox",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!response.ok) return null;
    return pickRelease(await response.json());
  } catch {
    return null;
  }
}

export function checkIsDue(lastCheckedAt: string | null, now: number = Date.now()): boolean {
  if (!lastCheckedAt) return true;
  const then = Date.parse(lastCheckedAt);
  return Number.isNaN(then) || now - then >= CHECK_INTERVAL_MS;
}

// ── the orchestrator main talks to ───────────────────────────────────────────────────────────

export interface ManagedSummary {
  supported: boolean;
  version: string | null;
  pending: string | null;
  lastCheckedAt: string | null;
  bytes: number;
  root: string | null;
  busy: boolean;
}

export interface ManagedTetravox {
  root: string;
  target: InstallTarget | null;
  /** Promote a pending download. Call once, at startup, before the first probe. */
  activate(): Promise<void>;
  /** The active managed executable, or null. Pure filesystem — never the network. */
  location(): { path: string; version: string | null } | null;
  summary(): Promise<ManagedSummary>;
  /** Install the newest release now. Concurrent callers join the one in flight. */
  ensureInstalled(): Promise<InstallOutcome>;
  /** Check the release index now and install anything newer. Answers what it did. */
  checkNow(): Promise<{ checked: boolean; installed: string | null }>;
  /** Check at most once per 24 h, in the background, swallowing every failure. */
  maybeCheck(): void;
  remove(): Promise<void>;
}

/**
 * The stateful wrapper `src/main/index.ts` holds.
 *
 * It owns exactly two pieces of state — the cached `ManagedState` and the in-flight install
 * promise — and both exist for the same reason: **a probe must be able to answer instantly.**
 * Every IPC call in the viewer bridge re-probes, so reading `current.json` from disk on each one
 * would put a synchronous file read in front of every render of the Settings card.
 */
export function createManagedTetravox(options: {
  root: string;
  platform: string;
  arch: string;
  onProgress?: (event: ProgressEvent) => void;
  deps?: InstallDeps;
  env?: NodeJS.ProcessEnv;
}): ManagedTetravox {
  const target = detectTarget(options.platform, options.arch);
  const root = options.root;
  const env = options.env ?? process.env;
  const emit = options.onProgress ?? ((): void => undefined);
  const deps: InstallDeps = { ...options.deps, onProgress: emit };
  let cached: ManagedState = { ...EMPTY_STATE };
  let inFlight: Promise<InstallOutcome> | null = null;

  const refresh = async (): Promise<ManagedState> => {
    cached = await readState(root);
    return cached;
  };

  const location = (): { path: string; version: string | null } | null => {
    if (!target || !cached.version) return null;
    const path = executableIn(join(root, cached.version), target);
    return existsSync(path) ? { path, version: cached.version } : null;
  };

  const install = async (): Promise<InstallOutcome> => {
    if (!target) throw new Error("Tetravox publishes no build for this platform");
    const release = await resolveLatestRelease(deps, env);
    if (!release) throw new Error("could not reach the Tetravox release index — check your connection");
    const outcome = await installRelease(root, target, release, deps);
    await refresh();
    return outcome;
  };

  const ensureInstalled = (): Promise<InstallOutcome> => {
    if (inFlight) return inFlight;
    inFlight = install().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };

  return {
    root,
    target,
    async activate(): Promise<void> {
      if (!target) return;
      cached = await activatePending(root, target);
    },
    location,
    async summary(): Promise<ManagedSummary> {
      const state = await refresh();
      return {
        supported: target !== null,
        version: location() ? state.version : null,
        pending: state.pending,
        lastCheckedAt: state.lastCheckedAt,
        bytes: await diskUsage(root),
        root,
        busy: inFlight !== null,
      };
    },
    ensureInstalled,
    async checkNow(): Promise<{ checked: boolean; installed: string | null }> {
      if (!target) return { checked: false, installed: null };
      emit({ phase: "checking" });
      const release = await resolveLatestRelease(deps, env);
      const state = await refresh();
      if (!release) {
        await writeState(root, { ...state, lastCheckedAt: new Date().toISOString() });
        await refresh();
        return { checked: false, installed: null };
      }
      const newest = state.pending ?? state.version;
      if (newest && compareVersions(release.version, newest) <= 0) {
        await writeState(root, { ...state, lastCheckedAt: new Date().toISOString() });
        await refresh();
        return { checked: true, installed: null };
      }
      const outcome = await ensureInstalled();
      return { checked: true, installed: outcome.version };
    },
    maybeCheck(): void {
      void (async (): Promise<void> => {
        try {
          const state = await refresh();
          if (!checkIsDue(state.lastCheckedAt)) return;
          await this.checkNow();
        } catch {
          /* a background update that fails is not an event in a user's day */
        }
      })();
    },
    async remove(): Promise<void> {
      await rm(root, { recursive: true, force: true });
      cached = { ...EMPTY_STATE };
    },
  };
}
