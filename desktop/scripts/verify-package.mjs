#!/usr/bin/env node
/**
 * verify-package.mjs — inspect a *built* TI-Toolbox desktop app and fail loudly if it is not
 * shippable. Run in the release workflow's unsigned validation job (docs/dev/RELEASE.md § 3),
 * before anything is signed, notarised or published, and locally against a `--dir` build.
 *
 * It exists because the things that break a packaged Electron app are invisible in the source
 * tree and in `electron-vite build` output: they only show up once electron-builder has decided
 * what goes inside `app.asar` and what sits beside it in `resources/`. The two defects this was
 * written against, both real:
 *
 *   1. `desktop/docker/docker-compose.v3.yml` was not in electron-builder.yml's `files:` list,
 *      while `src/main/stack.ts#resolveComposeFile` reads it from `app.getAppPath()/docker/` at
 *      startup. Every packaged build therefore died with `compose-invalid: docker-compose.v3.yml
 *      not found` on first launch — a defect no unit test or `npm run build` can see.
 *   2. The legacy launcher (`package/`, v2.4.0) was what the release workflow actually built, so
 *      the version inside the artifact did not match the tag it was published under.
 *
 * Usage:
 *   node scripts/verify-package.mjs <app-path> [--expect-version X.Y.Z] [--expect-runtime]
 *
 * <app-path> is whatever electron-builder produced for the platform:
 *   macOS    .../mac-arm64/TI-Toolbox.app  (or the mac-arm64 directory itself)
 *   Linux    .../linux-unpacked
 *   Windows  .../win-unpacked
 * A directory containing exactly one of those is also accepted, so CI can pass `release/`.
 *
 * Exit status is 0 only when every check passes; each failure is printed as `FAIL <check>`.
 * No dependencies: the asar header is parsed here rather than pulled from @electron/asar, so the
 * script runs against a downloaded artifact with no node_modules next to it.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------------------------
// asar reader (format: [uint32 4][uint32 pickleSize][uint32 jsonLen][json][...file data])
// ---------------------------------------------------------------------------------------------

/**
 * Parse an asar archive's header. Returns { header, dataStart }.
 *
 * Layout (four little-endian uint32 fields, then the JSON, then the file data), matching
 * @electron/asar's own `readArchiveHeaderSync` — reproduced here so this script has no deps:
 *   [0]  4                — size of the next field
 *   [4]  pickleSize       — total size of the header pickle; file data begins at 8 + pickleSize
 *   [8]  stringPickleSize — size of the string pickle inside it (unused here)
 *   [12] jsonLen          — byte length of the JSON header, which starts at offset 16
 */
function readAsarHeader(asarPath) {
  const buf = readFileSync(asarPath);
  if (buf.length < 16) throw new Error(`${asarPath}: too short to be an asar archive`);
  const pickleSize = buf.readUInt32LE(4);
  const jsonLen = buf.readUInt32LE(12);
  if (pickleSize < 4 || 8 + pickleSize > buf.length || 16 + jsonLen > buf.length) {
    throw new Error(`${asarPath}: asar header sizes are out of range (not an asar archive?)`);
  }
  return { header: JSON.parse(buf.subarray(16, 16 + jsonLen).toString("utf8")), dataStart: 8 + pickleSize };
}

/** Every path inside an asar header, POSIX-separated, files only. */
function asarPaths(header) {
  const out = [];
  const walk = (node, prefix) => {
    for (const [name, child] of Object.entries(node.files ?? {})) {
      const p = prefix ? `${prefix}/${name}` : name;
      if (child.files) walk(child, p);
      else out.push(p);
    }
  };
  walk(header, "");
  return out;
}

// ---------------------------------------------------------------------------------------------
// locating the app
// ---------------------------------------------------------------------------------------------

/**
 * Resolve <app-path> to { kind, resourcesDir, executable }.
 * `kind` is darwin | linux | win32 — derived from the artifact's own shape, NOT from
 * process.platform, so a Linux CI runner could in principle check a macOS bundle.
 */
