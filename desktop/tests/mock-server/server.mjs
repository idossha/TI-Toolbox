// Mock tit.server implementing contracts/openapi.yaml completely, from fixtures under
// desktop/tests/fixtures/. Plain Node http + the `ws` package; ES modules; no new dependencies.
//
// Auth (same as the real server, v0 rules carried unchanged into v1):
//   - /api/health and GET /auth/session are public; every other route needs
//     `Authorization: Bearer <token>` or the `tit_session` cookie minted by /auth/session.
//   - POST /auth/logout (cookie or bearer) forgets the session id and clears the cookie (204).
//   - /ws/system and /ws/jobs accept the cookie or ?token=, and a present Origin must match Host.
//
// Fake job engine: POST /api/jobs (or /api/jobs/groups) creates a job that moves
// queued -> running -> succeeded/failed/cancelled, emitting stage/progress/log/artifact/result/exit
// Events with increasing `seq`. Two mock-only escape hatches on the request `config`:
//   - `config.__mock_fail === true`   -> the job ends in `failed` instead of `succeeded`.
//   - `config.__mock_fast === true`   -> the run timeline takes ~300-500ms instead of ~6-10s
//   - `config.__mock_log_lines = N`   -> N extra log lines up front, for specs that need a log
//                                        taller than the pane showing it (jobs.spec.ts's Raw log).
//                                        (used by the contract self-test so it doesn't sleep).
//
// "/" serves out/renderer if built, so the real bundle can be exercised end to end. Port 8790
// by default; override with --port=NNNN, TIT_MOCK_PORT, or (for the renderer's own dev proxy)
// TIT_MOCK_HOST.
import { createServer } from "node:http";
import { createReadStream, existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { basename, dirname, extname, join, normalize, resolve as resolvePath, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, "..", "fixtures");
const rendererDir = join(here, "..", "..", "out", "renderer");
const repoRoot = join(here, "..", "..", "..");

function argPort() {
  const flag = process.argv.find((a) => a === "--port" || a.startsWith("--port="));
  if (!flag) return undefined;
  if (flag.includes("=")) return Number(flag.split("=")[1]);
  const i = process.argv.indexOf(flag);
  return Number(process.argv[i + 1]);
}
const PORT = argPort() ?? Number(process.env.TIT_MOCK_PORT ?? 8790);
const HOST = process.env.TIT_MOCK_HOST ?? "127.0.0.1";
const TOKEN = process.env.TIT_MOCK_TOKEN ?? "mock-token";
const WS_INTERVAL_MS = Number(process.env.TIT_MOCK_WS_INTERVAL_MS ?? 2000);
// Real-bytes mode for the in-app (Tetravox) viewer: TIT_MOCK_DATA_ROOT points at a directory of
// real volumes/meshes on the host (e.g. .../derivatives/SimNIBS/sub-ernie). GET/HEAD
// /api/files/raw/<absolute host path without its leading slash> then streams the real file, so an
// e2e run can feed the engine actual NIfTI/msh bytes. Unset (CI default) => the route 404s, which
// keeps contract.test.ts's exact path-coverage assertion meaningful without shipping large
// binary fixtures.
const DATA_ROOT = process.env.TIT_MOCK_DATA_ROOT ? resolvePath(process.env.TIT_MOCK_DATA_ROOT) : "";
// The Tetravox embed bundle served at /tetravox/ (W3a, docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)
// §1): defaults to the deterministic fake embed fixture (desktop/tests/e2e/fixtures/fake-embed/)
// so the desktop e2e suite exercises the real /tetravox/ route + iframe wiring without the actual
// WASM/WebGL2 bundle. Point TIT_MOCK_EMBED_DIR at a real build to test against it instead.
const EMBED_DIR = resolvePath(
  process.env.TIT_MOCK_EMBED_DIR ?? join(here, "..", "e2e", "fixtures", "fake-embed")
);

// ------------------------------------------------------------------------------------ fixtures
const loadJson = (name) => JSON.parse(readFileSync(join(fixturesDir, name), "utf8"));
const fixturePath = (...parts) => join(fixturesDir, ...parts);

const subjects = loadJson("subjects.json");
const subjectDetails = loadJson("subject_details.json");
const simulations = loadJson("simulations.json");
const version = loadJson("version.json");
const capabilities = loadJson("capabilities.json");
const project = loadJson("project.json");
const montageListSeed = loadJson("montage_list.json");
const atlases = loadJson("atlases.json");
const atlasRegions = loadJson("atlas_regions.json");
const leadfields = loadJson("leadfields.json");
const flexRuns = loadJson("flex_runs.json");
const exRuns = loadJson("ex_runs.json");
const analyses = loadJson("analyses.json");
const reports = loadJson("reports.json");
const groupCatalog = loadJson("group_catalog.json");
const groupStatsDetail = loadJson("group_stats_detail.json");
const simulationFigures = loadJson("simulation_figures.json");
const subjectInfo = loadJson("subject_info.json");
const overviewSmall = loadJson("overview.json");
const roisSeed = loadJson("rois_seed.json");
const freehandSeed = loadJson("freehand_seed.json");
const notesSeed = loadJson("notes_seed.json");
const settingsSeed = loadJson("settings_seed.json");

const PROJECT_ROOT = project.container_path; // "/mnt/example"
const NET_SIZES = { "GSN-HydroCel-185": 185, "EGI_template": 256 };
const CONFIG_NAMES = [
  "SimulationConfig",
  "Montage",
  "FlexConfig",
  "ExConfig",
  "MExConfig",
  "AnalyzerConfig",
  "PreprocessConfig",
  "QSIPrepConfig",
  "QSIReconConfig",
  "GroupComparisonConfig",
  "CorrelationConfig",
  "SourceConfig",
  "LeadfieldConfig",
  "BlenderMontageConfig",
  "BlenderVectorConfig",
  "BlenderRegionConfig",
];

// mutable, in-memory (reset on restart) stores seeded from the fixtures above
const montages = structuredClone(montageListSeed.nets); // { net: { uni_polar_montages, multi_polar_montages } }
const rois = structuredClone(roisSeed);
const freehand = structuredClone(freehandSeed);
let notes = structuredClone(notesSeed);
let settingsStore = structuredClone(settingsSeed);
const processes = [
  { pid: 4231, name: "simnibs_python", cmdline: "simnibs_python -m tit.sim /mnt/example/code/ti-toolbox/jobs/0001/spec.json", cpu_percent: 0, rss: 1.8 * 1024 ** 3, started: Date.now() / 1000 - 600 },
  { pid: 4310, name: "charm", cmdline: "charm 101 T1.nii.gz --forceqform", cpu_percent: 0, rss: 3.2 * 1024 ** 3, started: Date.now() / 1000 - 3600 },
];

// ---------------------------------------------------------------------------- overview projects
// R1's gate needs two mock PROJECTS, not two fixtures of the same size: the point of
// `GET /api/catalog/overview` is that the page's request count does not grow with the project, and
// a 3-subject project cannot show that. `overview.json` is the small one (the same three subjects
// every other fixture here describes); the large one is generated deterministically from it, 30
// subjects wide, and deliberately spends its rows on every PresenceState -- `partial` (DICOMs
// staged, never converted), `pending` (a job running right now) and `failed` (its last one did
// not) included, since those are exactly the states the old two-state booleans could not say.
// Switch between them with `POST /api/__mock/project {"subjects": 3 | 30}`.
const STATE_CYCLE = ["present", "absent", "partial", "pending", "failed"];

function makeLargeOverview(n = 30) {
  const at = (i, offset) => STATE_CYCLE[(i + offset) % STATE_CYCLE.length];
  const subjects = Array.from({ length: n }, (_, i) => {
    const id = `S${String(i + 1).padStart(3, "0")}`;
    const m2m = i % 4 === 3 ? "absent" : "present";
    const leadfields = i % 3 === 0 ? ["GSN-HydroCel-185"] : [];
    const simulations = i % 5;
    return {
      id,
      raw: i % 7 === 6 ? "partial" : "present",
      fastsurfer: at(i, 0),
      freesurfer: at(i, 2),
      m2m,
      dwi: at(i, 1),
      ct: at(i, 3),
      leadfield: leadfields.length ? "present" : at(i, 4),
      eeg_net: "present",
      leadfields,
      eeg_nets: ["GSN-HydroCel-185"],
      counts: { simulations, optimizations: i % 3, analyses: i % 2 },
      readiness: [
        { stage: "preprocess", ready: true, reason: null },
        { stage: "simulator", ready: m2m === "present", reason: m2m === "present" ? null : "no head model" },
        {
          stage: "optimizer",
          ready: m2m === "present" && leadfields.length > 0,
          reason: m2m === "present" ? (leadfields.length ? null : "no leadfield") : "no head model",
        },
        { stage: "analyzer", ready: simulations > 0, reason: simulations > 0 ? null : "no simulations" },
      ],
    };
  });
  const have = (fn) => subjects.filter(fn).length;
  return {
    subjects,
    totals: {
      subjects: subjects.length,
      simulations: subjects.reduce((n2, s2) => n2 + s2.counts.simulations, 0),
      optimizations: subjects.reduce((n2, s2) => n2 + s2.counts.optimizations, 0),
      analyses: subjects.reduce((n2, s2) => n2 + s2.counts.analyses, 0),
      coverage: [
        { id: "raw", have: have((s2) => s2.raw === "present"), total: subjects.length },
        { id: "recon", have: have((s2) => s2.fastsurfer === "present" || s2.freesurfer === "present"), total: subjects.length },
        { id: "m2m", have: have((s2) => s2.m2m === "present"), total: subjects.length },
        { id: "dwi", have: have((s2) => s2.dwi === "present"), total: subjects.length },
        { id: "leadfield", have: have((s2) => s2.leadfield === "present" || s2.leadfield === "partial"), total: subjects.length },
      ],
    },
  };
}

const overviewProjects = { 3: overviewSmall, 30: makeLargeOverview(30) };
let overview = overviewProjects[3];

// ------------------------------------------------------------------------------------- helpers
const startedAt = Date.now();
const sessions = new Set();
const nowIso = () => new Date().toISOString();

function cookies(req) {
  const out = {};
  for (const part of (req.headers.cookie ?? "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}
function bearerAuthed(req) {
  return (req.headers.authorization ?? "") === `Bearer ${TOKEN}`;
}
function cookieAuthed(req) {
  const sid = cookies(req).tit_session;
  return !!(sid && sessions.has(sid));
}
function authed(req, url) {
  if (bearerAuthed(req)) return true;
  if (cookieAuthed(req)) return true;
  if (url && url.searchParams.get("token") === TOKEN) return true;
  return false;
}
// Mirrors tit/server/auth.py's `_cookie_csrf_ok` (ra_14 finding #7 / rb_12 mock-parity gap): a
// cookie alone is enough for a safe method, but a state-changing request must additionally prove
// same-origin via `Origin` (matching Host) or `Sec-Fetch-Site: same-origin` — otherwise a
// same-site-but-different-origin page could ride the session cookie into a mutation. Bearer/query
// `?token=` auth is exempt, same as the real server (a script proves it isn't a browser CSRF).
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
function cookieCsrfOk(req) {
  const origin = req.headers.origin;
  if (origin !== undefined) {
    try {
      return new URL(origin).host === req.headers.host;
    } catch {
      return false;
    }
  }
  const sfs = req.headers["sec-fetch-site"];
  if (sfs !== undefined) return sfs === "same-origin";
  return false; // neither header present -- can't prove same-origin, so don't trust it
}
function json(res, status, body, extraHeaders = {}) {
  const data = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "content-length": Buffer.byteLength(data), ...extraHeaders });
  res.end(data);
}
function text(res, status, body, contentType = "text/plain; charset=utf-8", extraHeaders = {}) {
  res.writeHead(status, { "content-type": contentType, "content-length": Buffer.byteLength(body), ...extraHeaders });
  res.end(body);
}
function noContent(res, extraHeaders = {}) {
  res.writeHead(204, extraHeaders);
  res.end();
}
/** Same-origin WebSocket policy: absent Origin (curl/tests) is fine; a present one must match Host. */
function originAllowed(req) {
  const origin = req.headers.origin;
  if (origin === undefined) return true;
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false;
  }
}
function startSession(res) {
  const sid = randomBytes(16).toString("hex");
  sessions.add(sid);
  res.writeHead(303, { location: "/", "set-cookie": `tit_session=${sid}; HttpOnly; SameSite=Strict; Path=/` });
  res.end();
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      if (!data) return resolve({});
      try {
        resolve(JSON.parse(data));
      } catch {
        resolve({});
      }
    });
    req.on("error", reject);
  });
}
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json", ".map": "application/json", ".woff2": "font/woff2", ".wasm": "application/wasm" };
function serveStatic(res, pathname) {
  if (!existsSync(join(rendererDir, "index.html"))) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end("<!doctype html><title>mock tit.server</title><p>Renderer not built. Run <code>npm run build</code> in desktop/ and reload.</p>");
    return;
  }
  const rel = normalize(pathname === "/" ? "/index.html" : pathname).replace(/^(\.\.[/\\])+/, "");
  const file = join(rendererDir, rel);
  if (!file.startsWith(rendererDir) || !existsSync(file) || !statSync(file).isFile()) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
    return;
  }
  res.writeHead(200, { "content-type": MIME[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}

// The embed's own CSP -- mirrors tit/server/static.py's TETRAVOX_CSP exactly, so a spec
// asserting on this header behaves the same against the mock and the real server.
const TETRAVOX_CSP =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; " +
  "worker-src 'self' blob:; connect-src 'self'; img-src 'self' data: blob:; " +
  "style-src 'self' 'unsafe-inline'";
/** GET /tetravox, /tetravox/, /tetravox/index.html and every /tetravox/<asset>. Not a SPA
 * fallback (mirrors tit/server/static.py::resolve_tetravox_file): an unknown asset 404s. */
function serveTetravox(res, pathname) {
  if (!existsSync(join(EMBED_DIR, "manifest.json"))) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("tetravox embed not installed");
    return;
  }
  var rel = pathname === "/tetravox" || pathname === "/tetravox/" ? "/index.html" : pathname.slice("/tetravox".length);
  rel = normalize(rel === "/" ? "/index.html" : rel).replace(/^(\.\.[/\\])+/, "");
  var file = join(EMBED_DIR, rel);
  if (!file.startsWith(EMBED_DIR) || !existsSync(file) || !statSync(file).isFile()) {
    res.writeHead(404, { "content-type": "text/plain", "content-security-policy": TETRAVOX_CSP });
    res.end("not found");
    return;
  }
  res.writeHead(200, {
    "content-type": MIME[extname(file)] ?? "application/octet-stream",
    "content-security-policy": TETRAVOX_CSP,
  });
  createReadStream(file).pipe(res);
}

// --- system snapshot generator (random walk so charts move) ---
let cpu = 12;
let memPercent = 41;
function snapshot() {
  cpu = Math.min(100, Math.max(0, cpu + (Math.random() - 0.5) * 12));
  memPercent = Math.min(100, Math.max(0, memPercent + (Math.random() - 0.5) * 2));
  const total = 32 * 1024 ** 3;
  const used = Math.round((total * memPercent) / 100);
  return {
    ts: Date.now() / 1000,
    cpu_percent: Number(cpu.toFixed(1)),
    cpu_count: 12,
    mem: { total, available: total - used, used, percent: Number(memPercent.toFixed(1)) },
    disk: { total: 1000 * 1024 ** 3, free: 412 * 1024 ** 3, percent: 58.8 },
    processes: processes.map((p) => ({ ...p, cpu_percent: Number((Math.random() * 100).toFixed(1)), rss: Math.round(p.rss) })),
  };
}

// ------------------------------------------------------------------------------- tiny CSV I/O
function parseCsv(raw) {
  const lines = raw.replace(/\r\n/g, "\n").trim().split("\n");
  const columns = lines[0].split(",");
  const rows = lines.slice(1).map((line) =>
    line.split(",").map((cell) => {
      if (cell === "true") return true;
      if (cell === "false") return false;
      if (cell !== "" && !Number.isNaN(Number(cell))) return Number(cell);
      return cell;
    }),
  );
  return { columns, rows };
}
const exResultsCsv = {
  ex: parseCsv(readFileSync(fixturePath("ex_results", "final_output_ex.csv"), "utf8")),
  mex: parseCsv(readFileSync(fixturePath("ex_results", "final_output_mex.csv"), "utf8")),
};
const analysisSummaryCsv = parseCsv(readFileSync(fixturePath("analysis_summary.csv"), "utf8"));

// ---------------------------------------------------------------------------- jailed file access
// "Jailed to the project directory": a requested path must live under PROJECT_ROOT with no `..`.
const EXT_FALLBACK = {
  ".png": { file: fixturePath("artifacts", "sample.png"), contentType: "image/png" },
  ".csv": { file: fixturePath("artifacts", "sample.csv"), contentType: "text/csv; charset=utf-8" },
  ".pdf": { file: fixturePath("artifacts", "sample.pdf"), contentType: "application/pdf" },
  ".json": { file: fixturePath("artifacts", "sample.json"), contentType: "application/json" },
  ".txt": { file: fixturePath("artifacts", "sample.txt"), contentType: "text/plain; charset=utf-8" },
  ".log": { file: fixturePath("artifacts", "sample.log"), contentType: "text/plain; charset=utf-8" },
};
/** Explicit virtual-path -> local-fixture-file registry, populated as catalog fixtures load. */
const artifactRegistry = new Map();
function registerArtifact(virtualPath, file, contentType) {
  if (virtualPath) artifactRegistry.set(virtualPath, { file, contentType });
}
for (const list of Object.values(simulationFigures)) {
  for (const f of list) registerArtifact(f.path, fixturePath("artifacts", "sample.png"), "image/png");
}
for (const a of groupStatsDetail.artifacts) {
  if (a.kind === "pdf") registerArtifact(a.path, fixturePath("artifacts", "sample.pdf"), "application/pdf");
  if (a.kind === "text") registerArtifact(a.path, fixturePath("artifacts", "sample.txt"), "text/plain; charset=utf-8");
  if (a.kind === "log") registerArtifact(a.path, fixturePath("artifacts", "sample.log"), "text/plain; charset=utf-8");
}
for (const subject of Object.keys(analyses)) {
  for (const sim of Object.keys(analyses[subject])) {
    for (const a of analyses[subject][sim]) {
      registerArtifact(a.csv, fixturePath("analysis_summary.csv"), "text/csv; charset=utf-8");
      registerArtifact(a.json, fixturePath("artifacts", "sample.json"), "application/json");
      if (a.pdf) registerArtifact(a.pdf, fixturePath("artifacts", "sample.pdf"), "application/pdf");
    }
  }
}
for (const subject of Object.keys(flexRuns)) {
  for (const run of flexRuns[subject]) {
    for (const a of run.artifacts ?? []) {
      registerArtifact(a.path, fixturePath("artifacts", a.kind === "png" ? "sample.png" : "sample.json"), a.kind === "png" ? "image/png" : "application/json");
    }
  }
}
for (const subject of Object.keys(exRuns)) {
  for (const kind of ["ex", "mex"]) {
    for (const run of exRuns[subject]?.[kind] ?? []) {
      for (const a of run.artifacts ?? []) {
        registerArtifact(a.path, fixturePath("artifacts", a.kind === "png" ? "sample.png" : "sample.csv"), a.kind === "png" ? "image/png" : "text/csv; charset=utf-8");
      }
    }
  }
}
/**
 * The run manifests the Results preview reads through `GET /api/files/text` (program U14): a
 * simulation's `documentation/config.json`, a flex run's `summary.txt` and
 * `electrode_positions.json`, an ex/mEx run's `run_config.json`. These are the real files from the
 * maintainer's Dataset 000 (`tests/fixtures/preview/`, paths rewritten to this mock's own project
 * root), so the page is exercised against the shapes it will meet, not against invented ones.
 */
for (const subject of Object.keys(simulations)) {
  for (const sim of simulations[subject]) {
    registerArtifact(`${sim.path}/documentation/config.json`, fixturePath("preview", "simulation_config.json"), "application/json");
  }
}
for (const subject of Object.keys(flexRuns)) {
  for (const run of flexRuns[subject]) {
    registerArtifact(`${run.path}/summary.txt`, fixturePath("preview", "flex_summary.txt"), "text/plain; charset=utf-8");
    registerArtifact(`${run.path}/electrode_positions.json`, fixturePath("preview", "electrode_positions.json"), "application/json");
  }
}
for (const subject of Object.keys(exRuns)) {
  for (const kind of ["ex", "mex"]) {
    for (const run of exRuns[subject]?.[kind] ?? []) {
      registerArtifact(`${run.path}/run_config.json`, fixturePath("preview", "ex_run_config.json"), "application/json");
    }
  }
}

const REPORT_HTML = {
  "ernie-thalamus-2026-08-01": fixturePath("reports", "thalamus_report.html"),
  "ernie-l_insula-2026-08-10": fixturePath("reports", "l_insula_report.html"),
  "ernie-docs_example-2026-07-20": fixturePath("reports", "docs_example_report.html"),
  "101-thalamus-2026-08-05": fixturePath("reports", "thalamus_report.html"),
};
for (const subject of Object.keys(reports)) {
  for (const r of reports[subject]) {
    const file = REPORT_HTML[r.id];
    if (file) registerArtifact(r.path, file, "text/html; charset=utf-8");
  }
}

function resolveJailed(rawPath) {
  if (typeof rawPath !== "string" || !rawPath) return { notFound: true };
  const normalized = normalize(rawPath).replace(/\\/g, "/");
  if (normalized.includes("..") || !(normalized === PROJECT_ROOT || normalized.startsWith(`${PROJECT_ROOT}/`))) {
    return { jailed: true };
  }
  const explicit = artifactRegistry.get(rawPath) ?? artifactRegistry.get(normalized);
  if (explicit) return explicit;
  const fallback = EXT_FALLBACK[extname(normalized).toLowerCase()];
  if (fallback) return fallback;
  return { notFound: true };
}
function tailLines(str, tail) {
  if (!tail) return str;
  const lines = str.replace(/\r\n/g, "\n").split("\n");
  return lines.slice(Math.max(0, lines.length - tail)).join("\n");
}

// ---------------------------------------------------------------------------- catalog handlers
function subjectDetail(id) {
  const base = subjects.subjects.find((s) => s.id === id);
  const extra = subjectDetails[id];
  if (!base || !extra) return null;
  return { ...base, ...extra };
}
function montagesResponse() {
  const nets = {};
  for (const [net, data] of Object.entries(montages)) {
    nets[net] = { uni_polar: data.uni_polar_montages ?? {}, multi_polar: data.multi_polar_montages ?? {} };
  }
  return { nets };
}
const MONTAGE_KIND_KEY = { uni_polar: "uni_polar_montages", multi_polar: "multi_polar_montages" };
function electrodesFor(net) {
  const n = NET_SIZES[net] ?? 128;
  return Array.from({ length: n }, (_, i) => `E${i + 1}`);
}
function regionsFor(atlasId, hemi) {
  const entry = atlasRegions[atlasId];
  if (!entry) return null;
  // Cortical (per-hemisphere .annot) atlases: id is that hemisphere's own label index, hemi is
  // "lh"/"rh". Subcortical/volumetric atlases ("both"): id is the voxel label value, hemi is null.
  if (entry.both) return entry.both.map((r) => ({ id: r.id, name: r.name, hemi: null }));
  const hemis = hemi && hemi !== "both" ? [hemi] : ["lh", "rh"];
  const out = [];
  for (const h of hemis) {
    for (const r of entry[h] ?? []) out.push({ id: r.id, name: r.name, hemi: h });
  }
  return out;
}

// -------------------------------------------------------------------------- validate / plan
const PER_SUBJECT_KINDS = new Set(["pre", "sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex", "leadfield", "analyzer", "source", "blender"]);
function validateConfig(kind, config) {
  const cfg = config && typeof config === "object" ? config : {};
  const errors = [];
  if (kind === "analyzer" && cfg.mode === "group") {
    // AnalyzerConfig.mode="group" runs run_group_analysis over subject_ids, not subject_id.
    if (!(Array.isArray(cfg.subject_ids) && cfg.subject_ids.length)) {
      errors.push({ path: "subject_ids", message: "subject_ids is required in group mode" });
    }
  } else if (PER_SUBJECT_KINDS.has(kind) && !cfg.subject_id) {
    errors.push({ path: "subject_id", message: "subject_id is required" });
  }
  // `leadfield_hdf`, not `eeg_net`: neither `ExConfig` nor `MExConfig` HAS an `eeg_net` field
  // (that is a `FlexConfig` mapping option — tit/opt/config.py), so the rule this replaces refused
  // every valid ex/mEx config. It went unnoticed while the Optimizer only validated flex configs
  // before submitting; the jobs table validates one config per kind, which is what found it.
  if ((kind === "ex" || kind === "mex") && !cfg.leadfield_hdf) {
    errors.push({ path: "leadfield_hdf", message: "leadfield_hdf is required" });
  }
  if ((kind === "flex" || kind === "flex_adaptive" || kind === "flex_pareto") && !cfg.roi) {
    errors.push({ path: "roi", message: "roi is required" });
  }
  if (kind === "sim" && !(Array.isArray(cfg.montages) && cfg.montages.length)) {
    errors.push({ path: "montages", message: "at least one montage is required" });
  }
  return { ok: errors.length === 0, errors };
}
/**
 * AnalyzerConfig has no `name`/`run_name` field (unlike sim/flex/ex) -- the analysis folder name
 * is derived from its ROI (atlas for cortical/subcortical, sphere center+radius for spherical) and
 * field, matching the naming this mock's own analyses.json fixture already uses
 * ("Thalamus_DK40_TI_max" = simulation "Thalamus" + atlas "DK40" + field "TI_max").
 */
function analyzerAnalysisName(cfg) {
  const sim = cfg.simulation || "NewRun";
  const field = cfg.field || "TI_max";
  const roiToken =
    cfg.analysis_type === "spherical"
      ? (() => {
          const [x = 0, y = 0, z = 0] = Array.isArray(cfg.center) ? cfg.center : [];
          return `sphere_x${x}_y${y}_z${z}_r${cfg.radius ?? 5}`;
        })()
      : cfg.atlas || "unknown_atlas";
  return `${sim}_${roiToken}_${field}`;
}
function outputDirFor(kind, subject, config) {
  const base = `${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}`;
  const cfg = config && typeof config === "object" ? config : {};
  const name = cfg.name || cfg.run_name || "NewRun";
  switch (kind) {
    case "pre":
      return `${base}/m2m_${subject}`;
    // B3/FXU1: `buildSimulationConfig` cannot set `name`/`run_name` (SimulationConfig is
    // `additionalProperties: false`), so every montage would plan into one "NewRun" column and the
    // Simulator's matrix would have a single column instead of one per montage (DESIGN.md §4.5).
    case "sim":
      return `${base}/Simulations/${(cfg.montages && cfg.montages[0] && (cfg.montages[0].name || cfg.montages[0].id)) || name}`;
    case "flex":
    case "flex_adaptive":
    case "flex_pareto":
      return `${base}/flex-search/${name}`;
    case "ex":
      return `${base}/ex-search/${name}`;
    case "mex":
      return `${base}/mex-search/${name}`;
    case "leadfield":
      return `${base}/leadfields/${cfg.eeg_net || "GSN-HydroCel-185"}`;
    case "analyzer":
      return `${base}/Simulations/${cfg.simulation || "Thalamus"}/Analyses/${analyzerAnalysisName(cfg)}`;
    case "stats":
      return `${PROJECT_ROOT}/derivatives/group/stats/${name}`;
    case "source":
      return `${base}/forward`;
    // The 3D visual exporter's four modes are all kind="blender", discriminated by the config's
    // own `_type` -- and each writes somewhere different under visual_exports
    // (tit/blender/*_exporter.py). One "blender/NewRun" for all four would have made the Plan card
    // say the same wrong path for every mode.
    case "blender": {
      const veBase = `${PROJECT_ROOT}/derivatives/ti-toolbox/visual_exports/sub-${subject}`;
      if (cfg._type === "SubcorticalConfig") return `${veBase}/sub-cortical`;
      if (cfg._type === "MontageConfig") return `${veBase}/montage_publication`;
      return `${veBase}/${cfg.simulation_name || name}`;
    }
    case "nifti_average":
    case "nilearn":
      return `${PROJECT_ROOT}/derivatives/group/${kind}/${name}`;
    default:
      return `${base}/${kind}/${name}`;
  }
}
function existsForFixture(kind, subject, config) {
  const cfg = config && typeof config === "object" ? config : {};
  if (kind === "analyzer") {
    const list = analyses[subject]?.[cfg.simulation] ?? [];
    return list.some((a) => a.name === analyzerAnalysisName(cfg));
  }
  const name = cfg.name || cfg.run_name;
  if (!name) return false;
  if (kind === "sim") return (simulations[subject] ?? []).some((s) => s.name === name);
  if (kind === "flex" || kind === "flex_adaptive" || kind === "flex_pareto") return (flexRuns[subject] ?? []).some((r) => r.name === name);
  if (kind === "ex") return (exRuns[subject]?.ex ?? []).some((r) => r.run_name === name);
  if (kind === "mex") return (exRuns[subject]?.mex ?? []).some((r) => r.run_name === name);
  return false;
}
const COST_TABLE = {
  pre: { cpus: 4, mem_gb: 16 },
  sim: { cpus: 4, mem_gb: 8 },
  flex: { cpus: 8, mem_gb: 16 },
  flex_adaptive: { cpus: 8, mem_gb: 16 },
  flex_pareto: { cpus: 8, mem_gb: 16 },
  ex: { cpus: 8, mem_gb: 12 },
  mex: { cpus: 12, mem_gb: 16 },
  leadfield: { cpus: 8, mem_gb: 24 },
  analyzer: { cpus: 2, mem_gb: 4 },
  stats: { cpus: 4, mem_gb: 8 },
  source: { cpus: 2, mem_gb: 6 },
  blender: { cpus: 1, mem_gb: 4 },
  nifti_average: { cpus: 2, mem_gb: 6 },
  nilearn: { cpus: 2, mem_gb: 6 },
};
/** The machine the mock claims to be: 12 emulated cores, like the maintainer's dev container. */
const MOCK_SYSTEM = { cpus: 12, emulated: true, factor: 3.0 };
/** A small mirror of `tit/jobs/eta.py`'s model — enough that the numbers MOVE with the inputs the
 *  real one reads (electrodes in the cap, pairs, subjects), which is what the specs assert. */
function etaFor(kind, n, cfg) {
  const count = Math.max(1, n);
  const config = cfg && typeof cfg === "object" ? cfg : {};
  if (kind === "leadfield") {
    const net = String(config.eeg_net ?? "").replace(/\.csv$/, "");
    const electrodes = NET_SIZES[net];
    if (!electrodes) return null;
    return Math.round((2.0 + 0.276 * electrodes) * 10) / 10;
  }
  if (kind === "sim") {
    const montages = Array.isArray(config.montages) ? config.montages : [];
    const pairs = montages.reduce((t, m) => t + (Array.isArray(m?.electrode_pairs) ? m.electrode_pairs.length : 2), 0) || 2;
    return Math.round((2.2 + 1.7 * pairs) * count * 10) / 10;
  }
  if (kind === "ex" || kind === "mex") return 14.0 * count;
  if (kind === "flex" || kind === "flex_adaptive" || kind === "flex_pareto") return 25.0 * count;
  if (kind === "pre") return 50.0 * count;
  return null;
}
function costFor(kind, n, cfg) {
  const base = COST_TABLE[kind] ?? { cpus: 2, mem_gb: 4 };
  const count = Math.max(1, n);
  return {
    cpus: base.cpus * count,
    mem_gb: base.mem_gb * Math.max(1, Math.ceil(count / 2)),
    eta_minutes: etaFor(kind, count, cfg),
    system: MOCK_SYSTEM,
  };
}
/** Resolve one MontageSources entry (flex run pick or freehand stim-config) against the fixtures,
 * one output row per (subject, source) pair -- matches PlanResolved.montages's contract note. */
function resolveMontageSources(montageSources, ids) {
  const ms = montageSources && typeof montageSources === "object" ? montageSources : {};
  const resolved = [];
  for (const src of ms.flex ?? []) {
    for (const subject of src.subject ? [src.subject] : ids) {
      const run = (flexRuns[subject] ?? []).find((r) => r.name === src.run);
      resolved.push({
        source: "flex",
        subject,
        run: src.run,
        electrode_type: src.electrode_type ?? null,
        eeg_net: src.eeg_net ?? run?.manifest?.eeg_net ?? null,
        electrodes: run?.manifest?.electrodes ?? null,
        found: !!run,
      });
    }
  }
  for (const src of ms.freehand ?? []) {
    for (const subject of src.subject ? [src.subject] : ids) {
      const entry = (freehand[subject] ?? []).find((f) => f.name === src.name);
      resolved.push({
        source: "freehand",
        subject,
        name: src.name,
        type: entry?.type ?? null,
        electrode_positions: entry?.electrode_positions ?? null,
        found: !!entry,
      });
    }
  }
  return resolved;
}
function resolvedFor(kind, config, montageSources, ids) {
  const cfg = config && typeof config === "object" ? config : {};
  if (kind === "sim") {
    const montages = [...(Array.isArray(cfg.montages) ? cfg.montages : []), ...resolveMontageSources(montageSources, ids)];
    return montages.length ? { montages } : null;
  }
  if (["flex", "flex_adaptive", "flex_pareto"].includes(kind)) {
    return { montages: Array.isArray(cfg.montages) && cfg.montages.length ? cfg.montages : [{ source: "flex", note: "resolved at run time from the flex-search DE result" }] };
  }
  if (kind === "ex" || kind === "mex") {
    const n = NET_SIZES[cfg.eeg_net] ?? 185;
    const nPairs = kind === "mex" ? 2 : 1;
    const nCurrentSplits = 7;
    const nCombinations = Math.round((n * (n - 1)) / 2) * nCurrentSplits * nPairs;
    return { search_space: { n_electrodes: n, n_current_splits: nCurrentSplits, n_pairs: nPairs, n_combinations: nCombinations } };
  }
  return null;
}
/** Where each pre-processing stage writes, mirroring `tit/jobs/plans.py::_pre_stage_output_dir`. */
function preStageOutputDir(tag, subject) {
  const derivs = `${PROJECT_ROOT}/derivatives`;
  switch (tag) {
    case "G1":
      return `${PROJECT_ROOT}/sub-${subject}/anat`;
    case "G2a":
      return `${derivs}/SimNIBS/sub-${subject}/m2m_${subject}`;
    case "G2b":
      return `${derivs}/freesurfer/sub-${subject}`;
    case "G3":
      return `${derivs}/ti-toolbox/tissue_analysis/sub-${subject}`;
    case "G4":
      return `${derivs}/qsiprep/sub-${subject}`;
    case "G5":
      return `${derivs}/qsirecon/sub-${subject}`;
    case "G6":
      return `${derivs}/SimNIBS/sub-${subject}/dti`;
    default:
      return `${derivs}/ti-toolbox/reports/sub-${subject}`;
  }
}
/** Which stage outputs the subject fixtures already have — what makes the matrix a mix of chips. */
function preStageExists(tag, subject) {
  const s = (subjects.subjects ?? []).find((x) => x.id === subject);
  if (!s) return false;
  switch (tag) {
    case "G1":
      return !!s.has_raw;
    case "G2a":
      return !!s.has_m2m;
    case "G2b":
      return !!s.has_fastsurfer;
    default:
      return false;
  }
}

function planFor(kind, config, subjectIds, overwrite, montageSources) {
  const cfg = config && typeof config === "object" ? config : {};
  const ids = subjectIds && subjectIds.length ? subjectIds : cfg.subject_id ? [cfg.subject_id] : [];
  // kind=pre is a STAGE dag, not one job per subject: `tit/server/routes/plan.py::_plan_pre`
  // returns one PlanJob per (subject, stage) and appends an aligned `resolved.stages[]` carrying
  // each job's tags. The mock now does the same, so the Plan grid is a real subject x stage matrix
  // here rather than a single `m2m` column (FXU1).
  if (kind === "pre") {
    const stages = planPreprocessingStages(cfg);
    const tags = [];
    const jobsPre = [];
    for (const subject of ids) {
      for (const stage of stages) {
        const output_dir = preStageOutputDir(stage.tag, subject);
        const exists = preStageExists(stage.tag, subject);
        jobsPre.push({ kind, subject, output_dir, exists, will_overwrite: exists && !!overwrite });
        tags.push({ tags: [stage.tag], label: `sub-${subject}:${stage.tag}` });
      }
      // No report row: a report is an attachment of the job that produced it, never a plan
      // row, a job, or a CPU/MEM/ETA contribution (mirrors tit.jobs.plans.plan_preprocessing).
    }
    const conflictsPre = [];
    for (const subject of ids) {
      for (const job of jobRegistry.values()) {
        if (job.status.state === "running" && job.status.kind === kind && job.status.subject_ids.includes(subject)) {
          conflictsPre.push({ key: `${kind}:${subject}`, held_by: job.status.id, kind, subject, started_at: job.status.started_at ?? job.status.created_at });
        }
      }
    }
    const warningsPre = [];
    // GUI-voice sentences (DESIGN.md §6 rule 8, checklist item 9), not CLI-flag phrasing — this
    // names the actual control (preprocess's "Existing outputs" radio, `index.tsx`'s
    // `ExistingOutputPolicy`), which is what a reader would otherwise have to guess at.
    if (jobsPre.some((j) => j.exists && !j.will_overwrite))
      warningsPre.push("Output already exists. Choose “Replace and rerun” to overwrite it.");
    if (jobsPre.some((j) => j.will_overwrite)) warningsPre.push("Existing output will be replaced.");
    return { jobs: jobsPre, lock_conflicts: conflictsPre, cost: costFor(kind, ids.length, cfg), warnings: warningsPre, resolved: { stages: tags } };
  }
  const jobsPlan = ids.map((subject) => {
    const output_dir = outputDirFor(kind, subject, cfg);
    const exists = existsForFixture(kind, subject, cfg);
    return { kind, subject, output_dir, exists, will_overwrite: exists && !!overwrite };
  });
  const lock_conflicts = [];
  for (const subject of ids) {
    for (const job of jobRegistry.values()) {
      if (job.status.state === "running" && job.status.kind === kind && job.status.subject_ids.includes(subject)) {
        lock_conflicts.push({ key: `${kind}:${subject}`, held_by: job.status.id, kind, subject, started_at: job.status.started_at ?? job.status.created_at });
      }
    }
  }
  const warnings = [];
  // GUI-voice sentences (DESIGN.md §6 rule 8, checklist item 9), not CLI-flag phrasing. Shared
  // across every non-"pre" kind (sim/flex/ex/mex/analyzer/stats/nilearn/nifti_average), whose
  // confirm-button wording varies ("Overwrite and run", "Run analysis", …) — naming the mechanism
  // (the run-time confirmation) rather than one kind's specific button label keeps this true for
  // all of them.
  if (jobsPlan.some((j) => j.exists && !j.will_overwrite)) warnings.push("Output already exists. Running will ask you to confirm the overwrite.");
  if (jobsPlan.some((j) => j.will_overwrite)) warnings.push("Existing output will be replaced.");
  return { jobs: jobsPlan, lock_conflicts, cost: costFor(kind, ids.length, cfg), warnings, resolved: resolvedFor(kind, cfg, montageSources, ids) };
}

// ---------------------------------------------------------------------------------- ViewSpec
/** Parse an undeclared `?percentile=lo,hi` convenience param (e.g. "95,99.9"); `null` if absent
 * or malformed. Not part of openapi.yaml's declared query parameters for this route -- a
 * mock-only hook so ViewLayer.percentile has a real, exercisable path end to end (the actual
 * voxel-intensity math this would need against a real NIfTI is server-side work per
 * pages/viewer/PARITY.md; this mock resolves it with a fixed, deterministic formula instead). */
/** basename -> real file, indexed once under TIT_MOCK_DATA_ROOT (unset => always empty). */
let dataRootIndex = null;
function dataRootFiles() {
  if (dataRootIndex) return dataRootIndex;
  dataRootIndex = new Map();
  if (!DATA_ROOT) return dataRootIndex;
  const walk = (dir, depth) => {
    if (depth > 6) return;
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full, depth + 1);
      else if (entry.isFile() && !dataRootIndex.has(entry.name)) dataRootIndex.set(entry.name, full);
    }
  };
  walk(DATA_ROOT, 0);
  return dataRootIndex;
}
/** With TIT_MOCK_DATA_ROOT set, point a fixture layer at the real file of the same basename, so
 * the scene's /api/files/raw URLs actually stream bytes. Unset => the layer is untouched. */
