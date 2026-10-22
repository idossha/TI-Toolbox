// @vitest-environment jsdom
/**
 * Cluster permutation: re-running an analysis name that already exists (p23).
 *
 * The server refuses a stats job whose `stats/<mode>/<analysis_name>/` folder exists unless the
 * submission says `overwrite: true` (`tit/server/overwrite_policy.py`, HTTP 409). The panel never
 * sent `overwrite`, so a re-run of a name was a dead-end "Could not queue" toast. It now opens the
 * same skip/replace dialog the NIfTI averaging panel shows, and "Replace and rerun" resubmits the
 * same config with `overwrite: true`; "Skip" queues nothing. A refusal that is not a 409, and a
 * 409 on the Replace resubmission itself, stay error toasts (no dialog loop).
 *
 * What is mocked: only the wire. `api.GET`/`api.POST` of the real openapi-fetch client are
 * spied on, so the panel's own `createStatsJob` (`cluster-permutation/api.ts`) builds the
 * `POST /api/jobs` body that is asserted here. A body without `overwrite` makes the server answer
 * 409 again, so Replace would do nothing.
 *
 * Expected values: the `JobRequest` contract (`kind`, `config`, `subject_ids`, `overwrite`,
 * `contracts/openapi.yaml`), the server's 409 rule, the rows and name written into the page
 * session below, and the dialog's own test ids (`ExistingOutputsDialog.tsx`). The Replace body
 * is compared with the first submission, not retyped. Nothing reads the disk. Dated 2026-10-22.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/api/client", async (original) => ({ ...(await original<object>()), getSubjects: vi.fn(async () => []) }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string) => toast.error(message),
}));
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: page } = await import("../../src/renderer/pages/panels/cluster-permutation/index");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

type Wire = { data?: unknown; error?: unknown; response: Response };
const ok = (data: unknown): Wire => ({ data, response: new Response(null, { status: 200 }) });
const refused = (status: number, detail: string): Wire => ({ error: { detail }, response: new Response(null, { status }) });
const CONFLICT = () => refused(409, "Outputs of this stats job already exist. Explicit overwrite confirmation is required: /p/stats");

const PLAN = { jobs: [{ kind: "stats", subject: "", output_dir: "/p/stats", exists: true, will_overwrite: true }], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] };

/** What `POST /api/jobs` answers, one entry per submission, in order. */
let jobAnswers: Wire[];
/** Every `POST /api/jobs` body the panel sent. */
let jobBodies: Record<string, unknown>[];

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of Object.values(toast)) fn.mockReset();
  jobAnswers = [];
  jobBodies = [];
  vi.spyOn(api, "GET").mockImplementation((async (path: string) =>
    path === "/api/catalog/simulations" ? ok({ simulations: [] }) : refused(404, `unexpected GET ${path}`)) as never);
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
  writeSession(sessionSlot("", "mode"), "classification");
  writeSession(sessionSlot("", "analysisName"), "rerun");
  writeSession(sessionSlot("", "rows"), [
    { id: "r1", subjectId: "001", simulationName: "M1", response: 1, effectSize: undefined, weight: 1 },
    { id: "r2", subjectId: "002", simulationName: "M1", response: 0, effectSize: undefined, weight: 1 },
  ]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

async function settle() {
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
}

const byTestId = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`);

async function pressRun() {
  await settle();
  const run = byTestId("run-button")!;
  expect(run.disabled, "the 1-vs-1 comparison is runnable").toBe(false);
  await act(async () => run.click());
  await settle();
}

async function pressReplace() {
  await act(async () => byTestId("existing-outputs-replace")!.click());
  await settle();
}

it("asks instead of failing when the analysis name exists, and Replace resubmits with overwrite on the wire", async () => {
  jobAnswers = [CONFLICT(), ok({ id: "job-2" })];
  await pressRun();

  // The first submission is the plain one: the rows and the name in the session, no overwrite.
  expect(jobBodies).toHaveLength(1);
  expect(jobBodies[0]).toMatchObject({ kind: "stats", subject_ids: ["001", "002"], overwrite: false });
  expect(jobBodies[0]!.config).toMatchObject({ _type: "GroupComparisonConfig", analysis_name: "rerun" });
  expect(toast.error).not.toHaveBeenCalled();
  expect(byTestId("existing-outputs-replace")).not.toBeNull();

  await pressReplace();
  // The same job, now with the user's confirmation the server needs to stop answering 409.
  expect(jobBodies).toHaveLength(2);
  expect(jobBodies[1]).toEqual({ ...jobBodies[0], overwrite: true });
  expect(byTestId("existing-outputs-replace")).toBeNull();
  expect(toast.success).toHaveBeenCalledTimes(1);
  expect(toast.error).not.toHaveBeenCalled();
});

it("Skip leaves the existing analysis alone and queues nothing", async () => {
  jobAnswers = [CONFLICT()];
  await pressRun();

  await act(async () => byTestId("existing-outputs-skip")!.click());
  await settle();
  expect(jobBodies).toHaveLength(1);
  expect(byTestId("existing-outputs-skip")).toBeNull();
  expect(toast.success).not.toHaveBeenCalled();
});

it("a refusal that is not about existing outputs stays an error, with no dialog", async () => {
  jobAnswers = [refused(422, "Missing inputs")];
  await pressRun();

  expect(toast.error).toHaveBeenCalledTimes(1);
  expect(byTestId("existing-outputs-replace")).toBeNull();
  expect(jobBodies).toHaveLength(1);
});

it("a 409 on the Replace resubmission is an error toast, not the dialog again", async () => {
  // The folder could not be replaced (another job took it meanwhile, say): asking a second time
  // would loop; the user is told the analysis was not queued.
  jobAnswers = [CONFLICT(), CONFLICT()];
  await pressRun();
  await pressReplace();

  expect(jobBodies.map((b) => b.overwrite)).toEqual([false, true]);
  expect(toast.error).toHaveBeenCalledTimes(1);
  expect(toast.error.mock.calls[0]![0]).toBe("Could not queue the analysis.");
  expect(byTestId("existing-outputs-replace")).toBeNull();
  expect(toast.success).not.toHaveBeenCalled();
});
