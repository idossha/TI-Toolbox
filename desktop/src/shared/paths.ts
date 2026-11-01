/**
 * Container -> host path mapping for one mounted project.
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
 * same test suite can exercise Windows/WSL/macOS path shapes from any CI runner. `tit/host_path.py`
 * holds the same rules (plus the host -> container direction the server needs); both suites read
 * `tests/fixtures/host_paths.json` so they cannot drift.
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

interface ParsedHostPath {
  /** `"/"` (POSIX), `"C:/"` (a Windows drive) or `"//server/share/"` (UNC, incl. WSL `\\wsl.localhost\...`). */
  root: string;
  segments: string[];
}

function parseHostPath(raw: string): ParsedHostPath {
  const norm = raw.replace(/\\/g, "/");
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

/**
 * The `<name>` in `/mnt/<name>` the compose stack mounts `hostDir` at. Throws for a drive or share
 * root, which has no name. `tit/host_path.py`'s `project_dir_name` is the same rule.
 */
export function projectDirName(hostDir: string): string {
  const { segments } = parseHostPath(hostDir);
  const name = segments[segments.length - 1];
  if (!name) throw new Error(`Project directory has no name: ${hostDir}`);
  return name;
}

function normContainerPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "");
}

/**
 * A container path under `containerRoot` -> the host path under `hostRoot`, in `platform`'s native
 * syntax. `null` when `hostRoot` is unknown (`Project.host_path` was null) or the path is not under
 * `containerRoot` (`/mnt/000x` is not under `/mnt/000`). `tit/host_path.py`'s `to_host` agrees.
 */
export function containerToHostPath(
  containerPath: string,
  containerRoot: string,
  hostRoot: string | null,
  platform: HostPlatform,
): string | null {
  if (!hostRoot) return null;
  const norm = normContainerPath(containerPath);
  const prefix = normContainerPath(containerRoot);
  if (norm !== prefix && !norm.startsWith(prefix + "/")) return null;
  const rest = norm.slice(prefix.length).split("/").filter(Boolean);
  if (rest.includes("..")) return null;
  const project = parseHostPath(hostRoot);
  return joinHostPath(project.root, [...project.segments, ...rest], platform);
}
