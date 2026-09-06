/**
 * `resolveFollowedJob` — which job a run page's Terminal follows (DESIGN.md v3 §4.6, fix lane
 * FXU2). "Which log am I reading" must never be a guess, and — the rule this lane added — opening
 * a page must never *look* like it started a job, so the rule is a pure function with its own
 * tests rather than an `if` chain inside a component.
 */
import { describe, expect, it } from "vitest";
import { resolveFollowedJob, type FollowableJob } from "../../src/renderer/pages/_shared/run/terminalSources";

function j(over: Partial<FollowableJob> & { id: string; kind: string; state: FollowableJob["state"] }): FollowableJob {
  return {
    subject: over.subjects?.join(", ") ?? "ernie",
    subjects: ["ernie"],
    elapsed: "1m 0s",
    createdAt: 1000,
    ...over,
  };
}

describe("resolveFollowedJob", () => {
  const running = j({ id: "r", kind: "pre", state: "running", subjects: ["ernie"], createdAt: 3000 });
  const olderRunning = j({ id: "r2", kind: "pre", state: "queued", subjects: ["999"], createdAt: 4000 });
  const finished = j({ id: "f", kind: "pre", state: "succeeded", subjects: ["ernie"], createdAt: 2000 });
  const otherKind = j({ id: "x", kind: "sim", state: "running", subjects: ["ernie"], createdAt: 9000 });

  it("pins nothing when the only job of this kind has finished — an idle page is an idle page", () => {
    // The maintainer's screenshot: opening Pre-processing showed `pre · 102 · succeeded 12s` with
    // a full DICOM log, which reads as "a job is happening". It never is.
    expect(resolveFollowedJob([finished], ["pre"], ["ernie"])).toBeNull();
    const alsoFinished = j({ id: "f2", kind: "pre", state: "failed", createdAt: 8000 });
    expect(resolveFollowedJob([finished, alsoFinished], ["pre"], ["ernie"])).toBeNull();
  });

  it("follows a job that is genuinely running or queued when the page opens", () => {
    expect(resolveFollowedJob([finished, running], ["pre"], ["ernie"])?.id).toBe("r");
    const queued = j({ id: "q", kind: "pre", state: "queued", createdAt: 100 });
    expect(resolveFollowedJob([queued], ["pre"], ["ernie"])?.id).toBe("q");
  });

  it("keeps a pin the user made, whatever state that job is in", () => {
    // Page-session state (`usePageSession("pinnedJob")`), so it survives navigation in the session.
    expect(resolveFollowedJob([running, finished], ["pre"], ["ernie"], "f")?.id).toBe("f");
  });

  it("falls back to the running job when the pinned id is not in the list any more", () => {
    expect(resolveFollowedJob([running], ["pre"], ["ernie"], "gone")?.id).toBe("r");
    expect(resolveFollowedJob([finished], ["pre"], ["ernie"], "gone")).toBeNull();
  });

  it("prefers the running job whose subjects intersect the page's selection", () => {
    // `olderRunning` is newer but belongs to a subject the page has not selected.
    expect(resolveFollowedJob([running, olderRunning], ["pre"], ["ernie"])?.id).toBe("r");
  });

  it("drops the subject filter when nothing intersects — a run is still a run", () => {
    expect(resolveFollowedJob([olderRunning], ["pre"], ["ernie"])?.id).toBe("r2");
  });

  it("never follows a job of another kind, however new it is", () => {
    expect(resolveFollowedJob([otherKind, finished], ["pre"], ["ernie"])).toBeNull();
    expect(resolveFollowedJob([otherKind], ["pre"], ["ernie"])).toBeNull();
  });

  it("follows any of the page's kinds — the merged Optimizer's flex/ex/mex", () => {
    const ex = j({ id: "e", kind: "ex", state: "running", createdAt: 5000 });
    expect(resolveFollowedJob([ex, otherKind], ["flex", "ex", "mex"], ["ernie"])?.id).toBe("e");
  });

  it("ties break on createdAt descending", () => {
    const a = j({ id: "a", kind: "pre", state: "running", createdAt: 10 });
    const b = j({ id: "b", kind: "pre", state: "running", createdAt: 20 });
    expect(resolveFollowedJob([a, b], ["pre"], ["ernie"])?.id).toBe("b");
  });

  it("returns null when there is nothing of this kind at all — the empty console, not a wrong log", () => {
    expect(resolveFollowedJob([], ["pre"], ["ernie"])).toBeNull();
  });
});
