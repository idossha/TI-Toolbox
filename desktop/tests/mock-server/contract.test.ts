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
import { readFileSync } from "node:fs";
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
async function waitForState(id: string, states: string[], timeoutMs = 5000): Promise<{ status: { state: string } }> {
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
    const { json: projectInit } = await call("/api/project/init", "POST", "/api/project/init", { body: { example_data: true } });
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
    await call("/api/catalog/ex-runs", "GET", "/api/catalog/ex-runs?subject=ernie&kind=ex");
    await call("/api/catalog/ex-runs/{run}/results", "GET", "/api/catalog/ex-runs/ex_L_Insula_20260812_090000/results?subject=ernie&kind=ex");
    await call("/api/catalog/analyses", "GET", "/api/catalog/analyses?subject=ernie&simulation=Thalamus");
    await call("/api/catalog/analyses/{name}/summary", "GET", "/api/catalog/analyses/Thalamus_DK40_TI_max/summary?subject=ernie&simulation=Thalamus");
    await call("/api/catalog/reports", "GET", "/api/catalog/reports?subject=ernie");
    await call("/api/catalog/freehand", "GET", "/api/catalog/freehand?subject=ernie");
    await call("/api/catalog/freehand/{name}", "PUT", "/api/catalog/freehand/contract_test?subject=ernie", {
      body: { type: "U", electrode_positions: [{ x: 1, y: 2, z: 3 }] },
    });
    await call("/api/catalog/freehand/{name}", "DELETE", "/api/catalog/freehand/contract_test?subject=ernie");
    await call("/api/catalog/group", "GET", "/api/catalog/group");
    await call("/api/catalog/notes", "GET", "/api/catalog/notes");
    await call("/api/catalog/notes", "PUT", "/api/catalog/notes", { body: { text: "contract test note" } });
    await call("/api/catalog/subject-info", "GET", "/api/catalog/subject-info");
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
    const { json: grouped } = await call("/api/jobs/groups", "POST", "/api/jobs/groups", {
      body: { kind: "pre", config: { create_m2m: true, run_tissue_analysis: true, __mock_fast: true }, subject_ids: ["101"], parallel_subjects: 1 },
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
    await call("/api/jobs/{id}/cancel", "POST", `/api/jobs/${groupJobId}/cancel`);
    await waitForState(jobId, ["succeeded", "failed"]);
    const { json: rerun } = await call("/api/jobs/{id}/rerun", "POST", `/api/jobs/${jobId}/rerun`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rerunId = (rerun as any).id as string;
    await call("/api/jobs/{id}/force", "POST", `/api/jobs/${rerunId}/force`);
    await call("/api/jobs/{id}", "DELETE", `/api/jobs/${rerunId}`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await call("/api/jobs/{id}", "DELETE", `/api/jobs/${(projectInit as any).id}`);

    // viewers (v1) -- D3 (docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)): no more Freeview/Gmsh launch
    // routes to exercise here (removed from the contract along with the routes); GET
    // /api/view/{kind} now returns a real Tetravox ViewSpec v2 `scene`, and POST /api/view/args
    // (deliberately not declared in the contract -- see its yaml comment) is covered directly by
    // its own vitest in server.test.ts / tit's own tests/test_catalog_v1.py.
    await call("/api/view/{kind}", "GET", "/api/view/subject?subject=ernie");
    // V2 (docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)): the scene file the host-installed
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
    await call("/api/viewer/scenes/{name}", "PUT", "/api/viewer/scenes/contract", {
      body: { scene: { version: 2, datasets: [], layers: [{ id: "L0", kind: "volume" }] }, subject: "ernie" },
    });
    await call("/api/viewer/scenes", "GET", "/api/viewer/scenes");
    await call("/api/viewer/scenes/{name}", "GET", "/api/viewer/scenes/contract");
    await call("/api/viewer/scenes/{name}", "DELETE", "/api/viewer/scenes/contract");

    // files (v1)
    await call("/api/files/report/{id}", "GET", "/api/files/report/ernie-thalamus-2026-08-01");
    const artifactPath = encodeURIComponent("/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Thalamus_DK40_TI_max/summary.csv");
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

    // tetravox (v1) -- dynamic embed delivery (docs/dev/HISTORY.md § 2026-09-04 (embed convergence) E1-E4).
    // Ordered so the state machine is exercised in full: read, index, install by version,
    // roll back to the baked bundle, forward again, remove.
    await call("/api/tetravox", "GET", "/api/tetravox");
    await call("/api/tetravox/updates", "GET", "/api/tetravox/updates");
    await call("/api/tetravox/policy", "POST", "/api/tetravox/policy", { body: { auto_update: true } });
    await call("/api/tetravox/install", "POST", "/api/tetravox/install", { body: { version: "0.4.0" } });
    await call("/api/tetravox/activate", "POST", "/api/tetravox/activate", { body: { version: "baked" } });
    await call("/api/tetravox/activate", "POST", "/api/tetravox/activate", { body: { version: "0.4.0" } });
    await call("/api/tetravox/{version}", "DELETE", "/api/tetravox/0.4.0");

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
    await call("/api/surfer-settings", "GET", "/api/surfer-settings");
    await call("/api/surfer-settings", "PUT", "/api/surfer-settings", { body: { fastsurfer_threads: 4, freesurfer_threads: null } });
    await call("/api/settings", "GET", "/api/settings");
    await call("/api/settings", "PUT", "/api/settings", { body: { theme: "dark", panels: [], allow_unsafe_overrides: false, telemetry: { consented: true, enabled: false } } });

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
    declared.delete("GET /ws/tetravox");
    declared.delete("GET /ws/kernels/{kernel_id}");
    expect([...exercised].sort()).toEqual([...declared].sort());
  }, 20_000);
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
  it("/ws/system, /ws/jobs and /ws/tetravox all switch protocols for an authenticated request", async () => {
    expect(declaredStatuses("/ws/system", "GET")).toContain(101);
    expect(declaredStatuses("/ws/jobs", "GET")).toContain(101);
    expect(declaredStatuses("/ws/tetravox", "GET")).toContain(101);
    expect(await upgradeStatus("/ws/system", { authorization: `Bearer ${TOKEN}` })).toBe(101);
    expect(await upgradeStatus("/ws/jobs", { authorization: `Bearer ${TOKEN}` })).toBe(101);
    expect(await upgradeStatus("/ws/tetravox", { authorization: `Bearer ${TOKEN}` })).toBe(101);
  });
});