function dataRootLayer(layer) {
  if (!DATA_ROOT) return layer;
  const index = dataRootFiles();
  const real = index.get(basename(layer.path));
  if (!real) return layer;
  const lut = layer.lut && layer.lut.includes("/") ? index.get(basename(layer.lut)) ?? null : layer.lut;
  return { ...layer, path: real, lut };
}

function parsePercentileParam(q) {
  const raw = q.get("percentile");
  if (!raw) return null;
  const [lo, hi] = raw.split(",").map(Number);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  return { lo, hi };
}
/** Resolve a heat-overlay layer's cal_min/cal_max from a requested percentile window -- a layer's
 * cal_min/cal_max are always the final absolute numbers a viewer applies, per ViewLayer's own
 * description, whether the caller asked via percentile or (the default here) explicit values. */
function resolvePercentileLayer(layer, percentile) {
  if (!percentile || layer.colormap !== "heat") return layer;
  const ceiling = 0.5; // matches this mock's fixed heat-overlay range (cal_max: 0.5) elsewhere
  return { ...layer, percentile, cal_min: Number(((percentile.lo / 100) * ceiling).toFixed(3)), cal_max: Number(((percentile.hi / 100) * ceiling).toFixed(3)) };
}
function buildViewSpec(kind, q) {
  const subject = q.get("subject") ?? "ernie";
  const space = q.get("space") ?? "subject";
  const field = q.get("field") ?? "TI_max";
  const base = `${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}`;
  const layers = [];
  if (kind === "custom") {
    const path = q.get("path") ?? `${base}/T1.nii.gz`;
    layers.push({ path, kind: path.endsWith(".msh") ? "label" : "volume", colormap: "grayscale", opacity: 1, visible: true, cal_min: null, cal_max: null, lut: null, percentile: null });
  } else {
    layers.push({ path: `${base}/m2m_${subject}/T1.nii.gz`, kind: "volume", colormap: "grayscale", opacity: 1, visible: true, cal_min: null, cal_max: null, lut: null, percentile: null });
    if (kind === "subject") {
      // R5's optional `atlas`: absent keeps the previous behaviour (the server picks
      // labeling.nii.gz), a named atlas is overlaid instead -- so the atlas the request asked for
      // is visible in the scene the client gets back, which is what the Viewer's e2e asserts on.
      const atlas = q.get("atlas");
      layers.push({
        path: atlas ? `${base}/m2m_${subject}/segmentation/${atlas}.nii.gz` : `${base}/m2m_${subject}/segmentation/labeling.nii.gz`,
        kind: "volume",
        colormap: "lut",
        opacity: 0.7,
        visible: true,
        cal_min: null,
        cal_max: null,
        lut: null,
        percentile: null,
      });
    }
    if (kind === "simulation" || kind === "analysis") {
      const sim = q.get("simulation") ?? "Thalamus";
      layers.push({
        path: `${base}/Simulations/${sim}/${field.startsWith("m") ? "mTI" : "TI"}/${space}_overlays/${subject}_${field}${space === "mni" ? "_MNI" : ""}.nii.gz`,
        kind: "volume",
        colormap: "heat",
        opacity: 0.7,
        visible: true,
        cal_min: 0,
        cal_max: 0.5,
        lut: null,
        percentile: null,
      });
    }
    if (kind === "analysis") {
      const atlas = q.get("roi") ?? "DK40";
      layers.push({ path: `${base}/m2m_${subject}/segmentation/lh.${atlas}.annot`, kind: "label", colormap: "lut", opacity: 0.5, visible: false, cal_min: null, cal_max: null, lut: "FreeSurferColorLUT", percentile: null });
    }
    if (kind === "group") {
      layers.length = 0;
      layers.push({ path: "/ti-toolbox/resources/atlas/MNI152_T1_1mm.nii.gz", kind: "volume", colormap: "grayscale", opacity: 1, visible: true, cal_min: null, cal_max: null, lut: null, percentile: null });
      layers.push({ path: `${PROJECT_ROOT}/derivatives/group/analyses/group_avg_${field}.nii.gz`, kind: "volume", colormap: "heat", opacity: 0.7, visible: true, cal_min: 0, cal_max: 0.5, lut: null, percentile: null });
    }
  }
  const percentile = parsePercentileParam(q);
  const resolvedLayers = layers.map((l) => dataRootLayer(resolvePercentileLayer(l, percentile)));
  const freeview_args = ["-v", ...resolvedLayers.map((l) => `${l.path}:colormap=${l.colormap}:opacity=${l.opacity}`)];
  const specSpace = kind === "group" ? "mni" : space;
  return { space: specSpace, layers: resolvedLayers, freeview_args, scene: sceneFor(specSpace, resolvedLayers, null) };
}

// ------------------------------------------------------------------------------ Tetravox scene
// Mirror of tit/viewspec.py's Tetravox ViewSpec v2 builder (to_tetravox_viewspec) -- see that
// module's docstring for why every field here is what it is (no per-file camera fit, no
// percentile-window escape hatch, DatasetRef.path/.absPath both the same /api/files/raw URL).
// Kept a deliberately close 1:1 port so a spec asserting on scene shape reads the same against
// this mock and the real server.
const MESH_EXTS = [".msh", ".gii"];
function sceneStem(name) {
  return name.replace(/\.(nii\.gz|nii|msh|gii|mgz)$/, "");
}
function sceneIsMesh(path) {
  const lowered = path.toLowerCase();
  return MESH_EXTS.some((e) => lowered.endsWith(e));
}
function sceneRole(path, colormap) {
  const name = basename(path).toLowerCase();
  if (sceneIsMesh(path)) return "mesh";
  if (colormap === "lut") return name.startsWith("electrode_overlay") ? "electrodes" : "atlas";
  if (colormap === "heat" || colormap === "jet") return "field";
  return "base";
}
/** Field name guessed from a mesh or field-volume basename; see tit/viewspec.py's
 * _scene_field_name (same guess, used for both a mesh's colour-by field and a curated
 * volume display name -- FX3 item 3 / qa-neuro-researcher-notes.md #4). */
function sceneFieldName(name) {
  const lowered = name.toLowerCase();
  if (lowered.includes("magne") || lowered.includes("tdcs")) return "magnE";
  if (lowered.includes("normal")) return "TI_normal";
  if (lowered.includes("mti")) return "mTI_max";
  if (lowered.includes("ti")) return "TI_max";
  return null;
}
/** Curated layer name for the inspector's Layers list; 1:1 port of
 * tit/viewspec.py's _scene_display_name -- see that function's docstring for the reasoning
 * (raw pipeline basenames like "grey_Thalamus_TI_subject_TI_max" gave a viewer no
 * explanation of what a layer was). The dataset's own `name` (the real basename) is
 * untouched -- only this curated layer name changes. */
function sceneDisplayName(name, role, fieldName) {
  const stem = sceneStem(name);
  const lowered = stem.toLowerCase();

  if (role === "electrodes") return "Electrodes";
  if (role === "atlas") return "Atlas";
  if (role === "base" && (lowered === "t1" || lowered.startsWith("t1_"))) return "T1";

  if (role === "mesh" || role === "field") {
    let region = null;
    if (lowered.startsWith("grey_")) region = "GM";
    else if (lowered.startsWith("white_")) region = "WM";

    if (role === "mesh") {
      const regionLabel = region ?? "Mesh";
      return fieldName ? `${regionLabel} mesh · ${fieldName}` : `${regionLabel} mesh (tags)`;
    }
    if (fieldName) return region ? `${region} · ${fieldName} (volume)` : `${fieldName} (volume)`;
  }

  return stem;
}
function rawUrlFor(path) {
  return `/api/files/raw/${String(path).replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/")}`;
}
function sceneSidecarRef(path) {
  const url = rawUrlFor(path);
  return { path: url, absPath: url };
}
const DEFAULT_SLICES = ["axial", "coronal", "sagittal"].map((mode, i) => ({
  id: mode,
  mode,
  normal: [[0, 0, 1], [0, -1, 0], [-1, 0, 0]][i],
  up: [[0, 1, 0], [0, 0, 1], [0, 0, 1]][i],
  camera: { center: [0, 0], mmPerPx: 0.6 },
}));
const DEFAULT_VIEW3D = {
  id: "view3d",
  camera: { target: [0, 0, 0], distance: 350, rotation: [0, 0, 0, 1], fovYDeg: 35, orthographic: false, near: 1, far: 1400 },
  showSlicePlanes: false,
};
const DEFAULT_ANNOTATIONS = { orientationLabels: true, cornerInfo: true, conventionBadge: true, scaleBar: true, colorbars: true, crosshair: true, orientationCube: true };
const DEFAULT_BACKGROUND = [0.058823529411764705, 0.06666666666666667, 0.08627450980392157, 1];
const ZERO_THRESHOLD = { lo: null, hi: null, symmetric: false, mode: "clamp", softEdge: 0 };

/**
 * A field layer's `[Scale, Threshold]`, mirroring `tit/viewspec.py::_volume_window`.
 *
 * `cal_min`/`cal_max` reach here already resolved to the p95/p99.9 window, so the heat scale spans
 * exactly them and the threshold floors at `cal_min` with `mode: "hide"` — everything below the
 * 95th percentile transparent, rather than a wash of low colour over the whole head (maintainer,
 * 2026-09-07). `mid` is the midpoint of the visible window so the ramp spans it.
 */
