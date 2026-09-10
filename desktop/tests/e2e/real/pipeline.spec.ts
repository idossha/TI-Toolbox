/**
 * D6's real-container gate: a **two-node** `sim -> analyzer` pipeline on `sub-ernie` runs end to
 * end as one job group.
 *
 * Two nodes, not four, and deliberately so: this row costs a real FEM simulation (~16 min under
 * emulation on this machine), and the rule from `docs/dev/CONTRIBUTING.md` §2.6 is that no two
 * FEM simulations run at once on the shared container. The four-node graph, the `after` chain and
 * the notebook export are all asserted against the mock in `tests/e2e/pipeline.spec.ts`; what only
 * a real server can prove is that the jobs the pipeline plans *actually run*, in order, with the
 * simulation name the Analyzer node was bound to.
 *
 * The montage is inlined into the `sim` node's own config under a `pc-real-<runid>` name (the same
 * convention `tests/smoke/payloads/sim.json` uses), so nothing in the shared project's
 * `montage_list.json` is touched and the outputs are trivially identifiable for cleanup.
 *
 * Offscreen by default (`feedback_e2e_no_monitor_hijack`); the UI half only asserts that the page
 * renders the receipt for this document, because the run itself is watched over the API.
 */
import { existsSync, rmSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { PROJECT_HOST_ROOT, connectReal, expectPage, gotoPage, launchElectronApp, waitForJobTerminal } from "../_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? String(Date.now()).slice(-6);
const SIM_NAME = `pc-real-${RUN_ID}`;
const SIM_DIR = join(PROJECT_HOST_ROOT, "derivatives/SimNIBS/sub-ernie/Simulations", SIM_NAME);

const DOC = {
  version: 1,
  name: SIM_NAME,
  nodes: [
    {
      id: "sim1",
      kind: "sim",
      position: { x: 0, y: 0 },
      config: {
        subject_ids: ["ernie"],
        montages: [
          {
            _type: "Montage",
            name: SIM_NAME,
            mode: "net",
            electrode_pairs: [
              ["E034", "E020"],
              ["E095", "E070"],
            ],
            eeg_net: "GSN-HydroCel-185.csv",
          },
        ],
        conductivity: "scalar",
        intensities: [1, 1],
        electrode_shape: "ellipse",
        electrode_dimensions: [8, 8],
        gel_thickness: 4,
        output_fields: ["TI_max"],
      },
    },
    {
      id: "an1",
      kind: "analyzer",
      position: { x: 320, y: 0 },
      config: {
        space: "mesh",
        analysis_type: "spherical",
        center: [-10, -18, 9],
        radius: 10,
        coordinate_space: "subject",
      },
    },
  ],
  edges: [
    { from: "sim1", to: "an1", port: "subjects" },
    { from: "sim1", to: "an1", port: "simulation" },
  ],
};

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${SERVER_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}`, ...(init?.headers ?? {}) },
  });
  return { status: response.status, body: await response.json() };
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-pipeline-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  if (existsSync(SIM_DIR)) {
    rmSync(SIM_DIR, { recursive: true, force: true });
    console.log(`real/pipeline: removed ${SIM_DIR}`);
  }
  await app?.close();
});

test("the Pipeline page loads against the real server", async () => {
  await gotoPage(page, "pipeline", "Pipeline");
  await expectPage(page, "pipeline");
  await expect(page.getByTestId("pipeline-canvas")).toBeVisible();
});

test("validate binds the Analyzer's simulation name to the Simulator's montage", async () => {
  const { status, body } = await api("/api/pipelines/validate", { method: "POST", body: JSON.stringify(DOC) });
  expect(status).toBe(200);
  const validation = body as { ok: boolean; jobs: { label: string; kind: string; after: string[] }[] };
  expect(validation.ok).toBe(true);
  // Two jobs, no resolve step: this Simulator names its own montage, so the simulation name the
  // Analyzer needs is knowable at submit time.
  expect(validation.jobs.map((j) => j.label)).toEqual(["sim1:0", "an1:0"]);
  expect(validation.jobs[1]!.after).toEqual(["sim1:0"]);
});

test("the whole pipeline runs as one group and completes", async () => {
  test.setTimeout(45 * 60_000);

  const run = await api("/api/pipelines/run", {
    method: "POST",
    body: JSON.stringify({ pipeline: DOC, parallel_subjects: 1 }),
  });
  expect(run.status).toBe(201);
  const result = run.body as { group_id: string; pipeline: string; jobs: { id: string; kind: string; group_id: string }[] };

  expect(result.pipeline).toBe(SIM_NAME);
  expect(result.jobs).toHaveLength(2);
  expect(new Set(result.jobs.map((j) => j.group_id))).toEqual(new Set([result.group_id]));

  const [simJob, analyzerJob] = result.jobs;
  expect(simJob!.kind).toBe("sim");
  expect(analyzerJob!.kind).toBe("analyzer");

  // The binding, as the server actually stamped it on the analyzer's spec.
  const detail = await api(`/api/jobs/${analyzerJob!.id}`);
  const spec = (detail.body as { spec: { config: Record<string, unknown>; after?: string[] } }).spec;
  expect(spec.config.simulation).toBe(SIM_NAME);
  expect(spec.after).toEqual([simJob!.id]);

  const sim = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: simJob!.id, timeoutMs: 35 * 60_000 });
  expect(sim.state, `sim job ${simJob!.id} did not succeed`).toBe("succeeded");

  const analysis = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: analyzerJob!.id, timeoutMs: 8 * 60_000 });
  expect(analysis.state, `analyzer job ${analyzerJob!.id} did not succeed`).toBe("succeeded");

  expect(existsSync(SIM_DIR), `${SIM_DIR} should exist after the pipeline ran`).toBe(true);
  expect(existsSync(join(SIM_DIR, "Analyses", "Mesh")), "the analyzer node wrote no mesh analysis").toBe(true);
});
