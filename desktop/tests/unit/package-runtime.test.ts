/** Artifact-level regression: a packaged app excludes node_modules, so YAML must be bundled.
 * Authored miniature asar/unpacked payloads isolate the loader defect without launching a GUI.
 */
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

function verify(asar: boolean, external?: 'main' | 'preload') {
  const root = mkdtempSync(join(tmpdir(), 'tit-package-runtime-'));
  try {
    const resources = join(root, 'resources');
    mkdirSync(join(resources, 'renderer'), { recursive: true });
    writeFileSync(join(resources, 'renderer/index.html'), '<main>fixture</main>');
    writeFileSync(join(resources, 'docker-compose.yml'), 'services:\n  tit:\n    image: idossha/ti-toolbox:fixture\n');
    writeFileSync(join(root, 'ti-toolbox'), 'fixture');
    const entries: Record<string, string> = {
      'package.json': JSON.stringify({ name: 'ti-toolbox-desktop', version: '3.0.0-dev.1', main: './out/main/index.js' }),
      'out/main/index.js': 'const electron = require("electron"); const fs = require("node:fs");',
      'out/preload/index.js': 'const electron = require("electron");',
    };
    if (external) entries[`out/${external}/index.js`] += '\nconst yaml = require("yaml");';
    if (asar) {
      type Entry = { files?: Record<string, Entry>; size?: number; offset?: string };
      const header: Entry = { files: {} };
      const data: Buffer[] = [];
      let offset = 0;
      for (const [name, source] of Object.entries(entries)) {
        const parts = name.split('/');
        let dir = header;
        for (const part of parts.slice(0, -1)) {
          dir.files![part] ??= { files: {} };
          dir = dir.files![part]!;
        }
        const bytes = Buffer.from(source);
        dir.files![parts.at(-1)!] = { size: bytes.length, offset: String(offset) };
        data.push(bytes); offset += bytes.length;
      }
      const json = Buffer.from(JSON.stringify(header));
      const prefix = Buffer.alloc(16);
      prefix.writeUInt32LE(4, 0); prefix.writeUInt32LE(json.length + 8, 4);
      prefix.writeUInt32LE(json.length + 4, 8); prefix.writeUInt32LE(json.length, 12);
      writeFileSync(join(resources, 'app.asar'), Buffer.concat([prefix, json, ...data]));
    } else {
      for (const [name, source] of Object.entries(entries)) {
        const target = join(resources, 'app', name);
        mkdirSync(resolve(target, '..'), { recursive: true }); writeFileSync(target, source);
      }
    }
    return spawnSync(process.execPath, ['scripts/verify-package.mjs', root, '--expect-version', '3.0.0-dev.1'], { encoding: 'utf8' });
  } finally { rmSync(root, { recursive: true, force: true }); }
}

for (const asar of [true, false]) describe(asar ? 'asar runtime' : 'unpacked runtime', () => {
  it('accepts bundled entries requiring only Electron and Node', () => {
    const result = verify(asar); expect(result.status, result.stdout + result.stderr).toBe(0);
  });
  for (const entry of ['main', 'preload'] as const) it(`rejects unshipped YAML in ${entry}`, () => {
    const result = verify(asar, entry);
    expect(result.status, result.stdout + result.stderr).toBe(1);
    expect(result.stdout + result.stderr).toContain('yaml');
  });
});