function volumeScaleAndThreshold(role, calMin, calMax) {
  if (role === "field") {
    const min = calMin ?? 0, max = calMax ?? 1;
    return [
      { kind: "heat", min, mid: (min + max) / 2, max, truncate: false, inverse: false, negative: "hide" },
      { lo: min, hi: null, symmetric: false, mode: "hide", softEdge: 0 },
    ];
  }
  return [{ kind: "linear", lo: calMin ?? 0, hi: calMax ?? 1 }, { ...ZERO_THRESHOLD }];
}
function meshScaleAndThreshold(fieldBounds) {
  const [lo, hi] = fieldBounds ?? [0, 1];
  return [{ kind: "linear", lo, hi }, { lo, hi: null, symmetric: false, mode: "clamp", softEdge: 0 }];
}

function sceneFor(space, layers, cursorIn) {
  const cursor = Array.isArray(cursorIn) && cursorIn.length === 3 ? cursorIn.map(Number) : [0, 0, 0];
  let fieldBounds = null;
  for (const layer of layers) {
    if (sceneIsMesh(layer.path)) continue;
    if (sceneRole(layer.path, layer.colormap) !== "field") continue;
    if (layer.cal_min != null && layer.cal_max != null) {
      fieldBounds = [layer.cal_min, layer.cal_max];
      break;
    }
  }

  const datasets = [];
  const sceneLayers = [];
  layers.forEach((layer, i) => {
    const path = layer.path;
    const name = basename(path);
    const role = sceneRole(path, layer.colormap);
    const isMesh = role === "mesh";
    const isLabel = layer.colormap === "lut" && !isMesh;
    const visible = layer.visible !== false;
    const fieldName = role === "mesh" || role === "field" ? sceneFieldName(name) : null;

    const sidecars = {};
    if (layer.lut && layer.lut.includes("/")) sidecars.lut = sceneSidecarRef(layer.lut);
    if (isMesh) {
      const opt = `${path}.opt`;
      const local = DATA_ROOT && opt.startsWith(DATA_ROOT + sep) ? opt : null;
      if (local && existsSync(local)) sidecars.opt = sceneSidecarRef(opt);
    }
    const datasetId = `ds${i}`;
    const url = rawUrlFor(path);
    const dataset = { id: datasetId, kind: isMesh ? "mesh" : "volume", name, path: url, absPath: url, fingerprint: "" };
    if (Object.keys(sidecars).length) dataset.sidecars = sidecars;
    datasets.push(dataset);

    // The file's own basename, exactly as on disk (maintainer, 2026-09-07: "please do not change
    // the name of the files that we load into the viewer"). `sceneDisplayName` is still ported
    // below because the composition tree labels its *choices* with it -- but never a layer.
    const base = { id: `L${i}`, datasetId, name, visible, opacity: layer.opacity ?? 1, pickable: true, showColorbar: true };
    if (isMesh) {
      const [scale, threshold] = meshScaleAndThreshold(fieldBounds);
      sceneLayers.push({
        ...base,
        kind: "mesh",
        colorMode: fieldName ? "field" : "solid",
        solidColor: [0.78, 0.78, 0.8, 1],
        field: fieldName ? { source: "elm", name: fieldName, component: "mag" } : null,
        colormap: "jet",
        scale,
        threshold,
        tagStyle: {},
        edges: { surface: false, caps: false },
        edgeColor: [0, 0, 0, 1],
        edgeWidthPx: 1,
        flatShading: false,
        faceMode: "cull",
        clip: { planes: [{ plane: { normal: [1, 0, 0], offset: cursor[0] }, enabled: true, followCursor: true }], caps: true, capColorMode: "inherit" },
        contoursIn2D: name.toLowerCase().startsWith("grey_"),
        contourWidthPx: 1,
        fillIn2D: true,
      });
    } else {
      sceneLayers.push({
        ...base,
        kind: "volume",
        volumeIndex: 0,
        colormap: role === "field" ? "turbo" : "gray",
        ...(() => {
          const [scale, threshold] = volumeScaleAndThreshold(role, layer.cal_min, layer.cal_max);
          return { scale, threshold };
        })(),
        interpolation: isLabel ? "nearest" : "linear",
        labelMode: "fill",
        outlineWidthPx: isLabel ? 2 : 1,
        showIn3D: isLabel,
        precision: "auto",
      });
    }
  });

  // A layout that reserves a 3D pane and a mesh nobody can see is an empty 3D pane. The layout
  // below gives the mesh a pane precisely *because* the scene has one, so the two must agree
  // (`tit/viewspec.py`, same comment).
  const meshLayers = sceneLayers.filter((l) => l.kind === "mesh");
  if (meshLayers.length > 0 && !meshLayers.some((l) => l.visible)) meshLayers[0].visible = true;

  const visibleIds = sceneLayers.filter((l) => l.visible).map((l) => l.id);
  const activeLayerId = visibleIds[0] ?? sceneLayers[0]?.id ?? null;
  const hasMesh = sceneLayers.some((l) => l.kind === "mesh");

  return {
    version: 2,
    datasets,
    layers: sceneLayers,
    activeLayerId,
    // NOT a 1:1 port: the real server fits every pane and the 3D camera to the scene's world
    // bounding box, read from each NIfTI's affine (`tit/viewspec.py::_fit_mm_per_px`). This mock
    // serves no NIfTI headers, so there is nothing here to measure and the engine defaults stand.
    // The fit is therefore asserted against the real server only (`tests/e2e/real/viewer-open`).
    slices: DEFAULT_SLICES.map((s) => ({ ...s, camera: { ...s.camera } })),
    view3d: { ...DEFAULT_VIEW3D, camera: { ...DEFAULT_VIEW3D.camera } },
    layout: hasMesh ? { kind: "3d+1", cells: ["view3d", "axial"] } : { kind: "2x2", cells: ["axial", "coronal", "sagittal", "view3d"] },
    cursor,
    radiological: false,
    background: [...DEFAULT_BACKGROUND],
    lighting: { ambient: 0.25, headlight: true },
    annotations: { ...DEFAULT_ANNOTATIONS },
    transparency: { mode: "twoPhase" },
  };
}

// ------------------------------------------------------------------------------------ job engine
const TERMINAL = new Set(["succeeded", "failed", "cancelled", "skipped", "lost"]);
const jobRegistry = new Map(); // id -> { spec, status, events: Event[], timers: Timeout[], cancelled }
const wsJobClients = new Set(); // Set<{ ws, subs: Map<jobId, sinceSeq> }>

function makeJobId() {
  return `job_${randomBytes(6).toString("hex")}`;
}
function stagesFor(kind) {
  switch (kind) {
    case "pre":
      // Matches the real server's stage tags (`tit/jobs/plans.py` G2a/G2b/G3): "charm" (SimNIBS
      // charm), "fastsurfer" (FastSurfer segmentation, the FreeSurfer recon-all replacement — see
      // `describePreStageDir`'s "(legacy)" fallback for the older, non-FastSurfer backend), "tissue".
      return ["charm", "fastsurfer", "tissue"];
    case "sim":
      return ["mesh", "fem_solve", "combine", "report"];
    case "flex":
    case "flex_adaptive":
    case "flex_pareto":
      return ["init", "evaluate", "converge"];
    case "ex":
    case "mex":
      return ["enumerate", "evaluate", "rank"];
    case "leadfield":
      return ["prepare", "solve", "save"];
    case "analyzer":
      return ["load", "roi_stats", "report"];
    case "stats":
      return ["permute", "cluster", "report"];
    case "source":
      return ["forward", "project"];
    case "blender":
      return ["render"];
    case "nifti_average":
      return ["average"];
    case "nilearn":
      return ["render"];
    case "project_init":
      return ["seed", "example_data"];
    case "report":
      return ["render"];
    case "tools":
      return ["run"];
    default:
      return ["run"];
  }
}
const LOGGER_FOR = {
  pre: "tit.pre.pipeline",
  sim: "tit.sim.simulator",
  flex: "tit.opt.flex.flex",
  flex_adaptive: "tit.opt.flex.flex",
  flex_pareto: "tit.opt.flex.flex",
  ex: "tit.opt.ex.ex_search",
  mex: "tit.opt.mex.mex",
  leadfield: "tit.opt.leadfield",
  analyzer: "tit.analyzer.analyzer",
  stats: "tit.stats",
  source: "tit.source",
  blender: "tit.blender",
  nifti_average: "tit.tools.nifti_average",
  nilearn: "tit.tools.nilearn_visuals",
  project_init: "tit.pre.example_data",
  // internal-only JobKinds (tit/jobs/spec.py::JOB_KINDS) reachable from the "pre" group DAG
  // (the per-subject report job) or standalone (an arbitrary module run as a "tools" job).
  report: "tit.reporting.core.assembler",
  tools: "tit.jobs.runner",
};
function loggerFor(kind) {
  return LOGGER_FOR[kind] ?? "tit.jobs.runner";
}
function buildArtifacts(job) {
  const subject = job.status.subject_ids[0] ?? "ernie";
  const base = `${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}`;
  const id = job.status.id;
  switch (job.status.kind) {
    case "sim":
      return [
        { path: `${base}/Simulations/mock_${id}/report/report.html`, kind: "report", label: "Simulation report" },
        { path: `${base}/Simulations/mock_${id}/TI/mesh/${subject}_TI.msh`, kind: "mesh", label: "TI mesh" },
      ];
    case "flex":
    case "flex_adaptive":
    case "flex_pareto":
      return [{ path: `${base}/flex-search/mock_${id}/manifest.json`, kind: "manifest", label: "Flex-search manifest" }];
    case "ex":
    case "mex":
      return [{ path: `${base}/${job.status.kind}-search/mock_${id}/final_output.csv`, kind: "table", label: "Final output" }];
    case "analyzer":
      return [{ path: `${base}/Simulations/mock/Analyses/mock_${id}/summary.csv`, kind: "table", label: "Summary" }];
    case "pre":
      // The report is an attachment of the job that produced it, not a job of its own -- the
      // real server records it here too (JobManager._attach_pre_report).
      return [
        { path: `${base}/m2m_${subject}/m2m_${subject}.log`, kind: "log", label: "Preprocessing log" },
        { path: `${base}/m2m_${subject}/report/report.html`, kind: "report", label: "Preprocessing report" },
      ];
    case "report":
      return [{ path: `${base}/m2m_${subject}/report/report.html`, kind: "report", label: "Preprocessing report" }];
    case "project_init":
      return [{ path: `${PROJECT_ROOT}/dataset_description.json`, kind: "manifest", label: "Project manifest" }];
    default:
      return [{ path: `${base}/${job.status.kind}/mock_${id}/output`, kind: job.status.kind, label: "Output" }];
  }
}
function emitEvent(job, partial) {
  const ev = { seq: job.events.length, ts: Date.now() / 1000, ...partial };
  job.events.push(ev);
  for (const client of wsJobClients) {
    if (client.subs.has(job.status.id) && client.ws.readyState === client.ws.OPEN) {
      client.ws.send(JSON.stringify({ type: "event", job_id: job.status.id, event: ev }));
    }
  }
  return ev;
}
function broadcastJob(job) {
  const payload = JSON.stringify({ type: "job", job: job.status });
  for (const client of wsJobClients) {
    if (client.ws.readyState === client.ws.OPEN) client.ws.send(payload);
  }
}
function lastLogLines(job, n) {
  return job.events
    .filter((e) => e.type === "log")
    .slice(-n)
    .map((e) => e.msg);
}
function clearJobTimers(job) {
  for (const t of job.timers) clearTimeout(t);
  job.timers = [];
}
function finishJob(job) {
  if (job.cancelled || TERMINAL.has(job.status.state)) return;
  const cfg = job.spec.config && typeof job.spec.config === "object" ? job.spec.config : {};
  const artifacts = buildArtifacts(job);
  // One flat-field "artifact" event per produced file, then a single "result" event carrying the
  // runner's arbitrary structured payload (outputs) plus the accumulated artifact list -- matches
  // contracts/events.schema.json's target shape (Event: artifact.{path,kind,label} flat, both
  // required; result.outputs required, result.artifacts optional).
  for (const a of artifacts) emitEvent(job, { type: "artifact", path: a.path, kind: a.kind, label: a.label });
  const outputs = Object.fromEntries(artifacts.map((a, i) => [a.kind || `artifact_${i}`, a.path]));
  emitEvent(job, { type: "result", outputs, artifacts });
  if (cfg.__mock_fail === true) {
    // A realistic Python traceback, so the failed-job fixture exercises the Summary tab's one-line
    // reason (`failureReason` in app/jobs-rail/format.ts) against frames it must skip.
    for (const msg of [
      "Traceback (most recent call last):",
      '  File "/opt/tit/sim/__main__.py", line 42, in <module>',
      "    main()",
      '  File "/opt/tit/sim/runner.py", line 88, in main',
      "    cfg = SimulationConfig(**payload)",
      "          ^^^^^^^^^^^^^^^^^^^^^^^^^^^",
      "TypeError: SimulationConfig.__init__() missing 2 required positional arguments: 'subject_id' and 'montages'",
    ]) {
      emitEvent(job, { type: "log", level: "error", logger: loggerFor(job.status.kind), msg });
    }
    emitEvent(job, { type: "exit", code: 1 });
    job.status.exit_code = 1;
    job.status.state = "failed";
    job.status.error = { type: "runner_failed", message: "synthetic failure requested via config.__mock_fail", last_lines: lastLogLines(job, 10) };
  } else {
    emitEvent(job, { type: "exit", code: 0 });
    job.status.exit_code = 0;
    job.status.state = "succeeded";
  }
  job.status.finished_at = nowIso();
  job.status.progress = { stage: "done", i: 1, n: 1, pct: 100 };
  job.status.liveness = null;
  job.status.artifacts = artifacts;
  broadcastJob(job);
  tick();
}
function runTimeline(job) {
  const cfg = job.spec.config && typeof job.spec.config === "object" ? job.spec.config : {};
  const stages = stagesFor(job.status.kind);
  const totalMs = cfg.__mock_fast === true ? 300 + Math.random() * 200 : 6000 + Math.random() * 4000;
  const perStage = totalMs / stages.length;
  const timers = [];
  const subjectLabel = job.status.subject_ids.join(",") || "(no subject)";
  // `__mock_log_lines` (see the file header): a log longer than any pane, emitted at once, so a
  // spec can prove a console really scrolls rather than hoping the stage lines overflow.
  const filler = Number(cfg.__mock_log_lines ?? 0);
  for (let i = 0; i < filler; i++) {
    timers.push(
      setTimeout(
        () =>
          emitEvent(job, {
            type: "log",
            level: "info",
            logger: loggerFor(job.status.kind),
            msg: `filler line ${i + 1} of ${filler} (${subjectLabel})`,
          }),
        10,
      ),
    );
  }
  stages.forEach((stage, si) => {
    const stageStart = si * perStage;
    timers.push(setTimeout(() => emitEvent(job, { type: "stage", stage }), stageStart));
    const nProg = 4;
    for (let i = 1; i <= nProg; i++) {
      const t = stageStart + (perStage * i) / nProg;
      const pct = Math.round(((si + i / nProg) / stages.length) * 100);
      timers.push(
        setTimeout(() => {
          job.status.progress = { stage, i, n: nProg, pct };
          emitEvent(job, { type: "progress", stage, i, n: nProg, pct });
        }, t),
      );
    }
    // A real stage writes tens of lines, not one (FXU1: the run page's Terminal is measured on the
    // populated state, and one line per stage made a live console look emptier than the last
    // run's log file it replaces). Four detail lines per stage, then the completion line.
    const detail = ["reading inputs", "resources: 4 CPU, 16 GB", "working…", "writing outputs"];
    detail.forEach((what, di) => {
      timers.push(
        setTimeout(
          () =>
            emitEvent(job, {
              type: "log",
              level: di === 2 && si % 3 === 1 ? "warning" : "info",
              logger: loggerFor(job.status.kind),
              msg: `${stage}: ${what} (${subjectLabel})`,
            }),
          stageStart + (perStage * (di + 1)) / 6,
        ),
      );
    });
    timers.push(
      setTimeout(() => emitEvent(job, { type: "log", level: "info", logger: loggerFor(job.status.kind), msg: `${stage}: complete for ${subjectLabel}` }), stageStart + perStage * 0.9),
    );
  });
  timers.push(setTimeout(() => finishJob(job), totalMs + 100));
  job.timers = timers;
}
// group_id -> parallel_subjects cap (JobGroupRequest.parallel_subjects): at most this many of the
// group's own jobs run at once, enforced here rather than by how many jobs are submitted -- every
// job is created "queued" immediately and the scheduler releases them this-many-at-a-time.
const groupParallelLimit = new Map();

// A job stays `queued` for as long as `isReady()` below finds ANY blocker: an unfinished `after`
// dependency, a same-(kind,subject) job still `running` (the P7 "one job of a kind per subject"
// exclusivity `isReady` enforces for every kind, not only the heavy ones), or a full `group_id`
// parallel-subjects slot. All three blockers are themselves jobs, and every job that ever reaches
// `running` is *itself* bounded -- `runTimeline`'s own final timer calls `finishJob` at
// `totalMs + 100`, at most 10 100 ms after it started -- so under one spec file's own traffic a
// queued job unblocks within a few multiples of that.
//
// The defect this guards (critic, 2026-09-04, `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §5a/§7.2):
// `npx playwright test` starts exactly one `tests/mock-server/server.mjs` process for the WHOLE
// invocation (`playwright.config.ts`'s `webServer`, `workers: 1`) and every spec FILE shares it, so
// a job an earlier file created and never itself drove to a terminal state -- no assertion in that
// file waited for it, and nothing cancelled it -- keeps its exclusivity slot for the rest of the
// run. A later, unrelated file (`layout.spec.ts`, which submits no job of its own) then sees that
// leftover as its OWN page's live job, measured forcing the right pane to the Terminal tab instead
// of Scene on all four run pages and blowing the L5a dead-space budget by up to 11 points; lane SUB
// independently hit the same class as a spurious "1 wait" clause in `optimizer.spec.ts`. Threads on
// a shared server are not something a fixture reset can be relied on here either (see this lane's
// own notes for why one was not wired in): a bound on the wait itself, enforced once, centrally, is
// what makes it true regardless of which spec files a run happens to include or their order.
//
// The bound is `QUEUE_WATCHDOG_MS`, checked in `tick()` below: a `queued` job that has been waiting
// longer than this is cancelled (reusing `cancelJob`, the same terminal transition a user's Cancel
// button drives) rather than left to wait indefinitely. The value is derived, not guessed, from the
// slowest legitimate same-file chain this mock models: `planPreprocessingStages`'s deepest DAG is
// five levels (G1 -> G4 -> G5 -> G6 -> report), each level up to a ~10 100 ms `runTimeline` in the
// worst case (`Math.random()` at its max) -- ~50 500 ms end to end -- so 90 000 ms clears that with
// ~40 s of margin while staying far below the minutes a leaked job would otherwise survive into a
// later file. `TIT_MOCK_QUEUE_WATCHDOG_MS` overrides it so `server.test.ts` can prove the mechanism
// in milliseconds rather than actually waiting 90 real seconds.
const QUEUE_WATCHDOG_MS = Number(process.env.TIT_MOCK_QUEUE_WATCHDOG_MS ?? 90_000);

function isReady(job) {
  const waitingOn = [];
  for (const depId of job.spec.after ?? []) {
    const dep = jobRegistry.get(depId);
    if (!dep) continue;
    if (["failed", "cancelled", "lost"].includes(dep.status.state)) return { skip: true };
    if (!TERMINAL.has(dep.status.state)) waitingOn.push({ key: `after:${depId}`, job_id: depId });
  }
  for (const other of jobRegistry.values()) {
    if (other === job || other.status.state !== "running") continue;
    if (other.status.kind !== job.status.kind) continue;
    if (job.status.subject_ids.some((s) => other.status.subject_ids.includes(s))) {
      waitingOn.push({ key: `${job.status.kind}:${job.status.subject_ids.join(",")}`, job_id: other.status.id });
    }
  }
  const limit = job.status.group_id && groupParallelLimit.get(job.status.group_id);
  if (limit) {
    const runningInGroup = [...jobRegistry.values()].filter((j) => j.status.group_id === job.status.group_id && j.status.state === "running");
    if (runningInGroup.length >= limit) {
      waitingOn.push({ key: `group:${job.status.group_id}`, job_id: runningInGroup[0].status.id });
    }
  }
  if (waitingOn.length) return { wait: waitingOn };
  return { ready: true };
}
function startRunning(job) {
  job.status.state = "running";
  job.status.started_at = nowIso();
  job.status.liveness = "active";
  job.status.waiting_on = [];
  broadcastJob(job);
  runTimeline(job);
}
function tick() {
  for (const job of jobRegistry.values()) {
    if (job.status.state !== "queued") continue;
    const r = isReady(job);
    if (r.skip) {
      job.status.state = "skipped";
      job.status.finished_at = nowIso();
      job.status.error = { type: "DependencyFailed", message: "a required job did not succeed", last_lines: [] };
      broadcastJob(job);
    } else if (r.wait) {
      if (Date.now() - job._createdAtMs >= QUEUE_WATCHDOG_MS) {
        emitEvent(job, {
          type: "log",
          level: "warning",
          logger: "mock.watchdog",
          msg: `cancelled: queued longer than ${QUEUE_WATCHDOG_MS}ms behind ${r.wait.map((w) => w.key).join(", ")} (stale job, most likely left behind by an earlier spec file)`,
        });
        cancelJob(job);
        continue;
      }
      job.status.waiting_on = r.wait;
    } else {
      job.status.waiting_on = [];
      startRunning(job);
    }
  }
}
setInterval(tick, 400);

function createJob({ kind, config, subject_ids, after = [], tags = [], overwrite = false, group_id = null, startImmediately = false }) {
  const id = makeJobId();
  const job = {
    // Raw ms, sibling to (never inside) `status` -- `status` is sent verbatim over the wire
    // (`GET /api/jobs`, `jobToDetail`) and the contract test (`contract.test.ts`) checks its shape
    // against `contracts/openapi.yaml`; a field the schema does not declare would fail it.
    // `status.created_at` is the ISO string clients see; this is the same instant, kept as a number
    // so the watchdog in `tick()` can compare it every 400ms without re-parsing a string.
    _createdAtMs: Date.now(),
    spec: { kind, config: config ?? {}, subject_ids: subject_ids ?? [], after, tags, overwrite },
    status: {
      id,
      kind,
      state: "queued",
      subject_ids: subject_ids ?? [],
      group_id,
      created_at: nowIso(),
      started_at: null,
      finished_at: null,
      progress: null,
      liveness: null,
      waiting_on: [],
      exit_code: null,
      error: null,
      artifacts: [],
      cpu_percent: null,
      rss: null,
      // The real server records where the runner's log file is written (`JobStatus.log_path` in
      // contracts/openapi.yaml), and the UI's "Reveal log file" actions exist only when it is
      // set -- so the mock sets it too, at the path `tit.jobs` uses.
      log_path: `${PROJECT_ROOT}/derivatives/ti-toolbox/logs/${(subject_ids ?? []).length === 1 ? `sub-${subject_ids[0]}` : "group"}/${kind}_${id}.log`,
    },
    events: [],
    timers: [],
    cancelled: false,
  };
  jobRegistry.set(id, job);
  if (startImmediately) {
    startRunningViewer(job);
  } else {
    broadcastJob(job);
    tick();
  }
  return job;
}
/** Viewer jobs (Freeview/Gmsh) launch instantly and stay `running` until cancelled/forced. */
function startRunningViewer(job) {
  job.status.state = "running";
  job.status.started_at = nowIso();
  job.status.liveness = "active";
  broadcastJob(job);
  emitEvent(job, { type: "log", level: "info", logger: "tit.viewers", msg: `launched ${job.status.kind} for ${job.spec.tags.join(",") || "viewer"}` });
}
function cancelJob(job) {
  if (TERMINAL.has(job.status.state)) return job.status;
  clearJobTimers(job);
  job.cancelled = true;
  job.status.state = "cancelled";
  job.status.finished_at = nowIso();
  job.status.liveness = null;
  job.status.waiting_on = [];
  emitEvent(job, { type: "exit", code: -15 }); // SIGTERM, tit.jobs.runner's cancel signal
  broadcastJob(job);
  tick();
  return job.status;
}
function forceJob(job) {
  if (TERMINAL.has(job.status.state)) return job.status;
  clearJobTimers(job);
  job.cancelled = true;
  job.status.state = "failed";
  job.status.exit_code = null;
  job.status.error = { type: "Forced", message: "forced to a terminal state without waiting for the process", last_lines: lastLogLines(job, 5) };
  job.status.finished_at = nowIso();
  job.status.liveness = null;
  emitEvent(job, { type: "exit", code: -9 }); // SIGKILL, tit.jobs.runner's escalation after cancel's grace period
  broadcastJob(job);
  tick();
  return job.status;
}
function jobToDetail(job) {
  return { spec: job.spec, status: job.status, artifacts: job.status.artifacts };
}

