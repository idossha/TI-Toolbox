// @vitest-environment jsdom
/**
 * The agent's plan card (app/proposals): what the user reads before approving, and what the
 * buttons send. Pins: settings are shown in the user's terms (goal, target, current, electrodes,
 * run name; a sim_from_flex step names its flex step); an output the plan would replace is a
 * danger callout that says whether replacing is allowed; Approve is disabled while the server
 * would refuse; Approve / Reject (with the note) / Edit (with the edited run name) call the
 * proposal routes; after approval a step's state follows its jobs in the live store and its job
 * opens on click.
 *
 * Where the expected values come from: the fixture below is authored here in the contract's
 * `Proposal` shape (contracts/openapi.yaml), so every expected string restates the fixture, not
 * the code. The server side of the same flow is tests/test_proposals_routes.py.
 * Reproduce: cd desktop && npx vitest run tests/unit/proposal-card.test.tsx
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { approveProposal, dismissProposal, editStep, rejectProposal, runStep } from "../../src/renderer/app/proposals/api";
import { ProposalCard, ProposalsStrip } from "../../src/renderer/app/proposals/ProposalCard";
import { liveStepState, overwrites, stepFacts, visibleProposals, type Proposal } from "../../src/renderer/app/proposals/model";
import type { JobStatus } from "../../src/renderer/app/jobs/types";

vi.mock("../../src/renderer/app/proposals/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../src/renderer/app/proposals/api")>()),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
  dismissProposal: vi.fn(),
  editStep: vi.fn(),
  runStep: vi.fn(),
}));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const plan = (extra: Partial<NonNullable<Proposal["steps"][number]["plan"]>> = {}) => ({
  errors: [],
  missing_inputs: [],
  outputs: [],
  will_overwrite: [],
  warnings: [],
  eta_minutes: null,
  deferred: null,
  ...extra,
});

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: "abcdef0123456789",
    title: "Maximise the field in the left thalamus",
    rationale: "You asked for the strongest field.",
    created_by: "agent",
    client: "Claude Code",
    created_at: "2026-10-07T10:00:00+00:00",
    updated_at: "2026-10-07T10:00:00+00:00",
    status: "pending",
    decision: { state: "pending", at: null, note: null },
    edited: false,
    proposed_steps: [],
    steps: [
      {
        id: "opt",
        kind: "flex",
        subject_ids: ["101"],
        after: [],
        overwrite: false,
        job_ids: [],
        state: "proposed",
        config: {
          goal: "mean",
          current_mA: 2,
          output_folder: "thalamus_mean",
          electrode: { shape: "ellipse", dimensions: [8, 8], gel_thickness: 4 },
          roi: { _type: "SubcorticalROI", atlas_path: ["/p/aseg.nii.gz"], label: [10], tissues: "GM" },
        },
        plan: plan({
          outputs: [{ subject: "101", output_dir: "/p/flex-search/thalamus_mean", exists: true }],
          will_overwrite: ["/p/flex-search/thalamus_mean"],
          eta_minutes: 25,
        }),
      },
      {
        id: "sim",
        kind: "sim_from_flex",
        subject_ids: ["101"],
        after: ["opt"],
        overwrite: false,
        job_ids: [],
        state: "proposed",
        config: { flex_step: "opt" },
        plan: plan({ deferred: "Electrodes and currents come from step opt's flex-search result once it finishes." }),
      },
    ],
    ...overrides,
  } as Proposal;
}

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
beforeEach(() => {
  vi.resetAllMocks();
  const store = new Map<string, string>(); // this jsdom's localStorage has no clear()
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  });
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

/** The card on /jobs; any other route prints where "Open in form" went and what it carried. */
function Landed() {
  const location = useLocation();
  return <pre data-testid="landed">{JSON.stringify({ path: location.pathname, state: location.state })}</pre>;
}
function inApp(node: React.ReactNode) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/jobs"]}>
        <Routes>
          <Route path="/jobs" element={node} />
          <Route path="*" element={<Landed />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
function render(p: Proposal, jobs: Record<string, JobStatus> = {}, onOpenJob = vi.fn()) {
  act(() => root.render(inApp(<ProposalCard proposal={p} jobs={jobs} onOpenJob={onOpenJob} />)));
  return onOpenJob;
}
const button = (name: string) => [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === name);
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
}
function type(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("states each step's settings in the user's terms", () => {
  const p = proposal();
  const facts = Object.fromEntries(stepFacts(p.steps[0]!, p.steps));
  expect(facts).toMatchObject({
    Goal: "Mean field in the target",
    Target: "Subcortical labels 10 · aseg.nii.gz",
    Current: "2 mA per channel",
    Electrodes: "ellipse 8 × 8 mm",
    "Run name": "thalamus_mean",
  });
  const sim = Object.fromEntries(stepFacts(p.steps[1]!, p.steps));
  expect(sim["Electrodes from"]).toBe("step opt (thalamus_mean)");
  expect(sim.Currents).toBe("the run's own");
  expect(overwrites(p)).toEqual([{ step: "opt", path: "/p/flex-search/thalamus_mean", allowed: false }]);
});

it("shows the plan, warns loudly about replaced output, and approves", async () => {
  vi.mocked(approveProposal).mockResolvedValue(proposal({ status: "running" }));
  render(proposal());
  const text = container.textContent ?? "";
  expect(text).toContain("Maximise the field in the left thalamus");
  expect(text).toContain("from Claude Code");
  expect(text).toContain("waiting for you");
  expect(text).toContain("after step opt");
  expect(text).toContain("~25 min");
  const alert = container.querySelector('[role="alert"]');
  expect(alert?.textContent).toContain("replaces existing results");
  expect(alert?.textContent).toContain("/p/flex-search/thalamus_mean");
  expect(alert?.textContent).toContain("not allowed yet");
  expect(button("Approve and run")!.disabled).toBe(true); // the server would refuse it too

  const allowed = proposal();
  allowed.steps[0] = { ...allowed.steps[0]!, overwrite: true };
  render(allowed);
  expect(container.querySelector('[role="alert"]')?.textContent).not.toContain("not allowed yet");
  act(() => button("Approve and run")!.click());
  await settle();
  expect(approveProposal).toHaveBeenCalledWith("abcdef0123456789");
});

it("cannot approve a plan the server would refuse", () => {
  const p = proposal();
  p.steps[0]!.plan = plan({ errors: ["roi: missing"] });
  render(p);
  expect(button("Approve and run")!.disabled).toBe(true);
  expect(container.textContent).toContain("Step opt: roi: missing");
});

it("rejects with the user's note", async () => {
  vi.mocked(rejectProposal).mockResolvedValue(proposal({ status: "rejected" }));
  render(proposal());
  act(() => button("Reject…")!.click());
  type(container.querySelector('input[aria-label="Rejection note"]')!, "use the right thalamus");
  act(() => button("Reject plan")!.click());
  await settle();
  expect(rejectProposal).toHaveBeenCalledWith("abcdef0123456789", "use the right thalamus");
});

it("edits a step's run name and the replace permission", async () => {
  vi.mocked(editStep).mockResolvedValue(proposal());
  render(proposal());
  act(() => button("Edit")!.click());
  const editor = container.querySelector('[data-testid="proposal-editor-opt"]')!;
  type(editor.querySelector('input[aria-label="Run name"]')!, "thalamus_v2");
  act(() => (editor.querySelector('button[role="checkbox"]') as HTMLButtonElement).click());
  act(() => button("Save step")!.click());
  await settle();
  const [id, step, edit] = vi.mocked(editStep).mock.calls[0]!;
  expect([id, step]).toEqual(["abcdef0123456789", "opt"]);
  expect(edit.config!.output_folder).toBe("thalamus_v2");
  expect(edit.config!.goal).toBe("mean");
  expect(edit.overwrite).toBe(true);
  expect(edit.subject_ids).toEqual(["101"]);
});

it("the editor's actions are one footer (Open in form, Cancel, Save step) and Cancel closes it", () => {
  render(proposal());
  act(() => button("Edit")!.click());
  const editor = container.querySelector('[data-testid="proposal-editor-opt"]')!;
  expect(button("Close")).toBeUndefined(); // no second close control in the step's head
  expect(container.querySelector('[data-testid="proposal-step-opt"] .proposal-step-end')?.textContent).not.toContain("Edit");
  const footer = editor.querySelector(".proposal-editor-actions")!;
  expect([...footer.querySelectorAll("button")].map((b) => b.textContent?.trim())).toEqual(["Open in form", "Cancel", "Save step"]);
  // The checkbox is the shared one: box and its label in one row element.
  const row = editor.querySelector(".checkbox-label-row")!;
  expect(row.querySelector('button[role="checkbox"]')).not.toBeNull();
  expect(row.textContent).toBe("Replace existing output");
  expect(editor.querySelector("details.proposal-editor-json")?.hasAttribute("open")).toBe(false); // JSON folded
  act(() => button("Cancel")!.click());
  expect(container.querySelector('[data-testid="proposal-editor-opt"]')).toBeNull();
  expect(button("Edit")).toBeDefined();
});

it("Open in form goes to the step's run page with the step, carrying what was typed", () => {
  render(proposal());
  const [flexEdit, simEdit] = [...container.querySelectorAll("button")].filter((b) => b.textContent?.trim() === "Edit");
  act(() => simEdit!.click());
  act(() => flexEdit!.click());
  const editor = container.querySelector('[data-testid="proposal-editor-opt"]')!;
  type(editor.querySelector('input[aria-label="Run name"]')!, "thalamus_v2");
  act(() => (editor.querySelector('button[role="checkbox"]') as HTMLButtonElement).click());
  act(() => [...editor.querySelectorAll("button")].find((b) => b.textContent === "Open in form")!.click());
  const landed = JSON.parse(container.querySelector('[data-testid="landed"]')!.textContent!);
  expect(landed.path).toBe("/optimizer");
  expect(landed.state.planStep).toMatchObject({
    proposalId: "abcdef0123456789",
    stepId: "opt",
    number: 1,
    title: "Maximise the field in the left thalamus",
    kind: "flex",
    subjectIds: ["101"],
    overwrite: true,
  });
  expect(landed.state.planStep.config.output_folder).toBe("thalamus_v2");
  expect(landed.state.planStep.config.goal).toBe("mean");
});

it("a sim_from_flex step opens on the Simulator, naming its flex step's run", () => {
  render(proposal());
  const simEdit = [...container.querySelectorAll("button")].filter((b) => b.textContent?.trim() === "Edit")[1]!;
  act(() => simEdit.click());
  act(() => button("Open in form")!.click());
  const landed = JSON.parse(container.querySelector('[data-testid="landed"]')!.textContent!);
  expect(landed.path).toBe("/simulator");
  expect(landed.state.planStep).toMatchObject({ stepId: "sim", number: 2, kind: "sim_from_flex", flexRun: "thalamus_mean" });
});

it("after approval follows each step's jobs live and opens them", () => {
  const p = proposal({ status: "running", decision: { state: "approved", at: "2026-10-07T10:01:00+00:00", note: null } });
  p.steps[0] = { ...p.steps[0]!, state: "queued", job_ids: ["job00001aaaa"] };
  p.steps[1] = { ...p.steps[1]!, state: "waiting" };
  const jobs = { job00001aaaa: { id: "job00001aaaa", state: "running" } as JobStatus };
  expect(liveStepState(p.steps[0]!, jobs)).toBe("running");
  expect(liveStepState(p.steps[0]!, {})).toBe("queued"); // store does not know it yet: the server's
  const onOpenJob = render(p, jobs);
  expect(container.querySelector('[data-testid="proposal-step-opt"]')?.getAttribute("data-state")).toBe("running");
  expect(container.querySelector('[data-testid="proposal-step-sim"]')?.getAttribute("data-state")).toBe("waiting");
  expect(button("Approve and run")).toBeUndefined();
  act(() => button("job00001")!.click());
  expect(onOpenJob).toHaveBeenCalledWith("job00001aaaa");
});

it("keeps undecided and in-flight plans, and only a day of the rest", () => {
  const now = Date.parse("2026-10-08T12:00:00Z");
  const old = { ...proposal(), id: "old", status: "succeeded", updated_at: "2026-10-01T00:00:00Z" } as Proposal;
  const recent = { ...proposal(), id: "recent", status: "rejected", updated_at: "2026-10-08T11:00:00Z" } as Proposal;
  const waiting = { ...proposal(), id: "waiting", updated_at: "2026-09-01T00:00:00Z" } as Proposal;
  const failed = { ...proposal(), id: "failed", status: "failed", updated_at: "2026-09-01T00:00:00Z" } as Proposal; // stays until dismissed
  expect(visibleProposals([old, recent, waiting, failed], now).map((p) => p.id)).toEqual(["recent", "waiting", "failed"]);
});

function renderStrip(proposals: Proposal[], onOpenJob = vi.fn()) {
  act(() => root.render(inApp(<ProposalsStrip proposals={proposals} jobs={{}} onOpenJob={onOpenJob} />)));
  return onOpenJob;
}
const done = (id: string, extra: Partial<Proposal> = {}) =>
  proposal({ id, title: `Plan ${id}`, status: "succeeded", decision: { state: "approved", at: null, note: null }, ...extra });

it("renders plans that need you, are in flight or failed as cards; done and rejected ones fold into a list", () => {
  const running = proposal({ id: "run", title: "Plan run", status: "running" });
  const failed = done("failed", { status: "failed" });
  failed.steps[0] = { ...failed.steps[0]!, job_ids: ["job00001aaaa"] };
  renderStrip([done("ok"), failed, proposal({ id: "wait" }), running, proposal({ id: "no", title: "Plan no", status: "rejected" })]);
  const cards = [...container.querySelectorAll('[data-testid="proposal-card"]')];
  expect(cards.map((c) => c.getAttribute("data-status"))).toEqual(["pending", "running", "failed"]); // pending, running, failed
  const toggle = container.querySelector(".finished-plans-toggle")!;
  expect(toggle.textContent).toContain("Finished plans (2)");
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(container.querySelectorAll('[data-testid="finished-plan"]')).toHaveLength(0); // collapsed by default
});

it("keeps a failed plan as a full card with its failed step, job link, Retry and Dismiss", async () => {
  const failed = done("failed", { status: "failed" });
  failed.steps[0] = { ...failed.steps[0]!, state: "succeeded", job_ids: ["job0000aaaa"] };
  failed.steps[1] = { ...failed.steps[1]!, state: "failed", job_ids: ["job00001bbbb"] };
  vi.mocked(runStep).mockResolvedValue(done("failed", { status: "running" }));
  vi.mocked(dismissProposal).mockResolvedValue(failed);
  client.setQueryData(["proposals"], [failed]);
  const onOpenJob = renderStrip([failed]);
  expect(container.querySelector('[data-testid="proposal-card"]')?.getAttribute("data-status")).toBe("failed");
  expect(container.querySelector('[data-testid="finished-plans"]')).toBeNull();
  expect(container.querySelector('[data-testid="proposal-step-sim"]')?.getAttribute("data-state")).toBe("failed");
  act(() => button("job00001")!.click());
  expect(onOpenJob).toHaveBeenCalledWith("job00001bbbb");

  const retries = [...container.querySelectorAll("button")].filter((b) => b.textContent?.trim() === "Retry step");
  expect(retries).toHaveLength(1); // only the failed step, not the succeeded one
  act(() => retries[0]!.click());
  await settle();
  expect(runStep).toHaveBeenCalledWith("failed", "sim");

  act(() => (container.querySelector('button[aria-label^="Dismiss"]') as HTMLButtonElement).click());
  await settle();
  expect(dismissProposal).toHaveBeenCalledWith("failed");
  expect(client.getQueryData(["proposals"])).toEqual([]);
});

it("shows no finished disclosure when nothing is finished", () => {
  renderStrip([proposal()]);
  expect(container.querySelector('[data-testid="finished-plans"]')).toBeNull();
});

it("lists finished plans compactly, remembers open, opens their jobs and dismisses", async () => {
  vi.mocked(dismissProposal).mockResolvedValue(done("ok"));
  const failed = done("failed", { status: "rejected" });
  failed.steps[0] = { ...failed.steps[0]!, job_ids: ["job00001aaaa"] };
  client.setQueryData(["proposals"], [done("ok"), failed]);
  const onOpenJob = renderStrip([done("ok"), failed]);
  act(() => (container.querySelector(".finished-plans-toggle") as HTMLButtonElement).click());
  const rows = [...container.querySelectorAll('[data-testid="finished-plan"]')];
  expect(rows.map((r) => r.getAttribute("data-status"))).toEqual(["succeeded", "rejected"]);
  expect(rows[0]!.textContent).toContain("Plan ok");
  expect(rows[0]!.textContent).toContain("done");
  expect(rows[0]!.textContent).toContain("from Claude Code");
  expect(container.querySelector('[data-testid="proposal-card"]')).toBeNull();
  expect(window.localStorage.getItem("tit-finished-plans-open")).toBe("1");

  act(() => button("job00001")!.click());
  expect(onOpenJob).toHaveBeenCalledWith("job00001aaaa");

  act(() => (rows[0]!.querySelector('button[aria-label^="Dismiss"]') as HTMLButtonElement).click());
  await settle();
  expect(dismissProposal).toHaveBeenCalledWith("ok");
  expect((client.getQueryData(["proposals"]) as Proposal[]).map((p) => p.id)).toEqual(["failed"]);

  act(() => root.unmount());
  root = createRoot(container);
  renderStrip([failed]); // a fresh mount reads the remembered state
  expect(container.querySelectorAll('[data-testid="finished-plan"]')).toHaveLength(1);
});