function locateApp(inputPath) {
  let p = resolve(inputPath);
  if (!existsSync(p)) throw new Error(`no such path: ${p}`);

  // A wrapper directory (e.g. `release/`): descend if it holds exactly one recognised artifact.
  if (statSync(p).isDirectory() && !p.endsWith(".app") && !existsSync(join(p, "resources"))) {
    // Recognise an artifact directly, else look one level down — electron-builder writes
    // `release/mac-arm64/TI-Toolbox.app` but `release/linux-unpacked` and `release/win-unpacked`.
    const isArtifact = (c) => c.endsWith(".app") || existsSync(join(c, "resources"));
    const children = readdirSync(p)
      .map((name) => join(p, name))
      .filter((c) => statSync(c).isDirectory());
    const nested = children.flatMap((c) =>
      isArtifact(c)
        ? [c]
        : readdirSync(c)
            .map((n) => join(c, n))
            .filter((n) => statSync(n).isDirectory() && isArtifact(n)),
    );
    if (nested.length === 1) p = nested[0];
    else if (nested.length > 1) throw new Error(`${p} holds ${nested.length} artifacts; pass one explicitly`);
  }

  if (p.endsWith(".app")) {
    return {
      kind: "darwin",
      appPath: p,
      resourcesDir: join(p, "Contents", "Resources"),
      executable: join(p, "Contents", "MacOS", basename(p, ".app")),
    };
  }
  const resourcesDir = join(p, "resources");
  if (!existsSync(resourcesDir)) throw new Error(`${p}: no resources/ and not a .app bundle`);
  const exeWin = readdirSync(p).find((n) => n.toLowerCase().endsWith(".exe") && n.toLowerCase() !== "elevate.exe");
  if (exeWin) return { kind: "win32", appPath: p, resourcesDir, executable: join(p, exeWin) };
  const exeLinux = readdirSync(p).find((n) => n === "ti-toolbox" || n === "TI-Toolbox");
  if (!exeLinux) throw new Error(`${p}: found resources/ but no executable (expected ti-toolbox)`);
  return { kind: "linux", appPath: p, resourcesDir, executable: join(p, exeLinux) };
}

// ---------------------------------------------------------------------------------------------
// checks
// ---------------------------------------------------------------------------------------------

const failures = [];
const notes = [];
function check(name, ok, detail) {
  if (ok) console.log(`ok   ${name}${detail ? ` — ${detail}` : ""}`);
  else {
    console.log(`FAIL ${name}${detail ? ` — ${detail}` : ""}`);
    failures.push(name);
  }
}

/**
 * Files that must never end up inside a shipped app. `tit/gui` is the deleted PyQt GUI (commit
 * 0daa748e) — if it reappears in an artifact, something is packaging the repository root rather
 * than `out/**`. The rest are dev-only inputs that indicate the same mistake.
 */
const FORBIDDEN = [
  { label: "tit/gui (deleted PyQt GUI)", test: (p) => p.startsWith("tit/gui/") || p.includes("/tit/gui/") },
  { label: "playwright config", test: (p) => p.endsWith("playwright.config.ts") },
  { label: "e2e/unit tests", test: (p) => p === "tests" || p.startsWith("tests/") },
  { label: "node_modules", test: (p) => p.startsWith("node_modules/") || p.includes("/node_modules/") },
  { label: "runtime staging scratch dir", test: (p) => p.startsWith(".runtime-staging/") },
  { label: "TypeScript sources", test: (p) => p.startsWith("src/") && p.endsWith(".ts") },
  { label: "electron-builder config", test: (p) => p === "electron-builder.yml" },
];

/** Files the app reads at runtime and therefore MUST be inside the asar. */
const REQUIRED_IN_ASAR = [
  // src/main/stack.ts#resolveComposeFile — read at every stack start; its absence is fatal.
  "docker/docker-compose.v3.yml",
  "package.json",
];

