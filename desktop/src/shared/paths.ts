/**
 * Host <-> container path mapping for one mounted project.
 *
 * The compose stack always mounts exactly one host directory at `/mnt/<basename>` inside the
 * container (`LOCAL_PROJECT_DIR:/mnt/${PROJECT_DIR_NAME}`, see the root `docker-compose.yml`).
 * Every path the server hands back to the renderer (artifacts, reports, "Reveal" targets) is a
 * *container* path under that mount. `shell.openPath`/`shell.showItemInFolder` need the matching
 * *host* path, so the main process (never the renderer — R5) converts one to the other with the
 * functions below.
 *
 * Pure and dependency-free on purpose: no `node:path` (its separator/casing rules are those of
 * the machine running the code, not of the host platform a path string claims to be from), so the
 * same test suite can exercise Windows/WSL/macOS path shapes from any CI runner.
 */

export type HostPlatform = "darwin" | "win32" | "linux";

/**
 * True if `path` (POSIX or Windows syntax, forward or back slashes) contains a literal `.` or `..`
 * path segment anywhere in it. Checked on the *raw* string, before any parsing/normalisation —
 * per ra_14 finding 3, a path with a dot-segment is rejected outright, never silently collapsed,
 * so a `..` can never survive (via `path.resolve`-style normalisation elsewhere) into a host path
 * handed to `shell.openPath`/`shell.showItemInFolder`. A segment merely containing a dot, such as
 * `foo.bar` or `..foo`, is not flagged — only an exact `.` or `..` segment is.
 */
export function hasDotSegment(path: string): boolean {
  return path
    .split(/[/\\]+/)
    .some((segment) => segment === "." || segment === "..");
}

/** Which host directory is mounted into the container, and in what platform's path syntax. */
export interface ProjectMount {
  /** Absolute host path to the project root, in the host's native syntax (e.g. `C:\Users\a\p`). */
  hostDir: string;
  /** Platform `hostDir` belongs to — governs case sensitivity and the reconstructed separator. */
  platform: HostPlatform;
}

const MOUNT_PREFIX = "/mnt";

interface ParsedHostPath {
  /** `"/"` (POSIX), `"C:/"` (a Windows drive) or `"//server/share/"` (UNC, incl. WSL `\\wsl.localhost\...`). */
  root: string;
  segments: string[];
}

function parseHostPath(raw: string): ParsedHostPath {
  const norm = raw.trim().replace(/\\/g, "/");
  // UNC (\\server\share\...): also covers WSL's \\wsl.localhost\<distro>\... and \\wsl$\<distro>\...
  // — structurally just another UNC path, so no special-casing is needed.
  const unc = norm.match(/^\/\/+([^/]+)\/([^/]+)\/?(.*)$/);
  if (unc) {
    const server = unc[1] ?? "";
    const share = unc[2] ?? "";
    const rest = unc[3] ?? "";
    return { root: `//${server}/${share}/`, segments: rest.split("/").filter(Boolean) };
  }
  const drive = norm.match(/^([A-Za-z]):\/?(.*)$/);
  if (drive) {
    const letter = drive[1] ?? "";
    const rest = drive[2] ?? "";
    return { root: `${letter.toUpperCase()}:/`, segments: rest.split("/").filter(Boolean) };
  }
  if (norm.startsWith("/")) {
    return { root: "/", segments: norm.slice(1).split("/").filter(Boolean) };
  }
  // Not an absolute path in any recognised syntax; treat everything as segments under no root so
  // callers get a clean "does not match" rather than throwing.
  return { root: "", segments: norm.split("/").filter(Boolean) };
}

function joinHostPath(root: string, segments: string[], platform: HostPlatform): string {
  const sep = platform === "win32" ? "\\" : "/";
  const uncMatch = root.match(/^\/\/([^/]+)\/([^/]+)\/$/);
  if (uncMatch) {
    const server = uncMatch[1] ?? "";
    const share = uncMatch[2] ?? "";
    const rest = segments.length ? sep + segments.join(sep) : "";
    return `${sep}${sep}${server}${sep}${share}${rest}`;
  }
  const driveMatch = root.match(/^([A-Za-z]):\/$/);
  if (driveMatch) {
    return `${driveMatch[1] ?? ""}:${sep}${segments.join(sep)}`;
  }
  // POSIX root.
  return "/" + segments.join("/");
}

function isCaseInsensitive(platform: HostPlatform): boolean {
  // Windows and (default, non-"Case-sensitive" APFS) macOS volumes fold case; Linux does not.
  return platform !== "linux";
}

function segmentsEqual(a: string, b: string, caseInsensitive: boolean): boolean {
  return caseInsensitive ? a.toLowerCase() === b.toLowerCase() : a === b;
}

/**
 * Root identity (drive letter, UNC server/share) is compared case-insensitively regardless of
 * platform: Windows drive letters and SMB/WSL hostnames are conventionally case-insensitive even
 * though the platform as a whole might not be (this only matters for the exotic case of a Linux
 * host reached over a UNC-style path, which does not occur in practice today).
 */
