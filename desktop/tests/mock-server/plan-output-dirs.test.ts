// The mock server plans, names and records the way the real tit.server does (package p38,
// 2026-10-22).
//
// What this pins, each against a table the REAL side wrote:
//   * POST /api/plan/{stats,nifti_average,nilearn,blender} -> the project-relative `output_dir`
//     in tests/fixtures/plan_output_dirs.json, which dev/gen_plan_output_dirs.py writes from the
//     real FastAPI plan route (tests/test_plan_output_dirs_fixture.py keeps it current). Before:
//     derivatives/group/stats/NewRun, derivatives/group/nilearn/NewRun, "<sim>" for regions.
//   * every mock job of a kind logs under the Python package that holds that kind's runner
//     (the table's `runner_package_for_kind`, from tit/jobs/kinds.py via importlib). Before:
//     "tit.tools.nifti_average" and "tit.tools.nilearn_visuals", modules that do not exist.
//   * POST /api/plan/{ex,mex} -> `resolved.search_space.n_combinations` equal to the brute-force
//     count in tests/fixtures/ex_search_counts.json (dev/gen_ex_counts.py). Before: n(n-1)/2 x 7.
//   * an existing group run (named in the mock's own group_catalog.json) plans as an overwrite
//     and POST /api/jobs answers 409 until `overwrite` is sent -- the real overwrite policy.
//   * an analysis view without an analysis name is a 404, as tit/viewspec.py::build_view makes it.
//   * caps are file names: every name /api/caps/available lists is one /api/caps/warp accepts,
//     and the stem the old mock used is a 404, as on the real server.
//
// Reproduce: cd desktop && npx vitest run tests/mock-server/plan-output-dirs.test.ts
import { spawn, type ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// pid-derived and off the other mock-server test files' bases (9300, 9800), so concurrent runs in
// separate worktrees and the two sibling files never share a port.
const PORT = 10400 + (process.pid % 500);
const TOKEN = "plan-dirs-token";
const BASE = `http://127.0.0.1:${PORT}`;
const AUTH = { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" };
const REPO = join(__dirname, "..", "..", "..");

interface PlanCase {
  id: string;
  kind: string;
  subject_ids: string[];
  config: Record<string, unknown>;
  jobs: { subject: string; output_dir: string }[];
}
interface PlanTable {
  project_placeholder: string;
  cases: PlanCase[];
  module_for_kind: Record<string, string>;
  runner_package_for_kind: Record<string, string>;
}
interface CountCase {
  id: string;
  kind: "ex" | "mex";
  mode?: "bucketed" | "all";
  buckets?: Record<string, string[]>;
  pool?: string[];
  total_current?: number;
  current_step?: number;
  channel_limit?: number | null;
  splits?: number[][];
  expected_combinations: number;
}

const planTable = JSON.parse(readFileSync(join(REPO, "tests", "fixtures", "plan_output_dirs.json"), "utf8")) as PlanTable;
const countTable = JSON.parse(readFileSync(join(REPO, "tests", "fixtures", "ex_search_counts.json"), "utf8")) as { cases: CountCase[] };
const groupCatalog = JSON.parse(readFileSync(join(__dirname, "..", "fixtures", "group_catalog.json"), "utf8")) as {
  stats: { name: string; type: string }[];
};

let child: ChildProcess;
let projectRoot = "";

beforeAll(async () => {
  child = spawn(process.execPath, [join(__dirname, "server.mjs")], {
    env: { ...process.env, TIT_MOCK_PORT: String(PORT), TIT_MOCK_TOKEN: TOKEN, TIT_MOCK_WS_INTERVAL_MS: "60000" },
    stdio: "ignore",
  });
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  const project = (await (await fetch(`${BASE}/api/project`, { headers: AUTH })).json()) as { container_path: string };
  projectRoot = project.container_path;
  expect(projectRoot.startsWith("/")).toBe(true);
}, 20_000);

afterAll(async () => {
  if (!child || child.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    child.once("exit", () => resolve());
    child.kill();
  });
});

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(`${BASE}${path}`, { method: "POST", headers: AUTH, body: JSON.stringify(body) });
}

function fill<T>(value: T): T {
  return JSON.parse(JSON.stringify(value).split(planTable.project_placeholder).join(projectRoot)) as T;
}

