// node-pty 1.1.0 publishes its macOS `spawn-helper` prebuilds without the executable bit, so every
// spawn fails with "posix_spawnp failed" (reproduced 2026-10-07 under Electron 44's Node). Restore
// the bit after `npm install`/`npm ci`; electron-builder copies the mode into the packaged app.
// ponytail: drop this script once a node-pty release ships the bit set.
import { chmodSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const prebuilds = join(dirname(fileURLToPath(import.meta.url)), "..", "node_modules", "node-pty", "prebuilds");
if (existsSync(prebuilds)) {
  for (const dir of readdirSync(prebuilds)) {
    const helper = join(prebuilds, dir, "spawn-helper");
    if (existsSync(helper)) chmodSync(helper, 0o755);
  }
}