function rootsEqual(a: string, b: string): boolean {
  return segmentsEqual(a, b, true);
}

function projectDirName(mount: ProjectMount): string {
  const { segments } = parseHostPath(mount.hostDir);
  const name = segments[segments.length - 1];
  if (!name) throw new Error(`Project directory has no name: ${mount.hostDir}`);
  return name;
}

/**
 * Map an absolute host path under `mount.hostDir` to its container path under `/mnt/<name>`.
 * Returns `null` if `hostPath` is not inside the mounted project (nothing else is visible to the
 * container, so there is no path to give back).
 */
export function hostToContainerPath(hostPath: string, mount: ProjectMount): string | null {
  const project = parseHostPath(mount.hostDir);
  const target = parseHostPath(hostPath);
  if (project.segments.length === 0 || !rootsEqual(target.root, project.root)) return null;
  const ci = isCaseInsensitive(mount.platform);
  if (target.segments.length < project.segments.length) return null;
  for (let i = 0; i < project.segments.length; i++) {
    if (!segmentsEqual(target.segments[i] ?? "", project.segments[i] ?? "", ci)) return null;
  }
  const rest = target.segments.slice(project.segments.length);
  return [`${MOUNT_PREFIX}/${projectDirName(mount)}`, ...rest].join("/");
}

/**
 * Map a container path under `/mnt/<name>` back to its absolute host path in `mount.platform`'s
 * native syntax. Returns `null` if `containerPath` is not under the mounted project's prefix.
 */
export function containerToHostPath(containerPath: string, mount: ProjectMount): string | null {
  const norm = containerPath.trim().replace(/\\/g, "/");
  const prefix = `${MOUNT_PREFIX}/${projectDirName(mount)}`;
  if (norm !== prefix && !norm.startsWith(prefix + "/")) return null;
  const rest = norm.slice(prefix.length).split("/").filter(Boolean);
  const project = parseHostPath(mount.hostDir);
  return joinHostPath(project.root, [...project.segments, ...rest], mount.platform);
}

/**
 * General form of `containerToHostPath`, for a project this app did not itself mount (no
 * `stack.start`-owned `ProjectMount`, e.g. a manually-connected external server or one launched
 * outside the compose stack): maps a container path to its host equivalent given an explicit
 * `(containerRoot, hostRoot)` pair instead of assuming the `/mnt/<name>` convention `stack.start`
 * always uses. `GET /api/project`'s `container_path`/`host_path` is exactly such a pair (`Project`
 * schema, `contracts/openapi.v1.yaml`). Returns `null` if `hostRoot` is unknown (`host_path` was
 * `null` — the server itself doesn't know it either, e.g. JupyterHub-hosted) or `containerPath`
 * is not under `containerRoot`.
 */
export function mapContainerToHostViaProjectRoot(
  containerPath: string,
  containerRoot: string,
  hostRoot: string | null,
  platform: HostPlatform,
): string | null {
  if (!hostRoot) return null;
  const norm = containerPath.trim().replace(/\\/g, "/");
  const prefix = containerRoot.trim().replace(/\\/g, "/").replace(/\/+$/, "");
  if (norm !== prefix && !norm.startsWith(prefix + "/")) return null;
  const rest = norm.slice(prefix.length).split("/").filter(Boolean);
  const project = parseHostPath(hostRoot);
  return joinHostPath(project.root, [...project.segments, ...rest], platform);
}

/**
 * The reverse of `mapContainerToHostViaProjectRoot`: maps an absolute host path back to its
 * container-path equivalent given an explicit `(containerRoot, hostRoot)` pair, for a project this
 * app did not itself mount (no `stack.start`-owned `ProjectMount`). Used by the file/directory
 * picker (`tit:selectFile`/`tit:selectDirectory`) so a host path the user just picked is handed to
 * the renderer as the container path its `PathInput` fields expect (ra_13 finding 8), not the raw
 * host path. Returns `null` if `hostRoot` is unknown or `hostPath` is not inside it — the caller
 * returns `undefined` (with the reason logged) rather than leaking an un-mappable host path.
 */
export function mapHostToContainerViaProjectRoot(
  hostPath: string,
  containerRoot: string,
  hostRoot: string | null,
  platform: HostPlatform,
): string | null {
  if (!hostRoot) return null;
  const project = parseHostPath(hostRoot);
  const target = parseHostPath(hostPath);
  if (project.segments.length === 0 || !rootsEqual(target.root, project.root)) return null;
  const ci = isCaseInsensitive(platform);
  if (target.segments.length < project.segments.length) return null;
  for (let i = 0; i < project.segments.length; i++) {
    if (!segmentsEqual(target.segments[i] ?? "", project.segments[i] ?? "", ci)) return null;
  }
  const rest = target.segments.slice(project.segments.length);
  const prefix = containerRoot.trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return [prefix, ...rest].join("/");
}