describe("POST /api/plan: the output folder the real server plans", () => {
  it("has group, stats-type and export-mode cases to check", () => {
    expect(new Set(planTable.cases.map((c) => c.kind))).toEqual(new Set(["stats", "nifti_average", "nilearn", "blender"]));
    expect(planTable.cases.filter((c) => "output_dir" in c.config).length).toBeGreaterThanOrEqual(4);
  });

  for (const c of planTable.cases) {
    it(`${c.id}: ${c.jobs.map((j) => j.output_dir).join(", ")}`, async () => {
      const res = await post(`/api/plan/${c.kind}`, { config: fill(c.config), subject_ids: c.subject_ids });
      expect(res.status).toBe(200);
      const plan = (await res.json()) as { jobs: { subject: string; output_dir: string }[] };
      const relative = plan.jobs.map((j) => ({
        subject: j.subject,
        output_dir: j.output_dir.startsWith(`${projectRoot}/`) ? j.output_dir.slice(projectRoot.length + 1) : j.output_dir,
      }));
      expect(relative).toEqual(c.jobs);
    });
  }
});

/** Every log line a fast mock job of `kind` wrote, by logger, once the job has ended. */
async function jobLoggers(kind: string): Promise<string[]> {
  const res = await post("/api/jobs", { kind, config: { __mock_fast: true }, subject_ids: [] });
  expect(res.status).toBe(201);
  const { id } = (await res.json()) as { id: string };
  const deadline = Date.now() + 15_000;
  for (;;) {
    const status = (await (await fetch(`${BASE}/api/jobs/${id}`, { headers: AUTH })).json()) as { status: { state: string } };
    if (["succeeded", "failed", "cancelled", "skipped", "lost"].includes(status.status.state)) break;
    if (Date.now() > deadline) throw new Error(`${kind} job ${id} did not finish`);
    await new Promise((r) => setTimeout(r, 100));
  }
  const events = (await (await fetch(`${BASE}/api/jobs/${id}/events`, { headers: AUTH })).json()) as { type: string; logger?: string }[];
  return events.filter((e) => e.type === "log" && e.logger && !e.logger.startsWith("mock.")).map((e) => e.logger!);
}

describe("mock jobs log as the kind's real runner", () => {
  it("covers every kind tit/jobs/kinds.py runs, each inside its runner's package", async () => {
    const kinds = Object.keys(planTable.module_for_kind);
    expect(kinds.length).toBeGreaterThanOrEqual(10);
    const results = await Promise.all(kinds.map(async (kind) => [kind, await jobLoggers(kind)] as const));
    for (const [kind, loggers] of results) {
      const pkg = planTable.runner_package_for_kind[kind]!;
      expect(loggers.length, `${kind} wrote log lines`).toBeGreaterThan(0);
      for (const logger of new Set(loggers)) {
        expect(logger === pkg || logger.startsWith(`${pkg}.`), `${kind}: ${logger} is inside ${pkg}`).toBe(true);
      }
    }
  }, 30_000);
});

describe("POST /api/plan/{ex,mex}: the runner's search-space count", () => {
  const cases = countTable.cases;
  it("has pool, bucket and mEx cases, including empty ones", () => {
    expect(cases.some((c) => c.kind === "ex" && c.mode === "all")).toBe(true);
    expect(cases.some((c) => c.kind === "ex" && c.mode === "bucketed")).toBe(true);
    expect(cases.some((c) => c.kind === "mex" && c.expected_combinations === 0)).toBe(true);
  });

  for (const c of cases) {
    it(`${c.id}: ${c.expected_combinations}`, async () => {
      const electrodes = c.mode === "all" ? { _type: "PoolElectrodes", electrodes: c.pool } : { _type: "BucketElectrodes", ...c.buckets };
      const config =
        c.kind === "ex"
          ? { subject_id: "ernie", leadfield_hdf: "lf.hdf5", electrodes, total_current: c.total_current, current_step: c.current_step, channel_limit: c.channel_limit }
          : { subject_id: "ernie", leadfield_hdf: "lf.hdf5", electrodes };
      const res = await post(`/api/plan/${c.kind}`, { config, subject_ids: ["ernie"] });
      expect(res.status).toBe(200);
      const plan = (await res.json()) as { resolved: { search_space: { n_combinations: number; n_current_ratios?: number } } };
      expect(plan.resolved.search_space.n_combinations).toBe(c.expected_combinations);
      if (c.kind === "ex") expect(plan.resolved.search_space.n_current_ratios).toBe(c.splits!.length);
    });
  }
});