// ------------------------------------------------------------------------------------- schema
function loadSchemaJson() {
  const real = join(repoRoot, "contracts", "generated", "config.schema.json");
  if (existsSync(real)) {
    try {
      return JSON.parse(readFileSync(real, "utf8"));
    } catch {
      /* fall through to placeholder */
    }
  }
  const $defs = {};
  for (const name of CONFIG_NAMES) $defs[name] = { type: "object", additionalProperties: true, description: `placeholder for ${name} (contracts/generated/config.schema.json not yet generated)` };
  return { $defs };
}

/**
 * kind -> the `contracts/generated/config.schema.json` `$defs` name whose `required` list a submitted config must
 * satisfy. Only the kinds whose real runner calls `deserialize_config(<Class>, data)` with no
 * fallback are listed -- for those, a missing required field is not a warning, it is a
 * `TypeError: <Class>.__init__() missing N required positional arguments` minutes into the run
 * (the regression this check exists for: the Simulator POSTed a `sim` config with no
 * `subject_id`/`montages` and the mock happily accepted it, so e2e stayed green while the real
 * backend died). `tit/jobs/config_check.py` is the real server's half of this.
 */
const SCHEMA_DEF_FOR_KIND = {
  sim: "SimulationConfig",
  flex: "FlexConfig",
  flex_adaptive: "FlexConfig",
  flex_pareto: "FlexConfig",
  ex: "ExConfig",
  mex: "MExConfig",
};

/**
 * Required-field errors for one submitted config, or `[]`.
 *
 * A config carrying a `__mock_*` escape hatch (`__mock_fast`, `__mock_fail`) is exempt: those are
 * this mock's own synthetic jobs, deliberately not real configs, and the real server rejects them
 * with a 422 too. Nothing the app builds from a page's form ever carries one, so the exemption
 * cannot hide a real regression.
 */
function schemaRequiredErrors(kind, config) {
  const name = SCHEMA_DEF_FOR_KIND[kind];
  if (!name) return [];
  const cfg = config && typeof config === "object" ? config : {};
  if (Object.keys(cfg).some((k) => k.startsWith("__mock_"))) return [];
  const def = (loadSchemaJson().$defs ?? {})[name];
  const required = Array.isArray(def?.required) ? def.required : [];
  return required
    .filter((field) => cfg[field] === undefined || cfg[field] === null || (Array.isArray(cfg[field]) && cfg[field].length === 0))
    .map((field) => `${field} is required`);
}

// ------------------------------------------------------------------------------------- routing
// `/:name` matches one segment; `/*name` (only ever as the last piece) matches the rest of the
// path including slashes -- FastAPI's `{path:path}`, which /api/files/raw/{path} needs.
function compileRoute(pattern) {
  const keys = [];
  const body = pattern
    .replace(/\/:([A-Za-z_]+)/g, (_, k) => (keys.push(k), "/([^/]+)"))
    .replace(/\/\*([A-Za-z_]+)$/, (_, k) => (keys.push(k), "/(.+)"));
  return { regex: new RegExp(`^${body}$`), keys };
}
const routeTable = [];
function route(method, pattern, handler) {
  routeTable.push({ method, ...compileRoute(pattern), handler });
}
function params(matcher, pathname) {
  const m = matcher.regex.exec(pathname);
  if (!m) return null;
  const out = {};
  matcher.keys.forEach((k, i) => (out[k] = decodeURIComponent(m[i + 1])));
  return out;
}

// --- system / auth (v0, unchanged) ---
route("GET", "/api/version", (ctx) => json(ctx.res, 200, version));
route("GET", "/api/capabilities", (ctx) => {
  // Computed, not the raw fixture: `tetravox_embed` is the *active* bundle, which the tetravox
  // routes below can change at runtime -- a Settings page that installed a bundle and then read a
  // frozen fixture would show two different answers on the same screen.
  const { release } = tvxResolve();
  return json(ctx.res, 200, {
    ...capabilities,
    tetravox_embed: {
      available: true,
      version: release.version,
      protocol: release.protocol,
      source: release.source,
      features: release.features,
      compatible: release.compatible,
      supported: TVX_SUPPORTED,
    },
  });
});
route("GET", "/api/project", (ctx) => json(ctx.res, 200, project));
route("POST", "/api/project/init", async (ctx) => {
  const body = await ctx.body();
  const job = createJob({ kind: "project_init", config: { example_data: !!body.example_data }, subject_ids: [] });
  json(ctx.res, 201, job.status);
});
route("GET", "/api/catalog/subjects", (ctx) => json(ctx.res, 200, subjects));
route("GET", "/api/catalog/simulations", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!subject) return json(ctx.res, 422, { detail: "subject is required" });
  if (!(subject in simulations)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, { simulations: simulations[subject] });
});
route("GET", "/api/catalog/simulations/:name", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!subject) return json(ctx.res, 422, { detail: "subject is required" });
  const sim = (simulations[subject] ?? []).find((s) => s.name === ctx.params.name);
  if (!sim) return json(ctx.res, 404, { detail: "unknown subject or simulation" });
  json(ctx.res, 200, sim);
});
route("GET", "/api/system", (ctx) => json(ctx.res, 200, snapshot()));
route("POST", "/api/system/terminate", async (ctx) => {
  const body = await ctx.body();
  const idx = processes.findIndex((p) => p.pid === body.pid);
  if (idx === -1) return json(ctx.res, 404, { detail: "no such process" });
  processes.splice(idx, 1);
  noContent(ctx.res);
});

// --- catalog (v1) ---
route("GET", "/api/catalog/subjects/:id", (ctx) => {
  const detail = subjectDetail(ctx.params.id);
  if (!detail) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, detail);
});
route("GET", "/api/catalog/electrode-overlays", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const simulation = ctx.url.searchParams.get("simulation");
  if (!subject || !simulation) return json(ctx.res, 422, { detail: "subject and simulation are required" });
  const sim = (simulations[subject] ?? []).find((s) => s.name === simulation);
  if (!sim) return json(ctx.res, 404, { detail: "unknown subject or simulation" });
  // Mirrors tit.catalog.electrode_overlays: one row per TI/mTI mode, "exists" false unless the
  // tools job that builds the NIfTI has already run (none of the fixtures pre-seed it).
  json(
    ctx.res,
    200,
    ["mTI", "TI"].map((mode) => ({
      mode,
      path: `/mnt/example/derivatives/SimNIBS/sub-${subject}/Simulations/${simulation}/${mode}/montage_imgs/electrode_overlay_subject.nii.gz`,
      exists: false,
    })),
  );
});
// --- run logs (FXU1) ---------------------------------------------------------------------------
// A run page's Terminal shows, when no job of its kind is live, the LAST log file of that kind for
// the current subject (DESIGN.md §4.6 rule 5). The real server has no catalog route for that yet —
// reported as a `tit/server` follow-up — so this mock defines the shape the renderer codes against
// and a 404 elsewhere simply falls through to the page's "What will run" panel.
//
// File names follow the real runners exactly: `tit/pre/utils.py::build_logger`
// (`<step>_<ts>.log`), `tit/sim/utils.py` (`Simulator_<ts>.log`), `tit/opt/{flex,ex,mex}`
// (`flex_search_ / ex_search_ / m_ex_search_<ts>.log`) and `tit/analyzer/analyzer.py`
// (`analyzer_<simulation>_<ts>.log`), all under `derivatives/ti-toolbox/logs/sub-<id>/`.
// The tracked fixture bodies live under `fixtures/run_logs/*.txt`: this repository ignores
// `*.log` globally, and the mock must be reproducible from a fresh checkout rather than from
// ignored local files.
const LOG_SEEDS = {
  pre: [{ name: "preprocess_20260827_084102.log", fixture: "preprocess.txt", modified: "2026-08-27T09:16:33Z" }],
  sim: [{ name: "Simulator_20260828_140211.log", fixture: "simulator.txt", modified: "2026-08-28T14:12:05Z" }],
  flex: [{ name: "flex_search_20260829_101500.log", fixture: "flex.txt", modified: "2026-08-29T10:44:31Z" }],
  ex: [{ name: "ex_search_20260830_090000.log", fixture: "ex.txt", modified: "2026-08-30T09:22:40Z" }],
  mex: [{ name: "m_ex_search_20260830_150000.log", fixture: "mex.txt", modified: "2026-08-30T15:30:05Z" }],
  analyzer: [{ name: "analyzer_Thalamus_20260831_112000.log", fixture: "analyzer.txt", modified: "2026-08-31T11:20:48Z" }],
};
const logCatalog = new Map(); // `${subject}:${kind}` -> entries, newest first
for (const subject of (subjects.subjects ?? []).map((s) => s.id)) {
  for (const [kind, seeds] of Object.entries(LOG_SEEDS)) {
    const entries = seeds.map((seed) => {
      const file = fixturePath("run_logs", seed.fixture);
      const path = `${PROJECT_ROOT}/derivatives/ti-toolbox/logs/sub-${subject}/${seed.name}`;
      registerArtifact(path, file, "text/plain; charset=utf-8");
      return { path, name: seed.name, kind, modified: seed.modified, size: statSync(file).size };
    });
    logCatalog.set(`${subject}:${kind}`, entries);
  }
}
route("GET", "/api/catalog/logs", (ctx) => {
  const q = ctx.url.searchParams;
  const subject = q.get("subject") ?? "";
  const kinds = (q.get("kind") ?? "").split(",").map((k) => k.trim()).filter(Boolean);
  const out = [];
  for (const kind of kinds.length ? kinds : Object.keys(LOG_SEEDS)) {
    out.push(...(logCatalog.get(`${subject}:${kind}`) ?? []));
  }
  out.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const limit = Number(q.get("limit")) || 20;
  json(ctx.res, 200, out.slice(0, limit));
});
route("GET", "/api/catalog/montages", (ctx) => json(ctx.res, 200, montagesResponse()));
route("PUT", "/api/catalog/montages/:net/:kind/:name", async (ctx) => {
  const { net, kind, name } = ctx.params;
  const key = MONTAGE_KIND_KEY[kind] ?? kind;
  const body = await ctx.body();
  montages[net] ??= { uni_polar_montages: {}, multi_polar_montages: {} };
  montages[net][key][name] = body.pairs ?? [];
  json(ctx.res, 200, montages[net][key][name]);
});
route("DELETE", "/api/catalog/montages/:net/:kind/:name", (ctx) => {
  const { net, kind, name } = ctx.params;
  const key = MONTAGE_KIND_KEY[kind];
  const bucket = montages[net]?.[key];
  if (!bucket || !(name in bucket)) return json(ctx.res, 404, { detail: "unknown montage" });
  delete bucket[name];
  noContent(ctx.res);
});
route("GET", "/api/catalog/eeg-nets", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const detail = subjectDetail(subject);
  if (!detail) return json(ctx.res, 404, { detail: "unknown subject" });
  json(
    ctx.res,
    200,
    detail.eeg_nets.map((name) => ({ name, electrodes: electrodesFor(name), n: NET_SIZES[name] ?? 128 })),
  );
});
route("GET", "/api/catalog/atlases", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const entry = atlases[subject];
  if (!entry) return json(ctx.res, 404, { detail: "unknown subject" });
  const space = ctx.url.searchParams.get("space");
  const kind = ctx.url.searchParams.get("kind");
  let list = kind ? entry[kind] ?? [] : [...entry.cortical, ...entry.subcortical];
  if (space) list = list.filter((a) => a.space === space);
  json(ctx.res, 200, list);
});
route("GET", "/api/catalog/atlases/regions", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const atlas = ctx.url.searchParams.get("atlas");
  if (!subjectDetail(subject)) return json(ctx.res, 404, { detail: "unknown subject" });
  const regions = regionsFor(atlas, ctx.url.searchParams.get("hemi"));
  if (!regions) return json(ctx.res, 404, { detail: "unknown atlas" });
  json(ctx.res, 200, regions);
});
// The sub-cortical exporter's label browser. A handful of real FreeSurfer aseg ids, with the
// voxel counts that make the list readable — enough to prove the picker writes chosen *ids* into
// `SubcorticalConfig.labels`, which is the only thing a mock can honestly prove here.
const NIFTI_LABELS = [
  { id: 10, name: "Left-Thalamus", n_voxels: 7421 },
  { id: 11, name: "Left-Caudate", n_voxels: 3610 },
  { id: 17, name: "Left-Hippocampus", n_voxels: 4188 },
  { id: 49, name: "Right-Thalamus", n_voxels: 7305 },
  { id: 53, name: "Right-Hippocampus", n_voxels: 4260 },
];
route("GET", "/api/catalog/nifti/labels", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!subjectDetail(subject)) return json(ctx.res, 404, { detail: "unknown subject" });
  const path = ctx.url.searchParams.get("path");
  // The server jails `path` to the project and 404s anything outside it; the mock reproduces the
  // shape of that answer, not the resolution itself.
  if (path && !path.includes("/derivatives/") && !path.includes("/m2m")) {
    return json(ctx.res, 404, { detail: "no readable label volume" });
  }
  json(ctx.res, 200, NIFTI_LABELS);
});
route("GET", "/api/catalog/rois", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in rois)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, rois[subject]);
});
route("POST", "/api/catalog/rois", async (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in rois)) return json(ctx.res, 404, { detail: "unknown subject" });
  const roi = await ctx.body();
  rois[subject] = rois[subject].filter((r) => r.name !== roi.name);
  rois[subject].push(roi);
  json(ctx.res, 201, roi);
});
route("DELETE", "/api/catalog/rois/:name", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const bucket = rois[subject];
  if (!bucket) return json(ctx.res, 404, { detail: "unknown subject" });
  const before = bucket.length;
  rois[subject] = bucket.filter((r) => r.name !== ctx.params.name);
  if (rois[subject].length === before) return json(ctx.res, 404, { detail: "unknown roi" });
  noContent(ctx.res);
});
route("GET", "/api/catalog/leadfields", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in leadfields)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, leadfields[subject]);
});
route("GET", "/api/catalog/flex-runs", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in flexRuns)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, flexRuns[subject]);
});
/**
 * `GET /api/catalog/flex-runs/:run/mapping` — the run's electrodes as one net's labels. The real
 * server maps the optimiser's XYZ onto *any* net the subject has (Hungarian assignment,
 * `tit/sim/montage_sources.py`) and caches the result beside the run; this mock returns the
 * precomputed mapping when the fixture has one and otherwise takes the first four electrodes of
 * the net, which is all a UI test can tell apart.
 */
route("GET", "/api/catalog/flex-runs/:run/mapping", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const net = ctx.url.searchParams.get("eeg_net");
  const run = (flexRuns[subject] ?? []).find((r) => r.name === ctx.params.run);
  if (!run) return json(ctx.res, 404, { detail: "unknown run" });
  const detail = subjectDetail(subject);
  if (!net || !detail?.eeg_nets.some((n) => n.replace(/\.csv$/, "") === net.replace(/\.csv$/, ""))) return json(ctx.res, 404, { detail: "unknown net" });
  const stem = (n) => n.replace(/\.csv$/, "");
  const known = (run.mappings ?? []).find((m) => stem(m.eeg_net) === stem(net));
  if (known) return json(ctx.res, 200, known);
  const labels = electrodesFor(net);
  const pairs = [];
  for (let i = 0; i + 1 < labels.length && pairs.length < 2; i += 2) pairs.push([labels[i], labels[i + 1]]);
  json(ctx.res, 200, { eeg_net: net, pairs });
});
route("GET", "/api/catalog/ex-runs", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const entry = exRuns[subject];
  if (!entry) return json(ctx.res, 404, { detail: "unknown subject" });
  const kind = ctx.url.searchParams.get("kind");
  json(ctx.res, 200, kind ? entry[kind] ?? [] : [...entry.ex, ...entry.mex]);
});
route("GET", "/api/catalog/ex-runs/:run/results", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const kind = ctx.url.searchParams.get("kind");
  const list = exRuns[subject]?.[kind];
  if (!list || !list.some((r) => r.run_name === ctx.params.run)) return json(ctx.res, 404, { detail: "unknown run" });
  json(ctx.res, 200, exResultsCsv[kind]);
});
// The pictures a simulation saved of itself (`tit/catalog.py::simulation_figures`): the montage
// visualisation under `<sim>/<TI|mTI>/montage_imgs/<name>_highlighted_visualization.png`.
route("GET", "/api/catalog/simulations/:name/figures", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const sim = (simulations[subject] ?? []).find((s) => s.name === ctx.params.name);
  if (!sim) return json(ctx.res, 404, { detail: "unknown subject or simulation" });
  json(ctx.res, 200, simulationFigures[`${subject}/${ctx.params.name}`] ?? []);
});
route("GET", "/api/catalog/analyses", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const simulation = ctx.url.searchParams.get("simulation");
  if (!(subject in simulations)) return json(ctx.res, 404, { detail: "unknown subject" });
  if (!simulations[subject].some((s) => s.name === simulation)) return json(ctx.res, 404, { detail: "unknown simulation" });
  json(ctx.res, 200, analyses[subject]?.[simulation] ?? []);
});
route("GET", "/api/catalog/analyses/:name/summary", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const simulation = ctx.url.searchParams.get("simulation");
  const list = analyses[subject]?.[simulation] ?? [];
  if (!list.some((a) => a.name === ctx.params.name)) return json(ctx.res, 404, { detail: "unknown analysis" });
  json(ctx.res, 200, analysisSummaryCsv);
});
route("GET", "/api/catalog/reports", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in reports)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, reports[subject]);
});
route("GET", "/api/catalog/freehand", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in freehand)) return json(ctx.res, 404, { detail: "unknown subject" });
  json(ctx.res, 200, freehand[subject]);
});
route("PUT", "/api/catalog/freehand/:name", async (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!(subject in freehand)) return json(ctx.res, 404, { detail: "unknown subject" });
  const cfg = await ctx.body();
  cfg.name = ctx.params.name;
  freehand[subject] = freehand[subject].filter((f) => f.name !== ctx.params.name);
  freehand[subject].push(cfg);
  json(ctx.res, 200, cfg);
});
route("GET", "/api/catalog/group", (ctx) => json(ctx.res, 200, groupCatalog));
// One group-statistics run's detail (`tit/catalog.py::group_stats_detail`). The `?empty=1` variant
// is the failed-run state the Results pane must be able to explain: a directory holding nothing
// but a log, and the reason from that log.
route("GET", "/api/catalog/group/stats/:name", (ctx) => {
  const type = ctx.url.searchParams.get("type");
  if (!groupCatalog.stats.some((s) => s.name === ctx.params.name && s.type === type))
    return json(ctx.res, 404, { detail: "unknown group-statistics run" });
  if (ctx.url.searchParams.get("empty") === "1") {
    const log = groupStatsDetail.artifacts.find((a) => a.kind === "log");
    return json(ctx.res, 200, {
      ...groupStatsDetail,
      status: "empty",
      reason:
        "Analysis failed: No voxel could be tested. Every voxel with data has zero within-group variance.",
      results: [],
      clusters: null,
      artifacts: [log],
    });
  }
  json(ctx.res, 200, groupStatsDetail);
});
route("GET", "/api/catalog/notes", (ctx) => json(ctx.res, 200, notes));
route("PUT", "/api/catalog/notes", async (ctx) => {
  const body = await ctx.body();
  notes = { text: body.text ?? "", updated_at: nowIso() };
  json(ctx.res, 200, notes);
});
route("GET", "/api/catalog/subject-info", (ctx) => json(ctx.res, 200, subjectInfo));
// R1: the Overview page's one aggregate read. Deliberately the ONLY route this page needs -- a
// spec counting requests here is counting the whole page.
route("GET", "/api/catalog/overview", (ctx) => json(ctx.res, 200, overview));

// ---------------------------------------------------------------------------------- scene (v1)
// The six `GET /api/scene/*` routes (plan of record `docs/dev/HISTORY.md § 2026-09-04 (scene service)` §2.1). They
// exist here for two reasons, each with the failure it prevents:
//
//  - `contract.test.ts` asserts that every operation the contract declares is exercised against
//    this server. Six declared-but-unimplemented paths made that gate red for three lanes.
//  - The run pages' scene pane must be drivable offscreen without the dev container, so the mock
//    serves the SAME `TVSC1` fixtures lane SCB's renderer tests read
//    (`tests/fixtures/scene/{skin,gm}.tvsc`) rather than a second, hand-written encoding that
//    could disagree with the format.
//
// `gm.tvsc` is served for BOTH `part=gm` and the labels payload, which is not a shortcut: the
// labels payload is defined as the gm positions plus their labels, and serving one file makes the
// alignment the client checks (same vertex count, same first and last vertex) true by construction
// — exactly as the real server derives its labels from the bytes it served for `gm`.
const SCENE_PARTS = { skin: "skin.tvsc", gm: "gm.tvsc" };
const sceneFile = (name) => readFileSync(fixturePath("scene", name));

/** Header + positions of a TVSC1 payload — enough for the manifest's counts and the bbox. */
function readTvscHead(buf) {
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const vertexCount = view.getUint32(8, true);
  const indexCount = view.getUint32(12, true);
  const box = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let v = 0; v < vertexCount; v += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = view.getFloat32(32 + v * 12 + axis * 4, true);
      if (value < box[axis]) box[axis] = value;
      if (value > box[axis + 3]) box[axis + 3] = value;
    }
  }
  return { vertexCount, triangles: indexCount / 3, bytes: buf.byteLength, bbox: box };
}
const sceneParts = Object.fromEntries(
  Object.entries(SCENE_PARTS).map(([id, file]) => {
    const bytes = sceneFile(file);
    return [id, { bytes, head: readTvscHead(bytes) }];
  }),
);
const sceneBbox = [0, 1, 2, 3, 4, 5].map((i) =>
  i < 3
    ? Math.min(...Object.values(sceneParts).map((p) => p.head.bbox[i]))
    : Math.max(...Object.values(sceneParts).map((p) => p.head.bbox[i])),
);
/**
 * `focus_bbox` — what a pane frames rather than what the scene contains, computed the way
 * `tit/scene/build.py::focus_bbox` computes it: every part's box with its floor raised to the
 * lowest **gm** vertex. On the real subjects that cuts the neck off (sub-ernie's skin reaches
 * z = -128.9 mm against -50.7 for grey matter); on these ellipsoid fixtures it cuts the bottom of
 * the larger shell off, which is enough for the pane's plumbing to be exercised offscreen.
 */
const sceneFocusFloorZ = sceneParts.gm.head.bbox[2];
const scenePartFocus = (part) => [
  part.bbox[0],
  part.bbox[1],
  Math.max(part.bbox[2], sceneFocusFloorZ),
  part.bbox[3],
  part.bbox[4],
  part.bbox[5],
];
const sceneFocusBbox = [
  sceneBbox[0],
  sceneBbox[1],
  Math.max(sceneBbox[2], sceneFocusFloorZ),
  sceneBbox[3],
  sceneBbox[4],
  sceneBbox[5],
];

/** The `gm.tvsc` fixture bands its vertices into exactly 32 labels (lane SCB's generator). */
const SCENE_LABEL_COUNT = 32;
function sceneLegendFor(atlasId) {
  const rows = regionsFor(atlasId, "both");
  if (!rows) return null;
  return rows.slice(0, SCENE_LABEL_COUNT).map((r, i) => ({
    label: i + 1,
    id: r.id,
    hemi: r.hemi ?? (i % 2 === 0 ? "lh" : "rh"),
    name: r.name,
    color: `#${(((i + 1) * 0x3b7f4d) & 0xffffff).toString(16).padStart(6, "0")}`,
  }));
}
function sceneCorticalAtlases(subject) {
  return (atlases[subject]?.cortical ?? []).filter((a) => sceneLegendFor(a.id));
}
/**
 * Electrode positions on the skin fixture's own ellipsoid, by a deterministic Fibonacci spiral —
 * so a marker really does land on the surface the pane draws, which is what makes a click test
 * meaningful. The semi-axes come from the served payload's bbox, never from a second constant.
 */
function sceneElectrodePositions(names) {
  const r = [0, 1, 2].map((i) => (sceneParts.skin.head.bbox[i + 3] - sceneParts.skin.head.bbox[i]) / 2);
  const golden = Math.PI * (3 - Math.sqrt(5));
  return names.map((name, i) => {
    // Upper hemisphere only: an EEG net has no electrodes under the chin.
    const z = 1 - (i / Math.max(1, names.length)) * 0.9;
    const radius = Math.sqrt(Math.max(0, 1 - z * z));
    const theta = golden * i;
    return { name, world: [r[0] * radius * Math.cos(theta), r[1] * radius * Math.sin(theta), r[2] * z] };
  });
}

