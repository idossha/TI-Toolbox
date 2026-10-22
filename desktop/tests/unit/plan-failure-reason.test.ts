/**
 * A plan request the server refuses becomes the blocked reason, in the server's own words
 * (p19, 2026-10-22; DESIGN.md §4.2 rule 8: the primary is never silently disabled — and never
 * enabled over a plan the server refused).
 *
 * Before: the Simulator computed `failed` and nothing read it (Run submitted every row); the
 * Analyzer's `Promise.all` dropped the whole plan on one 422, leaving "Resolving the plan…" with
 * Run enabled; the Optimizer stayed on "Resolving the run folders…" forever; Pre-processing never
 * read `planQuery.error`. The pages' wiring is driven end to end by
 * `tests/e2e/run-plan-errors.spec.ts` (and the Analyzer's collision by `run-collision.spec.ts`);
 * this file pins the shared sentence, the two pure seams, and the Analyzer's `blockedReasonFor`
 * order: the form's own clauses first, then the server's refusal, then two jobs into one folder
 * (a refused job has no folder to compare).
 *
 * The expected sentences are the server's `detail` strings as `api/client.ts::unwrap` hands them
 * over (an `ApiError` whose message IS the detail), typed here, prefixed by the row label.
 * Reproduce: `cd desktop && npx vitest run tests/unit/plan-failure-reason.test.ts`.
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import { planFailureReason } from "../../src/renderer/pages/_shared/run/planModel";
import { simPlanBlockedReason } from "../../src/renderer/pages/simulator/RunControls";
import { AnalyzerPlanError, planAnalyzerBatch, type AnalyzerJobSpec } from "../../src/renderer/pages/analyzer/api";
import { blockedReasonFor } from "../../src/renderer/pages/analyzer/AnalyzerPage";

const DETAIL = "mask_path: mask is not accessible";
const refused = (detail = DETAIL) => new ApiError(422, "/api/plan/{kind}", detail);

describe("planFailureReason", () => {
  it("quotes the first failed request's detail, prefixed with its job", () => {
    expect(planFailureReason([{ label: "Job 1" }, { label: "Job 2", error: refused() }, { label: "Job 3", error: refused("other") }])).toBe(
      `Job 2: ${DETAIL}`,
    );
  });

  it("is null while nothing has failed (pending and answered requests alike)", () => {
    expect(planFailureReason([{ label: "Job 1" }, { label: "Job 2", error: null }])).toBeNull();
    expect(planFailureReason([])).toBeNull();
  });

  it("quotes the detail alone when the page plans in one request", () => {
    expect(planFailureReason([{ error: refused() }])).toBe(DETAIL);
  });

  it("keeps the first non-empty line of a multi-line detail, the sentence a tooltip can show", () => {
    expect(planFailureReason([{ label: "Job 4", error: refused("\nfield 'roi' is required\n  at config.roi") }])).toBe(
      "Job 4: field 'roi' is required",
    );
  });

  it("states the status when the server sent no sentence, and a network failure as itself", () => {
    expect(planFailureReason([{ label: "Job 1", error: new ApiError(500, "/api/plan/{kind}") }])).toBe(
      "Job 1: /api/plan/{kind} failed with HTTP 500",
    );
    expect(planFailureReason([{ label: "Job 1", error: new TypeError("Failed to fetch") }])).toBe("Job 1: Failed to fetch");
  });
});

describe("Simulator: a refused row blocks the whole press", () => {
  it("names the row by subject and montage and quotes the server", () => {
    const rows = [
      { subjectId: "ernie", name: "M1" },
      { subjectId: "ernie", name: "M2" },
    ];
    const outcomes = [{ data: { jobs: [{ output_dir: "/p/sub-ernie/Simulations/M1" }] } }, { error: refused() }];
    expect(simPlanBlockedReason(rows, outcomes)).toBe(`ernie · M2: ${DETAIL}`);
  });

  it("reports the refusal before any collision among the rows that did answer", () => {
    const dir = "/p/sub-ernie/Simulations/M";
    const rows = [{ subjectId: "ernie", name: "M" }, { subjectId: "ernie", name: "M" }, { subjectId: "ernie", name: "X" }];
    const outcomes = [{ data: { jobs: [{ output_dir: dir }] } }, { data: { jobs: [{ output_dir: dir }] } }, { error: refused() }];
    expect(simPlanBlockedReason(rows, outcomes)).toBe(`ernie · X: ${DETAIL}`);
  });
});

/** An openapi-fetch client double: records each planned config, refuses the ones named "bad". */
function spyClient(costs: Record<string, { cpus: number; mem_gb: number; eta_minutes: number | null }>) {
  const planned: string[] = [];
  const client = {
    POST: async (_path: string, init: { body: { config: { simulation: string; subject_id: string } } }) => {
      const sim = init.body.config.simulation;
      planned.push(sim);
      if (sim === "bad") return { error: { detail: DETAIL }, response: new Response(null, { status: 422 }) };
      const cost = costs[sim] ?? { cpus: 1, mem_gb: 1, eta_minutes: null };
      return {
        data: {
          jobs: [{ kind: "analyzer", subject: init.body.config.subject_id, output_dir: `/p/${sim}`, exists: false, will_overwrite: false }],
          lock_conflicts: [],
          cost: { ...cost, system: null },
          warnings: [],
          resolved: null,
        },
        response: new Response(null, { status: 200 }),
      };
    },
  };
  return { planned, client: client as never };
}

