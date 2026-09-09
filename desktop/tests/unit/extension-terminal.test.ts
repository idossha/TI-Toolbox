import { describe, expect, it } from "vitest";
import { resolveFollowedJob, type FollowableJob } from "../../src/renderer/pages/_shared/run/terminalSources";
import { hasActiveJob } from "../../src/renderer/pages/_shared/run/RunPaneTabs";

function job(kind: string, state: FollowableJob["state"]): FollowableJob {
  return { id: "submitted", kind, state, subject: "101, 102", subjects: ["101", "102"], elapsed: "1s", createdAt: 10 };
}

describe.each(["source", "stats", "nifti_average", "nilearn", "blender"])("%s extension terminal", (kind) => {
  it("follows a group job for any participating subject and retains its completed log", () => {
    expect(resolveFollowedJob([job(kind, "running")], [kind], ["102"])?.id).toBe("submitted");
    expect(resolveFollowedJob([job(kind, "succeeded")], [kind], ["102"], null, ["submitted"])?.id).toBe("submitted");
  });
  it("does not make a fresh page look like it started an old job", () => {
    expect(resolveFollowedJob([job(kind, "succeeded")], [kind], ["102"])).toBeNull();
    expect(resolveFollowedJob([job("sim", "running")], [kind], ["102"])).toBeNull();
  });
  it("switches the automatic preview to terminal for queued jobs", () => {
    expect(hasActiveJob([job(kind, "queued")], [kind])).toBe(true);
    expect(hasActiveJob([job("sim", "running")], [kind])).toBe(false);
  });
});
