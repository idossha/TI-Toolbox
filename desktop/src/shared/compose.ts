/**
 * Pure helpers for driving the stack from the main process: the compose project name, the env map
 * the compose file's `${VAR}` references are interpolated from, and the exact user-facing message
 * for each way starting a stack can fail.
 *
 * The `docker compose` argument builders that used to live here are gone with `dockerCli.ts`: the
 * app reads the compose file itself (`composeFile.ts`) and realises it through the Engine API
 * (`main/docker/`, `main/stack.ts`), so there is no CLI invocation left to build arguments for and
 * no CLI stderr left to classify. What replaced `classifyDockerError` is `stackErrorMessage`, which
 * maps the engine client's own error `kind` — a structured value, not scraped text — onto copy.
 *
 * Deliberately free of any `node:*`/`electron` import (like `paths.ts`) — that keeps it inside both
 * `tsconfig.node.json`'s and `tsconfig.web.json`'s project, so `tests/unit/compose.test.ts`
 * type-checks under either, and lets it use the Web Crypto API (`globalThis.crypto`, present in
 * both the main process's Node runtime and any browser) instead of `node:crypto` for the one thing
 * here that needs real randomness.
 */

const BASE64URL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

function toBase64Url(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i] ?? 0;
    const b1 = bytes[i + 1];
    const b2 = bytes[i + 2];
    out += BASE64URL_CHARS[b0 >> 2];
    out += BASE64URL_CHARS[((b0 & 0x03) << 4) | ((b1 ?? 0) >> 4)];
    if (b1 !== undefined) out += BASE64URL_CHARS[((b1 & 0x0f) << 2) | ((b2 ?? 0) >> 6)];
    if (b2 !== undefined) out += BASE64URL_CHARS[b2 & 0x3f];
  }
  return out;
}

/** A fresh 32-byte URL-safe token, passed as the `TIT_SERVER_TOKEN` container env (TODO §2.8). */
export function generateToken(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  globalThis.crypto.getRandomValues(bytes);
  return toBase64Url(bytes);
}

/**
 * A small, stable, non-cryptographic 32-bit hash (8 lowercase hex chars) — plenty of headroom for
 * "one stack per host directory a user has open", and dependency-free (no `node:crypto`).
 * Two-lane xorshift-mix (cyrb-family), not sha256: nothing here is a security boundary, just a
 * short deterministic project-name suffix.
 */