function main() {
  const args = process.argv.slice(2);
  // --expect-version takes a value; everything else is a flag. Without skipping the value, an
  // invocation like `verify-package.mjs app --expect-version 3.0.0` looks like two positionals.
  const positional = args.filter((a, i) => !a.startsWith("--") && args[i - 1] !== "--expect-version");
  if (positional.length !== 1) {
    console.error("usage: node scripts/verify-package.mjs <app-path> [--expect-version X.Y.Z] [--expect-runtime]");
    process.exit(2);
  }
  const expectRuntime = args.includes("--expect-runtime");
  const versionArgIdx = args.indexOf("--expect-version");
  let expectVersion = versionArgIdx >= 0 ? args[versionArgIdx + 1] : undefined;
  if (!expectVersion) {
    // Fall back to the source of truth next to this script, so a local run needs no argument.
    const own = join(HERE, "..", "package.json");
    if (existsSync(own)) expectVersion = JSON.parse(readFileSync(own, "utf8")).version;
  }

  const app = locateApp(positional[0]);
  console.log(`# verifying ${app.appPath}`);
  console.log(`# platform  ${app.kind}`);
  console.log(`# expecting version ${expectVersion ?? "<unknown>"}`);
  console.log("");

  // --- 1. the app's own package.json (inside app.asar, or app/ when asar is off) --------------
  const asarPath = join(app.resourcesDir, "app.asar");
  const unpackedDir = join(app.resourcesDir, "app");
  let pkg;
  let paths;
  if (existsSync(asarPath)) {
    const { header, dataStart } = readAsarHeader(asarPath);
    paths = asarPaths(header);
    const pkgEntry = paths.find((p) => p === "package.json");
    check("app.asar present", true, `${paths.length} entries`);
    if (!pkgEntry) {
      check("app.asar contains package.json", false);
      return finish();
    }
    // Read package.json out of the archive by offset (offsets are strings in the header).
    const buf = readFileSync(asarPath);
    const node = header.files["package.json"];
    const at = dataStart + Number(node.offset);
    pkg = JSON.parse(buf.subarray(at, at + node.size).toString("utf8"));
  } else if (existsSync(unpackedDir)) {
    notes.push("asar is disabled in this build (resources/app/ instead of resources/app.asar)");
    check("app.asar present", true, "asar disabled — inspecting resources/app/");
    const walk = (dir, prefix) =>
      readdirSync(dir).flatMap((n) => {
        const full = join(dir, n);
        const rel = prefix ? `${prefix}/${n}` : n;
        return statSync(full).isDirectory() ? walk(full, rel) : [rel];
      });
    paths = walk(unpackedDir, "");
    pkg = JSON.parse(readFileSync(join(unpackedDir, "package.json"), "utf8"));
  } else {
    check("app.asar present", false, `neither ${asarPath} nor ${unpackedDir} exists`);
    return finish();
  }

  // --- 2. version ----------------------------------------------------------------------------
  check(
    "version matches",
    !expectVersion || pkg.version === expectVersion,
    `packaged ${pkg.version}, expected ${expectVersion ?? "<any>"}`,
  );
  check("version is not the legacy launcher's", pkg.name !== "ti-toolbox" || pkg.main !== "src/main.js", `name=${pkg.name} main=${pkg.main}`);

  // --- 3. main entry point exists inside the bundle -------------------------------------------
  const mainRel = String(pkg.main ?? "").replace(/^\.\//, "");
  check("package.json declares a main entry", Boolean(mainRel), mainRel || "<missing>");
  check("main entry is bundled", paths.includes(mainRel), mainRel);

  // --- 4. runtime-required files ---------------------------------------------------------------
  for (const req of REQUIRED_IN_ASAR) {
    check(`bundled: ${req}`, paths.includes(req));
  }

  // --- 5. nothing dev-only or deleted leaked in ------------------------------------------------
  for (const rule of FORBIDDEN) {
    const hits = paths.filter(rule.test);
    check(`absent: ${rule.label}`, hits.length === 0, hits.length ? `${hits.length} entries, e.g. ${hits[0]}` : undefined);
  }

  // --- 6. per-platform staged runtime -----------------------------------------------------------
  // The shipping app is Docker-backed: `tit.server` runs in idossha/ti-toolbox:<ver>, so a bundled
  // Python runtime is NOT expected. `--expect-runtime` is for a future native build (the parked
  // N0.4 spike, docs/dev/SPIKES.md), which stages resources/runtime/<platform>-<arch>.
  const archName = { darwin: "darwin-arm64", linux: "linux-x64", win32: "win32-x64" }[app.kind];
  const runtimeDir = join(app.resourcesDir, "runtime");
  const stagedRuntime = existsSync(runtimeDir) ? readdirSync(runtimeDir) : [];
  if (expectRuntime) {
    check(
      `runtime staged for ${app.kind}`,
      stagedRuntime.some((n) => n === archName || n.startsWith(`${app.kind}-`)),
      `resources/runtime holds [${stagedRuntime.join(", ")}], wanted ${archName}`,
    );
  } else {
    check(
      "no stray runtime staged (Docker-backed build)",
      stagedRuntime.length === 0,
      stagedRuntime.length ? `resources/runtime holds [${stagedRuntime.join(", ")}] but --expect-runtime was not passed` : "resources/runtime absent",
    );
  }

  // --- 7. the renderer bundle staged beside the asar -----------------------------------------
  // NOT inside app.asar: the window loads the UI over http from `tit.server` (src/main/index.ts
  // `loadURL`), and the copy in `resources/renderer` exists so a natively-spawned server — a plain
  // OS process with no asar access — has a real `--static-dir` to serve. electron-builder excludes
  // `out/renderer` from `files:` automatically because it is an extraResources source.
  check(
    "renderer staged at resources/renderer",
    existsSync(join(app.resourcesDir, "renderer", "index.html")),
    join(app.resourcesDir, "renderer", "index.html"),
  );

  // --- 8. executable exists and is the right name --------------------------------------------------
  check("executable present", existsSync(app.executable), app.executable);

  return finish();
}

function finish() {
  console.log("");
  for (const n of notes) console.log(`note ${n}`);
  if (failures.length) {
    console.error(`\n${failures.length} check(s) failed: ${failures.join(", ")}`);
    process.exit(1);
  }
  console.log("all checks passed");
  process.exit(0);
}

try {
  main();
} catch (err) {
  console.error(`verify-package.mjs: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(2);
}
