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

  describe("a job this page session started (maintainer, 2026-09-07)", () => {
    // The defect: the analyzer run the maintainer had just watched vanished from the terminal the
    // moment it succeeded — "TERMINAL · No job" with the log gone — because rules 1-3 follow only
    // running jobs and nothing had been pinned by hand.
    const mine = j({ id: "m", kind: "analyzer", state: "succeeded", subjects: ["ernie"], createdAt: 5000 });

    it("stays in the terminal after it finishes", () => {
      expect(resolveFollowedJob([mine], ["analyzer"], ["ernie"], null, ["m"])?.id).toBe("m");
      const failed = j({ id: "m", kind: "analyzer", state: "failed", createdAt: 5000 });
      expect(resolveFollowedJob([failed], ["analyzer"], ["ernie"], null, ["m"])?.id).toBe("m");
      const cancelled = j({ id: "m", kind: "analyzer", state: "cancelled", createdAt: 5000 });
      expect(resolveFollowedJob([cancelled], ["analyzer"], ["ernie"], null, ["m"])?.id).toBe("m");
    });

    it("is still not followed when this page session did not start it", () => {
      // The rule the earlier screenshot forced: opening a tab never auto-pins a finished job.
      expect(resolveFollowedJob([mine], ["analyzer"], ["ernie"])).toBeNull();
      expect(resolveFollowedJob([mine], ["analyzer"], ["ernie"], null, [])).toBeNull();
    });

    it("is replaced by the next run from this page", () => {
      const next = j({ id: "n", kind: "analyzer", state: "running", createdAt: 6000 });
      expect(resolveFollowedJob([mine, next], ["analyzer"], ["ernie"], null, ["n"])?.id).toBe("n");
      // …and once THAT one finishes it is the one that stays.
      const done = j({ id: "n", kind: "analyzer", state: "succeeded", createdAt: 6000 });
      expect(resolveFollowedJob([mine, done], ["analyzer"], ["ernie"], null, ["n"])?.id).toBe("n");
    });

    it("cleared — no started ids — is the empty console again", () => {
      expect(resolveFollowedJob([mine], ["analyzer"], ["ernie"], null, undefined)).toBeNull();
    });

    it("yields to a job that is actually running, and to an explicit pin", () => {
      const other = j({ id: "o", kind: "analyzer", state: "running", createdAt: 1 });
      expect(resolveFollowedJob([mine, other], ["analyzer"], ["ernie"], null, ["m"])?.id).toBe("o");
      expect(resolveFollowedJob([mine, other], ["analyzer"], ["ernie"], "m", ["m"])?.id).toBe("m");
    });

    it("settles on the newest of a multi-stage run, not the first stage to finish", () => {
      // Preprocessing expands one subject into one job per stage; the last one is the one to read.
      const s1 = j({ id: "s1", kind: "pre", state: "succeeded", createdAt: 10 });
      const s2 = j({ id: "s2", kind: "pre", state: "succeeded", createdAt: 20 });
      expect(resolveFollowedJob([s1, s2], ["pre"], ["ernie"], null, ["s1", "s2"])?.id).toBe("s2");
    });

    it("never crosses kinds — a started job of another page is not this page's log", () => {
      expect(resolveFollowedJob([mine], ["pre"], ["ernie"], null, ["m"])).toBeNull();
    });
  });

  it("returns null when there is nothing of this kind at all — the empty console, not a wrong log", () => {
    expect(resolveFollowedJob([], ["pre"], ["ernie"])).toBeNull();
  });
});
