import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { app } from "electron";
import type { TitSettings } from "../shared/tit-bridge";

const ALLOWED_KEYS = ["lastServerUrl", "lastProjectDir", "tetravoxPath"] as const;

function settingsPath(): string {
  return join(app.getPath("userData"), "settings.json");
}

export function readSettings(): TitSettings {
  try {
    const raw = JSON.parse(readFileSync(settingsPath(), "utf8")) as Record<string, unknown>;
    const out: TitSettings = {};
    if (typeof raw.lastServerUrl === "string") out.lastServerUrl = raw.lastServerUrl;
    if (typeof raw.lastProjectDir === "string") out.lastProjectDir = raw.lastProjectDir;
    if (typeof raw.tetravoxPath === "string") out.tetravoxPath = raw.tetravoxPath;
    return out;
  } catch {
    return {};
  }
}

/** Merge a partial; only whitelisted keys are kept and the token is never a key. */
export function updateSettings(partial: unknown): TitSettings {
  const current = readSettings();
  if (partial && typeof partial === "object") {
    const p = partial as Record<string, unknown>;
    for (const key of ALLOWED_KEYS) {
      if (typeof p[key] === "string") current[key] = p[key] as string;
    }
  }
  const file = settingsPath();
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(current, null, 2) + "\n");
  return current;
}
