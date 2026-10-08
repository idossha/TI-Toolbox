/**
 * The Assistant pane (ARCHITECTURE §6, "The user's own agent runs in a host terminal"): a real
 * pseudo-terminal on the HOST running the user's own `claude` or `codex` CLI, with the bundled
 * agent plugin attached and the connected session's URL/token in its environment so the
 * `ti-toolbox-jobs` MCP server reaches this app's server in Docker and native runtimes alike.
 *
 * TI-Toolbox never calls an AI service and never reads the CLIs' credentials: login state is the
 * exit status of the CLI's own status command (`claude auth status`, `codex login status`), whose
 * output is discarded. The renderer chooses only `"claude" | "codex"`; every executable path,
 * argument, directory and environment value is decided here.
 */
import { execFile } from "node:child_process";
import { accessSync, constants, existsSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, isAbsolute, join, relative, resolve, sep } from "node:path";
import type { TitAssistantCli, TitAssistantEffort, TitAssistantEvent, TitAssistantModel, TitAssistantOptions } from "../shared/tit-bridge";

export const ASSISTANT_CLIS: readonly TitAssistantCli[] = ["claude", "codex"];

export function isAssistantCli(value: unknown): value is TitAssistantCli {
  return value === "claude" || value === "codex";
}

/**
 * Session options. Accepted values, verified 2026-10-08: `claude --effort` takes low, medium, high,
 * xhigh, max (a bogus value only warns, hence the allowlist here) and `--model` the aliases
 * opus, sonnet, haiku, fable (each started a session on its latest model); Codex takes
 * `-c model_reasoning_effort=<level>` with low, medium, high, xhigh, max in its model catalog
 * (`codex debug models`). The menu stops at high; `/effort` inside the session reaches the rest.
 */
export const EFFORTS: readonly TitAssistantEffort[] = ["low", "medium", "high", "default"];
export const MODELS: Record<TitAssistantCli, readonly TitAssistantModel[]> = {
  claude: ["default", "opus", "sonnet", "haiku", "fable"],
  codex: ["default"],
};
export type AssistantOptions = Required<TitAssistantOptions>;
/** Low effort for both; Claude Code on Sonnet, Codex on its own model. */
const DEFAULTS: Record<TitAssistantCli, AssistantOptions> = {
  claude: { effort: "low", model: "sonnet" },
  codex: { effort: "low", model: "default" },
};

/** The renderer's options as the flags' source, or undefined for anything off the allowlist. Absent = the CLI's defaults. */
export function parseAssistantOptions(cli: TitAssistantCli, raw: unknown): AssistantOptions | undefined {
  if (raw === undefined || raw === null) return DEFAULTS[cli];
  if (typeof raw !== "object" || Array.isArray(raw)) return undefined;
  const { effort = DEFAULTS[cli].effort, model = DEFAULTS[cli].model, ...extra } = raw as Record<string, unknown>;
  if (Object.keys(extra).length) return undefined;
  if (!EFFORTS.includes(effort as TitAssistantEffort) || !MODELS[cli].includes(model as TitAssistantModel)) return undefined;
  return { effort: effort as TitAssistantEffort, model: model as TitAssistantModel };
}

/** The CLI's own login-status command: exit 0 = signed in, 1 = not (both verified 2026-10-07). */
const STATUS_ARGS: Record<TitAssistantCli, string[]> = { claude: ["auth", "status"], codex: ["login", "status"] };

const PATH_MARK = "__TIT_PATH__";

/** `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` for Assistant sessions (code.claude.com/docs/en/mcp, "Automatic backgrounding"). */
export const CLAUDE_MCP_BACKGROUND_MS = 5000;

type Run = (file: string, args: string[], options: { env: NodeJS.ProcessEnv; timeout: number; shell?: boolean }) => Promise<{ code: number; stdout: string }>;

export const runFile: Run = (file, args, options) =>
  new Promise((resolve) => {
    execFile(file, args, { ...options, windowsHide: true, maxBuffer: 1 << 20 }, (error, stdout) => {
      const code = error ? (typeof (error as { code?: unknown }).code === "number" ? (error as { code: number }).code : -1) : 0;
      resolve({ code, stdout: String(stdout ?? "") });
    });
  });

