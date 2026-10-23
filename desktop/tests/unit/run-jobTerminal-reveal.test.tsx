// @vitest-environment jsdom
/**
 * The run page terminal's folder button (DESIGN.md v3 §4.6, `JobTerminal.tsx`): which folder it
 * opens, and what it says it opens.
 *
 * It opened `code/ti-toolbox/jobs/<id>/` — the job's own bookkeeping record — for any job that had
 * registered no artifact yet, which is all of a simulation's or a search's run, and the *parent* of
 * a finished simulation's or search's folder (the first artifact it registers is that folder, as a
 * `dir`). The server now names the folder (`output_dir` on `GET /api/jobs/{id}`), and the button
 * opens it.
 *
 * The expected folders are `tests/fixtures/contracts/job_output_dirs.json`, written by
 * `dev/make_contract_fixtures.py` from the real `GET /api/jobs/{id}` on a synthetic project (kept
 * current by `tests/test_contract_fixtures_fresh.py`; the folders themselves are pinned in
 * `tests/test_job_output_dir.py`). Nothing is typed here as a path the server names.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "../fixtures/contracts/job_output_dirs.json";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

const opened: string[] = [];
vi.mock("../../src/renderer/app/jobs-rail/reveal", () => ({
  openFolder: (path: string) => opened.push(path),
  reveal: () => {},
}));

// What `GET /api/jobs/{id}` answers for the job under test.
let serverOutputDir: string | null = null;
vi.mock("../../src/renderer/app/jobs-rail/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../src/renderer/app/jobs-rail/api")>()),
  getJobOutputDir: async () => serverOutputDir,
}));

let allJobs: JobStatus[] = [];
vi.mock("../../src/renderer/app/jobs-rail/model", () => ({
  useJobsModel: () => ({ all: allJobs, now: 1000 }),
}));

vi.mock("../../src/renderer/app/jobs/useJobLogEvents", () => ({
  useJobLogEvents: () => ({ lines: [], isLoading: false }),
}));

// `VirtualList` needs a real ResizeObserver, irrelevant to this test's concern (the folder
// button), so it is stubbed out the same way `job-console.test.tsx` does.
vi.mock("../../src/renderer/ui/VirtualList", () => ({
  VirtualList: () => <div />,
}));

import { JobTerminal } from "../../src/renderer/pages/_shared/run/JobTerminal";

interface Case {
  id: string;
  kind: string;
  subject_ids: string[];
  artifacts: { path: string; kind: string; label?: string }[];
  output_dir: string | null;
}
const cases = fixture.cases as Case[];
const byId = (id: string): Case => {
  const found = cases.find((c) => c.id === id);
  if (!found) throw new Error(`fixture has no case ${id}`);
  return found;
};

const PROJECT = "/mnt/example";
const OUTPUT = "Open output folder";
const JOB = "Open job folder";

/** The jobs-list record the page holds for a fixture case: what the runner had registered so far. */
function jobFor(c: Case): { job: JobStatus; recordFolder: string } {
  const recordFolder = `${PROJECT}/code/ti-toolbox/jobs/${c.id}`;
  const job = {
    id: c.id,
    kind: c.kind,
    state: "running",
    subject_ids: c.subject_ids,
    created_at: new Date(0).toISOString(),
    artifacts: c.artifacts,
    log_path: `${recordFolder}/stdout.log`,
    progress: null,
    liveness: "active",
  } as JobStatus;
  return { job, recordFolder };
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  opened.length = 0;
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

/** Renders the terminal following `c`'s job and presses the folder button once it has its label. */
async function pressFolderButton(c: Case, label: string): Promise<HTMLElement> {
  const { job } = jobFor(c);
  allJobs = [job];
  serverOutputDir = c.output_dir;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <JobTerminal kinds={[c.kind]} subjects={c.subject_ids} startedJobIds={[c.id]} />
      </QueryClientProvider>,
    ),
  );
  const find = () => container.querySelector(`[aria-label="${label}"]`) as HTMLElement | null;
  await vi.waitFor(() => expect(find()).toBeTruthy());
  const button = find() as HTMLElement;
  await act(async () => button.click());
  return button;
}

