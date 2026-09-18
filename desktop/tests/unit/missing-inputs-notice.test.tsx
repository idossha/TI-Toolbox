// @vitest-environment jsdom
/**
 * A submission the server refused with HTTP 422 `{detail: "Missing inputs", missing: [...]}`
 * (`tit.jobs.preflight`) reaches the user as one blocking notice with one line per input:
 * what · where it was expected · how to produce it. Never a bare "Could not queue".
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({
  Toaster: () => null,
  toast: Object.assign(vi.fn(), { error: toastError, success: vi.fn(), message: vi.fn() }),
}));

import { ApiError, createApi, missingInputLines, unwrap } from "../../src/renderer/api/client";
import { notifySubmitError } from "../../src/renderer/ui/Toast";
import { batchReceipt, submitBatch } from "../../src/renderer/pages/analyzer/submitBatch";

const BASE = "http://test";
const MISSING = [
  {
    what: "volume parcellation for atlas 'DK40' of sub-101",
    expected_path: "/mnt/p/derivatives/fastsurfer/sub-101/mri/aparc.DKTatlas+aseg.deep.mgz",
    how_to_fix: "Run FastSurfer (or recon-all) for sub-101, or analyze in mesh space instead.",
  },
  { what: "simulation 'L_Insula' for sub-102", expected_path: null, how_to_fix: "Run the L_Insula simulation for sub-102 first." },
];

function refusedClient() {
  const fetch = vi.fn(
    async () =>
      new Response(JSON.stringify({ detail: "Missing inputs", missing: MISSING }), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
  );
  return createApi({ fetch, baseUrl: BASE });
}

async function submitRefused(): Promise<unknown> {
  const client = refusedClient();
  const result = await client.POST("/api/jobs", { body: { kind: "analyzer", config: {}, subject_ids: ["101"] } });
  try {
    return unwrap(result, "/api/jobs");
  } catch (error) {
    return error;
  }
}

describe("missing-inputs notice", () => {
  it("the 422 body becomes an ApiError carrying the list and a line-per-input message", async () => {
    const error = (await submitRefused()) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.missing).toEqual(MISSING);
    expect(error.message.split("\n")).toEqual(["Missing inputs:", ...missingInputLines(MISSING)]);
  });

  it("each line names what, where it was expected and how to fix it; a null path is skipped", () => {
    const lines = missingInputLines(MISSING);
    expect(lines[0]).toBe(`${MISSING[0]!.what} · expected at ${MISSING[0]!.expected_path} · ${MISSING[0]!.how_to_fix}`);
    expect(lines[1]).toBe(`${MISSING[1]!.what} · ${MISSING[1]!.how_to_fix}`);
  });

  it("notifySubmitError renders the list as a persistent blocking notice", async () => {
    toastError.mockClear();
    notifySubmitError("Could not queue the analysis.", await submitRefused());
    expect(toastError).toHaveBeenCalledTimes(1);
    const [message, options] = toastError.mock.calls[0] as [string, { duration: number; description: React.ReactElement }];
    expect(message).toBe("Could not queue the analysis. Missing inputs:");
    expect(options.duration).toBe(Infinity);
    const html = renderToStaticMarkup(options.description);
    expect(html.match(/<li>/g)).toHaveLength(2);
    expect(html).toContain("aparc.DKTatlas+aseg.deep.mgz");
    expect(html).toContain("analyze in mesh space instead");
  });

  it("any other failure stays a plain error with the server's detail", () => {
    toastError.mockClear();
    notifySubmitError("Could not queue the search.", new ApiError(422, "/api/jobs", "config is not a valid FlexConfig"));
    const [message, options] = toastError.mock.calls[0] as [string, { action?: { label: string } }];
    expect(message).toBe("Could not queue the search.");
    expect(options.action?.label).toBe("Details");
  });

  it("the analyzer batch keeps the list per rejected spec and the receipt stays one line", async () => {
    const error = await submitRefused();
    const outcome = await submitBatch(["a"], vi.fn().mockRejectedValue(error));
    expect(outcome.rejected[0]!.missing).toEqual(MISSING);
    expect(batchReceipt(outcome)).toBe("Could not queue the analysis: Missing inputs:");
  });
});
