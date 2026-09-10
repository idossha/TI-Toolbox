/**
 * Host-side TI-Toolbox *user* config directory (telemetry consent, anonymous id) — distinct from
 * Electron's own `userData` dir. Mounted into the container at `/root/.config/ti-toolbox` so it
 * persists across projects and container restarts. Ported from
 * `package/src/backend/env.js#getUserConfigDir` (read-only reference).
 *
 * Platform resolution: macOS/Linux `~/.config/ti-toolbox` (macOS deliberately does NOT use
 * `~/Library/Application Support`, which is Electron's own cache-filled `userData`); Windows
 * `%APPDATA%\ti-toolbox`.
 */
import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function userConfigDir(platform: NodeJS.Platform = process.platform, env: NodeJS.ProcessEnv = process.env): string {
  if (platform === "win32") {
    return join(env.APPDATA || join(homedir(), "AppData", "Roaming"), "ti-toolbox");
  }
  if (platform === "darwin") {
    return join(homedir(), ".config", "ti-toolbox");
  }
  return join(env.XDG_CONFIG_HOME || join(homedir(), ".config"), "ti-toolbox");
}

/** `userConfigDir()`, created if missing. */
export function ensureUserConfigDir(platform?: NodeJS.Platform, env?: NodeJS.ProcessEnv): string {
  const dir = userConfigDir(platform, env);
  mkdirSync(dir, { recursive: true });
  return dir;
}
