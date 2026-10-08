/**
 * The Assistant pane's host side (ARCHITECTURE §6): CLI discovery on the login-shell PATH, the
 * exact launch per CLI, the token's path (environment only, never a log line), and one real PTY.
 *
 * Expected flags come from the installed CLIs' own help and behaviour, checked 2026-10-07 against
 * Claude Code 2.1.293 and codex-cli 0.155.1 (`claude --plugin-dir … mcp list`, `codex -c … mcp get
 * --json`, `codex -c developer_instructions=… debug prompt-input`). The Codex override test below
 * re-asks the installed `codex` to parse what `buildLaunch` emits and skips, saying so, without it.
 * Windows `.cmd` and system-terminal launches are deliberately not exercised here (no Windows host).
 */
import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { buildLaunch, createAssistantSessions, findExecutable, isLoggedIn, isLoopbackOrigin, loginShellPath, shQuote, tomlString, type PtyProcess } from "./assistant";
import type { TitAssistantEvent } from "../shared/tit-bridge";

const TOKEN = "tok-3f9a-secret";
const base = {
  executable: "/home/u/.local/bin/claude",
  pluginDir: "/Applications/TI-Toolbox.app/Contents/Resources/agent-plugin",
  projectDir: "/data/my project",
  serverUrl: "http://127.0.0.1:8765",
  token: TOKEN,
  searchPath: "/home/u/.local/bin:/usr/bin",
  baseEnv: { HOME: "/home/u", PATH: "/usr/bin", ELECTRON_RUN_AS_NODE: "1", LANG: "en_US.UTF-8" },
  platform: "darwin" as const,
};

describe("login-shell PATH", () => {
  it("takes the PATH between the markers even when rc files print around it", async () => {
    const run = async () => ({ code: 0, stdout: "Welcome!\n__TIT_PATH__/Users/u/.local/bin:/opt/homebrew/bin:/usr/bin__TIT_PATH__\nbye" });
    const path = await loginShellPath({ PATH: "/usr/bin:/bin", SHELL: "/bin/zsh" }, "darwin", run, "/Users/u");
    expect(path.split(":").slice(0, 3)).toEqual(["/Users/u/.local/bin", "/opt/homebrew/bin", "/usr/bin"]);
    expect(path.split(":")).toContain("/bin");
    expect(new Set(path.split(":")).size).toBe(path.split(":").length);
  });
  it("asks the user's own shell for an interactive login PATH", async () => {
    const calls: [string, string[]][] = [];
    await loginShellPath({ PATH: "/usr/bin", SHELL: "/usr/local/bin/fish" }, "linux", async (file, args) => {
      calls.push([file, args]);
      return { code: 0, stdout: "" };
    });
    expect(calls[0]?.[0]).toBe("/usr/local/bin/fish");
    expect(calls[0]?.[1][0]).toBe("-ilc");
  });
  it("still finds the usual install directories when the shell fails", async () => {
    const path = await loginShellPath({ PATH: "/usr/bin:/bin" }, "darwin", async () => { throw new Error("timeout"); }, "/Users/u");
    expect(path.split(":")).toEqual(expect.arrayContaining(["/usr/bin", "/Users/u/.local/bin", "/opt/homebrew/bin"]));
  });
  it("uses the inherited PATH on Windows without running a shell", async () => {
    const path = await loginShellPath({ Path: "C:\\Windows;C:\\Users\\u\\AppData\\Roaming\\npm" }, "win32", async () => { throw new Error("must not run"); });
    expect(path).toBe("C:\\Windows;C:\\Users\\u\\AppData\\Roaming\\npm");
  });
});

