// @vitest-environment jsdom
/**
 * Optimizer: a mixed-kind Run whose second group is refused (G1-3).
 *
 * `POST /api/jobs/groups` takes one kind, so a table mixing a plain Flex search and an adaptive
 * focality search is two groups, submitted one after the other (ARCHITECTURE §7.5: the UI must
 * not imply atomicity). When the first group was accepted and the second failed, the page used to
 * say only "Could not queue the search.", keep the cached flex folder, and a re-press resubmitted
 * the accepted group as well. Now: the notice names the kind that was queued, the flex plan is
 * refetched (a fresh automatic folder), and a re-press submits only the kind that failed.
 *
 * What is mocked: only the wire (`api.GET`/`api.POST` of the real client) plus the panes that
 * draw (run panel, scene, row table) and the subject/jobs contexts. Expected values: the group
 * kinds come from `jobKindFor` (goal "focality" + adaptive → `flex_adaptive`, otherwise `flex`),
 * the `JobGroupRequest` contract and the answers queued below. Dated 2026-10-31.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/optimizer-partial-submit.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";
import { emptyOptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import { defaultFlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi";

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string) => toast.error(message),
}));
vi.mock("../../src/renderer/app/subjectContext", async (original) => ({
  ...(await original<object>()),
  useSubject: () => ({ id: "101", subjects: [{ id: "101", has_m2m: true }] }),
}));
vi.mock("../../src/renderer/app/jobs/useJobsStream", () => ({ useJobsStream: () => ({ jobs: {} }) }));
vi.mock("../../src/renderer/pages/_shared/run", async (original) => ({ ...(await original<object>()), RunPanel: () => null }));
vi.mock("../../src/renderer/pages/_shared/scene/TargetPreview", () => ({ TargetPreview: () => null }));
vi.mock("../../src/renderer/pages/optimizer/JobRows", () => ({ OptimizerJobRows: () => null }));

const { default: page } = await import("../../src/renderer/pages/optimizer/index");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

type Wire = { data?: unknown; error?: unknown; response: Response };
const ok = (data: unknown): Wire => ({ data, response: new Response(null, { status: 200 }) });
const refused = (status: number, detail: string): Wire => ({ error: { detail }, response: new Response(null, { status }) });

let groupAnswers: Wire[];
let groupBodies: { kind: string; overwrite?: boolean; config: { output_folder?: string } }[];
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

const sphere: RoiValue = { mode: "spherical", spheres: [{ x: 1, y: 2, z: 3, radius: 10 }], space: "subject", volumetric: false, tissues: "GM" };

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  for (const fn of Object.values(toast)) fn.mockReset();
  groupAnswers = [];
  groupBodies = [];
  vi.spyOn(api, "GET").mockImplementation((async () => ok([])) as never);
  vi.spyOn(api, "POST").mockImplementation((async (path: string, init: { body: Record<string, unknown> }) => {
    if (path === "/api/validate/{kind}") return ok({ ok: true, errors: [] });
    if (path === "/api/plan/{kind}") {
      const folder = (init.body.config as { output_folder?: string | null }).output_folder ?? "/p/derivatives/sub-101/flex/auto";
      return ok({ jobs: [{ kind: "flex", subject: "101", output_dir: folder, exists: false, will_overwrite: false }], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] });
    }
    if (path === "/api/jobs/groups") {
      groupBodies.push(structuredClone(init.body) as never);
      return groupAnswers.shift() ?? refused(500, "no answer queued");
    }
    return refused(404, `unexpected POST ${path}`);
  }) as never);

  clearPageSession();
  const plain = emptyOptimizerRow({ subjectId: "101", roi: sphere });
  const adaptive = emptyOptimizerRow({ subjectId: "101", roi: sphere, flex: { ...defaultFlexFormState(), goal: "focality", focalityMode: "adaptive" } });
  writeSession(sessionSlot("", "jobRows"), [plain, adaptive]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // The schema itself is loaded by setup-app-defaults.ts; this tells withAppDefaults it is there.
  client.setQueryData(["schema"], true);
  const Page = page.Component;
  act(() =>
    root.render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <Page />
        </QueryClientProvider>
      </MemoryRouter>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

async function settle() {
  for (let i = 0; i < 6; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }
}

async function pressRun() {
  await settle();
  const run = document.querySelector<HTMLButtonElement>('[data-testid="run-button"]')!;
  expect(run.disabled, run.title).toBe(false);
  await act(async () => run.click());
  await settle();
}

it("names the queued kind, refreshes the flex folder, and a re-press resubmits only the failed kind", async () => {
  groupAnswers = [ok({ group_id: "g1", jobs: [{ id: "j-flex" }] }), refused(500, "boom")];
  await pressRun();

  expect(groupBodies.map((b) => b.kind)).toEqual(["flex", "flex_adaptive"]);
  const queuedNotice = [...toast.success.mock.calls, ...toast.info.mock.calls].map((c) => String(c[0])).join(" ");
  expect(queuedNotice, "the accepted group is announced").toMatch(/flex\b/i);
  expect(toast.error).toHaveBeenCalledTimes(1);

  groupAnswers = [ok({ group_id: "g2", jobs: [{ id: "j-adaptive" }] })];
  await pressRun();
  expect(groupBodies.map((b) => b.kind), "only the refused kind is resubmitted").toEqual(["flex", "flex_adaptive", "flex_adaptive"]);
  // The accepted group invalidated the plan, so the re-press carries a freshly resolved folder.
  expect(groupBodies[2]!.config.output_folder, "the resubmitted job got a fresh folder").not.toBe(groupBodies[1]!.config.output_folder);
});
