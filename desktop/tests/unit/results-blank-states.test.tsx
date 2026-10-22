// @vitest-environment jsdom
/**
 * Results never renders a blank tree (p32, `pages/results/useOutputs.ts`, `pages/results/index.tsx`).
 *
 * A subject's tree is built once all five of its list reads (simulations, flex, ex, mEx, reports)
 * have landed. Before this fix a failed read left the subject `undefined` with `pending` false, so
 * the tree showed no skeleton, no empty state and no error. That always happened for a subject
 * known only from `sourcedata/`: `/api/catalog/subjects` lists it (`tit.catalog.list_subjects`),
 * but every per-subject route answers 404 "Unknown subject" because `tit.catalog.subject_ids`
 * (raw BIDS, FastSurfer, FreeSurfer or m2m) excludes it. Dataset 000's sub-102 and sub-test are
 * such subjects. The same blank showed on `Group` when `/api/catalog/group` failed.
 *
 * The page's api module is mocked at its network calls; the refusals carry the routes' wording.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import type { OutputsState, SubjectRow } from "../../src/renderer/pages/results/useOutputs";

const api = vi.hoisted(() => ({
  getSimulationsFor: vi.fn(),
  getFlexRuns: vi.fn(),
  getExRuns: vi.fn(),
  getReports: vi.fn(),
  getAnalyses: vi.fn(),
  getGroupCatalog: vi.fn(),
}));
const subjects = vi.hoisted(() => ({ list: [] as unknown[] }));

vi.mock("../../src/renderer/api/client", async (original) => ({
  ...(await original<object>()),
  getSubjects: vi.fn(async () => subjects.list),
}));
vi.mock("../../src/renderer/pages/results/api", async (original) => ({ ...(await original<object>()), ...api }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: page } = await import("../../src/renderer/pages/results/index");
const { useSubjectOutputs } = await import("../../src/renderer/pages/results/useOutputs");
const { clearPageSession } = await import("../../src/renderer/app/pageSession");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

/** `/api/catalog/subjects` rows: two onboarded subjects and one known only from sourcedata/. */
const ERNIE = { id: "ernie", has_raw: true, has_fastsurfer: true, has_freesurfer: false, has_m2m: true, n_simulations: 1 };
const S101 = { id: "101", has_raw: true, has_fastsurfer: false, has_freesurfer: false, has_m2m: true, n_simulations: 0 };
const S102 = { id: "102", has_raw: false, has_fastsurfer: false, has_freesurfer: false, has_m2m: false, n_simulations: 0, has_sourcedata: true };
/** A FastSurfer-only subject is in `subject_ids`, so its routes answer and it must be read. */
const FS_ONLY = { id: "fsonly", has_raw: false, has_fastsurfer: true, has_freesurfer: false, has_m2m: false, n_simulations: 0 };
/**
 * One subject per source `tit.catalog.subject_ids` unions (raw BIDS, FastSurfer, legacy FreeSurfer,
 * m2m), each with only that one artefact. Any one of them puts the subject in the onboarded set the
 * per-subject routes answer, so each must be read: reading none would print "no outputs yet" over
 * the simulations it really has.
 */
const SINGLE_SOURCE = (["has_raw", "has_fastsurfer", "has_freesurfer", "has_m2m"] as const).map((flag) => ({
  id: `only_${flag.slice("has_".length)}`,
  has_raw: false,
  has_fastsurfer: false,
  has_freesurfer: false,
  has_m2m: false,
  n_simulations: 1,
  [flag]: true,
}));

const SIM = {
  name: "Thalamus",
  path: "/mnt/p/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus",
  has_ti: true,
  has_mti: false,
  montages: ["F3_F4"],
  fields: ["TI_max"],
  space: ["subject"],
  report_ids: [],
  niftis: [],
  meshes: [],
};
/** The route's refusal when the flex catalog of 101 cannot be read. */
const FLEX_FAILED = new ApiError(500, "/api/catalog/flex-runs", "flex-search/run_a/flex_meta.json is not valid JSON");

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

async function settle() {
  for (let i = 0; i < 8; i++) await act(async () => await new Promise((resolve) => setTimeout(resolve, 0)));
}

/** What every per-subject catalog route answers a subject outside `subject_ids` (`routes/catalog.py`). */
function known(subject: string): void {
  if (subject === "102") throw new ApiError(404, "/api/catalog", `Unknown subject: ${subject}`);
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
  api.getSimulationsFor.mockImplementation(async (s: string) => (known(s), s === "ernie" ? [SIM] : []));
  api.getFlexRuns.mockImplementation(async (s: string) => {
    known(s);
    if (s === "101") throw FLEX_FAILED;
    return [];
  });
  api.getExRuns.mockImplementation(async (s: string) => (known(s), []));
  api.getReports.mockImplementation(async (s: string) => (known(s), []));
  api.getAnalyses.mockImplementation(async (s: string) => (known(s), []));
  api.getGroupCatalog.mockResolvedValue({ stats: [], nilearn: [], group_analyses: [] });
  subjects.list = [ERNIE, S101, S102];
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});

/** Every subject id any per-subject read was called with. */
function subjectsRead(): string[] {
  const calls = [api.getSimulationsFor, api.getFlexRuns, api.getExRuns, api.getReports, api.getAnalyses].flatMap((fn) => fn.mock.calls);
  return [...new Set(calls.map((c) => c[0] as string))].sort();
}