/**
 * The 404 `detail` every `/api/scene/*` route answers a subject-level problem with, or `null` when
 * there is none — the same two sentences, in the same order, as
 * `tit/server/routes/scene.py::_scene_subject`.
 *
 * Why it is copied rather than approximated: until 2026-09-04 all six routes here answered
 * `"Unknown subject: <id>"`, which is what the real server used to say and stopped saying in the
 * same round (lane FIX-B). A mock that keeps yesterday's wording lets a spec be written against a
 * sentence the product no longer sends, and that spec then passes for ever without having been
 * true (`docs/dev/HISTORY.md § 2026-09-04 (scene service)` O2).
 *
 * Both branches are data-driven off `subjects.json`'s own `has_m2m`, so they follow the fixtures
 * rather than a second list. The shipped fixture set has no subject without a head model —
 * `TIT_MOCK_SUBJECTS_NO_M2M` (comma-separated ids) is how a test reaches that branch without
 * adding a fourth subject to a fixture five other suites count.
 */
const MOCK_NO_M2M = new Set(
  (process.env.TIT_MOCK_SUBJECTS_NO_M2M ?? "").split(",").map((s) => s.trim()).filter(Boolean),
);
/** "101" before "ernie" before "MNI152" — `tit.paths.natural_key`'s order, which is the order the
 *  real server lists ids in. */
function naturalCompare(a, b) {
  const split = (s) => s.split(/(\d+)/).filter(Boolean);
  const [xa, xb] = [split(a), split(b)];
  for (let i = 0; i < Math.max(xa.length, xb.length); i += 1) {
    const l = xa[i];
    const r = xb[i];
    if (l === undefined) return -1;
    if (r === undefined) return 1;
    const ln = /^\d+$/.test(l);
    const rn = /^\d+$/.test(r);
    if (ln && rn) {
      if (Number(l) !== Number(r)) return Number(l) - Number(r);
    } else if (ln !== rn) {
      return ln ? -1 : 1;
    } else if (l.toLowerCase() !== r.toLowerCase()) {
      return l.toLowerCase() < r.toLowerCase() ? -1 : 1;
    }
  }
  return 0;
}
function sceneSubjectProblem(subject) {
  const row = subjects.subjects.find((s) => s.id === subject);
  if (!row || !subjectDetails[subject]) {
    const known = subjects.subjects.map((s) => s.id).sort(naturalCompare).join(", ");
    return `This project has no subject '${subject}'. It has: ${known || "no subjects at all"}.`;
  }
  if (row.has_m2m === false || MOCK_NO_M2M.has(subject)) {
    return (
      `${subject} has no head model yet: m2m_${subject}/ does not exist. ` +
      `Run Pre-processing (charm) on ${subject} to create it.`
    );
  }
  return null;
}

route("GET", "/api/scene/manifest", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  const detail = subjectDetail(subject);
  json(
    ctx.res,
    200,
    {
      subject,
      space: "subject-ras",
      bbox: sceneBbox,
      focus_bbox: sceneFocusBbox,
      parts: Object.entries(sceneParts).map(([id, part]) => ({
        id,
        kind: "surface",
        triangles: part.head.triangles,
        vertices: part.head.vertexCount,
        bytes: part.head.bytes,
        fingerprint: `mock-${id}-${part.head.vertexCount}`,
        url: `/api/scene/surface?subject=${encodeURIComponent(subject)}&part=${id}`,
        simplified: false,
        within_budget: true,
        max_deviation_mm: 0,
        bbox: part.head.bbox,
        focus_bbox: scenePartFocus(part.head),
      })),
      nets: (detail.eeg_nets ?? []).map((name) => ({
        name,
        electrodes: NET_SIZES[name] ?? 128,
        url: `/api/scene/electrodes?subject=${encodeURIComponent(subject)}&net=${encodeURIComponent(name)}`,
      })),
      atlases: sceneCorticalAtlases(subject).map((a) => ({
        id: a.id,
        hemispheres: a.hemispheres ?? ["lh", "rh"],
        regions: (sceneLegendFor(a.id) ?? []).length,
        url: `/api/scene/regions?subject=${encodeURIComponent(subject)}&atlas=${encodeURIComponent(a.id)}`,
      })),
      volumes: [
        {
          id: "labeling",
          url: `/api/files/raw${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}/m2m_${subject}/segmentation/labeling.nii.gz`,
          legend_url: `/api/scene/volume-legend?subject=${encodeURIComponent(subject)}&id=labeling`,
        },
      ],
      cache: { state: "ready", built_ms: 0 },
    },
    { "x-scene-cache": "hit", "x-scene-build-ms": "0" },
  );
});

function sceneTvsc(ctx, bytes, etag) {
  const headers = {
    etag,
    "cache-control": "private, max-age=0, must-revalidate",
    "x-scene-cache": "hit",
    "x-scene-build-ms": "0",
  };
  if ((ctx.req.headers["if-none-match"] ?? "") === etag) {
    ctx.res.writeHead(304, headers);
    return ctx.res.end();
  }
  ctx.res.writeHead(200, { "content-type": "application/octet-stream", "content-length": bytes.byteLength, ...headers });
  ctx.res.end(bytes);
}

route("GET", "/api/scene/surface", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const part = ctx.url.searchParams.get("part");
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  const entry = sceneParts[part];
  if (!entry) return json(ctx.res, 404, { detail: `Unknown scene part '${part}'; expected one of gm, skin` });
  sceneTvsc(ctx, entry.bytes, `"mock-${part}"`);
});

route("GET", "/api/scene/labels", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const atlas = ctx.url.searchParams.get("atlas");
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  if (!sceneLegendFor(atlas)) {
    const available = sceneCorticalAtlases(subject).map((a) => a.id).join(", ");
    return json(ctx.res, 404, { detail: `${subject} has no cortical atlas '${atlas}'; available: ${available}` });
  }
  sceneTvsc(ctx, sceneParts.gm.bytes, `"mock-labels-${atlas}"`);
});

route("GET", "/api/scene/regions", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const atlas = ctx.url.searchParams.get("atlas");
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  const legend = sceneLegendFor(atlas);
  if (!legend) {
    const available = sceneCorticalAtlases(subject).map((a) => a.id).join(", ");
    return json(ctx.res, 404, { detail: `${subject} has no cortical atlas '${atlas}'; available: ${available}` });
  }
  json(ctx.res, 200, {
    atlas,
    subject,
    aligned_to: "gm",
    vertices: sceneParts.gm.head.vertexCount,
    radius_mm: 3.0,
    labelled_fraction: 1,
    legend,
    url: `/api/scene/labels?subject=${encodeURIComponent(subject)}&atlas=${encodeURIComponent(atlas)}`,
    cache: { state: "ready", built_ms: 0 },
  });
});

route("GET", "/api/scene/electrodes", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const net = ctx.url.searchParams.get("net");
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  const detail = subjectDetail(subject);
  if (!(detail.eeg_nets ?? []).includes(net)) return json(ctx.res, 404, { detail: `${subject} has no EEG net file '${net}'` });
  const names = electrodesFor(net);
  json(ctx.res, 200, {
    net,
    space: "subject-ras",
    electrodes: sceneElectrodePositions(names),
    reference: sceneElectrodePositions(["ref"]).map((e) => ({ ...e, name: "Cz" })),
    fiducials: sceneElectrodePositions(["Nz", "LPA", "RPA"]),
  });
});

route("GET", "/api/scene/volume-legend", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const id = ctx.url.searchParams.get("id") ?? "labeling";
  const problem = sceneSubjectProblem(subject);
  if (problem) return json(ctx.res, 404, { detail: problem });
  if (id !== "labeling") return json(ctx.res, 404, { detail: `unknown scene volume '${id}'` });
  const rows = regionsFor("labeling.nii.gz", "both") ?? [];
  json(ctx.res, 200, { id, entries: rows.map((r, i) => ({ id: r.id, name: r.name, color: `#${((i + 1) * 0x2f6f3f & 0xffffff).toString(16).padStart(6, "0")}` })) });
});

// ---------------------------------------------------------------------------------- guide (v1)
// The five `GET /api/guide/*` routes (docs/dev/HISTORY.md § 2026-09-05 R4). The fixed guide scene is
// the same shapes as `/api/scene/*` with every project-dependent part removed: no `subject`, no
// cache state, no 202. It reuses the SAME TVSC1 fixtures the scene routes serve, for the reason
// the scene block gives — a second hand-written encoding could disagree with the format — and it
// answers identically no matter which subjects a page has selected, which is precisely what the
// guide gate counts requests for.
const GUIDE_ATLASES = ["DK40", "HCP_MMP1"].filter((id) => sceneLegendFor(id));
const GUIDE_NETS = Object.keys(NET_SIZES);

route("GET", "/api/guide/manifest", (ctx) => {
  json(
    ctx.res,
    200,
    {
      guide: { id: "ernie", label: "Ernie (SimNIBS example head)" },
      guide_version: 1,
      // Never "subject-ras": the pane keys click-to-config off this value.
      space: "guide-ras",
      bbox: sceneBbox,
      focus_bbox: sceneFocusBbox,
      parts: Object.entries(sceneParts).map(([id, part]) => ({
        id,
        kind: "surface",
        triangles: part.head.triangles,
        vertices: part.head.vertexCount,
        bytes: part.head.bytes,
        fingerprint: `guide-1-${id}`,
        url: `/api/guide/surface?part=${id}`,
        simplified: false,
        within_budget: true,
        max_deviation_mm: 0,
        bbox: part.head.bbox,
        focus_bbox: scenePartFocus(part.head),
      })),
      nets: GUIDE_NETS.map((name) => ({
        name,
        electrodes: NET_SIZES[name] ?? 128,
        url: `/api/guide/electrodes?net=${encodeURIComponent(name)}`,
      })),
      atlases: GUIDE_ATLASES.map((id) => ({
        id,
        hemispheres: ["lh", "rh"],
        regions: (sceneLegendFor(id) ?? []).length,
        url: `/api/guide/regions?atlas=${encodeURIComponent(id)}`,
      })),
      volumes: [],
      provenance: {
        source: "SimNIBS example dataset, subject 'ernie'",
        source_url: "https://github.com/simnibs/example-dataset",
        license: "GPL-3.0-or-later",
        notes: "See tit/scene/guide/PROVENANCE.md.",
      },
      cache: { state: "ready", built_ms: 0 },
    },
    { "x-guide-version": "1" },
  );
});

function guideBytes(ctx, bytes, etag) {
  const headers = { etag, "cache-control": "private, max-age=31536000, immutable", "x-guide-version": "1" };
  if ((ctx.req.headers["if-none-match"] ?? "") === etag) {
    ctx.res.writeHead(304, headers);
    return ctx.res.end();
  }
  ctx.res.writeHead(200, { "content-type": "application/octet-stream", "content-length": bytes.byteLength, ...headers });
  ctx.res.end(bytes);
}

route("GET", "/api/guide/surface", (ctx) => {
  const part = ctx.url.searchParams.get("part");
  const format = ctx.url.searchParams.get("format") ?? "tvsc";
  if (format !== "tvsc" && format !== "gii") {
    return json(ctx.res, 400, { detail: `Unknown guide format '${format}'; expected 'tvsc' or 'gii'` });
  }
  const entry = sceneParts[part];
  if (!entry) return json(ctx.res, 404, { detail: `the guide has no part '${part}'; it has: skin, gm.` });
  guideBytes(ctx, entry.bytes, `"guide-${part}-${format}"`);
});

route("GET", "/api/guide/labels", (ctx) => {
  const atlas = ctx.url.searchParams.get("atlas");
  if (!GUIDE_ATLASES.includes(atlas)) {
    return json(ctx.res, 404, { detail: `the guide has no atlas '${atlas}'; it has: ${GUIDE_ATLASES.join(", ")}.` });
  }
  guideBytes(ctx, sceneParts.gm.bytes, `"guide-labels-${atlas}"`);
});

route("GET", "/api/guide/regions", (ctx) => {
  const atlas = ctx.url.searchParams.get("atlas");
  if (!GUIDE_ATLASES.includes(atlas)) {
    return json(ctx.res, 404, { detail: `the guide has no atlas '${atlas}'; it has: ${GUIDE_ATLASES.join(", ")}.` });
  }
  json(ctx.res, 200, {
    atlas,
    space: "guide-ras",
    aligned_to: "gm",
    vertices: sceneParts.gm.head.vertexCount,
    radius_mm: 3.0,
    labelled_fraction: 1,
    legend: sceneLegendFor(atlas),
    url: `/api/guide/labels?atlas=${encodeURIComponent(atlas)}`,
    cache: { state: "ready", built_ms: 0 },
  });
});

route("GET", "/api/guide/electrodes", (ctx) => {
  const net = ctx.url.searchParams.get("net");
  if (!GUIDE_NETS.includes(net)) {
    return json(ctx.res, 404, { detail: `the guide has no net '${net}'; it has: ${GUIDE_NETS.join(", ")}.` });
  }
  json(ctx.res, 200, { net, space: "guide-ras", electrodes: sceneElectrodePositions(electrodesFor(net)) });
});


// --- schema (v1) ---
route("GET", "/api/schema", (ctx) => json(ctx.res, 200, loadSchemaJson()));
route("GET", "/api/schema/:name", (ctx) => {
  const def = loadSchemaJson().$defs?.[ctx.params.name];
  if (!def) return json(ctx.res, 404, { detail: "unknown config class name" });
  json(ctx.res, 200, def);
});

// --- validate / plan (v1) ---
route("POST", "/api/validate/:kind", async (ctx) => {
  const body = await ctx.body();
  json(ctx.res, 200, validateConfig(ctx.params.kind, body.config));
});
route("POST", "/api/plan/:kind", async (ctx) => {
  const body = await ctx.body();
  json(ctx.res, 200, planFor(ctx.params.kind, body.config, body.subject_ids, body.overwrite, body.montage_sources));
});

// --- jobs (v1) ---
// Test-only, mock-only: cancels and forgets every non-terminal job (and the group parallel-limit
// bookkeeping that goes with them). NOT in contracts/openapi.yaml — deliberately, since this
// endpoint exists only to give the e2e harness a way to say "a spec file's session is starting or
// ending, forget whatever an earlier one left running" and has no counterpart on tit.server; a
// widened contract or a `declared`/`exercised` mismatch in contract.test.ts would be the sign this
// leaked into it by accident. `tests/e2e/_helpers.ts::resetMockJobs` calls it once per
// `launchElectronApp` -- see that file's own comment for why (defect 1,
// docs/dev/HISTORY.md § 2026-09-04 (scene service) §5a/§7.2) the `QUEUE_WATCHDOG_MS` mechanism above cannot
// do this by itself: the job the critic measured forcing `layout.spec.ts`'s right pane to Terminal
// was 3 SECONDS old when observed -- legitimately still inside `runTimeline`'s own ~10.1s natural
// lifetime, not stuck by any definition a wait-duration heuristic could catch. Only an explicit
// per-file boundary can tell "abandoned by a file that has already moved on" apart from
// "legitimately three seconds into progressing".
// --- notebooks and kernels (NB lane) ---------------------------------------------------------
// The fake kernel is deliberately not a Python interpreter: it recognises `print(...)` and a
// bare arithmetic expression, and everything else is a NameError. That is enough to prove the
// *wiring* -- a cell's code reaches a kernel, its outputs come back attributed to that cell, and
// the reply ends the run -- which is the only thing a mock can honestly prove. Anything cleverer
// would be a Python emulator whose bugs would be mistaken for the product's.
const notebookStore = new Map();
const NOTEBOOK_DIR = "/mnt/000/code/ti-toolbox/notebooks";

function notebookName(name) {
  let rest = String(name ?? "").trim();
  let prefix = "";
  if (rest.startsWith("examples/")) {
    prefix = "examples/";
    rest = rest.slice(prefix.length);
  }
  rest = rest.replace(/\.ipynb$/, "");
  if (!/^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}$/.test(rest)) return null;
  return `${prefix}${rest}.ipynb`;
}

const EXAMPLE_NAME = "examples/getting-started.ipynb";

/** Mirrors `tit.server.notebooks.EXAMPLE_INTRO`'s feature set, not its prose. */
const EXAMPLE_INTRO = [
  "# Getting started with TI-Toolbox notebooks",
  "",
  "This notebook runs on the container's **SimNIBS Python**, so `tit`, `simnibs` and",
  "`matplotlib` are importable with *nothing to install*.",
  "",
  "## What it shows",
  "",
  "1. The environment.",
  "2. A `pandas` table.",
  "",
  "$$",
  "|\\vec{E}_{\\mathrm{TI}}| = 2\\,|\\vec{E}_2|",
  "$$",
  "",
  "and $2\\,|\\vec{E}_1|$ otherwise.",
  "",
  "```python",
  "from tit import get_path_manager",
  "```",
  "",
  "| step | cost |",
  "| --- | ---: |",
  "| environment | instant |",
  "",
  "See the [TI-Toolbox wiki](https://idossha.github.io/TI-Toolbox/).",
].join("\n");

function exampleNotebook() {
  return {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { name: "simnibs", display_name: "SimNIBS + TI-Toolbox", language: "python" },
      language_info: { name: "python" },
    },
    cells: [
      { cell_type: "markdown", id: "ex-intro", metadata: {}, source: EXAMPLE_INTRO },
      {
        cell_type: "code",
        id: "ex-env",
        metadata: {},
        execution_count: null,
        outputs: [],
        source: "print('project /mnt/000')",
      },
    ],
  };
}

/** Seeded on the first listing, exactly as the real server does. */
function seedExample() {
  if (notebookStore.has(EXAMPLE_NAME) || notebooksSeeded.deleted) return;
  const content = exampleNotebook();
  notebookStore.set(EXAMPLE_NAME, {
    content,
    size: JSON.stringify(content).length,
    modified: 0,
  });
}

const notebooksSeeded = { deleted: false };

function starterNotebook() {
  return {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { name: "simnibs", display_name: "SimNIBS + TI-Toolbox", language: "python" },
      language_info: { name: "python" },
    },
    cells: [
      {
        cell_type: "markdown",
        id: "intro",
        metadata: {},
        source:
          "# New TI-Toolbox notebook\n\nThis kernel is the container's **SimNIBS Python**, so `tit`, `simnibs`, `numpy`, `nibabel`, `pandas` and `matplotlib` are all importable with nothing to install.\n\nRun the cell below with **\u21e7\u21b5**. For a worked example \u2014 a real field summarised, plotted and tabulated \u2014 open `examples/getting-started.ipynb`.",
      },
      {
        cell_type: "code",
        id: "starter",
        metadata: {},
        execution_count: null,
        outputs: [],
        source:
          "# TI-Toolbox is already on this kernel's path \u2014 this cell proves it,\n# and it is the block every scripted workflow starts from.\nimport simnibs\n\nfrom tit import catalog, get_path_manager\nfrom tit.analyzer import Analyzer\nfrom tit.sim import SimulationConfig\n\npm = get_path_manager()\nsubjects = catalog.subject_ids(pm)\n\nprint('project ', pm.project_dir)\nprint('simnibs ', simnibs.__version__)\nprint('subjects', subjects)\n",
      },
    ],
  };
}

route("GET", "/api/notebooks", (ctx) => {
  seedExample();
  return json(ctx.res, 200, {
    dir: NOTEBOOK_DIR,
    notebooks: [...notebookStore.entries()]
      .map(([name, entry]) => ({
        name,
        size: entry.size,
        modified: entry.modified,
        example: name.startsWith("examples/"),
      }))
      // The example sorts last: a user's own notebooks are what they came for.
      .sort((a, b) => Number(a.example) - Number(b.example) || b.modified - a.modified),
  });
});

route("POST", "/api/notebooks", async (ctx) => {
  const body = await ctx.body();
  const name = notebookName(body?.name);
  if (name === null) return json(ctx.res, 422, { detail: "unusable notebook name" });
  if (notebookStore.has(name) && !body?.overwrite) {
    return json(ctx.res, 409, { detail: `${name} already exists in this project.` });
  }
  const content = body?.content ?? starterNotebook();
  if (!Array.isArray(content.cells)) return json(ctx.res, 422, { detail: "not a notebook" });
  notebookStore.set(name, {
    content,
    size: JSON.stringify(content).length,
    modified: Date.now() / 1000,
  });
  json(ctx.res, 200, { name, content });
});

route("GET", "/api/notebooks/*name", (ctx) => {
  const name = notebookName(ctx.params.name);
  const entry = name === null ? undefined : notebookStore.get(name);
  if (!entry) return json(ctx.res, 404, { detail: "no such notebook" });
  json(ctx.res, 200, { name, content: entry.content });
});

route("PUT", "/api/notebooks/*name", async (ctx) => {
  const name = notebookName(ctx.params.name);
  if (name === null) return json(ctx.res, 422, { detail: "unusable notebook name" });
  const body = await ctx.body();
  const content = body?.content;
  if (!content || !Array.isArray(content.cells)) {
    return json(ctx.res, 422, { detail: "That is not a valid notebook." });
  }
  const size = JSON.stringify(content).length;
  const modified = Date.now() / 1000;
  notebookStore.set(name, { content, size, modified });
  json(ctx.res, 200, { name, size, modified, example: name.startsWith("examples/") });
});

route("DELETE", "/api/notebooks/*name", (ctx) => {
  const name = notebookName(ctx.params.name);
  if (name === null || !notebookStore.has(name)) {
    return json(ctx.res, 404, { detail: "no such notebook" });
  }
  notebookStore.delete(name);
  if (name === EXAMPLE_NAME) notebooksSeeded.deleted = true;
  json(ctx.res, 200, { deleted: name });
});

const kernelStore = new Map();
const MOCK_MAX_KERNELS = 2;
let kernelSeq = 0;

function kernelDescribe(kernel) {
  return {
    id: kernel.id,
    name: "simnibs",
    displayName: "SimNIBS + TI-Toolbox",
    language: "python",
    cwd: "/mnt/000",
    state: kernel.state,
    startedAt: kernel.startedAt,
    lastUsed: kernel.lastUsed,
  };
}

route("GET", "/api/kernels", (ctx) =>
  json(ctx.res, 200, {
    kernels: [...kernelStore.values()].map(kernelDescribe),
    max: MOCK_MAX_KERNELS,
    idleTimeoutSeconds: 1800,
  })
);

route("POST", "/api/kernels", async (ctx) => {
  const body = await ctx.body();
  if (body?.kernelName === "missing") {
    return json(ctx.res, 501, {
      detail: {
        code: "no-kernelspec",
        message: "No kernel named 'missing' is installed in this container.",
      },
    });
  }
  if (kernelStore.size >= MOCK_MAX_KERNELS) {
    return json(ctx.res, 429, {
      detail: {
        code: "too-many-kernels",
        message: `${MOCK_MAX_KERNELS} kernels are already running, which is the limit for one TI-Toolbox container.`,
      },
    });
  }
  kernelSeq += 1;
  const kernel = {
    id: `k${kernelSeq}`,
    state: "idle",
    startedAt: Date.now() / 1000,
    lastUsed: Date.now() / 1000,
    executionCount: 0,
    sockets: new Set(),
    running: null,
  };
  kernelStore.set(kernel.id, kernel);
  json(ctx.res, 200, kernelDescribe(kernel));
});

route("DELETE", "/api/kernels/:id", (ctx) => {
  const kernel = kernelStore.get(ctx.params.id);
  if (!kernel) {
    return json(ctx.res, 404, { detail: { code: "no-such-kernel", message: "no such kernel" } });
  }
  kernelStore.delete(kernel.id);
  kernelBroadcast(kernel, { type: "status", state: "dead" });
  for (const ws of kernel.sockets) ws.close();
  json(ctx.res, 200, { id: kernel.id, state: "dead" });
});

route("POST", "/api/kernels/:id/interrupt", (ctx) => {
  const kernel = kernelStore.get(ctx.params.id);
  if (!kernel) {
    return json(ctx.res, 404, { detail: { code: "no-such-kernel", message: "no such kernel" } });
  }
  kernelInterrupt(kernel);
  json(ctx.res, 200, { id: kernel.id, interrupted: true });
});

route("POST", "/api/kernels/:id/restart", (ctx) => {
  const kernel = kernelStore.get(ctx.params.id);
  if (!kernel) {
    return json(ctx.res, 404, { detail: { code: "no-such-kernel", message: "no such kernel" } });
  }
  kernelInterrupt(kernel);
  kernel.executionCount = 0;
  kernel.state = "idle";
  kernelBroadcast(kernel, { type: "status", state: "starting" });
  kernelBroadcast(kernel, { type: "ready", kernel: kernelDescribe(kernel) });
  json(ctx.res, 200, kernelDescribe(kernel));
});

/**
 * The fake kernel's completer. A fixed vocabulary, matched on the token before
 * the cursor — enough to prove the ROUND TRIP (request out, matches back,
 * kernel-owned replacement range applied) without pretending to be jedi.
 */
const MOCK_NAMES = [
  "get_path_manager",
  "get_project",
  "catalog.subject_ids",
  "catalog.subject_detail",
  "catalog.list_simulations",
  "run_simulation",
  "SimulationConfig",
  "Analyzer",
  "print",
];

function kernelComplete(kernel, reqId, code, cursorPos) {
  const before = code.slice(0, cursorPos);
  const token = (/[\w.]*$/.exec(before) ?? [""])[0];
  const matches = token === "" ? [] : MOCK_NAMES.filter((name) => name.startsWith(token));
  kernelBroadcast(kernel, {
    type: "complete",
    reqId,
    matches,
    cursorStart: cursorPos - token.length,
    cursorEnd: cursorPos,
    metadata: {
      _jupyter_types_experimental: matches.map((text) => ({
        text,
        type: /^[A-Z]/.test(text.split(".").pop()) ? "class" : "function",
      })),
    },
  });
}