describe("an existing group run needs an explicit overwrite", () => {
  const existing = groupCatalog.stats.find((s) => s.type === "group_comparison")!;
  const config = {
    _type: "GroupComparisonConfig",
    analysis_name: existing?.name,
    subjects: [
      { subject_id: "ernie", simulation_name: "Thalamus", response: 1 },
      { subject_id: "101", simulation_name: "Thalamus", response: 0 },
    ],
  };

  it("plans the catalog's run by its analysis_name and type as one it would replace", async () => {
    expect(existing, "the group catalog fixture has a group comparison").toBeTruthy();
    const plan = (await (await post("/api/plan/stats", { config })).json()) as { jobs: { exists: boolean; will_overwrite: boolean; output_dir: string }[] };
    expect(plan.jobs).toHaveLength(1);
    expect(plan.jobs[0]).toMatchObject({ exists: true, will_overwrite: true });
    expect(plan.jobs[0]!.output_dir).toBe(`${projectRoot}/derivatives/ti-toolbox/stats/group_comparison/${existing.name}`);
    // The same name as a correlation is another folder, which does not exist.
    const other = (await (await post("/api/plan/stats", { config: { ...config, _type: "CorrelationConfig" } })).json()) as { jobs: { exists: boolean }[] };
    expect(other.jobs[0]!.exists).toBe(false);
  });

  it("refuses the submission with 409 until overwrite is confirmed", async () => {
    const refused = await post("/api/jobs", { kind: "stats", config, subject_ids: [] });
    expect(refused.status).toBe(409);
    expect(((await refused.json()) as { detail: string }).detail).toContain(`stats/group_comparison/${existing.name}`);
    const fresh = await post("/api/jobs", { kind: "stats", config: { ...config, analysis_name: "p38_never_run" }, subject_ids: [] });
    expect(fresh.status).toBe(201);
    const confirmed = await post("/api/jobs", { kind: "stats", config, subject_ids: [], overwrite: true });
    expect(confirmed.status).toBe(201);
  });
});

describe("an analysis view names its analysis", () => {
  it("is a 404 without the analysis name, on both view routes, and resolves with it", async () => {
    const without = await post("/api/view/open", { kind: "analysis", subject: "ernie", simulation: "Thalamus" });
    expect(without.status).toBe(404);
    const get = await fetch(`${BASE}/api/view/analysis?subject=ernie&simulation=Thalamus`, { headers: AUTH });
    expect(get.status).toBe(404);
    const named = await post("/api/view/open", { kind: "analysis", subject: "ernie", simulation: "Thalamus", analysis: "Thalamus_DK40_TI_max" });
    expect(named.status).toBe(200);
  });
});

describe("caps are named by their file names", () => {
  it("accepts every listed cap that has an MNI source for warping and 404s the stem the real server does not know", async () => {
    const available = (await (await fetch(`${BASE}/api/caps/available?subject=ernie`, { headers: AUTH })).json()) as {
      caps: { name: string; on_subject: boolean; source: string | null }[];
    };
    expect(available.caps.filter((c) => c.source !== null).length).toBeGreaterThanOrEqual(3);
    for (const cap of available.caps) {
      expect(cap.name.endsWith(".csv"), cap.name).toBe(true);
      const warp = await post("/api/caps/warp", { subject: "ernie", caps: [cap.name] });
      // A net only on the subject has no MNI file to warp from (`tit.caps.source_caps`): 404, as
      // the real route answers it and as the panel says ("cannot be re-applied here").
      expect(warp.status, cap.name).toBe(cap.source === null ? 404 : cap.on_subject ? 409 : 200);
    }
    const stem = await post("/api/caps/warp", { subject: "ernie", caps: ["GSN-HydroCel-185"] });
    expect(stem.status).toBe(404);
  });

  it("a warped cap is then inspectable and drawable by the same name", async () => {
    const warp = await post("/api/caps/warp", { subject: "101", caps: ["GSN-HydroCel-256.csv"], overwrite: true });
    expect(warp.status).toBe(200);
    const inspect = await fetch(`${BASE}/api/caps/inspect?subject=101&net=GSN-HydroCel-256.csv`, { headers: AUTH });
    expect(inspect.status).toBe(200);
    const electrodes = await fetch(`${BASE}/api/scene/electrodes?subject=101&net=GSN-HydroCel-256.csv`, { headers: AUTH });
    expect(electrodes.status).toBe(200);
  });
});