/**
 * The PATH a terminal would give the user. A macOS app started from Finder inherits launchd's
 * bare `/usr/bin:/bin:/usr/sbin:/sbin`, which finds neither `~/.local/bin/claude` nor
 * `/opt/homebrew/bin/codex`; an interactive login shell reads the rc files that add them. Windows
 * GUI apps already inherit the user's PATH. A few well-known install directories are appended in
 * case the shell is slow or prints nothing.
 */
export async function loginShellPath(env: NodeJS.ProcessEnv, platform: NodeJS.Platform, run: Run = runFile, home = homedir()): Promise<string> {
  const delimiter = platform === "win32" ? ";" : ":";
  const inherited = pathOf(env);
  if (platform === "win32") return inherited;
  const shell = env.SHELL || (platform === "darwin" ? "/bin/zsh" : "/bin/sh");
  let fromShell = "";
  try {
    const { stdout } = await run(shell, ["-ilc", `printf '%s' "${PATH_MARK}$PATH${PATH_MARK}"`], { env, timeout: 5000 });
    fromShell = stdout.split(PATH_MARK)[1] ?? "";
  } catch {
    // The fallback directories below still apply.
  }
  const wellKnown = [join(home, ".local", "bin"), join(home, ".claude", "local"), "/opt/homebrew/bin", "/usr/local/bin", join(home, ".npm-global", "bin")];
  const dirs = [...fromShell.split(delimiter), ...inherited.split(delimiter), ...wellKnown].filter(Boolean);
  return [...new Set(dirs)].join(delimiter);
}

function pathOf(env: NodeJS.ProcessEnv): string {
  const key = Object.keys(env).find((name) => name.toUpperCase() === "PATH");
  return (key && env[key]) || "";
}

function isExecutable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/** First `name` on `searchPath`; on Windows also `name.exe/.cmd/.bat` (npm installs `.cmd` shims). */
export function findExecutable(name: string, searchPath: string, platform: NodeJS.Platform, exists: (path: string) => boolean = isExecutable): string | undefined {
  const delimiter = platform === "win32" ? ";" : ":";
  const names = platform === "win32" ? [".exe", ".cmd", ".bat"].map((ext) => name + ext) : [name];
  for (const dir of searchPath.split(delimiter).filter(Boolean)) {
    for (const candidate of names) {
      const full = platform === "win32" ? `${dir.replace(/[\\/]+$/, "")}\\${candidate}` : `${dir.replace(/\/+$/, "")}/${candidate}`;
      if (exists(full)) return full;
    }
  }
  return undefined;
}

/**
 * The Python that runs the plugin's two MCP servers (stdlib-only, Python 3.9+). `python3` on macOS
 * and Linux; on Windows the `py` launcher (python.org installs), else `python` (also the Microsoft
 * Store install), else `python3`, because Windows has no `python3` unless the Store alias is set
 * up. Undefined when none is on the PATH: the launch then keeps the plugin's own `python3` default.
 */
export function findPython(searchPath: string, platform: NodeJS.Platform, exists: (path: string) => boolean = isExecutable): string | undefined {
  const names = platform === "win32" ? ["py", "python", "python3"] : ["python3"];
  for (const name of names) {
    const found = findExecutable(name, searchPath, platform, exists);
    if (found) return found;
  }
  return undefined;
}

const needsShell = (executable: string, platform: NodeJS.Platform) => platform === "win32" && /\.(cmd|bat)$/i.test(executable);

export async function isLoggedIn(cli: TitAssistantCli, executable: string, env: NodeJS.ProcessEnv, platform: NodeJS.Platform, run: Run = runFile): Promise<boolean> {
  // The arguments are constants, so the shell a Windows `.cmd` shim needs cannot inject anything.
  const { code } = await run(executable, STATUS_ARGS[cli], { env, timeout: 15000, shell: needsShell(executable, platform) });
  return code === 0;
}

/** A TOML string for a Codex `-c key=value` override: a literal string unless the text holds `'`. */
export function tomlString(text: string): string {
  return text.includes("'") || /[\r\n]/.test(text) ? JSON.stringify(text) : `'${text}'`;
}

export interface LaunchOptions {
  executable: string;
  /** The bundled `agent-plugin/` directory. */
  pluginDir: string;
  projectDir: string;
  serverUrl: string;
  token: string;
  searchPath: string;
  baseEnv: NodeJS.ProcessEnv;
  platform: NodeJS.Platform;
  /** From `parseAssistantOptions`; absent = the CLI's defaults (DEFAULTS). */
  options?: AssistantOptions;
  /** From `findPython`; absent = `python3`, the plugin's own default. */
  python?: string;
}