function kernelInspect(kernel, reqId, code, cursorPos) {
  const before = code.slice(0, cursorPos);
  const token = (/[\w.]*$/.exec(before) ?? [""])[0];
  const found = MOCK_NAMES.includes(token);
  // IPython's own `?` format: ANSI-coloured field labels, a signature that may
  // wrap, and a docstring that runs to the next label. The renderer parses
  // exactly this, so the mock emits exactly this rather than a tidier shape it
  // would never see in the container.
  const label = (name) => `\u001b[31m${name}:\u001b[39m`;
  const text = found
    ? [
        `${label("Signature")} ${token}(pm: 'PathManager') -> 'list[str]'`,
        `${label("Docstring")}`,
        "The mock kernel's answer for this name.",
        "",
        "A second paragraph the tooltip must not show.",
        `${label("File")}      /ti-toolbox/tit/mock.py`,
        `${label("Type")}      function`,
      ].join("\n")
    : "";
  kernelBroadcast(kernel, { type: "inspect", reqId, found, text });
}

function kernelBroadcast(kernel, event) {
  for (const ws of kernel.sockets) {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(event));
  }
}

function kernelInterrupt(kernel) {
  const run = kernel.running;
  if (!run) return;
  clearTimeout(run.timer);
  kernel.running = null;
  kernelBroadcast(kernel, {
    type: "output",
    reqId: run.reqId,
    output: {
      output_type: "error",
      ename: "KeyboardInterrupt",
      evalue: "",
      traceback: ["KeyboardInterrupt"],
    },
  });
  kernel.state = "idle";
  kernelBroadcast(kernel, { type: "status", state: "idle" });
  kernelBroadcast(kernel, {
    type: "reply",
    reqId: run.reqId,
    status: "error",
    executionCount: run.count,
  });
}

/** The whole of the fake language: print, an arithmetic expression, or a NameError. */
function kernelEvaluate(code) {
  const source = code.trim();
  const printed = /^print\((.*)\)$/s.exec(source);
  if (printed) {
    const argument = printed[1].trim();
    const literal = /^(['"])(.*)\1$/s.exec(argument);
    const text = literal ? literal[2] : evalArithmetic(argument);
    return [{ output_type: "stream", name: "stdout", text: `${text}\n` }];
  }
  if (source === "" || source.startsWith("#")) return [];
  const value = evalArithmetic(source);
  if (value === null) {
    const symbol = source.split(/\W/)[0] || source;
    return [
      {
        output_type: "error",
        ename: "NameError",
        evalue: `name '${symbol}' is not defined`,
        // Coloured the way IPython colours it, so the ported ANSI parser is
        // exercised by the mock as well as by a real kernel.
        traceback: [`\u001b[0;31mNameError \u001b[0m: name '${symbol}' is not defined`],
      },
    ];
  }
  return [
    {
      output_type: "execute_result",
      data: { "text/plain": String(value) },
      metadata: {},
      execution_count: null,
    },
  ];
}

/** Integer arithmetic only, over digits and + - * / ( ) -- a parser, never eval. */
function evalArithmetic(expression) {
  const source = expression.trim();
  if (!/^[\d+\-*/() .]+$/.test(source) || source === "") return null;
  let index = 0;
  const peek = () => source[index];
  const skip = () => {
    while (peek() === " ") index += 1;
  };
  function primary() {
    skip();
    if (peek() === "(") {
      index += 1;
      const value = sum();
      skip();
      index += 1;
      return value;
    }
    const start = index;
    while (index < source.length && /[\d.]/.test(source[index])) index += 1;
    return start === index ? NaN : Number(source.slice(start, index));
  }
  function product() {
    let value = primary();
    for (;;) {
      skip();
      const op = peek();
      if (op !== "*" && op !== "/") return value;
      index += 1;
      const right = primary();
      value = op === "*" ? value * right : value / right;
    }
  }
  function sum() {
    let value = product();
    for (;;) {
      skip();
      const op = peek();
      if (op !== "+" && op !== "-") return value;
      index += 1;
      const right = product();
      value = op === "+" ? value + right : value - right;
    }
  }
  const result = sum();
  return Number.isFinite(result) ? result : null;
}

function kernelExecute(kernel, reqId, code) {
  kernel.lastUsed = Date.now() / 1000;
  kernel.executionCount += 1;
  const count = kernel.executionCount;
  kernel.state = "busy";
  kernelBroadcast(kernel, { type: "status", state: "busy" });
  kernelBroadcast(kernel, { type: "input", reqId, executionCount: count });
  const outputs = kernelEvaluate(code);
  const errored = outputs.some((o) => o.output_type === "error");
  // A sleep is the one thing worth simulating: the e2e suite has to be able to
  // catch a cell mid-run in order to interrupt it.
  const sleeping = /\bsleep\(|\bwhile True\b/.test(code);
  const finish = () => {
    kernel.running = null;
    for (const output of outputs) kernelBroadcast(kernel, { type: "output", reqId, output });
    kernel.state = "idle";
    kernelBroadcast(kernel, { type: "status", state: "idle" });
    kernelBroadcast(kernel, {
      type: "reply",
      reqId,
      status: errored ? "error" : "ok",
      executionCount: count,
    });
  };
  kernel.running = { reqId, count, timer: setTimeout(finish, sleeping ? 30_000 : 0) };
}

route("POST", "/api/__mock/reset", (ctx) => {
  let cleared = 0;
  for (const job of jobRegistry.values()) {
    clearJobTimers(job);
    if (!TERMINAL.has(job.status.state)) cleared++;
  }
  jobRegistry.clear();
  for (const client of wsJobClients) client.subs.clear();
  groupParallelLimit.clear();
  notebookStore.clear();
  notebooksSeeded.deleted = false;
  for (const kernel of kernelStore.values()) {
    if (kernel.running) clearTimeout(kernel.running.timer);
    for (const ws of kernel.sockets) ws.close();
  }
  kernelStore.clear();
  json(ctx.res, 200, { jobs_cleared: cleared });
});
// Mock-only: publish one `tetravox.updated` event to every /ws/tetravox client, so the e2e
// suite can assert the toast the real background updater triggers (A3) without waiting 24 h or
// installing anything.
route("POST", "/api/__mock/tetravox-updated", async (ctx) => {
  const body = await ctx.body();
  const event = {
    type: "tetravox.updated",
    version: body?.version ?? "0.4.0",
    protocol: body?.protocol ?? 2,
    message: body?.message ?? `Tetravox ${body?.version ?? "0.4.0"} installed and active — reload the viewer to use it`,
  };
  tvxLastOutcome = { action: "installed", message: event.message, version: event.version, protocol: event.protocol, at: Date.now() / 1000 };
  for (const ws of wsTetravoxClients) if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(event));
  json(ctx.res, 200, { delivered: wsTetravoxClients.size });
});
// Mock-only: switch the project the overview routes describe (3 or 30 subjects). See
// `makeLargeOverview` above for why two sizes exist.
route("POST", "/api/__mock/project", async (ctx) => {
  const body = await ctx.body();
  const n = Number(body?.subjects ?? 3);
  if (!overviewProjects[n]) return json(ctx.res, 422, { detail: "subjects must be 3 or 30" });
  overview = overviewProjects[n];
  json(ctx.res, 200, { subjects: overview.totals.subjects });
});
route("GET", "/api/jobs", (ctx) => {
  const q = ctx.url.searchParams;
  let list = [...jobRegistry.values()].map((j) => j.status);
  if (q.get("state")) list = list.filter((s) => s.state === q.get("state"));
  if (q.get("subject")) list = list.filter((s) => s.subject_ids.includes(q.get("subject")));
  if (q.get("kind")) list = list.filter((s) => s.kind === q.get("kind"));
  list = list.slice().sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  const limit = Number(q.get("limit"));
  if (limit) list = list.slice(0, limit);
  json(ctx.res, 200, list);
});
route("POST", "/api/jobs", async (ctx) => {
  const body = await ctx.body();
  const missing = schemaRequiredErrors(body.kind, body.config);
  if (missing.length) {
    return json(ctx.res, 422, { detail: `config is not a valid ${SCHEMA_DEF_FOR_KIND[body.kind]} for kind ${JSON.stringify(body.kind)}: ${missing.join(", ")}` });
  }
  const job = createJob({ kind: body.kind, config: body.config, subject_ids: body.subject_ids ?? [], after: body.after ?? [], tags: body.tags ?? [], overwrite: !!body.overwrite });
  json(ctx.res, 201, job.status);
});
// Mirrors tit.jobs.plans.plan_preprocessing's G1..G6 stage DAG (own dependency comments there):
// each stage is only planned when its PreprocessConfig flag is set, every stage job's config is
// the group's config with every step flag but its own forced False, and a subject with any stage
// job gets its consolidated report as an attachment of its last stage job, never as a job.
const PRE_STAGE_FLAGS = ["convert_dicom", "create_m2m", "run_fastsurfer", "run_tissue_analysis", "run_qsiprep", "run_qsirecon", "extract_dti"];
function planPreprocessingStages(config) {
  const cfg = config && typeof config === "object" ? config : {};
  const stages = [];
  const has = (tag) => stages.some((s) => s.tag === tag);
  if (cfg.convert_dicom) stages.push({ tag: "G1", flags: { convert_dicom: true }, after: [] });
  if (cfg.create_m2m) stages.push({ tag: "G2a", flags: { create_m2m: true }, after: has("G1") ? ["G1"] : [] });
  if (cfg.run_fastsurfer) {
    stages.push({ tag: "G2b", flags: { run_fastsurfer: true }, after: has("G1") ? ["G1"] : [] });
  }
  if (cfg.run_tissue_analysis) stages.push({ tag: "G3", flags: { run_tissue_analysis: true }, after: has("G2a") ? ["G2a"] : [] });
  if (cfg.run_qsiprep) stages.push({ tag: "G4", flags: { run_qsiprep: true }, after: has("G1") ? ["G1"] : [] });
  if (cfg.run_qsirecon) stages.push({ tag: "G5", flags: { run_qsirecon: true }, after: has("G4") ? ["G4"] : [] });
  if (cfg.extract_dti) stages.push({ tag: "G6", flags: { extract_dti: true }, after: [...(has("G5") ? ["G5"] : []), ...(has("G2a") ? ["G2a"] : [])] });
  return stages;
}
// Every kind `JobGroupRequest.kind` accepts (contracts/openapi.yaml, R3). `pre` expands into
// the per-subject stage DAG above; the rest are one job per (subject, config) entry.
const GROUP_KINDS = ["pre", "sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex"];

route("POST", "/api/jobs/groups", async (ctx) => {
  const body = await ctx.body();
  if (!GROUP_KINDS.includes(body.kind)) {
    return json(ctx.res, 422, { detail: `kind must be one of ${GROUP_KINDS.join(", ")} for a job group, got ${JSON.stringify(body.kind)}` });
  }
  const subjectIds = body.subject_ids ?? [];
  const groupId = `group_${randomBytes(6).toString("hex")}`;
  const parallel = Math.max(1, Number(body.parallel_subjects) || 1);
  groupParallelLimit.set(groupId, parallel);
  const tags = Array.isArray(body.tags) ? body.tags : [];
  const created = [];

  if (body.kind !== "pre") {
    // One job per (subject, config) entry. `subject_configs` is optional; a subject with no entry
    // uses the template `config`. The real server FORCES each generated config's subject_id to its
    // own subject no matter what was sent -- so does this, because the batch e2e asserts exactly
    // that isolation off the submitted job's spec.
    const bySubject = new Map();
    for (const entry of body.subject_configs ?? []) {
      if (!subjectIds.includes(entry.subject_id)) {
        return json(ctx.res, 422, { detail: `subject_configs names subjects not in subject_ids: ${entry.subject_id}` });
      }
      if (!bySubject.has(entry.subject_id)) bySubject.set(entry.subject_id, []);
      bySubject.get(entry.subject_id).push(entry.config);
    }
    for (const subject of subjectIds) {
      for (const entry of bySubject.get(subject) ?? [body.config ?? {}]) {
        const resolved = { ...(entry && typeof entry === "object" ? entry : {}), subject_id: subject };
        // Same required-field gate as POST /api/jobs, applied to the config this group would
        // actually generate (subject_id already forced), mirroring the real server's
        // `plan_per_subject`, which round-trips every generated config through its dataclass.
        const missingEntry = schemaRequiredErrors(body.kind, resolved);
        if (missingEntry.length) {
          return json(ctx.res, 422, { detail: `config is not a valid ${SCHEMA_DEF_FOR_KIND[body.kind]} for kind ${JSON.stringify(body.kind)}: ${missingEntry.join(", ")}` });
        }
        created.push(
          createJob({
            kind: body.kind,
            config: resolved,
            subject_ids: [subject],
            tags: [`group:${groupId}`, ...tags],
            group_id: groupId,
            overwrite: !!body.overwrite,
          }),
        );
      }
    }
    return json(ctx.res, 201, { group_id: groupId, jobs: created.map((j) => j.status) });
  }

  for (const subject of subjectIds) {
    const stages = planPreprocessingStages(body.config);
    const jobIdByTag = new Map();
    const subjectJobs = [];
    for (const stage of stages) {
      const stageConfig = { ...(body.config ?? {}), ...Object.fromEntries(PRE_STAGE_FLAGS.map((f) => [f, false])), ...stage.flags, subject_id: subject };
      const after = stage.after.map((t) => jobIdByTag.get(t)).filter(Boolean);
      const job = createJob({ kind: "pre", config: stageConfig, subject_ids: [subject], after, tags: [`group:${groupId}`, stage.tag], group_id: groupId });
      jobIdByTag.set(stage.tag, job.status.id);
      subjectJobs.push(job);
      created.push(job);
    }
    // No trailing report job: the real server attaches the consolidated subject report to the
    // last stage job of the subject (JobManager._attach_pre_report) instead of scheduling one.
  }
  json(ctx.res, 201, { group_id: groupId, jobs: created.map((j) => j.status) });
});
// ---------------------------------------------------------------------------------- pipelines
// A JS mirror of `tit/pipeline/{document,validate,plan}.py`. It is deliberately a *mirror*, not a
// stub that always says yes: the e2e gate asserts that a 4-node pre -> flex -> sim -> analyzer
// pipeline runs as ONE group whose `after` chain equals the edges, which only means anything if
// this planner builds the same DAG the server does. `desktop/tests/unit/pipeline-graph.test.ts`
// and `tests/test_pipeline_graph.py` assert the same refusal table on both sides.
const PIPE_PORTS = {
  subjects: { inputs: [], outputs: ["subjects"], required: [] },
  pre: { inputs: ["subjects"], outputs: ["subjects"], required: ["subjects"] },
  leadfield: { inputs: ["subjects"], outputs: ["subjects", "leadfield"], required: ["subjects"] },
  flex: { inputs: ["subjects", "roi"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  ex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  mex: { inputs: ["subjects", "roi", "leadfield"], outputs: ["subjects", "montages", "roi"], required: ["subjects"] },
  sim: { inputs: ["subjects", "montages"], outputs: ["subjects", "simulation"], required: ["subjects"] },
  analyzer: { inputs: ["subjects", "simulation", "roi"], outputs: ["subjects"], required: ["subjects"] },
  source: { inputs: ["subjects"], outputs: ["subjects"], required: ["subjects"] },
  stats: { inputs: ["subjects"], outputs: [], required: ["subjects"] },
};
const PIPE_KINDS = ["subjects", "pre", "leadfield", "flex", "ex", "mex", "sim", "analyzer", "source", "stats"];
// Mirrors `tit.pipeline.validate.KIND_READINESS`: what each kind needs of a subject, and what it
// leaves behind for the nodes after it.
const PIPE_CAPABILITIES = ["raw", "m2m", "leadfield", "simulation"];
const PIPE_CAP_LABEL = { raw: "raw MRI", m2m: "head model", leadfield: "leadfield", simulation: "simulations" };
const PIPE_READINESS = {
  subjects: { requires: [], produces: [] },
  pre: { requires: ["raw"], produces: ["m2m"] },
  leadfield: { requires: ["m2m"], produces: ["leadfield"] },
  flex: { requires: ["m2m"], produces: [] },
  ex: { requires: ["m2m", "leadfield"], produces: [] },
  mex: { requires: ["m2m", "leadfield"], produces: [] },
  sim: { requires: ["m2m"], produces: ["simulation"] },
  analyzer: { requires: ["simulation"], produces: [] },
  source: { requires: ["m2m"], produces: [] },
  stats: { requires: ["simulation"], produces: [] },
};
const PIPE_PORT_TYPES = ["subjects", "montages", "simulation", "roi", "leadfield"];
const PIPE_PORT_LABEL = { subjects: "Subjects", montages: "Montage names", simulation: "Simulation name", roi: "ROI", leadfield: "Leadfield" };
const PIPE_DYNAMIC = new Set(["montages", "leadfield", "simulation"]);
const PIPE_PLACEHOLDER = { montages: ["montages", []], leadfield: ["leadfield_hdf", ""], simulation: ["simulation", ""] };
const pipelineStore = new Map();

function pipeDoc(body) {
  const raw = body && typeof body === "object" && body.pipeline ? body.pipeline : body;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("pipeline document must be a JSON object");
  if ((raw.version ?? 1) !== 1) throw new Error(`unsupported pipeline document version ${JSON.stringify(raw.version)}`);
  if (!Array.isArray(raw.nodes) || (raw.edges !== undefined && !Array.isArray(raw.edges))) throw new Error("`nodes` and `edges` must be arrays");
  const nodes = raw.nodes.map((n) => {
    if (!n || typeof n.id !== "string" || !n.id) throw new Error("each node needs a non-empty string id");
    if (!PIPE_KINDS.includes(n.kind)) throw new Error(`node ${n.id}: unknown kind ${JSON.stringify(n.kind)}`);
    return { id: n.id, kind: n.kind, label: n.label ?? null, config: n.config ?? {}, position: { x: Number(n.position?.x ?? 0), y: Number(n.position?.y ?? 0) } };
  });
  const edges = (raw.edges ?? []).map((e) => {
    if (typeof e?.from !== "string" || typeof e?.to !== "string") throw new Error("each edge needs string `from` and `to` node ids");
    if (!PIPE_PORT_TYPES.includes(e.port)) throw new Error(`edge ${e.from}->${e.to}: unknown port ${JSON.stringify(e.port)}`);
    return { from: e.from, to: e.to, port: e.port };
  });
  return { version: 1, name: typeof raw.name === "string" && raw.name ? raw.name : "pipeline", nodes, edges };
}
const pipeName = (n) => n.label || `${n.kind} (${n.id})`;
const pipeIn = (doc, id) => doc.edges.filter((e) => e.to === id);
const pipeOut = (doc, id) => doc.edges.filter((e) => e.from === id);

function pipeSubjectsOf(config) {
  const list = Array.isArray(config?.subject_ids) ? config.subject_ids.filter((s) => String(s).trim()) : [];
  if (list.length) return list.map(String);
  const one = String(config?.subject_id ?? "").trim();
  return one ? [one] : [];
}
function pipeSatisfied(port, config) {
  if (port === "subjects") return pipeSubjectsOf(config).length > 0;
  if (port === "montages") return Array.isArray(config?.montages) && config.montages.length > 0;
  if (port === "simulation") return !!String(config?.simulation ?? "").trim();
  if (port === "leadfield") return !!String(config?.leadfield_hdf ?? "").trim();
  if (port === "roi") return ["roi", "roi_name", "roi_names", "region", "atlas", "center"].some((k) => config?.[k] !== undefined && config[k] !== null && config[k] !== "" && !(Array.isArray(config[k]) && !config[k].length));
  return false;
}
/** Mirrors `tit.pipeline.validate.readiness_from_overview` — read from the live mock overview. */
function pipeReadiness() {
  const out = {};
  for (const row of overview.subjects ?? []) {
    const caps = new Set();
    if (row.raw === "present") caps.add("raw");
    if (row.m2m === "present") caps.add("m2m");
    if (row.leadfield === "present" || row.leadfield === "partial") caps.add("leadfield");
    if ((row.counts?.simulations ?? 0) > 0) caps.add("simulation");
    out[row.id] = caps;
  }
  return out;
}

/** Mirrors `capabilities_at`: the project's facts at a cohort, plus what each node on the way makes. */
function pipeCapabilities(doc, id, readiness, seen = new Set()) {
  const node = doc.nodes.find((n) => n.id === id);
  if (!node || seen.has(id)) return {};
  seen.add(id);
  const upstream = pipeIn(doc, id).find((e) => e.port === "subjects")?.from;
  if (upstream === undefined) {
    const out = {};
    for (const sid of pipeSubjectsOf(node.config)) out[sid] = new Set(readiness[sid] ?? []);
    return out;
  }
  const inherited = pipeCapabilities(doc, upstream, readiness, seen);
  const from = doc.nodes.find((n) => n.id === upstream);
  const produced = PIPE_READINESS[from?.kind]?.produces ?? [];
  const out = {};
  for (const [sid, caps] of Object.entries(inherited)) out[sid] = new Set([...caps, ...produced]);
  return out;
}

/** `[[capability, [subjects missing it]]]` for a kind, in table order. */
function pipeUnmet(kind, caps) {
  const out = [];
  for (const capability of PIPE_READINESS[kind]?.requires ?? []) {
    const missing = Object.entries(caps)
      .filter(([, have]) => !have.has(capability))
      .map(([sid]) => sid)
      .sort();
    if (missing.length) out.push([capability, missing]);
  }
  return out;
}

function pipeTopo(doc) {
  const ids = doc.nodes.map((n) => n.id);
  const indeg = Object.fromEntries(ids.map((i) => [i, 0]));
  for (const e of doc.edges) if (indeg[e.to] !== undefined && indeg[e.from] !== undefined) indeg[e.to] += 1;
  const ready = ids.filter((i) => indeg[i] === 0);
  const order = [];
  while (ready.length) {
    const cur = ready.shift();
    order.push(cur);
    for (const e of pipeOut(doc, cur)) {
      if (indeg[e.to] === undefined) continue;
      indeg[e.to] -= 1;
      if (indeg[e.to] === 0) {
        ready.push(e.to);
        ready.sort((a, b) => ids.indexOf(a) - ids.indexOf(b));
      }
    }
  }
  return order.length === ids.length ? order : null;
}
function pipeValidate(doc) {
  const issues = [];
  const byId = new Map(doc.nodes.map((n) => [n.id, n]));
  if (!doc.nodes.length) issues.push({ level: "error", message: "a pipeline needs at least one node", code: "empty" });
  const bound = new Set();
  for (const e of doc.edges) {
    const src = byId.get(e.from);
    const dst = byId.get(e.to);
    if (!src || !dst) { issues.push({ level: "error", message: "edge refers to a node that is not on the canvas", edge: e, code: "edge_unknown_node" }); continue; }
    if (e.from === e.to) { issues.push({ level: "error", message: "a node cannot feed itself", edge: e, code: "self_edge" }); continue; }
    if (!PIPE_PORTS[src.kind].outputs.includes(e.port)) { issues.push({ level: "error", message: `${pipeName(src)} does not produce ${PIPE_PORT_LABEL[e.port]}`, edge: e, code: "bad_output", port: e.port }); continue; }
    if (!PIPE_PORTS[dst.kind].inputs.includes(e.port)) { issues.push({ level: "error", message: `${pipeName(dst)} does not take ${PIPE_PORT_LABEL[e.port]}`, edge: e, code: "bad_input", port: e.port }); continue; }
    const key = `${e.to} ${e.port}`;
    if (bound.has(key)) { issues.push({ level: "error", message: `${pipeName(dst)} has ${PIPE_PORT_LABEL[e.port]} wired twice`, edge: e, code: "double_bound", port: e.port }); continue; }
    bound.add(key);
  }
  let order = pipeTopo(doc);
  if (order === null) { issues.push({ level: "error", message: "the pipeline has a cycle", code: "cycle" }); order = []; }
  for (const node of doc.nodes) {
    for (const port of PIPE_PORTS[node.kind].required) {
      if (bound.has(`${node.id} ${port}`)) continue;
      if (pipeSatisfied(port, node.config)) continue;
      issues.push({ level: "error", message: `${pipeName(node)} needs ${PIPE_PORT_LABEL[port]}: wire it from an upstream node or set it in the node's form`, node_id: node.id, code: "missing_input", port });
    }
    if (!node.config || !Object.keys(node.config).length) issues.push({ level: "warning", message: `${pipeName(node)} has no configuration yet`, node_id: node.id, code: "unconfigured" });
  }
  const readiness = pipeReadiness();
  for (const node of doc.nodes) {
    const caps = pipeCapabilities(doc, node.id, readiness);
    if (!Object.keys(caps).length) continue;
    for (const [capability, missing] of pipeUnmet(node.kind, caps)) {
      issues.push({
        level: "error",
        message: `${pipeName(node)}: ${missing.join(", ")} ${missing.length === 1 ? "has" : "have"} no ${PIPE_CAP_LABEL[capability]}`,
        node_id: node.id,
        code: "not_ready",
        port: "subjects",
      });
    }
  }

  if (doc.nodes.length > 1) {
    const wired = new Set(doc.edges.flatMap((e) => [e.from, e.to]));
    for (const node of doc.nodes) if (!wired.has(node.id)) issues.push({ level: "warning", message: `${pipeName(node)} is not connected to anything; it will run on its own`, node_id: node.id, code: "unconnected" });
  }
  return { ok: !issues.some((i) => i.level === "error"), issues, order };
}
function pipeSimNames(config) {
  return (config?.montages ?? []).map((m) => String(m?.name ?? "").trim()).filter(Boolean);
}
function pipeIsDynamic(doc, edge) {
  if (!PIPE_DYNAMIC.has(edge.port)) return false;
  if (edge.port !== "simulation") return true;
  return !pipeSimNames(doc.nodes.find((n) => n.id === edge.from)?.config).length;
}
function pipeSubjects(doc, id, cache) {
  if (cache.has(id)) return cache.get(id);
  const node = doc.nodes.find((n) => n.id === id);
  let subjects = [];
  for (const e of pipeIn(doc, id)) if (e.port === "subjects") { subjects = pipeSubjects(doc, e.from, cache); break; }
  if (!subjects.length) subjects = pipeSubjectsOf(node?.config);
  cache.set(id, subjects);
  return subjects;
}
function pipePlan(doc) {
  const { ok, order } = pipeValidate(doc);
  if (!ok) return null;
  const cache = new Map();
  const labels = new Map();
  const planned = [];
  for (const id of order) {
    const node = doc.nodes.find((n) => n.id === id);
    // The cohort runs nothing: it names who the graph is about and hands them on over the wire.
    if (node.kind === "subjects") {
      labels.set(id, []);
      continue;
    }
    const incoming = pipeIn(doc, id);
    const upstream = [];
    for (const e of incoming) if (!pipeIsDynamic(doc, e)) upstream.push(...(labels.get(e.from) ?? []));
    const config = { ...node.config };
    for (const e of incoming) {
      if (!pipeIsDynamic(doc, e)) continue;
      const [key, empty] = PIPE_PLACEHOLDER[e.port];
      if (config[key] === undefined) config[key] = empty;
      const label = `${id}:resolve:${e.port}`;
      planned.push({ label, kind: "tools", config: { module: "tit.tools.pipeline_resolve", args: ["--pipeline", doc.name, "--node", id, "--port", e.port] }, subject_ids: pipeSubjects(doc, e.from, cache), after: [...(labels.get(e.from) ?? [])], tags: [`pipeline:${doc.name}`, `node:${id}`, "resolve"] });
      upstream.push(label);
    }
    const after = [...new Set(upstream)].sort();
    const subjects = pipeSubjects(doc, id, cache);
    const simulations = incoming.filter((e) => e.port === "simulation").flatMap((e) => pipeSimNames(doc.nodes.find((n) => n.id === e.from)?.config));
    const mine = [];
    if (node.kind === "stats") {
      mine.push({ label: `${id}:0`, kind: node.kind, config: { ...config, subject_ids: subjects }, subject_ids: subjects, after, tags: [`pipeline:${doc.name}`, `node:${id}`] });
    } else {
      let index = 0;
      for (const subject of subjects) {
        for (const simulation of simulations.length ? simulations : [null]) {
          const entry = { ...config, subject_id: subject };
          if (node.kind === "pre") entry.subject_ids = [subject];
          else delete entry.subject_ids;
          if (simulation !== null) entry.simulation = simulation;
          mine.push({ label: `${id}:${index++}`, kind: node.kind, config: entry, subject_ids: [subject], after, tags: [`pipeline:${doc.name}`, `node:${id}`] });
        }
      }
    }
    planned.push(...mine);
    labels.set(id, mine.map((j) => j.label));
  }
  return planned;
}

route("GET", "/api/pipelines/kinds", (ctx) =>
  json(ctx.res, 200, {
    port_types: PIPE_PORT_TYPES,
    capabilities: PIPE_CAPABILITIES.map((capability) => ({ capability, label: PIPE_CAP_LABEL[capability] })),
    kinds: PIPE_KINDS.map((kind) => ({
      kind,
      inputs: PIPE_PORTS[kind].inputs,
      outputs: PIPE_PORTS[kind].outputs,
      required: PIPE_PORTS[kind].required,
      requires: PIPE_READINESS[kind].requires,
      produces: PIPE_READINESS[kind].produces,
    })),
  }),
);
route("GET", "/api/pipelines", (ctx) => json(ctx.res, 200, [...pipelineStore.entries()].map(([name, entry]) => ({ name, modified_at: entry.modified_at, size: JSON.stringify(entry.doc).length, nodes: (entry.doc.nodes ?? []).length, edges: (entry.doc.edges ?? []).length })).sort((a, b) => a.name.localeCompare(b.name))));
route("POST", "/api/pipelines/validate", async (ctx) => {
  let doc;
  try { doc = pipeDoc(await ctx.body()); } catch (err) { return json(ctx.res, 422, { detail: String(err.message ?? err) }); }
  const result = pipeValidate(doc);
  return json(ctx.res, 200, { ...result, jobs: (pipePlan(doc) ?? []).map(({ label, kind, subject_ids, after, tags }) => ({ label, kind, subject_ids, after, tags })) });
});
route("POST", "/api/pipelines/run", async (ctx) => {
  const body = await ctx.body();
  let doc;
  try { doc = pipeDoc(body); } catch (err) { return json(ctx.res, 422, { detail: String(err.message ?? err) }); }
  const result = pipeValidate(doc);
  if (!result.ok) return json(ctx.res, 422, { detail: { message: "pipeline does not validate", issues: result.issues.filter((i) => i.level === "error") } });
  const planned = pipePlan(doc);
  const groupId = `group_${randomBytes(6).toString("hex")}`;
  groupParallelLimit.set(groupId, Math.max(1, Number(body.parallel_subjects) || 1));
  const idByLabel = new Map();
  const created = [];
  for (const p of planned) {
    const job = createJob({ kind: p.kind, config: p.config, subject_ids: p.subject_ids, after: p.after.map((l) => idByLabel.get(l)).filter(Boolean), tags: [`group:${groupId}`, ...p.tags], group_id: groupId });
    idByLabel.set(p.label, job.status.id);
    created.push(job);
  }
  return json(ctx.res, 201, { group_id: groupId, pipeline: doc.name, jobs: created.map((j) => j.status) });
});
route("POST", "/api/pipelines/export", async (ctx) => {
  if ((ctx.url.searchParams.get("format") ?? "ipynb") !== "ipynb") return json(ctx.res, 422, { detail: "only format=ipynb is supported" });
  let doc;
  try { doc = pipeDoc(await ctx.body()); } catch (err) { return json(ctx.res, 422, { detail: String(err.message ?? err) }); }
  const order = pipeTopo(doc) ?? doc.nodes.map((n) => n.id);
  const mermaid = ["graph LR", ...doc.nodes.map((n) => `  ${n.id}["${pipeName(n)}"]`), ...doc.edges.map((e) => `  ${e.from} -->|${e.port}| ${e.to}`)].join("\n");
  const cells = [
    { cell_type: "markdown", id: "cell-0", metadata: {}, source: `# ${doc.name}\n\n\`\`\`mermaid\n${mermaid}\n\`\`\`\n` },
    { cell_type: "code", id: "cell-1", metadata: {}, execution_count: null, outputs: [], source: "from tit import get_path_manager\n" },
  ];
  order.forEach((id, i) => {
    const node = doc.nodes.find((n) => n.id === id);
    cells.push({ cell_type: "markdown", id: `cell-m${i}`, metadata: {}, source: `## ${pipeName(node)}` });
    cells.push({ cell_type: "code", id: `cell-c${i}`, metadata: {}, execution_count: null, outputs: [], source: `${node.id}_subjects = ${JSON.stringify(pipeSubjectsOf(node.config))}\n` });
  });
  const notebook = { cells, metadata: { kernelspec: { display_name: "Python 3", language: "python", name: "python3" }, language_info: { name: "python" }, ti_toolbox: { pipeline: doc } }, nbformat: 4, nbformat_minor: 5 };
  ctx.res.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
  ctx.res.end(JSON.stringify(notebook, null, 1));
});
const PIPE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$/;
route("GET", "/api/pipelines/:name", (ctx) => {
  if (!PIPE_NAME_RE.test(ctx.params.name)) return json(ctx.res, 422, { detail: "illegal pipeline name" });
  const entry = pipelineStore.get(ctx.params.name);
  if (!entry) return json(ctx.res, 404, { detail: `no saved pipeline named ${JSON.stringify(ctx.params.name)}` });
  return json(ctx.res, 200, entry.doc);
});
route("PUT", "/api/pipelines/:name", async (ctx) => {
  if (!PIPE_NAME_RE.test(ctx.params.name)) return json(ctx.res, 422, { detail: "illegal pipeline name" });
  let doc;
  try { doc = pipeDoc(await ctx.body()); } catch (err) { return json(ctx.res, 422, { detail: String(err.message ?? err) }); }
  doc.name = ctx.params.name;
  pipelineStore.set(ctx.params.name, { doc, modified_at: Date.now() / 1000 });
  return json(ctx.res, 200, { name: ctx.params.name, saved: true });
});
route("DELETE", "/api/pipelines/:name", (ctx) => {
  if (!PIPE_NAME_RE.test(ctx.params.name)) return json(ctx.res, 422, { detail: "illegal pipeline name" });
  if (!pipelineStore.delete(ctx.params.name)) return json(ctx.res, 404, { detail: "no such pipeline" });
  ctx.res.writeHead(204);
  ctx.res.end();
});

route("GET", "/api/jobs/:id", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  json(ctx.res, 200, jobToDetail(job));
});
route("DELETE", "/api/jobs/:id", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  if (!TERMINAL.has(job.status.state)) cancelJob(job); // mock convenience: cancel-then-forget
  jobRegistry.delete(ctx.params.id);
  for (const client of wsJobClients) client.subs.delete(ctx.params.id);
  noContent(ctx.res);
});
route("GET", "/api/jobs/:id/events", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  const sinceParam = ctx.url.searchParams.get("since");
  const since = sinceParam === null ? -1 : Number(sinceParam);
  json(ctx.res, 200, job.events.filter((e) => e.seq > since));
});
route("GET", "/api/jobs/:id/log", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  const lines = job.events.filter((e) => e.type === "log").map((e) => `${e.level.toUpperCase()} ${e.logger} ${e.msg}`);
  const tail = Number(ctx.url.searchParams.get("tail")) || undefined;
  text(ctx.res, 200, tailLines(lines.join("\n"), tail) || "");
});
route("POST", "/api/jobs/:id/cancel", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  json(ctx.res, 200, cancelJob(job));
});
route("POST", "/api/jobs/:id/rerun", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  const rerun = createJob({ kind: job.spec.kind, config: job.spec.config, subject_ids: job.spec.subject_ids, tags: job.spec.tags, overwrite: job.spec.overwrite });
  json(ctx.res, 201, rerun.status);
});
route("POST", "/api/jobs/:id/force", (ctx) => {
  const job = jobRegistry.get(ctx.params.id);
  if (!job) return json(ctx.res, 404, { detail: "unknown job" });
  json(ctx.res, 200, forceJob(job));
});

