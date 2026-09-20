// @vitest-environment jsdom
/**
 * The page terminal's folder button (DESIGN.md v3 §4.6, `JobTerminal.tsx`). Commit d03ff911 made
 * the Jobs page's own console reveal a job's real output folder (`jobFolder()`:
 * `derivatives/SimNIBS/.../Simulations/<montage>/`, never `code/ti-toolbox/jobs/<id>/`) instead of
 * the log's bookkeeping folder — but every page terminal (Analyzer, Simulator, Optimizer, all built
 * on this shared `JobTerminal`) still opened `code/ti-toolbox/jobs/<id>/`, because `resolveFollowedJob`
 * only ever hands the pane a `FollowableJob`, which drops `artifacts`. This pins the fix: the pane
 * looks the full `JobStatus` back up in `useJobsModel()`'s `all` and reveals `jobFolder(rawJob)`.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

const revealed: string[] = [];
vi.mock("../../src/renderer/app/jobs-rail/reveal", () => ({
  reveal: (path: string) => revealed.push(path),
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

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  revealed.length = 0;
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

function analyzerJob(): JobStatus {
  return {
    id: "a1",
    kind: "analyzer",
    state: "succeeded",
    subject_ids: ["ernie"],
    created_at: new Date(0).toISOString(),
    log_path: "/code/ti-toolbox/jobs/a1/stdout.log",
    artifacts: [
      { path: "/data/derivatives/SimNIBS/sub-ernie/Analyses/mesh/scene.tetravox.json", kind: "scene" },
      { path: "/data/derivatives/SimNIBS/sub-ernie/Analyses/mesh/report.json", kind: "report" },
    ],
    progress: undefined,
    liveness: null,
  };
}

describe("JobTerminal folder reveal", () => {
  it("reveals the job's artifact directory, not the log bookkeeping folder, when artifacts exist", async () => {
    allJobs = [analyzerJob()];
    await act(async () =>
      root.render(
        <JobTerminal kinds={["analyzer"]} subjects={["ernie"]} startedJobIds={["a1"]} />,
      ),
    );

    const button = container.querySelector('[aria-label="Show the job\'s output folder"]') as HTMLElement;
    expect(button).toBeTruthy();
    await act(async () => button.click());
    expect(revealed).toEqual(["/data/derivatives/SimNIBS/sub-ernie/Analyses/mesh"]);
  });

  it("falls back to the log file's folder, labelled as a log reveal, when the job has no artifacts yet", async () => {
    allJobs = [
      {
        id: "a2",
        kind: "analyzer",
        state: "running",
        subject_ids: ["ernie"],
        created_at: new Date(0).toISOString(),
        log_path: "/code/ti-toolbox/jobs/a2/stdout.log",
        artifacts: [],
        progress: undefined,
        liveness: "active",
      },
    ];
    await act(async () =>
      root.render(
        <JobTerminal kinds={["analyzer"]} subjects={["ernie"]} startedJobIds={["a2"]} />,
      ),
    );

    const button = container.querySelector('[aria-label="Reveal log file"]') as HTMLElement;
    expect(button).toBeTruthy();
    await act(async () => button.click());
    expect(revealed).toEqual(["/code/ti-toolbox/jobs/a2"]);
  });
});