export interface Launch {
  file: string;
  args: string[];
  cwd: string;
  env: Record<string, string>;
}

/**
 * Claude Code: `--plugin-dir` loads the bundled plugin for this session only. When the user has
 * already installed `ti-toolbox@ti-toolbox`, Claude Code lists the session copy as
 * `ti-toolbox@inline` and registers each of its MCP servers once (`claude --plugin-dir … mcp list`,
 * 2.1.293), so nothing is registered twice and the tools match this app's version.
 *
 * The plugin's `.mcp.json` starts both servers with `${TIT_PYTHON:-python3}` (Claude Code expands
 * it; there is no per-platform command), so a Claude Code session gets `TIT_PYTHON` = `findPython`'s
 * answer unless the user set it, and Codex is given the same interpreter as its `command`.
 *
 * Codex has no plugin directory flag: `-c mcp_servers.<name>.*` overrides register both servers for
 * this run only, `env_vars` forwards the server URL/token (Codex starts MCP servers with a minimal
 * environment otherwise — verified with an env-dumping server), and `developer_instructions` points
 * it at the `ti-run-pipelines` skill. Nothing is written to `~/.codex` or `~/.claude`.
 */
export function buildLaunch(cli: TitAssistantCli, o: LaunchOptions): Launch {
  const sep = o.platform === "win32" ? "\\" : "/";
  const plugin = (...parts: string[]) => [o.pluginDir.replace(/[\\/]+$/, ""), ...parts].join(sep);
  const { effort, model } = o.options ?? DEFAULTS[cli];
  let args: string[];
  if (cli === "claude") {
    args = ["--plugin-dir", o.pluginDir];
    if (effort !== "default") args.push("--effort", effort);
    if (model !== "default") args.push("--model", model);
  } else {
    const python = o.python ?? "python3";
    const instructions =
      "TI-Toolbox is open on this project folder and its job server is reachable through the ti-toolbox-jobs MCP tools. " +
      `When the user asks you to run TI-Toolbox pipelines (stage scans, preprocess, optimise, simulate), first read ${plugin("skills", "ti-run-pipelines", "SKILL.md")} and follow it. ` +
      `The other TI-Toolbox skills are the SKILL.md files under ${plugin("skills")}.`;
    args = [
      "-c", `mcp_servers.ti-toolbox.command=${tomlString(python)}`,
      "-c", `mcp_servers.ti-toolbox.args=[${tomlString(plugin("mcp", "server.py"))}]`,
      "-c", `mcp_servers.ti-toolbox-jobs.command=${tomlString(python)}`,
      "-c", `mcp_servers.ti-toolbox-jobs.args=[${tomlString(plugin("mcp", "jobs_server.py"))}]`,
      "-c", `mcp_servers.ti-toolbox-jobs.env_vars=['TIT_SERVER_URL','TIT_SERVER_TOKEN']`,
      "-c", `developer_instructions=${tomlString(instructions)}`,
    ];
    // Enum values only (parseAssistantOptions), so the literal needs no escaping.
    if (effort !== "default") args.push("-c", `model_reasoning_effort="${effort}"`);
  }
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(o.baseEnv)) {
    if (value === undefined || key.toUpperCase() === "PATH" || key.startsWith("ELECTRON_")) continue;
    env[key] = value;
  }
  Object.assign(env, { PATH: o.searchPath, TERM: "xterm-256color", COLORTERM: "truecolor", TIT_SERVER_URL: o.serverUrl, TIT_SERVER_TOKEN: o.token });
  // Claude Code moves an MCP call still running after this delay (default 120 s) to a background
  // task and wakes the agent when it returns; 5 s lets `watch_proposal` free the conversation at
  // once instead of after two minutes. A value the user set themselves wins.
  if (cli === "claude" && env.CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS === undefined) env.CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS = String(CLAUDE_MCP_BACKGROUND_MS);
  if (cli === "claude" && o.python && env.TIT_PYTHON === undefined) env.TIT_PYTHON = o.python;
  if (needsShell(o.executable, o.platform)) {
    // ponytail: unverified on Windows; ConPTY cannot start a .cmd shim itself, cmd.exe can.
    return { file: "cmd.exe", args: ["/d", "/s", "/c", o.executable, ...args], cwd: o.projectDir, env };
  }
  return { file: o.executable, args, cwd: o.projectDir, env };
}

