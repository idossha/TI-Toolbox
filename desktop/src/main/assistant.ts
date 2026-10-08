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
import { accessSync, constants, existsSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { TitAssistantCli, TitAssistantEvent } from "../shared/tit-bridge";

export const ASSISTANT_CLIS: readonly TitAssistantCli[] = ["claude", "codex"];

export function isAssistantCli(value: unknown): value is TitAssistantCli {
  return value === "claude" || value === "codex";
}

/** The CLI's own login-status command: exit 0 = signed in, 1 = not (both verified 2026-10-07). */
const STATUS_ARGS: Record<TitAssistantCli, string[]> = { claude: ["auth", "status"], codex: ["login", "status"] };

const PATH_MARK = "__TIT_PATH__";

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
 * Codex has no plugin directory flag: `-c mcp_servers.<name>.*` overrides register both servers for
 * this run only, `env_vars` forwards the server URL/token (Codex starts MCP servers with a minimal
 * environment otherwise — verified with an env-dumping server), and `developer_instructions` points
 * it at the `ti-run-pipelines` skill. Nothing is written to `~/.codex` or `~/.claude`.
 */
export function buildLaunch(cli: TitAssistantCli, o: LaunchOptions): Launch {
  const sep = o.platform === "win32" ? "\\" : "/";
  const plugin = (...parts: string[]) => [o.pluginDir.replace(/[\\/]+$/, ""), ...parts].join(sep);
  let args: string[];
  if (cli === "claude") {
    args = ["--plugin-dir", o.pluginDir];
  } else {
    const python = "python3";
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
  }
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(o.baseEnv)) {
    if (value === undefined || key.toUpperCase() === "PATH" || key.startsWith("ELECTRON_")) continue;
    env[key] = value;
  }
  Object.assign(env, { PATH: o.searchPath, TERM: "xterm-256color", COLORTERM: "truecolor", TIT_SERVER_URL: o.serverUrl, TIT_SERVER_TOKEN: o.token });
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
export function openInSystemTerminal(launch: Launch, platform: NodeJS.Platform, scratchDir: string, spawnDetached: (file: string, args: string[], env: Record<string, string>, cwd: string) => void): void {
  if (platform === "darwin") {
    const script = join(scratchDir, `ti-toolbox-assistant-${process.pid}-${Date.now()}.command`);
    const exports = ["PATH", "TERM", "COLORTERM", "TIT_SERVER_URL", "TIT_SERVER_TOKEN"].map((key) => `export ${key}=${shQuote(launch.env[key] ?? "")}`);
    const body = ["#!/bin/sh", 'rm -f -- "$0"', ...exports, `cd ${shQuote(launch.cwd)} || exit 1`, `exec ${[launch.file, ...launch.args].map(shQuote).join(" ")}`, ""].join("\n");
    if (existsSync(script)) rmSync(script);
    writeFileSync(script, body, { mode: 0o700 });
    spawnDetached("open", ["-a", "Terminal", script], launch.env, launch.cwd);
  } else if (platform === "win32") {
    // ponytail: unverified on Windows; `start` hands its environment to the new console.
    spawnDetached("cmd.exe", ["/d", "/c", "start", '""', "/D", launch.cwd, "cmd.exe", "/k", launch.file, ...launch.args], launch.env, launch.cwd);
  } else {
    // ponytail: Debian's alternatives link only; other desktops get the pane or a copied command.
    spawnDetached("x-terminal-emulator", ["-e", launch.file, ...launch.args], launch.env, launch.cwd);
  }
}