export function hash8(input: string): string {
  let h1 = 0xdeadbeef ^ input.length;
  let h2 = 0x41c6ce57 ^ input.length;
  for (let i = 0; i < input.length; i++) {
    const ch = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  return (h1 >>> 0).toString(16).padStart(8, "0");
}

/**
 * Project name for a given host project directory. Every project directory gets its own stack
 * (TODO §2.7 "Switch project"), named deterministically so re-running `stack.start` for the same
 * directory always finds the same container — via the `tit.project` label — instead of creating a
 * second one. Also prefixes the container, network and volume names, matching what `docker compose`
 * itself would have produced for the same file, so `docker ps` still reads the way a user expects.
 */
export function computeProjectName(hostProjectDir: string): string {
  return `ti-toolbox-${hash8(hostProjectDir)}`;
}

/** Label keys every object this app creates carries — the whole basis of attach-or-start. */
export const LABEL_PROJECT = "tit.project";
export const LABEL_STACK = "tit.stack";
export const LABEL_SERVICE = "tit.service";
export const LABEL_HOST_DIR = "tit.host_project_dir";
/** Value of `tit.stack` on everything this app creates — one generation of the stack definition. */
export const STACK_ID = "ti-toolbox-v3";

export interface StackEnvInput {
  hostProjectDir: string;
  projectDirName: string;
  userConfigDir: string;
  port: number;
  token: string;
  timezone: string;
  hostOs: string;
  hostOsVersion: string;
  hostArch: string;
  /**
   * Dev only: a repo checkout to bind-mount at `/ti-toolbox` in place of the image's own `tit`.
   * Absent (or empty) means *no such mount* — see `main/stack.ts#resolveRepoDir`, which returns a
   * value only for an unpackaged run that asked for one by name.
   */
  repoDir?: string;
  /** Dev only: overrides `${TIT_STATIC_DIR:-/opt/ti-toolbox/ui}` — a locally built renderer bundle. */
  staticDir?: string;
  /**
   * Dev only: `TIT_SERVER_RELOAD=1`, which makes the image entrypoint run uvicorn with
   * `--reload --reload-dir /ti-toolbox/tit`. Only useful together with `repoDir` — there is
   * nothing to watch without the worktree mounted at `/ti-toolbox`.
   */
  serverReload?: boolean;
  /** Dev only: `${TIT_IMAGE_TAG}`. Absent leaves the compose file's own default (`dev`). */
  imageTag?: string;
}

/**
 * The env map `${VAR}` references in the compose file are interpolated from. A plain object (not a
 * `Map`/class) so it serialises trivially for logging and tests.
 *
 * `DISPLAY` and `FREESURFER_VOLUME` are gone (decisions D2/D3): there is no X11 in the product and
 * no FreeSurfer service or volume in the stack. `TIT_REPO_DIR`/`TIT_STATIC_DIR` are optional — the
 * shipped image carries `tit` and the UI, and a compose file that does not reference them never
 * needs them set.
 *
 * `TIT_REPO_DIR` is always present, and is the **empty string** when there is no dev repo to mount.
 * That is deliberate and load-bearing: `stack.ts` interpolates the compose file from
 * `{...process.env, ...buildStackEnv(...)}`, so leaving the key out would let a stray host
 * `TIT_REPO_DIR` in the developer's own shell (or, once packaged, in the user's environment)
 * bind-mount a host directory over the image's baked-in `/ti-toolbox` — the very thing D1 says
 * ships inside the image. An empty value makes `${TIT_REPO_DIR:-}` interpolate to `""`, which
 * `composeFile.ts` drops as a whole volume entry rather than handing Docker an empty bind source.
 */
export function buildStackEnv(input: StackEnvInput): Record<string, string> {
  const env: Record<string, string> = {
    LOCAL_PROJECT_DIR: input.hostProjectDir,
    PROJECT_DIR_NAME: input.projectDirName,
    TIT_USER_CONFIG: input.userConfigDir,
    TIT_HOST_OS: input.hostOs,
    TIT_HOST_OS_VERSION: input.hostOsVersion,
    TIT_HOST_ARCH: input.hostArch,
    TZ: input.timezone,
    TIT_SERVER_PORT: String(input.port),
    TIT_SERVER_TOKEN: input.token,
    TIT_REPO_DIR: input.repoDir ?? "",
    // Always present, empty by default, for exactly the reason `TIT_REPO_DIR` is: the compose file
    // is interpolated from `{...process.env, ...buildStackEnv(...)}`, so an omitted key would let a
    // stray `TIT_SERVER_RELOAD=1` in the developer's shell (or, once packaged, a user's) start the
    // server under uvicorn `--reload` — a file watcher over a mount that may not exist, in a
    // container nobody asked to be reloadable.
    TIT_SERVER_RELOAD: input.serverReload ? "1" : "",
  };
  if (input.staticDir) env.TIT_STATIC_DIR = input.staticDir;
  if (input.imageTag) env.TIT_IMAGE_TAG = input.imageTag;
  return env;
}

/**
 * Every distinct way starting or stopping the stack can fail, in the app's own vocabulary.
 * `not-installed` / `not-running` / `socket-permission` / `unsupported-engine` come straight from
 * the engine client's `DockerEngineError.kind`; the rest are raised by `stack.ts` itself.
 */
export type StackErrorKind =
  | "not-installed"
  | "not-running"
  | "socket-permission"
  | "unsupported-engine"
  | "image-pull-failed"
  | "health-timeout"
  | "container-exited"
  | "compose-invalid"
  | "unknown";

/**
 * The exact launcher copy for each failure. `detail` is appended when it carries something the
 * user can act on (the daemon's own message, the compose key at fault, the container's last log
 * line) — never swallowed, because an unclassified failure with no detail is unactionable.
 *
 * `socket-permission` names the Linux fix explicitly (`docker` group) because that is the single
 * most common first-run failure on Linux and the remediation is not guessable.
 */
export function stackErrorMessage(kind: StackErrorKind, detail?: string): string {
  const suffix = detail ? ` (${detail.trim()})` : "";
  switch (kind) {
    case "not-installed":
      return "Docker was not found on this machine. Install Docker Desktop (macOS/Windows) or Docker Engine (Linux), then try again." + suffix;
    case "not-running":
      return "Docker is installed but not running. Start Docker Desktop (or your Docker daemon) and try again." + suffix;
    case "socket-permission":
      return (
        "Permission denied talking to the Docker socket. On Linux, add your user to the docker group " +
        "(sudo usermod -aG docker $USER), then log out and back in. On macOS, restart Docker Desktop." +
        suffix
      );
    case "unsupported-engine":
      return "This container engine is not supported yet. TI-Toolbox needs Docker Desktop or Docker Engine; Podman is not supported." + suffix;
    case "image-pull-failed":
      return "The TI-Toolbox image could not be downloaded. Check your internet connection and registry access, then try again." + suffix;
    case "health-timeout":
      return "The container started but its server never answered. Check the container logs, then try again." + suffix;
    case "container-exited":
      return "The container exited while starting up." + suffix;
    case "compose-invalid":
      return "The stack definition could not be read." + suffix;
    default:
      return "Starting the Docker stack failed." + suffix;
  }
}
