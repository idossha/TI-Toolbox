// Gate 0 for the mock server: drives every path+method declared in contracts/openapi.yaml
// against a live instance of server.mjs and checks (a) the response status is one the contract
// declares for that operation and (b) for 200 JSON responses, the required properties of the
// declared schema (resolving local $refs; allOf merged; oneOf tried leniently; x-tit-config
// placeholders accepted as opaque objects) are present. Also exercises the job lifecycle end to
// end (submit -> events -> succeeded) and cancel, and the two WebSocket upgrades.
//
// The contract is parsed in memory: with the `yaml` package (a real desktop/ dependency since W4)
// directly, and otherwise by shelling out to python3 (pyyaml) and reading its STDOUT. A test run
// writes nothing into the source tree — this used to overwrite the tracked
// `tests/fixtures/generated/openapi.json`, so running the suite dirtied the worktree and a read-only
// checkout failed in the fixture write rather than on anything about the contract (audit TEST-01).
// The tracked JSON copy is owned by `dev/build_contract.py` / `npm run gen:api`, not by a test.
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { request as httpRequest } from "node:http";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// pid-derived so two agents running `vitest` concurrently in separate worktrees don't collide on
// a fixed port (ra_11 finding 4). Different base offset than server.test.ts's so the two files
// never share a port even when both land on the same pid modulus.
const PORT = 9800 + (process.pid % 500);
const TOKEN = "contract-token";
const BASE = `http://127.0.0.1:${PORT}`;
let child: ChildProcess;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let spec: any;
const exercised = new Set<string>();

beforeAll(async () => {
  const yamlPath = join(__dirname, "..", "..", "..", "contracts", "openapi.yaml");
  try {
    // `yaml` is a real desktop/ dependency now (W4 added it for stack.ts's own compose parsing),
    // so this import type-checks on its own -- no suppression comment needed. The python3
    // fallback below still exists for environments where `node_modules` isn't installed at all.
    const { parse } = await import("yaml");
    spec = parse(readFileSync(yamlPath, "utf8"));
  } catch {
    const json = execFileSync(
      "python3",
      ["-c", `import yaml, json, sys\njson.dump(yaml.safe_load(open(${JSON.stringify(yamlPath)})), sys.stdout)`],
      { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
    );
    spec = JSON.parse(json);
  }

  child = spawn(process.execPath, [join(__dirname, "server.mjs")], {
    env: { ...process.env, TIT_MOCK_PORT: String(PORT), TIT_MOCK_TOKEN: TOKEN, TIT_MOCK_WS_INTERVAL_MS: "60000" },
    stdio: "ignore",
  });
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error("mock server did not start");
}, 20_000);

afterAll(async () => {
  if (!child || child.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    child.once("exit", () => resolve());
    child.kill();
  });
});