/** The connected server must be on this machine: a remote page must never drive a host shell. */
export function isLoopbackOrigin(origin: string): boolean {
  try {
    return ["127.0.0.1", "localhost", "[::1]"].includes(new URL(origin).hostname);
  } catch {
    return false;
  }
}

/** The minimal node-pty surface used here, so the session manager is testable with a fake. */
export interface PtyProcess {
  pid: number;
  onData(listener: (data: string) => void): unknown;
  onExit(listener: (event: { exitCode: number }) => void): unknown;
  write(data: string): void;
  resize(cols: number, rows: number): void;
  kill(signal?: string): void;
}

export type SpawnPty = (file: string, args: string[], options: { name: string; cols: number; rows: number; cwd: string; env: Record<string, string> }) => PtyProcess;

/** At most one live session per CLI; starting again replaces it (the pane's Restart). */
export function createAssistantSessions(spawn: SpawnPty, emit: (event: TitAssistantEvent) => void, log: (message: string) => void) {
  const sessions = new Map<TitAssistantCli, PtyProcess>();
  const clampSize = (value: unknown, fallback: number) => (Number.isInteger(value) && (value as number) > 1 && (value as number) <= 1000 ? (value as number) : fallback);
  const kill = (cli: TitAssistantCli) => {
    const pty = sessions.get(cli);
    if (!pty) return;
    sessions.delete(cli);
    try {
      pty.kill();
    } catch {
      // Already gone.
    }
    log(`assistant: stopped ${cli} (pid ${pty.pid})`);
  };
  return {
    start(cli: TitAssistantCli, launch: Launch, cols: unknown, rows: unknown): void {
      kill(cli);
      const pty = spawn(launch.file, launch.args, { name: "xterm-256color", cols: clampSize(cols, 100), rows: clampSize(rows, 30), cwd: launch.cwd, env: launch.env });
      sessions.set(cli, pty);
      // Never the arguments or environment: the environment carries the session token.
      log(`assistant: started ${cli} (pid ${pty.pid}) in ${launch.cwd}`);
      pty.onData((data) => {
        if (sessions.get(cli) === pty) emit({ cli, type: "data", data });
      });
      pty.onExit(({ exitCode }) => {
        if (sessions.get(cli) !== pty) return;
        sessions.delete(cli);
        emit({ cli, type: "exit", code: exitCode });
      });
    },
    write(cli: TitAssistantCli, data: unknown): void {
      if (typeof data === "string" && data.length <= 1 << 20) sessions.get(cli)?.write(data);
    },
    resize(cli: TitAssistantCli, cols: unknown, rows: unknown): void {
      const pty = sessions.get(cli);
      if (pty) pty.resize(clampSize(cols, 100), clampSize(rows, 30));
    },
    running: (cli: TitAssistantCli) => sessions.has(cli),
    kill,
    killAll(): void {
      for (const cli of [...sessions.keys()]) kill(cli);
    },
  };
}

