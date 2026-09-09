/** Rerun submits a fresh reviewed spec, never the old destructive flag via /rerun. */
import { describe, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { prepareJobRerun, rerunJob, withRerunPolicy, type RerunSpec } from "../../src/renderer/app/jobs-rail/api";

const spec = { kind: "source", subject_ids: ["ernie"], overwrite: true, after: ["old-dependency"], config: { forward: { overwrite: "true" } } } as unknown as RerunSpec;

describe("rerun output policy", () => {
  it("clears old top-level and nested flags and old dependencies", () => {
    expect(withRerunPolicy(spec, false)).toMatchObject({ overwrite: false, config: { forward: { overwrite: false } } });
    expect(withRerunPolicy(spec, false).after).toBeUndefined();
    expect(spec.overwrite).toBe(true);
  });

  it("previews the old job before any submit", async () => {
    const GET = vi.fn().mockResolvedValue({ data: { spec }, response: { ok: true } });
    const POST = vi.fn().mockResolvedValue({ data: { jobs: [{ exists: true }] }, response: { ok: true } });
    const client = { GET, POST } as unknown as typeof api;
    expect(await prepareJobRerun("old-job", client)).toMatchObject({ existing: 1, spec: { overwrite: false } });
    expect(POST.mock.calls[0]?.[0]).toBe("/api/plan/{kind}");
    expect(POST.mock.calls[0]?.[1].body.config.forward.overwrite).toBe(false);
  });

  it.each([false, true])("uses this decision (%s), not the old rerun endpoint", async (overwrite) => {
    const POST = vi.fn().mockResolvedValue({ data: {}, response: { ok: true } });
    await rerunJob(spec, overwrite, { POST } as unknown as typeof api);
    expect(POST.mock.calls[0]?.[0]).toBe("/api/jobs");
    expect(POST.mock.calls[0]?.[1].body.overwrite).toBe(overwrite);
    expect(POST.mock.calls[0]?.[1].body.config.forward.overwrite).toBe(overwrite);
  });

  it("allows a fresh report job without calling its unsupported plan endpoint", async () => {
    const GET = vi.fn().mockResolvedValue({ data: { spec: { ...spec, kind: "report" } }, response: { ok: true } });
    const POST = vi.fn();
    expect(await prepareJobRerun("old-report", { GET, POST } as unknown as typeof api)).toMatchObject({ existing: 0, spec: { kind: "report", overwrite: false } });
    expect(POST).not.toHaveBeenCalled();
  });

  it("does not submit jobs whose destinations cannot be previewed", async () => {
    const GET = vi.fn().mockResolvedValue({ data: { spec: { ...spec, kind: "tools" } }, response: { ok: true } });
    const POST = vi.fn();
    await expect(prepareJobRerun("old-job", { GET, POST } as unknown as typeof api)).rejects.toThrow(/no output preview/);
    expect(POST).not.toHaveBeenCalled();
  });
});
