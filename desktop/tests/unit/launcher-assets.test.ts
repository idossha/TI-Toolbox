import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { resolveRendererDir } from "../../src/main/launcher";

const roots: string[] = [];
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "tit-launcher-assets-"));
  roots.push(root);
  return root;
}
function renderer(path: string) {
  mkdirSync(path, { recursive: true });
  writeFileSync(join(path, "index.html"), "<main>Launcher</main>");
}

it("loads packaged renderer assets outside app.asar", () => {
  const resources = fixture();
  renderer(join(resources, "renderer"));
  expect(resolveRendererDir(resources, join(resources, "app.asar/out/main"), join(resources, "app.asar")))
    .toBe(join(resources, "renderer"));
});

it("loads the built checkout renderer relative to the main entrypoint", () => {
  const root = fixture();
  renderer(join(root, "out/renderer"));
  expect(resolveRendererDir(undefined, join(root, "out/main"), "/unrelated/app"))
    .toBe(join(root, "out/renderer"));
});

it("ignores incomplete resource directories and falls back to a complete app bundle", () => {
  const root = fixture();
  mkdirSync(join(root, "resources/renderer"), { recursive: true });
  renderer(join(root, "app/out/renderer"));
  expect(resolveRendererDir(join(root, "resources"), join(root, "missing/main"), join(root, "app")))
    .toBe(join(root, "app/out/renderer"));
});

it("does not resolve a renderer without an entry document", () => {
  const root = fixture();
  mkdirSync(join(root, "renderer"));
  expect(resolveRendererDir(root, join(root, "out/main"), root)).toBeUndefined();
});
