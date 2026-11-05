// @vitest-environment jsdom
/**
 * The Networks tab's "Assess networks" action, the way out of a simulation with no network outputs.
 *
 * What it pins (2026-11-05): the missing tractogram and network are shown in the server's own words
 * instead of a button that could only be refused; existing `tract/` outputs are replaced only on
 * the user's answer, whether the plan says so first or the server's 409 says so late; and a finished
 * tract job refreshes the list the tab reads.
 *
 * Where the expectations come from: the wire config is the one `TractConfig` (tit/tract/config.py)
 * deserialises, replayed through the real runner by tests/test_runner_dispatch_replay.py from the
 * corpus fixture tract/assess.json. Plan and preflight answers are authored here; their real shapes
 * are pinned by tests/test_tract_routes.py. The component renders for real with its API mocked.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/visual-exporter-assess.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const model = vi.hoisted(() => ({ all: [] as { id: string; kind: string; state: string }[] }));
vi.mock("../../src/renderer/app/jobs-rail/model", async (original) => ({
  ...(await original<object>()),
  useJobsModel: () => ({ all: model.all }),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/api", () => ({
  preflightTract: vi.fn(),
  planTract: vi.fn(),
  createTractJob: vi.fn(),
}));

import { ApiError } from "../../src/renderer/api/client";
import { queriesAffectedBy } from "../../src/renderer/app/jobs/invalidation";
import { clearPageSession } from "../../src/renderer/app/pageSession";
import { AssessNetworks } from "../../src/renderer/pages/panels/visual-exporter/AssessNetworks";
import * as api from "../../src/renderer/pages/panels/visual-exporter/api";

const CONFIG = {
  _type: "TractConfig",
  subject_id: "ernie",
  stages: ["assess"],
  assess: { simulations: ["L_Insula"], selections: [{ name: "all", kind: "all" }] },
};
const planned = (willOverwrite: boolean) => ({ jobs: [{ will_overwrite: willOverwrite }] }) as never;

let container: HTMLElement;
let root: Root;
let onQueued: ReturnType<typeof vi.fn<(job: api.JobStatus) => void>>;

async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function mount(): Promise<void> {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onQueued = vi.fn<(job: api.JobStatus) => void>();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <AssessNetworks subjectId="ernie" simulationName="L_Insula" onQueued={onQueued} />
      </QueryClientProvider>,
    );
  });
  await settle();
}

const byTestId = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="${id}"]`);
async function click(id: string): Promise<void> {
  await act(async () => {
    byTestId(id)!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  clearPageSession();
  model.all = [];
  vi.mocked(api.preflightTract).mockReset().mockResolvedValue([]);
  vi.mocked(api.planTract).mockReset().mockResolvedValue(planned(false));
  vi.mocked(api.createTractJob).mockReset().mockResolvedValue({ id: "job1" } as never);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("Assess networks", () => {
  it("shows what the job needs instead of a button when the tractogram and network are absent", async () => {
    vi.mocked(api.preflightTract).mockResolvedValue([
      { what: "tractogram for sub-ernie", expected_path: "/t/tractogram.trx", how_to_fix: "Run Tractography for sub-ernie first." },
      { what: "network for sub-ernie", expected_path: "/t/network.npz", how_to_fix: "Run Tractography for sub-ernie first." },
    ]);
    await mount();
    expect(byTestId("ve-assess-networks")).toBeNull();
    const reason = byTestId("ve-assess-missing")!.textContent;
    expect(reason).toContain("tractogram for sub-ernie");
    expect(reason).toContain("/t/network.npz");
    expect(reason).toContain("Run Tractography for sub-ernie first.");
  });

  it("queues the assess-only config without overwrite when nothing would be replaced", async () => {
    await mount();
    expect(vi.mocked(api.preflightTract).mock.calls[0]).toEqual([CONFIG, "ernie"]);
    await click("ve-assess-networks");
    expect(vi.mocked(api.createTractJob).mock.calls).toEqual([[CONFIG, "ernie", false]]);
    expect(onQueued).toHaveBeenCalledWith({ id: "job1" });
  });

  it("asks before replacing what the plan says exists, and sends overwrite only on Replace", async () => {
    vi.mocked(api.planTract).mockResolvedValue(planned(true));
    await mount();
    await click("ve-assess-networks");
    expect(api.createTractJob).not.toHaveBeenCalled();
    await click("existing-outputs-replace");
    expect(vi.mocked(api.createTractJob).mock.calls).toEqual([[CONFIG, "ernie", true]]);
  });

  it("queues nothing when the answer is Skip", async () => {
    vi.mocked(api.planTract).mockResolvedValue(planned(true));
    await mount();
    await click("ve-assess-networks");
    await click("existing-outputs-skip");
    expect(api.createTractJob).not.toHaveBeenCalled();
    expect(byTestId("existing-outputs-skip")).toBeNull();
  });

  it("asks when the server refuses (409) a replacement a stale plan did not report", async () => {
    vi.mocked(api.createTractJob).mockRejectedValueOnce(new ApiError(409, "/api/jobs", "exists"));
    await mount();
    await click("ve-assess-networks");
    expect(byTestId("existing-outputs-replace")).not.toBeNull();
    expect(onQueued).not.toHaveBeenCalled();
  });

  it("does not offer a second run of this simulation while its job is queued or running", async () => {
    await mount();
    await click("ve-assess-networks");
    model.all = [{ id: "job1", kind: "tract", state: "running" }];
    act(() => root.render(
      <QueryClientProvider client={new QueryClient()}>
        <AssessNetworks subjectId="ernie" simulationName="L_Insula" onQueued={onQueued} />
      </QueryClientProvider>,
    ));
    await settle();
    expect(byTestId("ve-assess-networks")!.disabled).toBe(true);
    expect(byTestId("ve-assess-networks")!.textContent).toContain("Assessing");
  });

  it("is refreshed by a finished tract job, which rewrites what the tab reads", () => {
    const keys = queriesAffectedBy("tract").map((key) => key[0]);
    expect(keys).toContain("simulation-networks");
    expect(keys).toContain("tract-preflight");
    expect(queriesAffectedBy("blender").map((key) => key[0])).toContain("simulation-networks");
  });
});
