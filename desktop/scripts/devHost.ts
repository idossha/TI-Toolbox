/** Local API server for --host development; Docker-backed dev remains the default. */
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { join } from "node:path";

export async function availableHostPort(preferred: number): Promise<number> {
  for (let port = preferred; port < Math.min(preferred + 64, 65536); port++) {
    const available = await new Promise<boolean>((resolve) => {
      const socket = createServer();
      socket.once("error", () => resolve(false));
      socket.listen(port, "127.0.0.1", () => socket.close(() => resolve(true)));
    });
    if (available) return port;
  }
  throw new Error("No free localhost port for the development API.");
}

export async function startHostServer(repoDir: string, projectDir: string, preferredPort: number) {
  const port = await availableHostPort(preferredPort);
  const origin = `http://127.0.0.1:${port}`;
  const token = randomBytes(32).toString("hex");
  const venv = join(repoDir, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const python = process.env.TIT_DEV_PYTHON || (existsSync(venv) ? venv : "python3");
  const child = spawn(python, ["-m", "tit.server", "--host", "127.0.0.1", "--project", projectDir, "--port", String(port), "--reload", "--reload-dir", join(repoDir, "tit"), "--dev-origin", "http://127.0.0.1:5173", "--dev-origin", "http://localhost:5173"], {
    cwd: repoDir,
    env: { ...process.env, PYTHONPATH: repoDir, TIT_SERVER_TOKEN: token, TIT_STATIC_DIR: join(repoDir, "desktop/out/renderer"), LOCAL_PROJECT_DIR: projectDir },
    stdio: "inherit",
    detached: process.platform !== "win32",
  });
  let failure: Error | undefined;
  child.once("error", (error) => { failure = error; });
  child.once("exit", (code) => { failure = new Error(`Host API exited (${code}). Install the host dependencies or set TIT_DEV_PYTHON.`); });
  const stop = () => {
    if (!child.pid) return;
    try {
      if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      else process.kill(-child.pid, "SIGTERM");
    } catch { /* Already stopped. */ }
  };
  try {
    for (let attempt = 0; attempt < 180; attempt++) {
      if (failure) throw failure;
      const healthy = await fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(500) }).then((r) => r.ok).catch(() => false);
      if (healthy) return { origin, token, attached: false, stop };
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error("Host API startup timed out. Check its output above.");
  } catch (error) {
    stop();
    throw error;
  }
}