/** POSIX single-quoting for the system-terminal script. */
export const shQuote = (value: string) => `'${value.replace(/'/g, `'\\''`)}'`;

/**
 * "Open in system terminal": the same launch in the user's own terminal app. macOS opens a
 * `.command` script in Terminal (LaunchServices does not pass an environment), so the script
 * carries the URL/token, lives in the user-only app data directory and deletes itself on its first
 * line. Linux and Windows pass the environment to the terminal they start instead; no file.
 */
export function openInSystemTerminal(
  launch: Launch,
  platform: NodeJS.Platform,
  scratchDir: string,
  spawnDetached: (file: string, args: string[], env: Record<string, string>, cwd: string) => void,
  which: (bin: string) => string | undefined = (bin) => (bin.includes("/") ? (isExecutable(bin) ? bin : undefined) : findExecutable(bin, launch.env.PATH ?? "", platform)),
): void {
  if (platform === "darwin") {
    const script = join(scratchDir, `ti-toolbox-assistant-${process.pid}-${Date.now()}.command`);
    const exports = ["PATH", "TERM", "COLORTERM", "TIT_SERVER_URL", "TIT_SERVER_TOKEN", "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS", "TIT_PYTHON"]
      .filter((key) => launch.env[key] !== undefined)
      .map((key) => `export ${key}=${shQuote(launch.env[key]!)}`);
    const body = ["#!/bin/sh", 'rm -f -- "$0"', ...exports, `cd ${shQuote(launch.cwd)} || exit 1`, `exec ${[launch.file, ...launch.args].map(shQuote).join(" ")}`, ""].join("\n");
    if (existsSync(script)) rmSync(script);
    writeFileSync(script, body, { mode: 0o700 });
    spawnDetached("open", ["-a", "Terminal", script], launch.env, launch.cwd);
  } else if (platform === "win32") {
    // ponytail: unverified on Windows; `start` hands its environment to the new console.
    spawnDetached("cmd.exe", ["/d", "/c", "start", '""', "/D", launch.cwd, "cmd.exe", "/k", launch.file, ...launch.args], launch.env, launch.cwd);
  } else {
    const terminal = linuxTerminalCommand(which, launch.env, launch.cwd, [launch.file, ...launch.args]);
    if (!terminal) throw new Error(NO_LINUX_TERMINAL);
    spawnDetached(terminal.file, terminal.args, launch.env, launch.cwd);
  }
}

/**
 * Linux terminals in the order they are tried after `$TERMINAL`, each with its own way of taking
 * a working directory and a command (argv, never a shell string, so nothing needs quoting). The
 * spawn's `cwd` covers the ones with no directory flag. `$TERMINAL` named after one of these gets
 * its flags; any other gets the near-universal `-e`.
 */
const LINUX_TERMINALS: Record<string, (dir: string, command: string[]) => string[]> = {
  "x-terminal-emulator": (_dir, command) => ["-e", ...command],
  "gnome-terminal": (dir, command) => [`--working-directory=${dir}`, "--", ...command],
  konsole: (dir, command) => ["--workdir", dir, "-e", ...command],
  "xfce4-terminal": (dir, command) => [`--working-directory=${dir}`, "-x", ...command],
  kitty: (dir, command) => ["--directory", dir, ...command],
  alacritty: (dir, command) => ["--working-directory", dir, "-e", ...command],
  xterm: (_dir, command) => ["-e", ...command],
};

export const NO_LINUX_TERMINAL =
  "No terminal application was found. Install one (gnome-terminal, konsole, xfce4-terminal, kitty, alacritty or xterm) or set $TERMINAL, or use the terminal on this page.";

/** The first terminal found: `$TERMINAL`, then `LINUX_TERMINALS` in order; undefined when none is installed. */
export function linuxTerminalCommand(which: (bin: string) => string | undefined, env: NodeJS.ProcessEnv, dir: string, command: string[]): { file: string; args: string[] } | undefined {
  const preferred = env.TERMINAL?.trim();
  for (const name of [...(preferred ? [preferred] : []), ...Object.keys(LINUX_TERMINALS)]) {
    const file = which(name);
    if (file) return { file, args: (LINUX_TERMINALS[basename(name)] ?? LINUX_TERMINALS.xterm!)(dir, command) };
  }
  return undefined;
}

export type ProjectPath = { ok: true; path: string; directory: boolean } | { ok: false; error: string };

/**
 * A path an Assistant session printed (absolute, or relative to the project folder it runs in) as
 * the real path it names, only when that is inside the project folder and exists. Symlinks are
 * resolved on both sides first, so neither `..` nor a link can reach outside.
 */
export function resolveProjectPath(raw: unknown, projectDir: string): ProjectPath {
  if (typeof raw !== "string" || !raw || raw.length > 4096 || raw.includes("\0")) return { ok: false, error: "Not a file path." };
  let root: string;
  let real: string;
  try {
    root = realpathSync(projectDir);
  } catch {
    return { ok: false, error: "The project folder is not on this computer." };
  }
  try {
    real = realpathSync(resolve(projectDir, raw));
  } catch {
    return { ok: false, error: `${raw} does not exist.` };
  }
  const rel = relative(root, real);
  if (isAbsolute(rel) || rel.split(sep)[0] === "..") return { ok: false, error: `${raw} is outside the project folder.` };
  return { ok: true, path: real, directory: statSync(real).isDirectory() };
}