describe("the terminal's folder button opens the job's output folder", () => {
  it("a simulation, while it runs: the montage's folder, not the job record", async () => {
    const c = byId("sim_running");
    expect(c.output_dir).toMatch(/\/derivatives\/SimNIBS\/sub-ernie\/Simulations\/L_Insula$/);
    const button = await pressFolderButton(c, OUTPUT);
    expect(opened).toEqual([c.output_dir]);
    expect(button.getAttribute("title")).toBe(OUTPUT);
  });

  it("a simulation, once its runner has registered the folder: that folder, not its parent", async () => {
    const c = byId("sim_finished");
    // The first artifact the runner registers is the folder itself; its parent is `Simulations/`.
    expect(c.artifacts[0]).toMatchObject({ kind: "dir", path: c.output_dir });
    await pressFolderButton(c, OUTPUT);
    expect(opened).toEqual([c.output_dir]);
    expect(opened[0]).not.toBe(c.output_dir?.replace(/\/[^/]+$/, ""));
  });

  it("a flex search, while it runs and when it is done: the run folder", async () => {
    for (const id of ["flex_running", "flex_finished"]) {
      opened.length = 0;
      const c = byId(id);
      expect(c.output_dir).toMatch(/\/derivatives\/SimNIBS\/sub-ernie\/flex-search\/[^/]+$/);
      await pressFolderButton(c, OUTPUT);
      expect(opened).toEqual([c.output_dir]);
      await act(async () => root.render(<div />));
    }
  });

  it("an ex search once it has registered its results: the run folder holding them", async () => {
    const c = byId("ex_finished");
    await pressFolderButton(c, OUTPUT);
    expect(opened).toEqual([c.output_dir]);
    expect(c.artifacts.every((a) => a.path.startsWith(`${c.output_dir}/`))).toBe(true);
  });

  it("an analysis: the analysis folder, not the folder of whichever file was registered first", async () => {
    const c = byId("analyzer_finished");
    expect(c.output_dir).toMatch(/\/Simulations\/L_Insula\/Analyses\/Mesh\/[^/]+$/);
    // The runner registered a figure first; its directory is a sub-folder of the analysis.
    expect(c.artifacts[0]?.path.startsWith(`${c.output_dir}/figures/`)).toBe(true);
    await pressFolderButton(c, OUTPUT);
    expect(opened).toEqual([c.output_dir]);
  });

  it("a pre-processing stage with a folder of its own: that folder", async () => {
    const c = byId("pre_charm");
    await pressFolderButton(c, OUTPUT);
    expect(opened).toEqual([c.output_dir]);
  });
});

describe("a job with no output folder opens its own folder, and says so", () => {
  for (const id of ["sim_queued_folder_not_created", "sim_two_montages", "ex_running_unnamed"]) {
    it(id, async () => {
      const c = byId(id);
      expect(c.output_dir).toBeNull();
      const button = await pressFolderButton(c, JOB);
      expect(opened).toEqual([jobFor(c).recordFolder]);
      expect(button.getAttribute("title")).toBe(JOB);
      expect(container.querySelector(`[aria-label="${OUTPUT}"]`)).toBeNull();
    });
  }

  it("and shows no folder button at all when the server gave no log path either", async () => {
    const c = byId("sim_two_montages");
    const { job } = jobFor(c);
    allJobs = [{ ...job, log_path: null }];
    serverOutputDir = null;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await act(async () =>
      root.render(
        <QueryClientProvider client={client}>
          <JobTerminal kinds={[c.kind]} subjects={c.subject_ids} startedJobIds={[c.id]} />
        </QueryClientProvider>,
      ),
    );
    expect(container.querySelector('[aria-label="Clear terminal"]')).toBeTruthy();
    expect(container.querySelector(`[aria-label="${OUTPUT}"], [aria-label="${JOB}"]`)).toBeNull();
  });
});

describe("never a path outside the project", () => {
  it("refuses an output folder that is relative or climbs out, and opens the job's own folder", async () => {
    for (const hostile of ["derivatives/SimNIBS/sub-ernie", `${PROJECT}/../etc`]) {
      opened.length = 0;
      const c: Case = { ...byId("sim_running"), output_dir: hostile };
      await pressFolderButton(c, JOB);
      expect(opened).toEqual([jobFor(c).recordFolder]);
      await act(async () => root.render(<div />));
    }
  });
});