describe("CLI detection", () => {
  it("returns the first executable on the PATH", () => {
    const present = new Set(["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]);
    expect(findExecutable("codex", "/usr/bin:/opt/homebrew/bin:/usr/local/bin", "darwin", (p) => present.has(p))).toBe("/opt/homebrew/bin/codex");
    expect(findExecutable("claude", "/usr/bin", "darwin", (p) => present.has(p))).toBeUndefined();
  });
  it("finds npm's .cmd shim on Windows", () => {
    const present = new Set(["C:\\Users\\u\\AppData\\Roaming\\npm\\codex.cmd"]);
    expect(findExecutable("codex", "C:\\Windows;C:\\Users\\u\\AppData\\Roaming\\npm\\", "win32", (p) => present.has(p))).toBe("C:\\Users\\u\\AppData\\Roaming\\npm\\codex.cmd");
  });
  it("reads login state from the status command's exit code only", async () => {
    const seen: string[][] = [];
    const run = (code: number) => async (_file: string, args: string[]) => {
      seen.push(args);
      return { code, stdout: '{"loggedIn": true, "email": "someone@example.org"}' };
    };
    expect(await isLoggedIn("claude", "/x/claude", {}, "darwin", run(0))).toBe(true);
    expect(await isLoggedIn("codex", "/x/codex", {}, "darwin", run(1))).toBe(false);
    expect(seen).toEqual([["auth", "status"], ["login", "status"]]);
  });
});

describe("launch", () => {
  it("attaches the bundled plugin to Claude Code for this session only", () => {
    const launch = buildLaunch("claude", base);
    expect(launch.file).toBe(base.executable);
    expect(launch.args).toEqual(["--plugin-dir", base.pluginDir]);
    expect(launch.cwd).toBe(base.projectDir);
  });
  it("registers both MCP servers and the pipeline guidance for Codex without touching ~/.codex", () => {
    const launch = buildLaunch("codex", { ...base, executable: "/opt/homebrew/bin/codex" });
    const overrides = launch.args.filter((_, i) => launch.args[i - 1] === "-c");
    expect(launch.args.filter((a) => a === "-c")).toHaveLength(overrides.length);
    expect(overrides).toContain(`mcp_servers.ti-toolbox-jobs.args=['${base.pluginDir}/mcp/jobs_server.py']`);
    expect(overrides).toContain(`mcp_servers.ti-toolbox.args=['${base.pluginDir}/mcp/server.py']`);
    expect(overrides).toContain("mcp_servers.ti-toolbox-jobs.env_vars=['TIT_SERVER_URL','TIT_SERVER_TOKEN']");
    expect(overrides.find((o) => o.startsWith("developer_instructions="))).toContain(`${base.pluginDir}/skills/ti-run-pipelines/SKILL.md`);
    expect(launch.args.join(" ")).not.toContain(TOKEN);
  });
  it("puts the session URL and token in the environment, and nothing of Electron's", () => {
    const { env } = buildLaunch("claude", base);
    expect(env.TIT_SERVER_URL).toBe(base.serverUrl);
    expect(env.TIT_SERVER_TOKEN).toBe(TOKEN);
    expect(env.PATH).toBe(base.searchPath);
    expect(env.TERM).toBe("xterm-256color");
    expect(env.LANG).toBe("en_US.UTF-8");
    expect(env.ELECTRON_RUN_AS_NODE).toBeUndefined();
  });
  it("leaves one PATH key on Windows and starts a .cmd shim through cmd.exe", () => {
    const launch = buildLaunch("codex", { ...base, platform: "win32", executable: "C:\\npm\\codex.cmd", pluginDir: "C:\\TI\\resources\\agent-plugin", baseEnv: { Path: "C:\\Windows" }, searchPath: "C:\\Windows;C:\\npm" });
    expect(Object.keys(launch.env).filter((k) => k.toUpperCase() === "PATH")).toEqual(["PATH"]);
    expect(launch.file).toBe("cmd.exe");
    expect(launch.args.slice(0, 4)).toEqual(["/d", "/s", "/c", "C:\\npm\\codex.cmd"]);
    expect(launch.args).toContain("mcp_servers.ti-toolbox-jobs.args=['C:\\TI\\resources\\agent-plugin\\mcp\\jobs_server.py']");
  });
  it("quotes TOML and shell values safely", () => {
    expect(tomlString("/a b/c")).toBe("'/a b/c'");
    expect(tomlString("/Users/o'brien/x")).toBe('"/Users/o\'brien/x"');
    expect(shQuote("it's here")).toBe(`'it'\\''s here'`);
  });
  it("only drives a terminal for a server on this computer", () => {
    expect(isLoopbackOrigin("http://127.0.0.1:8765")).toBe(true);
    expect(isLoopbackOrigin("http://localhost:8765")).toBe(true);
    expect(isLoopbackOrigin("https://lab-server.example.org")).toBe(false);
    expect(isLoopbackOrigin("not a url")).toBe(false);
  });
});

let codexPath: string | undefined;
try {
  codexPath = execFileSync("sh", ["-lc", "command -v codex"], { encoding: "utf8" }).trim() || undefined;
} catch {
  codexPath = undefined;
}
describe.skipIf(!codexPath)("the installed Codex reads the overrides", () => {
  it("parses the job server registration exactly as built", () => {
    const launch = buildLaunch("codex", { ...base, executable: codexPath! });
    const out = execFileSync(codexPath!, [...launch.args, "mcp", "get", "ti-toolbox-jobs", "--json"], { encoding: "utf8", timeout: 30000 });
    const transport = (JSON.parse(out) as { transport: { command: string; args: string[]; env_vars: string[] } }).transport;
    expect(transport.command).toBe("python3");
    expect(transport.args).toEqual([`${base.pluginDir}/mcp/jobs_server.py`]);
    expect(transport.env_vars).toEqual(["TIT_SERVER_URL", "TIT_SERVER_TOKEN"]);
  });
});
if (!codexPath) console.log("skipping: codex override parse — codex is not on this machine's PATH");

function fakePty() {
  const listeners: { data?: (d: string) => void; exit?: (e: { exitCode: number }) => void } = {};
  const writes: string[] = [];
  const sizes: [number, number][] = [];
  let killed = 0;
  const pty: PtyProcess = {
    pid: 4242,
    onData: (l) => (listeners.data = l),
    onExit: (l) => (listeners.exit = l),
    write: (d) => writes.push(d),
    resize: (c, r) => sizes.push([c, r]),
    kill: () => { killed++; },
  };
  return { pty, listeners, writes, sizes, killed: () => killed };
}

describe("sessions", () => {
  it("keeps one session per CLI, forwards I/O and never logs the token", () => {
    const ptys = [fakePty(), fakePty()];
    const spawnArgs: unknown[] = [];
    const events: TitAssistantEvent[] = [];
    const logs: string[] = [];
    const sessions = createAssistantSessions((...args) => { spawnArgs.push(args); return ptys[spawnArgs.length - 1]!.pty; }, (e) => events.push(e), (m) => logs.push(m));
    const launch = buildLaunch("claude", base);
    sessions.start("claude", launch, 120, 40);
    expect((spawnArgs[0] as [string, string[], { cols: number; rows: number }])[2]).toMatchObject({ cols: 120, rows: 40, cwd: base.projectDir });
    ptys[0]!.listeners.data!("hello");
    sessions.write("claude", "/login\r");
    sessions.write("claude", 42);
    sessions.resize("claude", 80, 9999);
    expect(ptys[0]!.writes).toEqual(["/login\r"]);
    expect(ptys[0]!.sizes).toEqual([[80, 30]]);
    // Restart replaces the first session; its late output and exit are dropped.
    sessions.start("claude", launch, 0, 0);
    expect(ptys[0]!.killed()).toBe(1);
    ptys[0]!.listeners.data!("stale");
    ptys[0]!.listeners.exit!({ exitCode: 9 });
    ptys[1]!.listeners.exit!({ exitCode: 0 });
    expect(events).toEqual([{ cli: "claude", type: "data", data: "hello" }, { cli: "claude", type: "exit", code: 0 }]);
    expect(sessions.running("claude")).toBe(false);
    expect(logs.length).toBeGreaterThan(0);
    expect(logs.join("\n")).not.toContain(TOKEN);
  });
  it("killAll ends every CLI's session", () => {
    const ptys = [fakePty(), fakePty()];
    let n = 0;
    const sessions = createAssistantSessions(() => ptys[n++]!.pty, () => {}, () => {});
    sessions.start("claude", buildLaunch("claude", base), 80, 24);
    sessions.start("codex", buildLaunch("codex", base), 80, 24);
    sessions.killAll();
    expect(ptys.map((p) => p.killed())).toEqual([1, 1]);
    expect(sessions.running("claude") || sessions.running("codex")).toBe(false);
  });
});

describe.skipIf(process.platform === "win32")("a real pseudo-terminal", () => {
  it("runs a harmless command through node-pty and reports its output and exit code", async () => {
    const { spawn } = await import("node-pty");
    const events: TitAssistantEvent[] = [];
    const done = new Promise<void>((resolve) => {
      const sessions = createAssistantSessions(spawn as never, (e) => { events.push(e); if (e.type === "exit") resolve(); }, () => {});
      sessions.start("claude", { file: "/bin/sh", args: ["-c", '[ -t 1 ] && t=yes; printf "tty=%s url=%s" "$t" "$TIT_SERVER_URL"; exit 3'], cwd: "/", env: { PATH: "/usr/bin:/bin", TIT_SERVER_URL: base.serverUrl } }, 80, 24);
    });
    await done;
    const output = events.filter((e) => e.type === "data").map((e) => (e as { data: string }).data).join("");
    expect(output).toContain(`tty=yes url=${base.serverUrl}`);
    expect(events.at(-1)).toEqual({ cli: "claude", type: "exit", code: 3 });
  });
});