// --- viewers (v1) ---
// D3 (docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)): the external Freeview/Gmsh launch routes
// (POST /api/viewers/freeview, POST /api/viewers/gmsh) are removed -- there is no X11 in this
// runtime; viewing is the Tetravox embed at /tetravox/ (served above), fed by GET
// /api/files/raw/{path} and this route's `view` (a real Tetravox ViewSpec v2 document). `scene` is
// the same document with host paths -- what POST /api/view/open writes to disk for export.
route("GET", "/api/view/:kind", (ctx) => json(ctx.res, 200, buildViewSpec(ctx.params.kind, ctx.url.searchParams)));
// POST /api/view/open. The mock writes no file (it has no project on disk) but answers the same
// shape, including the two path languages and a scene whose dataset paths are *host* paths --
// which is what the e2e's "Open calls the launch bridge with the file the server just wrote"
// assertion needs, and the one thing a URL-shaped mock answer would have hidden.
const MOCK_HOST_ROOT = "/Users/mock/datasets/000";
route("POST", "/api/view/open", async (ctx) => {
  const body = (await ctx.body()) ?? {};
  const kind = String(body.kind ?? "");
  if (!["subject", "simulation", "analysis", "group", "custom"].includes(kind)) {
    return json(ctx.res, 422, { detail: "kind must be one of analysis, custom, group, simulation, subject" });
  }
  const params = new URLSearchParams();
  for (const key of ["subject", "simulation", "space", "field", "analysis", "atlas", "roi", "path"]) {
    if (body[key] !== undefined && body[key] !== null && body[key] !== "") params.set(key, String(body[key]));
  }
  const spec = buildViewSpec(kind, params);
  const localise = (u) =>
    typeof u === "string" && u.startsWith("/api/files/raw/") ? "/" + decodeURIComponent(u.slice("/api/files/raw/".length)) : u;
  // Two addressings of one resolution, as tit/server/routes/viewers.py::view_open answers: `view`
  // keeps the /api/files/raw URLs the embed fetches through this origin, `scene` re-roots them
  // onto the host for the file that is written. Cloned from the same `spec.scene`, never rebuilt.
  const view = JSON.parse(JSON.stringify(spec.scene ?? {}));
  const scene = JSON.parse(JSON.stringify(spec.scene ?? {}));
  for (const dataset of scene.datasets ?? []) {
    for (const key of ["path", "absPath"]) if (dataset[key]) dataset[key] = localise(dataset[key]);
    for (const sidecar of Object.values(dataset.sidecars ?? {})) {
      for (const key of ["path", "absPath"]) if (sidecar[key]) sidecar[key] = localise(sidecar[key]);
    }
  }
  // VM2: when the client sends `files`, that list *is* the scene -- these datasets, this order.
  // A deliberate mirror of tit/viewspec.py::_layers_from_files: a path the view type already
  // produced keeps that view type's layer settings, and only an added path is described from
  // scratch. `dry_run` writes nothing (the mock writes nothing either way; the flag is echoed so
  // the client and the spec can tell the two calls apart).
  if (Array.isArray(body.files)) {
    const byPath = new Map((spec.layers ?? []).map((l) => [l.path, l]));
    const chosen = [];
    const seen = new Set();
    for (const raw of body.files) {
      if (typeof raw !== "string" || seen.has(raw) || raw.startsWith("/etc/")) continue;
      seen.add(raw);
      chosen.push(byPath.get(raw) ?? defaultLayerForPath(raw));
    }
    if (chosen.length === 0) return json(ctx.res, 404, { detail: "The server built no scene for this selection" });
    const rebuilt = sceneFor(spec.space, chosen, null);
    for (const dataset of rebuilt.datasets ?? []) {
      for (const key of ["path", "absPath"]) if (dataset[key]) dataset[key] = localise(dataset[key]);
      for (const sidecar of Object.values(dataset.sidecars ?? {})) {
        for (const key of ["path", "absPath"]) if (sidecar[key]) sidecar[key] = localise(sidecar[key]);
      }
    }
    const rebuiltUrls = sceneFor(spec.space, chosen, null);
    scene.datasets = rebuilt.datasets;
    scene.layers = rebuilt.layers;
    scene.activeLayerId = rebuilt.activeLayerId;
    scene.layout = rebuilt.layout;
    view.datasets = rebuiltUrls.datasets;
    view.layers = rebuiltUrls.layers;
    view.activeLayerId = rebuiltUrls.activeLayerId;
    view.layout = rebuiltUrls.layout;
    spec.layers = chosen;
  }
  const name = `${kind}.tetravox.json`;
  json(ctx.res, 200, {
    name,
    path: `${PROJECT_ROOT}/code/ti-toolbox/viewer/${name}`,
    host_path: `${MOCK_HOST_ROOT}/code/ti-toolbox/viewer/${name}`,
    scene,
    view,
    files: (scene.datasets ?? []).map((d, index) => ({
      id: d.id,
      kind: d.kind,
      name: d.name ?? String(d.path ?? "").split("/").pop(),
      path: d.path,
      // Both path languages: the row is handed back in `files` when it is kept, moved or joined
      // by another, and the server jails container paths (VM2).
      container_path: spec.layers?.[index]?.path ?? d.path,
      // Deterministic stand-in sizes: the mock has no files on disk, and a list that showed no
      // size would make "the list says how much is about to open" untestable.
      bytes: d.kind === "mesh" ? 24_117_248 + index : 4_194_304 + index,
    })),
    dry_run: Boolean(body.dry_run),
  });
});
// VM2: the default layer for a file the *user* added -- a mirror of tit/viewspec.py's
// _layer_for_path, derived from the name alone (a mesh is a hidden jet surface, a labelled volume
// gets a LUT at 0.7, anything anatomical is opaque grayscale, everything else is a heat field).
function defaultLayerForPath(path) {
  const name = path.split("/").pop().toLowerCase();
  const base = { path, cal_min: null, cal_max: null, percentile: null };
  if (name.endsWith(".msh") || name.endsWith(".gii")) {
    return { ...base, kind: "label", colormap: "jet", opacity: 1, visible: false, lut: null };
  }
  if (/labeling|aseg|aparc|atlas|label|seg|dk40|hcp_mmp1|a2009s|schaefer|final_tissues/.test(name)) {
    return { ...base, kind: "volume", colormap: "lut", opacity: 0.7, visible: true, lut: null };
  }
  if (/t1|t2|mni152|template|brain|orig|conform/.test(name)) {
    return { ...base, kind: "volume", colormap: "grayscale", opacity: 1, visible: true, lut: null };
  }
  return { ...base, kind: "volume", colormap: "heat", opacity: 0.85, visible: true, lut: null };
}

// VM2: everything the "+ Add…" picker offers. Only files a scene can use, grouped and sized.
route("GET", "/api/viewer/candidates", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  if (!subject) return json(ctx.res, 200, { candidates: [] });
  const simulation = ctx.url.searchParams.get("simulation");
  const base = `${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}`;
  const m2m = `${base}/m2m_${subject}`;
  const entry = (path, group, kind = "volume", bytes = 4_194_304) => ({ name: path.split("/").pop(), path, kind, group, bytes });
  const candidates = [
    entry(`${m2m}/T1.nii.gz`, "Head model"),
    entry(`${m2m}/T1_${subject}_MNI.nii.gz`, "Head model"),
    entry(`${m2m}/final_tissues.nii.gz`, "Head model"),
    entry(`${m2m}/${subject}.msh`, "Head model", "mesh", 64_000_000),
    entry(`${m2m}/surfaces/lh.central.gii`, "Surfaces", "mesh", 8_000_000),
    entry(`${m2m}/surfaces/rh.central.gii`, "Surfaces", "mesh", 8_000_000),
    entry(`${m2m}/segmentation/labeling.nii.gz`, "Atlases"),
  ];
  if (simulation) {
    const sim = `${base}/Simulations/${simulation}`;
    candidates.push(
      entry(`${sim}/TI/niftis/${simulation}_TI_subject_TI_max.nii.gz`, "Simulation volumes"),
      entry(`${sim}/TI/mesh/grey_${simulation}_TI.msh`, "Simulation meshes", "mesh", 63_926_663),
      entry(`${sim}/TI/montage_imgs/electrode_overlay_subject.nii.gz`, "Electrodes"),
    );
  }
  json(ctx.res, 200, { candidates });
});

// VM: saved Viewer compositions. In-memory here (the mock has no project on disk); the real
// server writes <project>/code/ti-toolbox/viewer/presets/<slug>.json.
const VIEWER_PRESETS = new Map();
route("GET", "/api/viewer/presets", (ctx) => json(ctx.res, 200, { presets: [...VIEWER_PRESETS.values()] }));
route("PUT", "/api/viewer/presets/:name", async (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!name.trim()) return json(ctx.res, 422, { detail: `Unusable preset name: ${name}` });
  const document = { ...((await ctx.body()) ?? {}), name };
  VIEWER_PRESETS.set(name, document);
  json(ctx.res, 200, document);
});
route("DELETE", "/api/viewer/presets/:name", (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!VIEWER_PRESETS.delete(name)) return json(ctx.res, 404, { detail: `No preset named ${name}` });
  json(ctx.res, 200, { name, deleted: true });
});
// ── the composition tree, saved compositions and saved scenes (2026-09-07) ────────────────────
//
// The tree is what the Menu draws instead of a row of dropdowns. Ported closely enough that a spec
// asserting on tree shape reads the same against either server: the same three branches, the same
// per-node fields, the same "exactly one anatomy input and the grey-matter field start ticked".
//
// The one thing this cannot mirror is `available: false` for a file that has gone missing -- the
// mock has no project on disk, so every node it invents exists by construction. That case is the
// real server's to prove (`tests/test_viewer_library.py`).
const treeNode = (path, { label, kind = "volume", bytes = 4_194_304, defaultOn = false } = {}) => {
  const name = path.split("/").pop();
  // The tree is the one place a curated label is still wanted -- it is a label for *choosing*, and
  // the filename sits beside it in the row's tooltip and in the list below. Layers are named by
  // their file (see `sceneFor`); these are not layers.
  const fieldName = sceneFieldName(name);
  return {
    id: path,
    name,
    label: label ?? sceneDisplayName(name, sceneRole(path, fieldName ? "heat" : "grayscale"), fieldName),
    path,
    kind,
    bytes,
    default_on: defaultOn,
    available: true,
    reason: null,
  };
};

route("GET", "/api/viewer/tree", (ctx) => {
  const subject = ctx.url.searchParams.get("subject");
  const space = ctx.url.searchParams.get("space") === "mni" ? "mni" : "subject";
  const chosen = ctx.url.searchParams.getAll("simulations");
  const empty = { subject, space, anatomy: [], simulations: [], analyses: [], available: false, reason: null };
  if (!subject) return json(ctx.res, 200, { ...empty, reason: "no subject chosen" });

  const base = `${PROJECT_ROOT}/derivatives/SimNIBS/sub-${subject}`;
  const m2m = `${base}/m2m_${subject}`;
  const anatomy = [
    treeNode(`${m2m}/T1.nii.gz`, { defaultOn: space === "subject" }),
    treeNode(`${m2m}/T2_reg.nii.gz`),
    treeNode(`${m2m}/${subject}.msh`, { kind: "mesh", bytes: 64_000_000 }),
    treeNode(`${m2m}/surfaces/lh.central.gii`, { kind: "mesh", bytes: 8_000_000 }),
    treeNode(`${m2m}/segmentation/labeling.nii.gz`, { label: "labeling" }),
  ];
  if (space === "mni") anatomy.push(treeNode("/ti-toolbox/resources/atlas/MNI152_T1_1mm.nii.gz", { label: "MNI152 template", defaultOn: true }));

  // Driven by the same fixture `GET /api/catalog/simulations` answers from, not a second hard-coded
  // list: a subject whose catalog has three simulations and whose tree offers two is a mock that
  // disagrees with itself, and a deep link to the missing one has nowhere to land.
  const simNames = (simulations[subject] ?? []).map((sim) => sim.name);
  // `simBranches`, not `simulations`: that name is the module-level fixture this line above reads,
  // and shadowing it here put the read in its own temporal dead zone — every tree request became a
  // 500 and the Menu drew no tree at all.
  const simBranches = simNames.map((name) => {
    const sim = `${base}/Simulations/${name}`;
    const suffix = space === "mni" ? "MNI_MNI" : "subject";
    return {
      name,
      fields: [
        treeNode(`${sim}/TI/niftis/${name}_TI_${suffix}_TI_max.nii.gz`, { label: "TI_max (volume)" }),
        treeNode(`${sim}/TI/niftis/grey_${name}_TI_${suffix}_TI_max.nii.gz`, { label: "GM · TI_max (volume)", defaultOn: true }),
        treeNode(`${sim}/TI/niftis/white_${name}_TI_${suffix}_TI_max.nii.gz`, { label: "WM · TI_max (volume)" }),
      ],
      meshes: [treeNode(`${sim}/TI/mesh/grey_${name}_TI.msh`, { label: "GM mesh · TI_max", kind: "mesh", bytes: 63_926_663 })],
      electrodes: [treeNode(`${sim}/TI/montage_imgs/electrode_overlay_subject.nii.gz`, { label: "Electrodes" })],
    };
  });

  const analyses = simNames
    .filter((name) => chosen.length === 0 || chosen.includes(name))
    .map((name) => ({
      name: `${name}_DK40_TI_max`,
      simulation: name,
      space: "voxel",
      outputs: [treeNode(`${base}/Simulations/${name}/Analyses/Voxel/${name}_DK40_TI_max/roi_mask.nii.gz`, { label: "ROI mask" })],
    }));

  json(ctx.res, 200, { subject, space, anatomy, simulations: simBranches, analyses, available: true, reason: null });
});

