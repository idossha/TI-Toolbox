import { existsSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

/**
 * Verified cleanup for a page that has no field to tag its own output (Analyzer's `output_dir` is
 * always `null` from the UI — the server names it): snapshot a directory before Run, diff it after
 * the job succeeds, and remove only the entries that were not there before. This is `cleanupSmokeOutputs`'
 * "smoke" in the name" guarantee restated as a fact about the filesystem instead of a naming
 * convention, for the one page that cannot supply the convention.
 */
export function snapshotDir(absPath: string): Set<string> {
  if (!existsSync(absPath)) return new Set();
  return new Set(readdirSync(absPath));
}

/** Removes every entry under `absPath` that is not in `before` (P6: never touch a pre-existing
 *  output — proven per-entry, not assumed from a name). Returns the names it removed. */
export function removeNewEntriesSince(absPath: string, before: Set<string>): string[] {
  if (!existsSync(absPath)) return [];
  const removed: string[] = [];
  for (const name of readdirSync(absPath)) {
    if (before.has(name)) continue;
    rmSync(join(absPath, name), { recursive: true, force: true });
    removed.push(name);
  }
  return removed;
}
