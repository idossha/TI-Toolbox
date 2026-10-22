/**
 * Host-side TI-Toolbox *user* config directory (telemetry consent, anonymous id) — distinct from
 * Electron's own `userData` dir. Mounted into the container at `/root/.config/ti-toolbox` so it
 * persists across projects and container restarts.
 *
 * One rule for every launcher (`tit/launch.py#user_config_path`, `loader.sh#user_config_dir`,
 * `tests/fixtures/user_config_dirs.json`), so a telemetry opt-out made through one is the one the
 * others mount; it is the table `docs/wiki/telemetry.md` documents. macOS `~/.config/ti-toolbox`
 * always (a Dock launch never sees a shell's `XDG_CONFIG_HOME`, and macOS deliberately does NOT use
 * `~/Library/Application Support`, which is Electron's own cache-filled `userData`); Windows
 * `%APPDATA%\ti-toolbox`; Linux `$XDG_CONFIG_HOME/ti-toolbox` when set and non-empty, else
 * `~/.config/ti-toolbox`. Joined in the target platform's own path syntax.
 */
import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { posix, win32 } from "node:path";

export function userConfigDir(
  platform: NodeJS.Platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
  home: string = homedir(),
): string {
  if (platform === "win32") {
    return win32.join(env.APPDATA || win32.join(home, "AppData", "Roaming"), "ti-toolbox");
  }
  const xdg = platform === "darwin" ? "" : env.XDG_CONFIG_HOME;
  return posix.join(xdg || posix.join(home, ".config"), "ti-toolbox");
}

/** `userConfigDir()`, created if missing. */
export function ensureUserConfigDir(platform?: NodeJS.Platform, env?: NodeJS.ProcessEnv): string {
  const dir = userConfigDir(platform, env);
  mkdirSync(dir, { recursive: true });
  return dir;
}