describe("useSubjectOutputs", () => {
  async function run(rows: SubjectRow[], selected: string): Promise<OutputsState> {
    let state: OutputsState | undefined;
    function Probe() {
      state = useSubjectOutputs(rows, selected);
      return null;
    }
    act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
    await settle();
    return state!;
  }

  it("exposes the failed read of a subject instead of leaving it silently undefined", async () => {
    const state = await run([ERNIE, S101], "101");
    expect(state.pending).toBe(false);
    expect(state.bySubject["101"]).toBeUndefined();
    expect(state.errors["101"]?.message).toBe("flex-search/run_a/flex_meta.json is not valid JSON");
    // The other subject is unaffected: its one simulation is its one output.
    expect(state.errors.ernie).toBeUndefined();
    expect(state.bySubject.ernie?.total).toBe(1);
  });

  // The five list reads a subject's tree waits on. Whichever one fails, its reason is the subject's
  // error: a scan that skipped one would leave that failure as the old silent blank.
  /** Fails `getExRuns` for one of its two kinds only; the other kind still answers. */
  const failExKind = (failing: string, message: string) =>
    api.getExRuns.mockImplementation(async (_s: string, kind: string) => {
      if (kind === failing) throw new ApiError(500, "/api/catalog/ex-runs", message);
      return [];
    });
  it.each([
    { read: "simulations", message: "Simulations/ is unreadable", fail: (m: string) => api.getSimulationsFor.mockRejectedValueOnce(new ApiError(500, "/api/catalog/simulations", m)) },
    { read: "flex runs", message: "flex-search/ is unreadable", fail: (m: string) => api.getFlexRuns.mockRejectedValueOnce(new ApiError(500, "/api/catalog/flex-runs", m)) },
    { read: "ex runs", message: "ex-search/ is unreadable", fail: (m: string) => failExKind("ex", m) },
    { read: "mex runs", message: "mex-search/ is unreadable", fail: (m: string) => failExKind("mex", m) },
    { read: "reports", message: "reports/ is unreadable", fail: (m: string) => api.getReports.mockRejectedValueOnce(new ApiError(500, "/api/catalog/reports", m)) },
  ])("exposes a failed $read read as the subject's error", async ({ message, fail }) => {
    fail(message);
    const state = await run([ERNIE], "ernie");
    expect(state.errors.ernie?.message).toBe(message);
    expect(state.bySubject.ernie).toBeUndefined();
  });

  it("sends no per-subject read for a sourcedata-only subject and reports it as empty", async () => {
    const state = await run([ERNIE, S101, S102, FS_ONLY], "102");
    expect(subjectsRead()).toEqual(["101", "ernie", "fsonly"]);
    expect(state.bySubject["102"]?.total).toBe(0);
    expect(state.errors["102"]).toBeUndefined();
    expect(state.bySubject.fsonly?.total).toBe(0);
  });

  it.each(SINGLE_SOURCE)("reads $id, a subject with only that one artefact, and lists its simulation", async (row) => {
    api.getSimulationsFor.mockImplementation(async (s: string) => (known(s), [{ ...SIM, path: `/mnt/p/derivatives/SimNIBS/sub-${s}/Simulations/Thalamus` }]));
    const state = await run([row, S102], row.id);
    expect(subjectsRead()).toEqual([row.id]);
    expect(state.errors[row.id]).toBeUndefined();
    expect(state.bySubject[row.id]?.total).toBe(1);
    expect(state.bySubject["102"]?.total).toBe(0);
  });

  it("exposes a failed group catalog", async () => {
    api.getGroupCatalog.mockReset().mockRejectedValue(new ApiError(500, "/api/catalog/group", "stats/group_comparison is unreadable"));
    const state = await run([ERNIE], "Group");
    expect(state.group).toBeUndefined();
    expect(state.groupError?.message).toBe("stats/group_comparison is unreadable");
  });
});

describe("the Results tree", () => {
  async function renderPage() {
    const Page = page.Component;
    act(() =>
      root.render(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={["/results"]}>
            <Page />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    await settle();
  }

  async function pick(id: string) {
    await act(async () => container.querySelector<HTMLButtonElement>(`[data-testid="results-subject-${id}"]`)!.click());
    await settle();
  }

  const tree = () => container.querySelector('[data-testid="results-tree-rows"]')!;

  it("says a subject's read failed, with the route's reason, instead of drawing nothing", async () => {
    await renderPage();
    await pick("101");
    const alert = tree().querySelector('[role="alert"]');
    expect(alert?.textContent).toContain("Could not load 101's outputs.");
    expect(alert?.textContent).toContain("flex-search/run_a/flex_meta.json is not valid JSON");
    expect(tree().querySelectorAll('[role="treeitem"]')).toHaveLength(0);
  });

  it("shows 'no outputs yet' and a 0 count for a sourcedata-only subject, without asking the server", async () => {
    await renderPage();
    await pick("102");
    expect(tree().textContent).toContain("102 has no outputs yet.");
    expect(tree().querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-testid="results-subject-102"]')?.textContent).toBe("1020");
    expect(subjectsRead()).not.toContain("102");
  });

  it("says the group catalog failed on the Group row", async () => {
    api.getGroupCatalog.mockReset().mockRejectedValue(new ApiError(500, "/api/catalog/group", "stats/group_comparison is unreadable"));
    await renderPage();
    await pick("Group");
    const alert = tree().querySelector('[role="alert"]');
    expect(alert?.textContent).toContain("Could not load the group outputs.");
    expect(alert?.textContent).toContain("stats/group_comparison is unreadable");
  });

  it("still draws a subject whose reads all landed", async () => {
    await renderPage();
    await pick("ernie");
    expect(tree().querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-testid="results-node-simulation:ernie:Thalamus"]')).not.toBeNull();
  });
});
