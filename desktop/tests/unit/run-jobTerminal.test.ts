/**
 * `resolveFollowedJob` — rules 1–4 of DESIGN.md v3 §4.6. "Which log am I reading" must never be a
 * guess, so the rule that picks the job is a pure function with its own tests rather than an
 * `if` chain inside a component.
 */
import { describe, expect, it } from "vitest";
import { kindsLabel, resolveFollowedJob, type FollowableJob } from "../../src/renderer/pages/_shared/run/JobTerminal";

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

  it("rule 1 — the pinned job wins outright", () => {
    expect(resolveFollowedJob([running, finished], ["pre"], ["ernie"], "f")?.id).toBe("f");
  });

  it("rule 1 falls through when the pinned id is not in the list any more", () => {
    expect(resolveFollowedJob([running], ["pre"], ["ernie"], "gone")?.id).toBe("r");
  });

  it("rule 2 — the newest running/queued job of this kind whose subjects intersect the selection", () => {
    // `olderRunning` is newer but belongs to a subject the page has not selected.
    expect(resolveFollowedJob([running, olderRunning], ["pre"], ["ernie"])?.id).toBe("r");
  });

  it("rule 3 — the subject filter is dropped when nothing intersects", () => {
    expect(resolveFollowedJob([olderRunning], ["pre"], ["ernie"])?.id).toBe("r2");
  });

  it("rule 4 — the most recently finished job of this kind, so a log stays readable after it ends", () => {
    expect(resolveFollowedJob([finished], ["pre"], ["ernie"])?.id).toBe("f");
  });

  it("never follows a job of another kind, however new it is", () => {
    expect(resolveFollowedJob([otherKind, finished], ["pre"], ["ernie"])?.id).toBe("f");
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

  it("returns null when there is nothing of this kind at all — the empty state, not a wrong log", () => {
    expect(resolveFollowedJob([], ["pre"], ["ernie"])).toBeNull();
  });
});

describe("copy", () => {
  it("kindsLabel names the page's kinds for the empty state's hint", () => {
    expect(kindsLabel(["pre"])).toBe("Pre-processing");
    expect(kindsLabel(["flex", "ex", "mex"])).toBe("Flex-search, Ex-search and mEx-search");
  });
});
