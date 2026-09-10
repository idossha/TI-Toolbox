/**
 * Analyzer Run fan-out (audit UI-05): one rejected submission must not hide the accepted ones,
 * and the next press must retry only what was refused.
 */
import { describe, expect, it, vi } from "vitest";
import { batchReceipt, submitBatch } from "../../src/renderer/pages/analyzer/submitBatch";

describe("submitBatch", () => {
  it("reports the accepted ids and the rejected specs when one submission fails", async () => {
    const submit = vi
      .fn()
      .mockResolvedValueOnce({ id: "job-1" })
      .mockRejectedValueOnce(new Error("subject 101 has no simulation Thalamus"));
    const outcome = await submitBatch(["a", "b"], submit);
    expect(submit).toHaveBeenCalledTimes(2); // both were attempted, not short-circuited
    expect(outcome.acceptedIds).toEqual(["job-1"]);
    expect(outcome.rejected.map((r) => r.spec)).toEqual(["b"]);
    expect(outcome.rejected[0]!.message).toContain("no simulation");
  });

  it("retrying submits only the specs that were refused", async () => {
    const first = vi.fn().mockResolvedValueOnce({ id: "job-1" }).mockRejectedValueOnce(new Error("boom"));
    const outcome = await submitBatch(["a", "b"], first);
    const retry = vi.fn().mockResolvedValue({ id: "job-2" });
    const second = await submitBatch(
      outcome.rejected.map((r) => r.spec),
      retry,
    );
    expect(retry).toHaveBeenCalledTimes(1);
    expect(retry).toHaveBeenCalledWith("b");
    expect(second.acceptedIds).toEqual(["job-2"]);
  });

  it("all accepted: nothing to retry", async () => {
    const outcome = await submitBatch(["a", "b"], vi.fn().mockResolvedValue({ id: "x" }));
    expect(outcome.rejected).toEqual([]);
    expect(outcome.acceptedIds).toHaveLength(2);
  });
});

describe("batchReceipt", () => {
  it("names both halves of a partial failure", () => {
    const text = batchReceipt({ acceptedIds: ["a", "b"], rejected: [{ spec: 1, message: "boom" }] });
    expect(text).toContain("2 of 3");
    expect(text).toContain("retry");
  });

  it("a total failure carries the server's reason for a single job", () => {
    expect(batchReceipt({ acceptedIds: [], rejected: [{ spec: 1, message: "no such subject" }] })).toContain(
      "no such subject",
    );
  });

  it("the all-accepted wording is unchanged", () => {
    expect(batchReceipt({ acceptedIds: ["a"], rejected: [] })).toBe("Queued: analysis");
    expect(batchReceipt({ acceptedIds: ["a", "b"], rejected: [] })).toBe("Queued: 2 analyses");
  });
});