const VIEWER_COMPOSITIONS = new Map();
route("GET", "/api/viewer/compositions", (ctx) => json(ctx.res, 200, { compositions: [...VIEWER_COMPOSITIONS.values()] }));
route("PUT", "/api/viewer/compositions/:name", async (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!name.trim() || name.includes("/")) return json(ctx.res, 422, { detail: `Unusable name: ${name}` });
  const document = { version: 1, ...((await ctx.body()) ?? {}), name, saved_at: new Date().toISOString() };
  VIEWER_COMPOSITIONS.set(name, document);
  json(ctx.res, 200, document);
});
route("DELETE", "/api/viewer/compositions/:name", (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!VIEWER_COMPOSITIONS.delete(name)) return json(ctx.res, 404, { detail: `No composition named ${name}` });
  json(ctx.res, 200, { name, deleted: true });
});

// Saved scenes. The suffix is asserted here as well as on the server, because it is the one
// property that fails *silently* at the far end: the Tetravox app routes anything else as a
// dataset and reads the JSON as a volume.
const SAVED_SCENES = new Map();
const sceneSlug = (name) => name.replace(/[^A-Za-z0-9._ -]/g, "-").trim().replace(/ /g, "_");
/** A listing row: everything but the scene document, which is megabytes and is fetched by name. */
const sceneRow = (row) => {
  const listed = { ...row };
  delete listed.scene;
  return listed;
};
route("GET", "/api/viewer/scenes", (ctx) =>
  json(ctx.res, 200, {
    scenes: [...SAVED_SCENES.values()]
      .map(sceneRow)
      .sort((a, b) => String(b.saved_at ?? "").localeCompare(String(a.saved_at ?? ""))),
  }),
);
route("GET", "/api/viewer/scenes/suggest/name", (ctx) => {
  const parts = ["subject", "simulation", "field"].map((k) => ctx.url.searchParams.get(k)).filter(Boolean);
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  json(ctx.res, 200, { name: [...parts, date].join("_").replace(/[^A-Za-z0-9._-]+/g, "-") || "scene" });
});
route("GET", "/api/viewer/scenes/:name", (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  const row = SAVED_SCENES.get(name);
  if (!row) return json(ctx.res, 404, { detail: `No saved scene named ${name}` });
  json(ctx.res, 200, { name, path: row.path, scene: row.scene });
});
route("PUT", "/api/viewer/scenes/:name", async (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!name.trim() || name.includes("/") || name.startsWith(".")) return json(ctx.res, 422, { detail: `Unusable name: ${name}` });
  const body = (await ctx.body()) ?? {};
  const scene = body.scene;
  if (!scene || typeof scene !== "object" || !Array.isArray(scene.layers) || scene.layers.length === 0) {
    return json(ctx.res, 422, { detail: "A scene must be the embed's serialized ViewSpec, with at least one layer" });
  }
  const slug = sceneSlug(name);
  // A thumbnail is kept only when it is a real PNG data URL, matching the server's own check --
  // "it decoded" is not the same as "it is an image", and this route writes into a project.
  const thumbnail = typeof body.thumbnail === "string" && body.thumbnail.startsWith("data:image/png;base64,");
  const row = {
    name,
    slug,
    path: `${PROJECT_ROOT}/code/ti-toolbox/viewer/scenes/${slug}.tetravox.json`,
    host_path: `${PROJECT_ROOT}/code/ti-toolbox/viewer/scenes/${slug}.tetravox.json`,
    bytes: JSON.stringify(scene).length,
    saved_at: new Date().toISOString(),
    subject: body.subject ?? null,
    simulation: body.simulation ?? null,
    field: body.field ?? null,
    space: body.space ?? null,
    has_thumbnail: thumbnail,
    scene,
  };
  SAVED_SCENES.set(name, row);
  json(ctx.res, 200, sceneRow(row));
});
route("DELETE", "/api/viewer/scenes/:name", (ctx) => {
  const name = decodeURIComponent(ctx.params.name);
  if (!SAVED_SCENES.delete(name)) return json(ctx.res, 404, { detail: `No saved scene named ${name}` });
  json(ctx.res, 200, { name, deleted: true });
});

route("POST", "/api/view/args", async (ctx) => {
  const body = await ctx.body();
  const spec = body.viewspec ?? {};
  const layers = Array.isArray(spec.layers) ? spec.layers : [];
  const freeview_args = layers.map((l) => `${l.path}:colormap=${l.colormap ?? "grayscale"}:opacity=${l.opacity ?? 1}:visible=${l.visible === false ? 0 : 1}`);
  json(ctx.res, 200, {
    freeview_args,
    freeview_command: ["freeview", ...freeview_args],
    scene: sceneFor(spec.space === "mni" ? "mni" : "subject", layers, null),
  });
});

// --- files (v1) ---
route("GET", "/api/files/report/:id", (ctx) => {
  const file = REPORT_HTML[ctx.params.id];
  if (!file || !existsSync(file)) return json(ctx.res, 404, { detail: "unknown report" });
  text(ctx.res, 200, readFileSync(file, "utf8"), "text/html; charset=utf-8", {
    "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:;",
  });
});
route("GET", "/api/files/artifact", (ctx) => {
  const resolved = resolveJailed(ctx.url.searchParams.get("path"));
  if (resolved.jailed) return json(ctx.res, 403, { detail: "path escapes the project jail" });
  if (resolved.notFound || !existsSync(resolved.file)) return json(ctx.res, 404, { detail: "not found" });
  res_stream(ctx.res, resolved.file, resolved.contentType);
});
route("GET", "/api/files/text", (ctx) => {
  const resolved = resolveJailed(ctx.url.searchParams.get("path"));
  if (resolved.jailed) return json(ctx.res, 403, { detail: "path escapes the project jail" });
  if (resolved.notFound || !existsSync(resolved.file)) return json(ctx.res, 404, { detail: "not found" });
  const tail = Number(ctx.url.searchParams.get("tail")) || undefined;
  text(ctx.res, 200, tailLines(readFileSync(resolved.file, "utf8"), tail));
});
route("GET", "/api/files/csv", (ctx) => {
  const resolved = resolveJailed(ctx.url.searchParams.get("path"));
  if (resolved.jailed) return json(ctx.res, 403, { detail: "path escapes the project jail" });
  if (resolved.notFound || !existsSync(resolved.file)) return json(ctx.res, 404, { detail: "not found" });
  json(ctx.res, 200, parseCsv(readFileSync(resolved.file, "utf8")));
});
function res_stream(res, file, contentType) {
  const stat = statSync(file);
  res.writeHead(200, { "content-type": contentType ?? (MIME[extname(file)] ?? "application/octet-stream"), "content-length": stat.size });
  createReadStream(file).pipe(res);
}

// --- raw bytes for the in-app viewer (v1), parity with tit/server/routes/files.py::raw ---
// The URL path IS the file's absolute path minus its leading slash, so the last segment stays the
// real filename (the engine's worker keys gzip inflation and volume-vs-mesh routing off it). Every
// response is opaque bytes: application/octet-stream + nosniff + attachment, never a content
// encoding (a .nii.gz must reach the worker still gzipped -- it inflates the stream itself).
const RAW_DENY_EXTS = [".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".mhtml"];
function rawResolve(urlPath) {
  // urlPath is already percent-decoded by params(); rebuild the absolute path and re-resolve it,
  // then require it to sit inside DATA_ROOT (a `..` or a symlink pointing out lands outside and
  // is refused). Parity with the real jail, which uses tit.viewspec.jail_roots.
  const resolved = resolvePath(`/${urlPath}`);
  if (!DATA_ROOT) return { notFound: true };
  if (resolved !== DATA_ROOT && !resolved.startsWith(DATA_ROOT + sep)) return { jailed: true };
  if (!existsSync(resolved) || !statSync(resolved).isFile()) return { notFound: true };
  return { file: resolved };
}
function rawHandler(headOnly) {
  return (ctx) => {
    const requested = ctx.params.path ?? "";
    if (RAW_DENY_EXTS.some((e) => requested.toLowerCase().endsWith(e))) {
      return json(ctx.res, 403, { detail: "File type not servable as raw data; use /api/files/artifact" });
    }
    const resolved = rawResolve(requested);
    if (resolved.jailed) return json(ctx.res, 403, { detail: "path escapes the project jail" });
    if (resolved.notFound) return json(ctx.res, 404, { detail: "not found" });
    const file = resolved.file;
    const stat = statSync(file);
    const etag = `"${Math.floor(stat.mtimeMs)}-${stat.size}"`;
    const base = {
      "content-type": "application/octet-stream",
      "accept-ranges": "bytes",
      etag,
      "last-modified": new Date(stat.mtimeMs).toUTCString(),
      "x-content-type-options": "nosniff",
      "content-disposition": `attachment; filename="${basename(file)}"`,
      "cache-control": "private, max-age=0, must-revalidate",
    };
    if ((ctx.req.headers["if-none-match"] ?? "") === etag) {
      ctx.res.writeHead(304, base);
      return ctx.res.end();
    }
    const range = /^bytes=(\d*)-(\d*)$/.exec(ctx.req.headers.range ?? "");
    if (range) {
      const suffix = range[1] === "";
      let start = suffix ? stat.size - Number(range[2]) : Number(range[1]);
      let end = suffix || range[2] === "" ? stat.size - 1 : Number(range[2]);
      if (!Number.isFinite(start) || start < 0 || start >= stat.size) {
        ctx.res.writeHead(416, { ...base, "content-range": `bytes */${stat.size}` });
        return ctx.res.end();
      }
      end = Math.min(end, stat.size - 1);
      ctx.res.writeHead(206, { ...base, "content-range": `bytes ${start}-${end}/${stat.size}`, "content-length": end - start + 1 });
      return headOnly ? ctx.res.end() : createReadStream(file, { start, end }).pipe(ctx.res);
    }
    ctx.res.writeHead(200, { ...base, "content-length": stat.size });
    return headOnly ? ctx.res.end() : createReadStream(file).pipe(ctx.res);
  };
}
route("GET", "/api/files/raw/*path", rawHandler(false));
route("HEAD", "/api/files/raw/*path", rawHandler(true));

// --- settings (v1) ---
route("GET", "/api/settings", (ctx) => json(ctx.res, 200, settingsStore));
route("PUT", "/api/settings", async (ctx) => {
  const body = await ctx.body();
  settingsStore = { ...settingsStore, ...body };
  json(ctx.res, 200, settingsStore);
});

// --- tetravox (v1): dynamic embed delivery ---
// A faithful in-memory model of tit/tetravox/{protocol,store,install}.py: a baked floor, an
// install root, a pin, and a release index. No download happens here -- the mock's job is the
// state machine the Settings page drives (install -> active, roll back -> baked, and back
// again), not the digest verification, which is tested in tests/test_tetravox_install.py.
const TVX_SUPPORTED = { min: 1, max: 2 };
const TVX_FEATURE_MIN_PROTOCOL = { volumes: 1, meshes: 1, cursor: 1, probe: 1, screenshot: 1, layers: 1, markers: 2, pick: 2, camera: 2 };
const tvxFeatures = (protocol) =>
  Object.keys(TVX_FEATURE_MIN_PROTOCOL)
    .filter((name) => protocol >= TVX_FEATURE_MIN_PROTOCOL[name])
    .sort();
const tvxCompatible = (protocol) => Number.isInteger(protocol) && protocol >= TVX_SUPPORTED.min && protocol <= TVX_SUPPORTED.max;
const tvxVersionKey = (v) => v.split(/[^0-9]+/).filter(Boolean).map(Number);
const tvxNewerFirst = (a, b) => {
  const ka = tvxVersionKey(a.version);
  const kb = tvxVersionKey(b.version);
  for (let i = 0; i < Math.max(ka.length, kb.length); i += 1) {
    const d = (kb[i] ?? 0) - (ka[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
};
const tvxRelease = (version, protocol, source, path) => ({
  version,
  protocol,
  source,
  path,
  name: "@tetravox/embed",
  sha: `${version}-mock`,
  features: tvxFeatures(protocol),
  compatible: tvxCompatible(protocol),
  active: false,
});
const TVX_INSTALL_ROOT = "/root/.config/ti-toolbox/tetravox/embed";
const TVX_INDEX_URL = "https://api.github.com/repos/idossha/tetravox/releases";
const tvxBaked = tvxRelease("0.3.4", 1, "baked", "/opt/tetravox/embed");
let tvxInstalled = [];
let tvxPin = null; // null | "baked" | a version
// A3: the policy (default on), the last check, and the last automatic outcome. In the server
// these live in <install root>/{policy.json,updates.json}; here they are three variables with
// the same meaning, so the Settings card drives the same state machine.
let tvxAutoUpdate = true;
let tvxCheckedAt = null;
let tvxLastOutcome = null;
const tvxIndex = [
  // A release past the range this build can host: the index lists it, the UI must show it as not
  // installable, and POST /api/tetravox/install must refuse it (E1 -- the app pins a *range*).
  { version: "0.5.0", protocol: 3, url: "https://github.com/idossha/tetravox/releases/download/embed-v0.5.0/tetravox-embed-0.5.0.tgz", sha256: "c".repeat(64), notes: "Protocol 3: needs a newer TI-Toolbox.", published: "2026-09-10" },
  { version: "0.4.0", protocol: 2, url: "https://github.com/idossha/tetravox/releases/download/embed-v0.4.0/tetravox-embed-0.4.0.tgz", sha256: "b".repeat(64), notes: "Protocol 2: points layer, pick events, camera get/set.", published: "2026-09-04" },
  { version: "0.3.4", protocol: 1, url: "https://github.com/idossha/tetravox/releases/download/embed-v0.3.4/tetravox-embed-0.3.4.tgz", sha256: "a".repeat(64), notes: "The version baked into this image.", published: "2026-09-03" },
];

function tvxResolve() {
  if (tvxPin === "baked") return { release: tvxBaked, reason: "pinned to the version baked into the image" };
  const pinned = tvxInstalled.find((r) => r.version === tvxPin && r.compatible);
  if (pinned) return { release: pinned, reason: `pinned to installed ${pinned.version}` };
  const newest = [...tvxInstalled].sort(tvxNewerFirst).find((r) => r.compatible);
  if (newest) return { release: newest, reason: `newest compatible installed version (${newest.version})` };
  return { release: tvxBaked, reason: "the version baked into the image" };
}

function tvxState() {
  const { release, reason } = tvxResolve();
  const mark = (r) => ({ ...r, active: r.path === release.path });
  return {
    active: mark(release),
    reason,
    installed: [...tvxInstalled].sort(tvxNewerFirst).map(mark),
    baked: mark(tvxBaked),
    supported: TVX_SUPPORTED,
    install_root: TVX_INSTALL_ROOT,
    index_url: TVX_INDEX_URL,
    auto_update: tvxAutoUpdate,
  };
}

route("GET", "/api/tetravox", (ctx) => json(ctx.res, 200, tvxState()));
route("GET", "/api/tetravox/updates", (ctx) => {
  // `?refresh=true` is "Check now"; without it the answer is the cached one (the real server
  // reads <install root>/updates.json rather than spending one of GitHub's 60 requests/hour).
  const refresh = ctx.url.searchParams.get("refresh") === "true";
  const cached = tvxCheckedAt !== null && !refresh;
  if (!cached) tvxCheckedAt = Date.now() / 1000;
  json(ctx.res, 200, {
    available: true,
    message: null,
    index_url: TVX_INDEX_URL,
    auto_update: tvxAutoUpdate,
    checked_at: tvxCheckedAt,
    from_cache: cached,
    last_outcome: tvxLastOutcome,
    releases: tvxIndex.map((entry) => ({
      ...entry,
      compatible: tvxCompatible(entry.protocol),
      installed: tvxInstalled.some((r) => r.version === entry.version),
    })),
  });
});
route("POST", "/api/tetravox/policy", async (ctx) => {
  const body = await ctx.body();
  if (typeof body.auto_update !== "boolean") return json(ctx.res, 400, { detail: "`auto_update` must be a boolean" });
  tvxAutoUpdate = body.auto_update;
  json(ctx.res, 200, tvxState());
});
route("POST", "/api/tetravox/install", async (ctx) => {
  const body = await ctx.body();
  const entry = body.version ? tvxIndex.find((e) => e.version === body.version) : tvxIndex.find((e) => e.url === body.url);
  if (!entry) return json(ctx.res, 404, { detail: `The release index has no version ${body.version ?? body.url}` });
  if (!body.version && body.sha256 !== entry.sha256) {
    return json(ctx.res, 400, { detail: `sha256 mismatch: the download is ${entry.sha256}, expected ${body.sha256}. Nothing was installed.` });
  }
  if (!tvxCompatible(entry.protocol)) {
    return json(ctx.res, 400, { detail: `That bundle speaks embed protocol ${entry.protocol}; this version of TI-Toolbox supports protocol ${TVX_SUPPORTED.min}-${TVX_SUPPORTED.max}. Update TI-Toolbox to install it.` });
  }
  tvxInstalled = tvxInstalled.filter((r) => r.version !== entry.version);
  tvxInstalled.push(tvxRelease(entry.version, entry.protocol, "installed", `${TVX_INSTALL_ROOT}/${entry.version}`));
  tvxPin = entry.version;
  json(ctx.res, 200, tvxState());
});
route("POST", "/api/tetravox/activate", async (ctx) => {
  const body = await ctx.body();
  if (typeof body.version !== "string" || !body.version) return json(ctx.res, 400, { detail: "`version` is required" });
  if (body.version !== "baked" && !tvxInstalled.some((r) => r.version === body.version)) {
    return json(ctx.res, 404, { detail: `Not installed: ${body.version}` });
  }
  tvxPin = body.version;
  json(ctx.res, 200, tvxState());
});
route("DELETE", "/api/tetravox/:version", (ctx) => {
  const { version } = ctx.params;
  if (!tvxInstalled.some((r) => r.version === version)) return json(ctx.res, 404, { detail: `Not installed: ${version}` });
  tvxInstalled = tvxInstalled.filter((r) => r.version !== version);
  if (tvxPin === version) tvxPin = null;
  json(ctx.res, 200, tvxState());
});

// --------------------------------------------------------------------------------------- HTTP
const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const p = url.pathname;

  if (p === "/api/health") return json(res, 200, { status: "ok", uptime_s: (Date.now() - startedAt) / 1000 });
  if (req.method === "GET" && p === "/auth/session") {
    if (url.searchParams.get("token") !== TOKEN) return json(res, 401, { detail: "bad token" });
    return startSession(res);
  }
  // Browser mode: the launcher prints http://host:port/?token=... (TODO 2.7).
  if (req.method === "GET" && p === "/" && url.searchParams.has("token")) {
    if (url.searchParams.get("token") !== TOKEN) return json(res, 401, { detail: "bad token" });
    return startSession(res);
  }
  if (p === "/auth/logout") {
    if (req.method !== "POST") return json(res, 405, { detail: "method not allowed" });
    if (!authed(req)) return json(res, 401, { detail: "not authenticated" });
    if (!bearerAuthed(req) && cookieAuthed(req) && !cookieCsrfOk(req)) {
      return json(res, 403, { detail: "Cross-site request blocked: missing or foreign Origin" });
    }
    sessions.delete(cookies(req).tit_session);
    res.writeHead(204, { "set-cookie": "tit_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" });
    return res.end();
  }

  // /tetravox/* (D1/D3, docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)): unauthenticated static asset
  // delivery, like "/" -- checked before the generic static fallback so it is never shadowed by
  // (and never falls back to) the renderer bundle's own index.html.
  if (p === "/tetravox" || p.startsWith("/tetravox/")) {
    if (req.method !== "GET") return json(res, 405, { detail: "method not allowed" });
    return serveTetravox(res, p);
  }

  if (!p.startsWith("/api/")) {
    if (req.method !== "GET") return json(res, 405, { detail: "method not allowed" });
    return serveStatic(res, p);
  }

  if (!authed(req, url)) return json(res, 401, { detail: "not authenticated" });
  if (!bearerAuthed(req) && url.searchParams.get("token") !== TOKEN && cookieAuthed(req)) {
    if (!SAFE_METHODS.has(req.method) && !cookieCsrfOk(req)) {
      return json(res, 403, { detail: "Cross-site request blocked: missing or foreign Origin" });
    }
  }

  for (const r of routeTable) {
    if (r.method !== req.method) continue;
    const matched = params(r, p);
    if (!matched) continue;
    const ctx = { req, res, url, params: matched, body: () => readBody(req) };
    try {
      await r.handler(ctx);
    } catch (err) {
      json(res, 500, { detail: String(err?.message ?? err) });
    }
    return;
  }
  json(res, 404, { detail: "not found" });
});

// ----------------------------------------------------------------------------------- WebSocket
const wssSystem = new WebSocketServer({ noServer: true });
const wssJobs = new WebSocketServer({ noServer: true });
// /ws/tetravox (A3): silent until the viewer bundle is replaced under the app. The mock has no
// background updater, so the only way an event appears here is the test hook below.
const wssTetravox = new WebSocketServer({ noServer: true });
const wssKernels = new WebSocketServer({ noServer: true });
const KERNEL_WS = /^\/ws\/kernels\/([^/]+)$/;
const wsTetravoxClients = new Set();
server.on("upgrade", (req, socket, head) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const kernelMatch = KERNEL_WS.exec(url.pathname);
  if (
    url.pathname !== "/ws/system" &&
    url.pathname !== "/ws/jobs" &&
    url.pathname !== "/ws/tetravox" &&
    kernelMatch === null
  ) {
    socket.write("HTTP/1.1 404 Not Found\r\n\r\n");
    socket.destroy();
    return;
  }
  if (!originAllowed(req)) {
    socket.write("HTTP/1.1 403 Forbidden\r\n\r\n");
    socket.destroy();
    return;
  }
  if (!authed(req, url)) {
    socket.write("HTTP/1.1 401 Unauthorized\r\n\r\n");
    socket.destroy();
    return;
  }
  if (url.pathname === "/ws/system") {
    wssSystem.handleUpgrade(req, socket, head, (ws) => {
      const send = () => ws.readyState === ws.OPEN && ws.send(JSON.stringify(snapshot()));
      send();
      const timer = setInterval(send, WS_INTERVAL_MS);
      ws.on("close", () => clearInterval(timer));
    });
    return;
  }
  if (kernelMatch !== null) {
    const kernel = kernelStore.get(kernelMatch[1]);
    if (!kernel) {
      // The real server accepts nothing and closes with 4404; before a
      // handshake there is no close code to send, so the upgrade is refused.
      socket.write("HTTP/1.1 404 Not Found\r\n\r\n");
      socket.destroy();
      return;
    }
    wssKernels.handleUpgrade(req, socket, head, (ws) => {
      kernel.sockets.add(ws);
      ws.send(JSON.stringify({ type: "ready", kernel: kernelDescribe(kernel) }));
      ws.on("message", (raw) => {
        let msg;
        try {
          msg = JSON.parse(raw.toString());
        } catch {
          return;
        }
        if (msg.op === "execute") {
          kernelExecute(kernel, String(msg.id ?? ""), String(msg.code ?? ""));
        } else if (msg.op === "interrupt") {
          kernelInterrupt(kernel);
        } else if (msg.op === "complete") {
          kernelComplete(kernel, String(msg.id ?? ""), String(msg.code ?? ""), Number(msg.cursorPos ?? 0));
        } else if (msg.op === "inspect") {
          kernelInspect(kernel, String(msg.id ?? ""), String(msg.code ?? ""), Number(msg.cursorPos ?? 0));
        }
      });
      ws.on("close", () => kernel.sockets.delete(ws));
    });
    return;
  }
  if (url.pathname === "/ws/tetravox") {
    wssTetravox.handleUpgrade(req, socket, head, (ws) => {
      wsTetravoxClients.add(ws);
      ws.on("close", () => wsTetravoxClients.delete(ws));
    });
    return;
  }
  wssJobs.handleUpgrade(req, socket, head, (ws) => {
    const client = { ws, subs: new Map() };
    wsJobClients.add(client);
    ws.on("message", (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (msg.subscribe && typeof msg.subscribe === "object") {
        for (const [jobId, sinceSeq] of Object.entries(msg.subscribe)) {
          client.subs.set(jobId, sinceSeq);
          const job = jobRegistry.get(jobId);
          if (job) {
            for (const ev of job.events) {
              if (ev.seq > sinceSeq) ws.send(JSON.stringify({ type: "event", job_id: jobId, event: ev }));
            }
          }
        }
      }
      if (Array.isArray(msg.unsubscribe)) {
        for (const jobId of msg.unsubscribe) client.subs.delete(jobId);
      }
    });
    ws.on("close", () => wsJobClients.delete(client));
  });
});

server.listen(PORT, HOST, () => {
  console.log(`mock tit.server (v1) on http://${HOST}:${PORT}  token=${TOKEN}  renderer=${existsSync(rendererDir) ? rendererDir : "(not built)"}`);
  console.log(`browser mode: http://${HOST}:${PORT}/?token=${TOKEN}`);
});
