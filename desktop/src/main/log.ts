import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { app } from "electron";

let logFile: string | undefined;

/** Minimal main-process log under app.getPath("logs"); call after app is ready. */
export function initLog(): string {
  // Tests isolate everything under TIT_USER_DATA_DIR; otherwise the platform's logs dir.
  if (process.env.TIT_USER_DATA_DIR) app.setAppLogsPath(join(app.getPath("userData"), "logs"));
  else app.setAppLogsPath();
  const dir = app.getPath("logs");
  mkdirSync(dir, { recursive: true });
  logFile = join(dir, "main.log");
  log("info", `TI-Toolbox desktop ${app.getVersion()} electron ${process.versions.electron}`);
  return logFile;
}

export function log(level: "info" | "warn" | "error", message: string): void {
  const line = `${new Date().toISOString()} ${level.toUpperCase()} ${message}\n`;
  if (!logFile) return;
  try {
    appendFileSync(logFile, line);
  } catch {
    // logging must never break the app
  }
}
