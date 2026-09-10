import { existsSync } from "node:fs";
import { join } from "node:path";

// Trusted local Overview origin. Host project selection is allowed only here.
export const LAUNCHER_ORIGIN = "app://launcher";

/** Locate the renderer shared by the local launcher and optional native server. */
export function resolveRendererDir(resourcesPath: string | undefined, mainDir: string, appPath: string): string | undefined {
  const candidates = [
    resourcesPath ? join(resourcesPath, "renderer") : null,
    join(mainDir, "..", "renderer"),
    join(appPath, "out", "renderer"),
  ].filter((candidate): candidate is string => Boolean(candidate));
  return candidates.find((candidate) => existsSync(join(candidate, "index.html")));
}