// ------------------------------------------------------------------------------- schema helpers
function resolveRef(ref: string) {
  const parts = ref.replace(/^#\//, "").split("/");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return parts.reduce((o: any, k: string) => o?.[k], spec);
}
function jsType(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  return typeof v;
}
/** Best-effort check that `value` carries the required properties `schema` (or its refs) declare. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function assertRequired(schema: any, value: unknown, label: string, depth = 0): void {
  if (!schema || depth > 4) return;
  if (value === null && Array.isArray(schema.type) && schema.type.includes("null")) return;
  if (schema.$ref) return assertRequired(resolveRef(schema.$ref), value, label, depth);
  if (schema["x-tit-config"]) {
    expect(typeof value, `${label}: expected an object (x-tit-config placeholder)`).toBe("object");
    return;
  }
  if (Array.isArray(schema.allOf)) {
    for (const sub of schema.allOf) assertRequired(sub, value, label, depth);
    return;
  }
  if (Array.isArray(schema.oneOf)) {
    // Lenient: validate against whichever branch's declared type matches the value's JS type.
    const branch = schema.oneOf
      .map((s: unknown) => (s && typeof s === "object" && "$ref" in (s as object) ? resolveRef((s as { $ref: string }).$ref) : s))
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .find((s: any) => (s?.type === "null" ? value === null : s?.type === undefined || s.type === jsType(value)));
    if (branch) assertRequired(branch, value, label, depth);
    return;
  }
  if (schema.type === "object" || schema.properties) {
    expect(value !== null && typeof value === "object", `${label}: expected an object, got ${jsType(value)}`).toBe(true);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const obj = value as Record<string, any>;
    for (const key of schema.required ?? []) {
      expect(obj, `${label}: missing required property "${key}"`).toHaveProperty(key);
    }
    if (schema.properties) {
      for (const [key, subSchema] of Object.entries(schema.properties)) {
        if (obj && key in obj) assertRequired(subSchema, obj[key], `${label}.${key}`, depth + 1);
      }
    }
    return;
  }
  if (schema.type === "array" && Array.isArray(value) && schema.items && value.length) {
    assertRequired(schema.items, value[0], `${label}[0]`, depth + 1);
  }
}
function declaredStatuses(opPath: string, method: string): number[] {
  const op = spec.paths[opPath][method.toLowerCase()];
  return Object.keys(op.responses)
    .filter((k) => /^\d+$/.test(k))
    .map(Number);
}
function responseSchemaFor(opPath: string, method: string, status: number) {
  const op = spec.paths[opPath][method.toLowerCase()];
  return op.responses[String(status)]?.content?.["application/json"]?.schema;
}

async function call(
  opPath: string,
  method: string,
  urlPath: string,
  opts: { body?: unknown; rawBody?: Uint8Array; auth?: boolean; headers?: Record<string, string> } = {},
): Promise<{ res: Response; json?: unknown }> {
  const { body, rawBody, auth = true, headers = {} } = opts;
  const res = await fetch(`${BASE}${urlPath}`, {
    method,
    headers: { ...(body !== undefined ? { "content-type": "application/json" } : {}), ...(auth ? { authorization: `Bearer ${TOKEN}` } : {}), ...headers },
    body: rawBody !== undefined ? Buffer.from(rawBody) : body !== undefined ? JSON.stringify(body) : undefined,
  });
  exercised.add(`${method} ${opPath}`);
  const statuses = declaredStatuses(opPath, method);
  expect(statuses, `${method} ${opPath} should declare a response for status ${res.status}`).toContain(res.status);
  const ct = res.headers.get("content-type") ?? "";
  let json: unknown;
  if (ct.includes("application/json")) {
    json = await res.json().catch(() => undefined);
    if (res.status >= 200 && res.status < 300) {
      const schema = responseSchemaFor(opPath, method, res.status);
      if (schema) assertRequired(schema, json, `${method} ${opPath} ${res.status}`);
    }
  } else {
    await res.text();
  }
  return { res, json };
}
type JobStatusRead = {
  state: string;
  cpu_percent_peak: number | null;
  cpu_percent_avg: number | null;
  rss_peak: number | null;
  rss_avg: number | null;
};
async function waitForState(id: string, states: string[], timeoutMs = 5000): Promise<{ status: JobStatusRead }> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const { json } = await call("/api/jobs/{id}", "GET", `/api/jobs/${id}`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const status = (json as any).status;
    if (states.includes(status.state)) return { status };
    if (Date.now() > deadline) throw new Error(`job ${id} did not reach ${states.join("|")}, stuck at ${status.state}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

// ------------------------------------------------------------------------ full-contract coverage
describe("contract coverage: every openapi.yaml path+method", () => {
  it("exercises every declared HTTP operation with a contract-valid response", async () => {
    // system / auth (v0, unchanged)
    await call("/api/health", "GET", "/api/health", { auth: false });
    {
      const res = await fetch(`${BASE}/auth/session?token=${TOKEN}`, { redirect: "manual" });
      exercised.add("GET /auth/session");
      expect(declaredStatuses("/auth/session", "GET")).toContain(res.status);
      expect(res.status).toBe(303);
    }
    await call("/api/version", "GET", "/api/version");
    await call("/api/capabilities", "GET", "/api/capabilities");
    await call("/api/project", "GET", "/api/project");
    await call("/api/project/status", "GET", "/api/project/status");
    await call("/api/project/status", "PATCH", "/api/project/status", { body: { example_subject_prompted: true } });
    const { json: projectInit } = await call("/api/project/init", "POST", "/api/project/init", { body: {} });
    // Example data is a plain route, not a job: nothing to submit, nothing to delete below.
    await call("/api/example-data", "GET", "/api/example-data");
    await call("/api/example-data/{dataset_id}/{part_id}", "POST", "/api/example-data/mni152/nifti");
    await call("/api/catalog/subjects", "GET", "/api/catalog/subjects");
    await call("/api/catalog/simulations", "GET", "/api/catalog/simulations?subject=ernie");
    await call("/api/catalog/simulations/{name}", "GET", "/api/catalog/simulations/Thalamus?subject=ernie");
    await call("/api/system", "GET", "/api/system");
    await call("/api/system/storage", "GET", "/api/system/storage");
    await call("/api/system/terminate", "POST", "/api/system/terminate", { body: { pid: 999999 } }); // 404: no such pid, declared

    // catalog (v1)
    await call("/api/catalog/subjects/{id}", "GET", "/api/catalog/subjects/ernie");
    await call("/api/catalog/electrode-overlays", "GET", "/api/catalog/electrode-overlays?subject=ernie&simulation=Thalamus");
    await call("/api/catalog/montages", "GET", "/api/catalog/montages");
    await call("/api/catalog/montages/{net}/{kind}/{name}", "PUT", "/api/catalog/montages/GSN-HydroCel-185/uni_polar/contract_test", {
      body: { pairs: [["E1", "E2"]] },
    });
    await call("/api/catalog/montages/{net}/{kind}/{name}", "DELETE", "/api/catalog/montages/GSN-HydroCel-185/uni_polar/contract_test");
    await call("/api/catalog/eeg-nets", "GET", "/api/catalog/eeg-nets?subject=ernie");
    await call("/api/catalog/atlases", "GET", "/api/catalog/atlases?subject=ernie&kind=cortical");
    await call("/api/catalog/atlases/regions", "GET", "/api/catalog/atlases/regions?subject=ernie&atlas=DK40&hemi=lh");
    await call("/api/catalog/regions", "GET", "/api/catalog/regions?subject=ernie&q=thalamus");
    await call("/api/catalog/nifti/labels", "GET", "/api/catalog/nifti/labels?subject=ernie");
    await call("/api/catalog/rois", "GET", "/api/catalog/rois?subject=ernie");
    await call("/api/catalog/rois", "POST", "/api/catalog/rois?subject=ernie", { body: { name: "contract_test_roi", x: 1, y: 2, z: 3, space: "subject" } });
    await call("/api/catalog/rois/{name}", "DELETE", "/api/catalog/rois/contract_test_roi?subject=ernie");
    await call("/api/catalog/leadfields", "GET", "/api/catalog/leadfields?subject=ernie");
    await call("/api/catalog/flex-runs", "GET", "/api/catalog/flex-runs?subject=ernie");
    await call(
      "/api/catalog/flex-runs/{run}/mapping",
      "GET",
      "/api/catalog/flex-runs/flex_Thalamus_20260810_101500/mapping?subject=ernie&eeg_net=EGI_template",
    );
    await call("/api/catalog/optimization-candidates", "GET", "/api/catalog/optimization-candidates?subject=ernie&kind=flex&run=flex_Thalamus_20260810_101500");
    await call("/api/catalog/optimization-candidates/{candidate_id}", "GET", "/api/catalog/optimization-candidates/trial-2?subject=ernie&kind=flex&run=flex_Thalamus_20260810_101500");
    await call("/api/catalog/optimization-candidates/{candidate_id}/mapping", "GET", "/api/catalog/optimization-candidates/trial-2/mapping?subject=ernie&run=flex_Thalamus_20260810_101500&eeg_net=GSN-HydroCel-185");
    await call("/api/catalog/ex-runs", "GET", "/api/catalog/ex-runs?subject=ernie&kind=ex");
    await call("/api/catalog/ex-runs/{run}/results", "GET", "/api/catalog/ex-runs/ex_L_Insula_20260812_090000/results?subject=ernie&kind=ex");
    await call("/api/catalog/analyses", "GET", "/api/catalog/analyses?subject=ernie&simulation=Thalamus");
    await call("/api/catalog/analyses/{name}/summary", "GET", "/api/catalog/analyses/cortical_2regions_DK40_71a9008a/summary?subject=ernie&simulation=Thalamus");
    await call("/api/catalog/reports", "GET", "/api/catalog/reports?subject=ernie");
    await call("/api/catalog/freehand", "GET", "/api/catalog/freehand?subject=ernie");
    await call("/api/catalog/freehand/{name}", "PUT", "/api/catalog/freehand/contract_test?subject=ernie", {
      body: { type: "U", electrode_positions: [{ x: 1, y: 2, z: 3 }] },
    });
    await call("/api/catalog/freehand/{name}", "DELETE", "/api/catalog/freehand/contract_test?subject=ernie");
    await call("/api/catalog/group", "GET", "/api/catalog/group");
    await call("/api/catalog/notes", "GET", "/api/catalog/notes");
    await call("/api/catalog/notes", "PUT", "/api/catalog/notes", { body: { text: "contract test note" } });
    await call("/api/catalog/overview", "GET", "/api/catalog/overview");
    await call("/api/catalog/project-summary", "GET", "/api/catalog/project-summary");

    // scene (v1) -- the six routes the run pages' 3D panes read (plan of record §2.1). `surface`
    // and `labels` answer `application/octet-stream`, so `call` only checks their declared status;
    // the embedded Tetravox pane requests them as GIfTI (`format=gii`) at runtime.
    await call("/api/scene/manifest", "GET", "/api/scene/manifest?subject=ernie");
    await call("/api/scene/surface", "GET", "/api/scene/surface?subject=ernie&part=gm");
    await call("/api/scene/labels", "GET", "/api/scene/labels?subject=ernie&atlas=DK40");
    await call("/api/scene/regions", "GET", "/api/scene/regions?subject=ernie&atlas=DK40");
    await call("/api/scene/electrodes", "GET", "/api/scene/electrodes?subject=ernie&net=GSN-HydroCel-185");
    await call("/api/scene/volume-legend", "GET", "/api/scene/volume-legend?subject=ernie&id=labeling");

    // caps (v1) -- the EEG caps panel.
    await call("/api/caps/available", "GET", "/api/caps/available?subject=ernie");
    // Caps are named by file name, as `PathManager.list_eeg_caps` names them; the real route 404s a stem.
    // 409, not 404: the name is a known MNI cap and that cap is already on ernie.
    expect((await call("/api/caps/warp", "POST", "/api/caps/warp", { body: { subject: "ernie", caps: ["GSN-HydroCel-185.csv"] } })).res.status).toBe(409);
    await call("/api/caps/upload", "POST", "/api/caps/upload?name=contract_cap.csv", {
      rawBody: new TextEncoder().encode("Electrode,1,2,3,A\n"), headers: { "content-type": "text/csv" },
    });
    const capsInspect = await call("/api/caps/inspect", "GET", "/api/caps/inspect?subject=ernie&net=GSN-HydroCel-185.csv&compare=EGI_template.csv");
    expect(capsInspect.res.status).toBe(200);
    expect((capsInspect.json as { net: string }).net).toBe("GSN-HydroCel-185.csv");

    // The fixed guide (plan R4). None of these takes a subject — that is the point.
    await call("/api/guide/manifest", "GET", "/api/guide/manifest");
    await call("/api/guide/surface", "GET", "/api/guide/surface?part=gm");
    await call("/api/guide/labels", "GET", "/api/guide/labels?atlas=DK40");
    await call("/api/guide/regions", "GET", "/api/guide/regions?atlas=DK40");
    await call("/api/guide/electrodes", "GET", "/api/guide/electrodes?net=GSN-HydroCel-185");

    // schema (v1)
    await call("/api/schema", "GET", "/api/schema");
    await call("/api/schema/{name}", "GET", "/api/schema/SimulationConfig");

    // validate / plan (v1)
    await call("/api/validate/{kind}", "POST", "/api/validate/sim", { body: { config: {} } });
    // analyzer's group mode validates subject_ids, not subject_id
    await call("/api/validate/{kind}", "POST", "/api/validate/analyzer", { body: { config: { mode: "group", subject_ids: ["ernie", "101"] } } });
    await call("/api/plan/{kind}", "POST", "/api/plan/sim", {
      body: {
        config: { subject_id: "ernie" },
        subject_ids: ["ernie"],
        montage_sources: { flex: [{ run: "flex_Thalamus_20260810_101500" }], freehand: [{ name: "custom_4electrode" }] },
      },
    });
    await call("/api/plan/{kind}", "POST", "/api/plan/analyzer", {
      body: { config: { subject_id: "ernie", simulation: "Thalamus", analysis_type: "cortical", atlas: "DK40", field: "TI_max" }, subject_ids: ["ernie"] },
    });

    // jobs (v1)
    await call("/api/jobs", "GET", "/api/jobs");
    const { json: submitted } = await call("/api/jobs", "POST", "/api/jobs", {
      body: { kind: "sim", config: { subject_id: "ernie", __mock_fast: true }, subject_ids: ["ernie"] },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const jobId = (submitted as any).id as string;
    // JobKind.tools (tit/jobs/kinds.py): runs an arbitrary module, not a spec.json pipeline stage.
    const { json: toolsJob } = await call("/api/jobs", "POST", "/api/jobs", {
      body: { kind: "tools", config: { module: "tit.tools.nifti_average", __mock_fast: true }, subject_ids: [] },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await call("/api/jobs/{id}/cancel", "POST", `/api/jobs/${(toolsJob as any).id}/cancel`);
    await call("/api/jobs/preflight", "POST", "/api/jobs/preflight", {
      body: { kind: "analyzer", config: { subject_id: "ernie" }, subject_ids: ["ernie"] },
    });
    const { json: grouped } = await call("/api/jobs/groups", "POST", "/api/jobs/groups", {
      body: { kind: "pre", config: { create_m2m: true, run_tissue_analysis: true, __mock_fast: true }, subject_ids: ["101"] },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const groupJobs = (grouped as any).jobs as { id: string; kind: string }[];
    // create_m2m (G2a) -> run_tissue_analysis (G3, after G2a) -> report (after G3): the per-stage
    // DAG tit.jobs.plans.plan_preprocessing builds, not one job per subject.
    // A report is an attachment of the job that produced it, never a job of its own.
    expect(groupJobs.map((j) => j.kind)).toEqual(["pre", "pre"]);
    const firstGroupJob = groupJobs[0];
    if (!firstGroupJob) throw new Error("expected at least one grouped job");
    const groupJobId = firstGroupJob.id;
    await call("/api/jobs/{id}", "GET", `/api/jobs/${jobId}`);
    await call("/api/jobs/{id}/events", "GET", `/api/jobs/${jobId}/events`);
    await call("/api/jobs/{id}/log", "GET", `/api/jobs/${jobId}/log`);
    await call("/api/jobs/{id}/artifacts", "GET", `/api/jobs/${jobId}/artifacts`);
    await call("/api/jobs/{id}/cancel", "POST", `/api/jobs/${groupJobId}/cancel`);
    await waitForState(jobId, ["succeeded", "failed"]);
    const { json: rerun } = await call("/api/jobs/{id}/rerun", "POST", `/api/jobs/${jobId}/rerun`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rerunId = (rerun as any).id as string;
    await call("/api/jobs/{id}/force", "POST", `/api/jobs/${rerunId}/force`);
    await call("/api/jobs/{id}", "DELETE", `/api/jobs/${rerunId}`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await call("/api/jobs/{id}", "DELETE", `/api/jobs/${(projectInit as any).id}`);

    // viewers (v1) -- D3 (docs/dev/DECISIONS.md § 2026-09-03 (One Docker image and a real development loop)): no more Freeview/Gmsh launch
    // routes to exercise here (removed from the contract along with the routes); GET
    // /api/view/{kind} now returns a real Tetravox ViewSpec v2 `scene`, and POST /api/view/args
    // (deliberately not declared in the contract -- see its yaml comment) is covered directly by
    // its own vitest in server.test.ts / tit's own tests/test_catalog_v1.py.
    await call("/api/view/{kind}", "GET", "/api/view/subject?subject=ernie");
    // V2 (docs/dev/DECISIONS.md § 2026-09-06 (Native panes, job rows and notebooks)): the scene file the host-installed
    // Tetravox app opens.
    await call("/api/view/open", "POST", "/api/view/open", { body: { kind: "subject", subject: "ernie" } });
    // VM: saved compositions. The path is /api/viewer/presets, not /api/view/presets, because the
    // latter is shadowed by GET /api/view/{kind}.
    await call("/api/viewer/presets/{name}", "PUT", "/api/viewer/presets/contract", {
      body: { name: "contract", selection: { kind: "subject", subject: "ernie" }, extras: [], overrides: {} },
    });
    await call("/api/viewer/presets", "GET", "/api/viewer/presets");
    await call("/api/viewer/candidates", "GET", "/api/viewer/candidates?subject=ernie&simulation=Thalamus");
    await call("/api/viewer/presets/{name}", "DELETE", "/api/viewer/presets/contract");

    // The composition tree, and the two things a person can keep: what they chose (a composition)
    // and what they were looking at (a scene, in Tetravox's own format).
    await call("/api/viewer/tree", "GET", "/api/viewer/tree?subject=ernie&space=subject&simulations=Thalamus");
    await call("/api/viewer/compositions/{name}", "PUT", "/api/viewer/compositions/contract", {
      body: { subject: "ernie", space: "subject", inputs: ["/mnt/example/T1.nii.gz"], simulations: ["Thalamus"] },
    });
    await call("/api/viewer/compositions", "GET", "/api/viewer/compositions");
    await call("/api/viewer/compositions/{name}", "DELETE", "/api/viewer/compositions/contract");

    await call("/api/viewer/scenes/suggest/name", "GET", "/api/viewer/scenes/suggest/name?subject=ernie&simulation=Thalamus&field=TI_max");
    await call("/api/viewer/scenes/{name}/native-destination", "POST", "/api/viewer/scenes/contract/native-destination");
    await call("/api/viewer/scenes/{name}", "PUT", "/api/viewer/scenes/contract", {
      body: { scene: { version: 2, datasets: [], layers: [{ id: "L0", kind: "volume" }] }, subject: "ernie" },
    });
    await call("/api/viewer/scenes", "GET", "/api/viewer/scenes");
    await call("/api/viewer/scenes/{name}", "GET", "/api/viewer/scenes/contract");
    await call("/api/viewer/scenes/{name}", "DELETE", "/api/viewer/scenes/contract");

    // files (v1)
    await call("/api/files/report/{id}", "GET", "/api/files/report/ernie/simulation_report_20260801_110000");
    const artifactPath = encodeURIComponent("/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Mesh/cortical_2regions_DK40_71a9008a/results.csv");
    await call("/api/files/artifact", "GET", `/api/files/artifact?path=${artifactPath}`);
    await call("/api/files/text", "GET", `/api/files/text?path=${artifactPath}&tail=2`);
    await call("/api/files/csv", "GET", `/api/files/csv?path=${artifactPath}`);
    const { json: uploadedMask } = await call("/api/files/mask", "POST", "/api/files/mask?subject=ernie&name=target.nii", {
      rawBody: new Uint8Array([1, 2, 3]), headers: { "content-type": "application/octet-stream" },
    });
    expect(uploadedMask).toEqual({ path: "/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/masks/target.nii" });

    // The in-app viewer's byte source. Without TIT_MOCK_DATA_ROOT (the CI default) there are no
    // real volumes to stream, so this is the declared 404 -- the point of the call is that the
    // route exists and is covered, which the exercised-vs-declared assertion below demands.
    await call(
      "/api/files/raw/{path}",
      "GET",
      "/api/files/raw/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz",
    );

    await call("/api/view/export", "POST", "/api/view/export", { body: { scene: { version: 2, datasets: [], layers: [] }, name: "contract" } });

    // notebooks and kernels (v1) -- NB lane, ARCHITECTURE §7.6. The order is the
    // lifecycle: create a notebook, read it, save it, start a kernel, drive it,
    // then take both away again.
    await call("/api/notebooks", "POST", "/api/notebooks", { body: { name: "contract" } });
    await call("/api/notebooks", "GET", "/api/notebooks");
    const { json: contractNb } = await call("/api/notebooks/{name}", "GET", "/api/notebooks/contract.ipynb");
    await call("/api/notebooks/{name}", "PUT", "/api/notebooks/contract.ipynb", {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      body: { content: (contractNb as any).content },
    });
    await call("/api/notebooks/{name}", "DELETE", "/api/notebooks/contract.ipynb");
    const { json: contractKernel } = await call("/api/kernels", "POST", "/api/kernels", { body: {} });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kernelId = (contractKernel as any).id as string;
    await call("/api/kernels", "GET", "/api/kernels");
    await call("/api/kernels/{kernel_id}/interrupt", "POST", `/api/kernels/${kernelId}/interrupt`);
    await call("/api/kernels/{kernel_id}/restart", "POST", `/api/kernels/${kernelId}/restart`);
    await call("/api/kernels/{kernel_id}", "DELETE", `/api/kernels/${kernelId}`);

    await call("/api/scene/target-preview", "POST", "/api/scene/target-preview", {
      body: { subject: "ernie", roi: { kind: "spherical", space: "subject", spheres: [{ center: [0, 0, 0], radius: 10 }] } },
    });

    // settings (v1)
    await call("/api/cpu-limit", "GET", "/api/cpu-limit");
    await call("/api/cpu-limit", "PUT", "/api/cpu-limit", { body: { percent: 50 } });
    await call("/api/surfer-settings", "GET", "/api/surfer-settings");
    await call("/api/surfer-settings", "PUT", "/api/surfer-settings", { body: { fastsurfer_threads: 4, freesurfer_threads: null } });
    await call("/api/surfer-settings/freesurfer-license", "PUT", "/api/surfer-settings/freesurfer-license", { body: { text: "someone@example.org\n12345\n *Ab1cD2eF3gH\n FSabc123DEF456" } });
    await call("/api/surfer-settings/freesurfer-license", "DELETE", "/api/surfer-settings/freesurfer-license");
    await call("/api/settings", "GET", "/api/settings");
    await call("/api/settings", "PUT", "/api/settings", { body: { theme: "dark", panels: [], telemetry: { consented: true, enabled: false } } });

    // agent proposals (v1): propose -> edit -> approve (a job is queued as `agent`) -> run is 409;
    // a second proposal is rejected.
    const step = { id: "sim", kind: "sim", subject_ids: ["ernie"], config: { montages: [] } };
    const { json: created } = await call("/api/proposals", "POST", "/api/proposals", { body: { title: "Simulate", steps: [step], client: "Claude Code" } });
    const pid = (created as { id: string }).id;
    await call("/api/proposals", "GET", "/api/proposals");
    await call("/api/proposals/{id}", "GET", `/api/proposals/${pid}`);
    await call("/api/proposals/{id}/steps/{step_id}", "PATCH", `/api/proposals/${pid}/steps/sim`, { body: { overwrite: true } });
    const { json: approved } = await call("/api/proposals/{id}/approve", "POST", `/api/proposals/${pid}/approve`, { body: {} });
    const [agentJobId] = (approved as { steps: { job_ids: string[] }[] }).steps[0]!.job_ids;
    const { json: queued } = await call("/api/jobs/{id}", "GET", `/api/jobs/${agentJobId}`);
    expect((queued as { status: { created_by: string } }).status.created_by).toBe("agent");
    const run = await call("/api/proposals/{id}/steps/{step_id}/run", "POST", `/api/proposals/${pid}/steps/sim/run`);
    expect(run.res.status).toBe(409);
    const { json: other } = await call("/api/proposals", "POST", "/api/proposals", { body: { title: "Other", steps: [step] } });
    const { json: rejected } = await call("/api/proposals/{id}/reject", "POST", `/api/proposals/${(other as { id: string }).id}/reject`, { body: { note: "no" } });
    expect((rejected as { status: string }).status).toBe("rejected");
    const otherId = (other as { id: string }).id;
    expect((await call("/api/proposals/{id}/dismiss", "POST", `/api/proposals/${pid}/dismiss`)).res.status).toBe(409);
    await call("/api/proposals/{id}/dismiss", "POST", `/api/proposals/${otherId}/dismiss`);
    const { json: listed } = await call("/api/proposals", "GET", "/api/proposals?include_dismissed=true");
    expect((listed as { id: string }[]).map((x) => x.id)).toContain(otherId);
    await call("/api/sim-from-flex", "GET", "/api/sim-from-flex?subject=ernie");

    // Logged out last (Bearer auth, not the cookie session, so nothing above depended on it).
    await call("/auth/logout", "POST", "/auth/logout");

    const declared = new Set<string>();
    for (const [pathTemplate, methods] of Object.entries(spec.paths as Record<string, Record<string, unknown>>)) {
      for (const method of Object.keys(methods)) {
        if (!["get", "post", "put", "delete", "patch"].includes(method)) continue;
        declared.add(`${method.toUpperCase()} ${pathTemplate}`);
      }
    }
    // Real WebSocket upgrades aren't plain fetch()able; covered by the dedicated tests below.
    declared.delete("GET /ws/system");
    declared.delete("GET /ws/jobs");
    declared.delete("GET /ws/kernels/{kernel_id}");
    // The real server keeps this route, but the desktop stopped reading it when R1 deleted the
    // Subject Info page, so the mock does not serve it. Pinned below: no renderer source asks for it.
    declared.delete("GET /api/catalog/subject-info");
    expect([...exercised].sort()).toEqual([...declared].sort());
  }, 20_000);

  it("leaves out only routes the desktop never reads", () => {
    const rendererDir = join(__dirname, "..", "..", "src", "renderer");
    // The generated contract types name every route; a reader is any other renderer source.
    const sources = (readdirSync(rendererDir, { recursive: true }) as string[]).filter(
      (file) => /\.(ts|tsx)$/.test(file) && !file.endsWith("schema.d.ts"),
    );
    expect(sources.length).toBeGreaterThan(100);
    const readers = sources.filter((file) => readFileSync(join(rendererDir, file), "utf8").includes("/api/catalog/subject-info"));
    expect(readers).toEqual([]);
  });
});

// --------------------------------------------------------------------- parity with the real server
// Expected values are read from the real server's source, not retyped: a report's CSP from
// tit/server/routes/files.py, the report kinds from tit/catalog.py, the candidate montage name
// from the real `candidate_detail` output (fixtures/contracts/, dev/make_contract_fixtures.py).
const repoFile = (...parts: string[]) => readFileSync(join(__dirname, "..", "..", "..", ...parts), "utf8");
const fixture = <T,>(...parts: string[]): T => JSON.parse(readFileSync(join(__dirname, "..", "fixtures", ...parts), "utf8")) as T;

/** `REPORT_CSP = ("..." "...")` in files.py: the adjacent string literals, joined. */
function realReportCsp(): string {
  const block = /^REPORT_CSP = \(([\s\S]*?)^\)/m.exec(repoFile("tit", "server", "routes", "files.py"));
  if (!block) throw new Error("REPORT_CSP not found in tit/server/routes/files.py");
  const literals = [...block[1]!.matchAll(/"([^"]*)"/g)].map((m) => m[1]);
  expect(literals.length).toBeGreaterThan(0);
  return literals.join("");
}
/** `_REPORT_KIND_TITLES = {...}` in catalog.py, as kind -> title. */
function realReportKinds(): Record<string, string> {
  const block = /^_REPORT_KIND_TITLES = \{([\s\S]*?)^\}/m.exec(repoFile("tit", "catalog.py"));
  if (!block) throw new Error("_REPORT_KIND_TITLES not found in tit/catalog.py");
  return Object.fromEntries([...block[1]!.matchAll(/"([a-z_]+)":\s*"([^"]+)"/g)].map((m) => [m[1]!, m[2]!]));
}

type ReportRow = { id: string; kind: string; title: string; path: string; created: string };
describe("mock reports match the real server's", () => {
  const reports = fixture<Record<string, ReportRow[]>>("reports.json");
  const all = Object.entries(reports).flatMap(([sid, rows]) => rows.map((r) => ({ sid, ...r })));

  it("serves a report under the real REPORT_CSP, unaltered and unsniffable", async () => {
    const csp = realReportCsp();
    expect(csp).toContain("script-src 'unsafe-inline'");
    expect(csp).toContain("sandbox allow-scripts");
    for (const { id, sid } of all) {
      // Both spellings the real `{report_id:path}` route takes: the slash encoded and plain.
      for (const url of [`/api/files/report/${encodeURIComponent(id)}`, `/api/files/report/${id}`]) {
        const res = await fetch(`${BASE}${url}`, { headers: { authorization: `Bearer ${TOKEN}` } });
        expect(res.status, url).toBe(200);
        expect(res.headers.get("content-security-policy")).toBe(csp);
        expect(res.headers.get("x-content-type-options")).toBe("nosniff");
        const body = await res.text();
        expect(body).toBe(readFileSync(join(__dirname, "..", "fixtures", "reports", sid, `${id.split("/")[1]}.html`), "utf8"));
      }
    }
    const missing = await fetch(`${BASE}/api/files/report/ernie/simulation_report_19990101_000000`, { headers: { authorization: `Bearer ${TOKEN}` } });
    expect(missing.status).toBe(404);
  });

  it("lists ids, kinds, titles and paths in the real catalog's grammar", () => {
    const kinds = realReportKinds();
    expect(Object.keys(kinds)).toContain("simulation_report");
    expect(all.length).toBeGreaterThan(0);
    for (const r of all) {
      expect(r.id).toMatch(new RegExp(`^${r.sid}/(charm_report|(simulation_report|flex_search_report|ex_search_report|dti_qc)_\\d{8}_\\d{6})$`));
      expect(Object.keys(kinds)).toContain(r.kind);
      expect(r.id.split("/")[1]!.startsWith(r.kind)).toBe(true);
      // Every mock report is a simulation or ex-search page, whose <title> names its run; the
      // real catalog lists such a report by that title (tit/catalog.py, _report_entry_title).
      const page = readFileSync(join(__dirname, "..", "fixtures", "reports", r.sid, `${r.id.split("/")[1]}.html`), "utf8");
      const pageTitle = /<title>([^<]+)<\/title>/.exec(page)?.[1];
      expect(pageTitle).toMatch(r.kind === "ex_search_report" ? / ex-search$/ : / simulation$/);
      expect(r.title).toBe(pageTitle);
      expect(r.path).toBe(`/mnt/example/derivatives/ti-toolbox/reports/sub-${r.sid}/${r.id.split("/")[1]}.html`);
    }
  });

  it("links every simulation's report_ids to a listed simulation report of its subject", () => {
    const simulations = fixture<Record<string, { name: string; report_ids: string[] }[]>>("simulations.json");
    let linked = 0;
    for (const [sid, sims] of Object.entries(simulations)) {
      for (const sim of sims) {
        for (const id of sim.report_ids) {
          const row = (reports[sid] ?? []).find((r) => r.id === id);
          expect(row, `${sid}/${sim.name} -> ${id}`).toBeDefined();
          expect(row!.kind).toBe("simulation_report");
          linked += 1;
        }
      }
    }
    expect(linked).toBeGreaterThan(0);
  });

  it("records a finished simulation job's report under the subject's reports folder", async () => {
    const { json: submitted } = await call("/api/jobs", "POST", "/api/jobs", {
      body: { kind: "sim", config: { subject_id: "ernie", __mock_fast: true }, subject_ids: ["ernie"] },
    });
    const id = (submitted as { id: string }).id;
    // The agent-approved sim job of the coverage test (not __mock_fast) may still hold the slot.
    expect((await waitForState(id, ["succeeded", "failed"], 25_000)).status.state).toBe("succeeded");
    const { json: artifacts } = await call("/api/jobs/{id}/artifacts", "GET", `/api/jobs/${id}/artifacts`);
    const files = (artifacts as { files: { path: string; kind: string }[] }).files;
    const reportFiles = files.filter((f) => f.kind === "report");
    expect(reportFiles).toHaveLength(1);
    expect(reportFiles[0]!.path).toMatch(/^\/mnt\/example\/derivatives\/ti-toolbox\/reports\/sub-ernie\/simulation_report_\d{8}_\d{6}\.html$/);
  }, 30_000);
});

describe("mock candidate detail is the real candidate_detail", () => {
  for (const kind of ["flex", "ex", "mex"]) {
    it(`${kind}: the mock resolves the generated request to the server's exact simulation_config`, async () => {
      const { request, response } = fixture<{
        request: { subject: string; kind: string; run: string; candidate_id: string };
        response: { simulation_config: Record<string, unknown> };
      }>("contracts", `candidate_detail_${kind}.json`);
      const query = new URLSearchParams({ subject: request.subject, kind: request.kind, run: request.run });
      const { res, json } = await call(
        "/api/catalog/optimization-candidates/{candidate_id}",
        "GET",
        `/api/catalog/optimization-candidates/${encodeURIComponent(request.candidate_id)}?${query}`,
      );
      expect(res.status).toBe(200);
      expect((json as { simulation_config: unknown }).simulation_config).toStrictEqual(response.simulation_config);
    });
  }
});

// The real `POST /api/plan/analyzer` answers (fixtures/contracts/analyzer_plans.json,
// dev/make_contract_fixtures.py): the folder PathManager.analysis_output_dir names for each config,
// whether it exists and whether running replaces it. The held cases are the analyses the mock's
// catalog lists (fixtures/analyses.json, the real catalog's listing of those same folders).
type AnalyzerPlanCase = {
  id: string;
  subject_ids: string[];
  held: boolean;
  config: Record<string, unknown>;
  jobs: { subject: string; output_dir: string; exists: boolean; will_overwrite: boolean }[];
};
describe("the mock plans an analysis where the real route does", () => {
  const { cases } = fixture<{ cases: AnalyzerPlanCase[] }>("contracts", "analyzer_plans.json");
  const analyses = fixture<Record<string, Record<string, { name: string; csv: string }[]>>>("analyses.json");

  it("covers the held analyses and every piece of the name grammar", () => {
    const held = Object.values(analyses).flatMap((perSim) => Object.values(perSim).flat());
    expect(cases.filter((c) => c.held)).toHaveLength(held.length);
    expect(held.length).toBeGreaterThanOrEqual(4);
    // One folder name per grammar branch: a sphere in each space, cortical one/many/unsafe,
    // subcortical, whole head, a NIfTI mask, a field and a tissue suffix, an explicit folder.
    const names = cases.map((c) => c.jobs[0]!.output_dir.split("/").pop()!);
    for (const pattern of [/^sphere_.*_subject$/, /^sphere_.*_MNI$/, /^cortical_lh\./, /^cortical_\dregions_/, /^cortical_.*_[0-9a-f]{8}$/, /^subcortical_/, /^whole_head_/, /^cortical_mask_/, /_hf_peak$/, /_WM$/, /_both$/]) {
      expect(names.some((n) => pattern.test(n)), String(pattern)).toBe(true);
    }
  });

  async function mockPlan(c: AnalyzerPlanCase) {
    const { res, json } = await call("/api/plan/{kind}", "POST", "/api/plan/analyzer", { body: { config: c.config, subject_ids: c.subject_ids } });
    expect(res.status).toBe(200);
    return (json as { jobs: Record<string, unknown>[] }).jobs.map(({ subject, output_dir, exists, will_overwrite }) => ({ subject, output_dir, exists, will_overwrite }));
  }
  const perSubject = (jobs: { subject: unknown }[]) => jobs.filter((j) => j.subject !== "");

  for (const c of cases) {
    it(`${c.id}: same folder, existence and overwrite as the real plan`, async () => {
      expect(perSubject(c.jobs)).toHaveLength(c.subject_ids.length);
      expect(perSubject(await mockPlan(c))).toStrictEqual(perSubject(c.jobs));
    });
  }

  // KNOWN GAP (reported): a group run's real plan adds the cohort summary job (subject "", the
  // config's output_dir, or a timestamped group_analysis/<group_run_name>_<stamp>). The mock plans
  // only the per-subject jobs. Flip to `it` when the mock plans it.
  it.fails("group_output_dir: the mock also plans the cohort summary job", async () => {
    const group = cases.find((c) => c.id === "group_output_dir")!;
    expect(group.jobs.some((j) => j.subject === "")).toBe(true);
    expect(await mockPlan(group)).toStrictEqual(group.jobs);
  });

  it("a held analysis is listed by the mock catalog in the folder the mock plans for it", async () => {
    for (const c of cases.filter((x) => x.held)) {
      const sim = c.config.simulation as string;
      const { json } = await call("/api/catalog/analyses", "GET", `/api/catalog/analyses?subject=${c.subject_ids[0]}&simulation=${sim}`);
      const folders = (json as { csv: string }[]).map((a) => a.csv.slice(0, a.csv.lastIndexOf("/")));
      expect(folders, c.id).toContain(c.jobs[0]!.output_dir);
    }
  });

  it("an existing analysis needs an explicit overwrite to be submitted again", async () => {
    // `check_overwrite_permission` 409s a plan with `will_overwrite`. Plain fetch: openapi.yaml
    // does not declare the 409 the real POST /api/jobs answers (reported, not owned here). No job
    // is created, so the lifecycle tests below keep the queue to themselves.
    const held = cases.find((c) => c.held)!;
    const refused = await fetch(`${BASE}/api/jobs`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
      body: JSON.stringify({ kind: "analyzer", config: held.config, subject_ids: held.subject_ids }),
    });
    expect(refused.status).toBe(409);
    expect(((await refused.json()) as { detail: string }).detail).toContain(held.jobs[0]!.output_dir);
  });
});

describe("contract: job lifecycle", () => {
  it("submit -> events -> succeeded", async () => {
    const { json: submitted } = await call("/api/jobs", "POST", "/api/jobs", {
      body: { kind: "analyzer", config: { subject_id: "ernie", __mock_fast: true }, subject_ids: ["ernie"] },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const id = (submitted as any).id as string;
    const { status } = await waitForState(id, ["succeeded", "failed"]);
    expect(status.state).toBe("succeeded");
    // A finished job keeps what it cost (JobStatus.cpu_percent_peak/_avg, rss_peak/_avg): the
    // peak bounds the average and both are sampled over the run, never left null once it ran.
    expect(status.cpu_percent_peak).toBeGreaterThan(0);
    expect(status.cpu_percent_avg).toBeGreaterThan(0);
    expect(status.cpu_percent_avg).toBeLessThanOrEqual(status.cpu_percent_peak ?? 0);
    expect(status.rss_peak).toBeGreaterThan(0);
    expect(status.rss_avg).toBeLessThanOrEqual(status.rss_peak ?? 0);
    const { json: events } = await call("/api/jobs/{id}/events", "GET", `/api/jobs/${id}/events`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const types = (events as any[]).map((e) => e.type);
    expect(types).toContain("result");
    expect(types).toContain("exit");
    const log = await (await fetch(`${BASE}/api/jobs/${id}/log`, { headers: { authorization: `Bearer ${TOKEN}` } })).text();
    expect(log.length).toBeGreaterThan(0);
  }, 10_000);

  it("submit a slow job, cancel it, and see it end cancelled without finishing", async () => {
    const { json: submitted } = await call("/api/jobs", "POST", "/api/jobs", {
      // A complete SimulationConfig: both routes now reject one whose schema-required fields
      // are missing, the way the real backend's `tit/jobs/config_check.py` does.
      body: {
        kind: "sim",
        config: { subject_id: "101", montages: [{ _type: "Montage", name: "m1", mode: "net", electrode_pairs: [["E1", "E2"]] }] },
        subject_ids: ["101"],
      },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const id = (submitted as any).id as string;
    const { json: cancelled } = await call("/api/jobs/{id}/cancel", "POST", `/api/jobs/${id}/cancel`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((cancelled as any).state).toBe("cancelled");
    await new Promise((r) => setTimeout(r, 200));
    const { json: after } = await call("/api/jobs/{id}", "GET", `/api/jobs/${id}`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((after as any).status.state).toBe("cancelled");
  });
});

describe("contract: auth", () => {
  it("401s an unauthenticated /api/ request", async () => {
    const res = await fetch(`${BASE}/api/version`);
    expect(res.status).toBe(401);
  });
});

describe("contract: WebSocket upgrades", () => {
  function upgradeStatus(path: string, headers: Record<string, string>): Promise<number> {
    return new Promise((resolve, reject) => {
      const req = httpRequest({
        host: "127.0.0.1",
        port: PORT,
        path,
        headers: {
          connection: "Upgrade",
          upgrade: "websocket",
          "sec-websocket-version": "13",
          "sec-websocket-key": Buffer.from("0123456789abcdef").toString("base64"),
          ...headers,
        },
      });
      req.on("upgrade", (res: { statusCode?: number }, socket: { destroy: () => void }) => {
        socket.destroy();
        resolve(res.statusCode ?? 0);
      });
      req.on("response", (res: { statusCode?: number; resume: () => void }) => {
        res.resume();
        resolve(res.statusCode ?? 0);
      });
      req.on("error", reject);
      req.end();
    });
  }
  it("/ws/system and /ws/jobs both switch protocols for an authenticated request", async () => {
    expect(declaredStatuses("/ws/system", "GET")).toContain(101);
    expect(declaredStatuses("/ws/jobs", "GET")).toContain(101);
    expect(await upgradeStatus("/ws/system", { authorization: `Bearer ${TOKEN}` })).toBe(101);
    expect(await upgradeStatus("/ws/jobs", { authorization: `Bearer ${TOKEN}` })).toBe(101);
  });
});