const spec = (simulation: string, label: string): AnalyzerJobSpec => ({
  config: { simulation, subject_id: "ernie" } as never,
  subjectIds: ["ernie"],
  label,
});

describe("Analyzer: planAnalyzerBatch", () => {
  it("plans every item even when one is refused, and says WHICH item failed with the server's error", async () => {
    const { planned, client } = spyClient({});
    const batch = planAnalyzerBatch([spec("a", "Job 1"), spec("bad", "Job 2"), spec("c", "Job 3")], false, client);
    const error = await batch.then(
      () => null,
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(AnalyzerPlanError);
    expect((error as AnalyzerPlanError).index).toBe(1);
    expect((error as AnalyzerPlanError).reason).toBeInstanceOf(ApiError);
    expect(((error as AnalyzerPlanError).reason as ApiError).message).toBe(DETAIL);
    // `allSettled`, not `all`: the third request was still made.
    expect(planned).toEqual(["a", "bad", "c"]);
  });

  it("keeps each item's own plan, in item order, beside the merge", async () => {
    const { client } = spyClient({});
    const result = await planAnalyzerBatch([spec("a", "Job 1"), spec("c", "Job 2")], false, client);
    expect(result.items?.map((p) => p.jobs.map((j) => j.output_dir))).toEqual([["/p/a"], ["/p/c"]]);
    expect(result.jobs.map((j) => j.output_dir)).toEqual(["/p/a", "/p/c"]);
  });
});

describe("Analyzer: blockedReasonFor states the server's verdicts after the form's", () => {
  const REFUSED = `Job 2: ${DETAIL}`;
  const SHARED = "Job 1 and Job 2 both write sub-ernie/Simulations/Thalamus/Analyses/A; the last to run would replace the others' results. Rename or remove one.";
  const complete = { subjectsBlocked: null, rowCount: 2, targetReady: true };

  it("blocks on the server's refusal of a complete table, verbatim", () => {
    expect(blockedReasonFor({ ...complete, planFailure: REFUSED })).toBe(REFUSED);
  });

  it("blocks on two jobs into one folder, verbatim", () => {
    expect(blockedReasonFor({ ...complete, outputCollision: SHARED })).toBe(SHARED);
  });

  it("names the refusal before the collision: a refused job's folder is unknown", () => {
    expect(blockedReasonFor({ ...complete, planFailure: REFUSED, outputCollision: SHARED })).toBe(REFUSED);
  });

  it("lets Run through when the server neither refused a job nor found a shared folder", () => {
    expect(blockedReasonFor({ ...complete, planFailure: null, outputCollision: null })).toBeNull();
  });

  it("says what the form lacks first: only a complete table is planned", () => {
    const server = { planFailure: REFUSED, outputCollision: SHARED };
    expect(blockedReasonFor({ ...complete, ...server, targetReady: false })).toBe("Complete the target before running.");
    expect(blockedReasonFor({ ...complete, ...server, groupMismatch: "mixed simulations" })).toBe("mixed simulations");
    expect(blockedReasonFor({ ...complete, ...server, subjectsBlocked: "101 cannot run — no simulations." })).toBe(
      "101 cannot run — no simulations.",
    );
    expect(blockedReasonFor({ ...complete, ...server, rowCount: 0 })).toBe("Add a row with a subject and a simulation.");
  });
});
