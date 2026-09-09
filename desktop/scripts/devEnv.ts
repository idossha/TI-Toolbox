/**
 * `desktop/.env.dev` — the four settings `npm run dev` needs, and nothing else.
 *
 * Parsed here rather than with `dotenv`: the format this file needs is `KEY=value`, comments and
 * blank lines, and a dependency whose behaviour has to be looked up is worse than twenty lines
 * whose behaviour is written down. What is deliberately NOT supported, so nobody writes it and
 * wonders: `${VAR}` expansion, multi-line values, and `export ` prefixes are not interpreted —
 * a value is the literal text after the first `=`, with one layer of matching quotes removed.
 *
 * The shell wins over the file (`TIT_DEV_PORT=8766 npm run dev`), which is the opposite of what
 * `dotenv` does by default. Reason: the file is the project's standing configuration and the
 * command line is what the developer means *this time*; a file that silently overrode the command
 * line would make a one-off run against a second port impossible to explain.
 */
import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { parseDocument } from "yaml";
import { interpolate } from "../src/shared/composeFile";

export const DEV_ENV_FILE = ".env.dev";
export const DEV_ENV_EXAMPLE = ".env.dev.example";

/** Resolved, validated configuration for one `npm run dev`. */
export interface DevConfig {
  /** Absolute host path of the BIDS project the container is opened for. */
  projectDir: string;
  /** `${TIT_IMAGE_TAG}` — which `idossha/ti-toolbox:<tag>` to run. */
  imageTag: string;
  /** Host port the container publishes, and the port the app connects to. */
  port: number;
  /** Bind-mount this worktree at `/ti-toolbox` and run the server with `--reload` scoped to it. */
  mountRepo: boolean;
}

/** A configuration problem the developer can fix, phrased as the fix. */
export class DevConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DevConfigError";
  }
}

/**
 * `KEY=value` lines. Blank lines and `#` comments are skipped; a line with no `=` is skipped too
 * (rather than throwing) so a half-written note in the file does not stop the dev loop. One layer
 * of matching `"` or `'` around the value is removed, so a path with spaces can be quoted.
 */
export function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

/**
 * The file's values, overlaid by whatever the invoking shell already set (empty values in the
 * shell do not count as set — an exported-but-empty variable is how a wrapper script accidentally
 * blanks a setting the file supplies).
 */
export function mergeDevEnv(fileVars: Record<string, string>, shell: NodeJS.ProcessEnv): Record<string, string> {
  const merged: Record<string, string> = { ...fileVars };
  for (const key of Object.keys(fileVars).concat(["TIT_DEV_PROJECT_DIR", "TIT_DEV_IMAGE_TAG", "TIT_DEV_PORT", "TIT_DEV_MOUNT_REPO"])) {
    const value = shell[key];
    if (value !== undefined && value !== "") merged[key] = value;
  }
  return merged;
}

function parseBool(raw: string, key: string): boolean {
  const value = raw.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(value)) return true;
  if (["0", "false", "no", "off"].includes(value)) return false;
  throw new DevConfigError(`${key} must be 1 or 0 (got "${raw}")`);
}

/**
 * Validated `DevConfig`, or a `DevConfigError` naming the variable and the fix. `desktopDir` is
 * only used to resolve a relative `TIT_DEV_PROJECT_DIR`, so `../..` in the file means what a
 * developer sitting in `desktop/` would expect.
 */
export function resolveDevConfig(vars: Record<string, string>, desktopDir: string): DevConfig {
  const projectRaw = (vars.TIT_DEV_PROJECT_DIR ?? "").trim();
  if (!projectRaw) {
    throw new DevConfigError(
      `TIT_DEV_PROJECT_DIR is not set. Run npm run dev -- --project /path/to/project, or copy ${DEV_ENV_EXAMPLE} to ${DEV_ENV_FILE} and point it at a BIDS project directory.`,
    );
  }
  const projectDir = isAbsolute(projectRaw) ? resolve(projectRaw) : resolve(desktopDir, projectRaw);
  if (!existsSync(projectDir)) throw new DevConfigError(`TIT_DEV_PROJECT_DIR does not exist: ${projectDir}`);

  const portRaw = (vars.TIT_DEV_PORT ?? "").trim();
  const port = portRaw === "" ? 8765 : Number(portRaw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new DevConfigError(`TIT_DEV_PORT must be a port number 1-65535 (got "${portRaw}")`);

  const tagRaw = (vars.TIT_DEV_IMAGE_TAG ?? "").trim();
  const mountRaw = (vars.TIT_DEV_MOUNT_REPO ?? "").trim();

  return {
    projectDir,
    imageTag: tagRaw === "" ? "dev" : tagRaw,
    port,
    mountRepo: mountRaw === "" ? true : parseBool(mountRaw, "TIT_DEV_MOUNT_REPO"),
  };
}

/** Reads `desktop/.env.dev` (absent is fine — the shell may carry everything) and resolves it. */
export function loadDevConfig(desktopDir: string, shell: NodeJS.ProcessEnv = process.env): DevConfig {
  const file = join(desktopDir, DEV_ENV_FILE);
  const fileVars = existsSync(file) ? parseDotenv(readFileSync(file, "utf8")) : {};
  const vars = mergeDevEnv(fileVars, shell);
  const compose = join(desktopDir, "..", "docker-compose.yml");
  if (!vars.TIT_DEV_IMAGE_TAG?.trim() && existsSync(compose)) {
    const image = parseDocument(readFileSync(compose, "utf8")).getIn(["services", "tit", "image"]);
    if (typeof image !== "string") throw new DevConfigError("docker-compose.yml has no tit image");
    const resolved = interpolate(image, {});
    if (!resolved.startsWith("idossha/ti-toolbox:")) throw new DevConfigError("Set TIT_DEV_IMAGE_TAG for this compose image");
    vars.TIT_DEV_IMAGE_TAG = resolved.slice("idossha/ti-toolbox:".length);
  }
  return resolveDevConfig(vars, desktopDir);
}
