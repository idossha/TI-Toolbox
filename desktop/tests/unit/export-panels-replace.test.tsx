// @vitest-environment jsdom
/**
 * 3D Visual Exporter and Nilearn visuals: re-exporting over outputs that already exist (G1-2).
 *
 * The server refuses a `blender` or `nilearn` job whose output folder exists unless the
 * submission says `overwrite: true` (`tit/server/overwrite_policy.py`, HTTP 409). Neither panel
 * sent `overwrite`, and the exporter's folder is fixed per subject and simulation, so every
 * re-export was a dead-end "Could not queue" toast. Both now open the shared skip/replace dialog
 * on that 409, as the cluster-permutation panel does; "Replace and rerun" resubmits with
 * `overwrite: true`, and Skip queues nothing. The exporter's regions mode queues an STL and a
 * PLY job: when the STL job was accepted and the PLY job 409s, Replace resubmits only the PLY.
 *
 * What is mocked: only the wire. `api.GET`/`api.POST` of the real openapi-fetch client are
 * spied on, so each panel's own `api.ts` builds the `POST /api/jobs` body asserted here.
 * Expected values: the `JobRequest` contract (`contracts/openapi.yaml`), the server's 409 rule,
 * the session written below and `ExistingOutputsDialog.tsx`'s test ids. Replace bodies are
 * compared with the first submission, not retyped. Dated 2026-10-31.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/export-panels-replace.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => [{ id: "101" }]) }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string) => toast.error(message),
}));
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/ExportPreview", () => ({ ExportPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: exporterPage } = await import("../../src/renderer/pages/panels/visual-exporter/index");
const { default: nilearnPage } = await import("../../src/renderer/pages/panels/nilearn-visuals/index");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

type Wire = { data?: unknown; error?: unknown; response: Response };
const ok = (data: unknown): Wire => ({ data, response: new Response(null, { status: 200 }) });
const refused = (status: number, detail: string): Wire => ({ error: { detail }, response: new Response(null, { status }) });
const CONFLICT = () => refused(409, "Outputs of this job already exist. Explicit overwrite confirmation is required: /p/out");
const PLAN = { jobs: [{ kind: "x", subject: "101", output_dir: "/p/out", exists: true, will_overwrite: true }], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] };

let jobAnswers: Wire[];
let jobBodies: Record<string, unknown>[];
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of Object.values(toast)) fn.mockReset();
  jobAnswers = [];
  jobBodies = [];
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/catalog/simulations") return ok({ simulations: [{ name: "M1", path: "/p/M1" }] });
    if (path === "/api/catalog/atlases/regions") return ok([]);
    return refused(404, `unexpected GET ${path}`);
  }) as never);
  vi.spyOn(api, "POST").mockImplementation((async (path: string, init: { body: Record<string, unknown> }) => {
    if (path === "/api/validate/{kind}") return ok({ ok: true, errors: [] });
    if (path === "/api/plan/{kind}") return ok(PLAN);
    if (path === "/api/jobs") {
      jobBodies.push(structuredClone(init.body));
      return jobAnswers.shift() ?? refused(500, "no answer queued");
    }
    return refused(404, `unexpected POST ${path}`);
  }) as never);
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function mount(page: { Component: () => React.ReactElement | null }, session: Record<string, unknown>) {
  for (const [key, value] of Object.entries(session)) writeSession(sessionSlot("", key), value);
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
}

async function settle() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
  }
}

const byTestId = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`);

async function press(id: string) {
  await settle();
  const button = byTestId(id);
  expect(button, id).not.toBeNull();
  await act(async () => button!.click());
  await settle();
}

describe("3D Visual Exporter", () => {
  beforeEach(() => mount(exporterPage as never, { mode: "vectors", subjectId: "101", simulationName: "M1" }));

  it("asks instead of failing when the export exists, and Replace resubmits with overwrite", async () => {
    jobAnswers = [CONFLICT(), ok({ id: "job-2" })];
    await press("run-button");
    expect(jobBodies).toHaveLength(1);
    expect(jobBodies[0]).toMatchObject({ kind: "blender", subject_ids: ["101"], overwrite: false });
    expect(toast.error).not.toHaveBeenCalled();

    await press("existing-outputs-replace");
    expect(jobBodies).toHaveLength(2);
    expect(jobBodies[1]).toEqual({ ...jobBodies[0], overwrite: true });
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("Skip queues nothing", async () => {
    jobAnswers = [CONFLICT()];
    await press("run-button");
    await press("existing-outputs-skip");
    expect(jobBodies).toHaveLength(1);
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("3D Visual Exporter, regions mode (two jobs)", () => {
  beforeEach(() => mount(exporterPage as never, { mode: "regions", subjectId: "101", simulationName: "M1" }));

  it("Replace resubmits only the job the server refused, not the one it already queued", async () => {
    jobAnswers = [ok({ id: "stl" }), CONFLICT(), ok({ id: "ply" })];
    await press("run-button");
    expect(jobBodies.map((b) => (b.config as { format: string }).format)).toEqual(["stl", "ply"]);

    await press("existing-outputs-replace");
    expect(jobBodies).toHaveLength(3);
    expect(jobBodies[2]).toEqual({ ...jobBodies[1], overwrite: true });
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe("Nilearn visuals", () => {
  beforeEach(() => mount(nilearnPage as never, { subdir: "figs", pairs: [{ id: "p1", subjectId: "101", simulationName: "M1" }] }));

  it("asks instead of failing when the folder exists, and Replace resubmits with overwrite", async () => {
    jobAnswers = [CONFLICT(), ok({ id: "job-2" })];
    await press("run-button");
    expect(jobBodies).toHaveLength(1);
    expect(jobBodies[0]).toMatchObject({ kind: "nilearn", subject_ids: ["101"], overwrite: false });
    expect(toast.error).not.toHaveBeenCalled();

    await press("existing-outputs-replace");
    expect(jobBodies).toHaveLength(2);
    expect(jobBodies[1]).toEqual({ ...jobBodies[0], overwrite: true });
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it("a 409 on the Replace resubmission is an error toast, not the dialog again", async () => {
    jobAnswers = [CONFLICT(), CONFLICT()];
    await press("run-button");
    await press("existing-outputs-replace");
    expect(jobBodies.map((b) => b.overwrite)).toEqual([false, true]);
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(byTestId("existing-outputs-replace")).toBeNull();
  });
});
