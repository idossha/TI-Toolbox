// @vitest-environment jsdom
/**
 * A submission the server refused with HTTP 422 `{detail: "Missing inputs", missing: [...]}`
 * (`tit.jobs.preflight`) reaches the user as a short, self-dismissing toast (title + the first
 * input's `what`) with a "Details" button opening the full per-input list — what, expected path,
 * how to fix — in the shared Dialog. Never a bare "Could not queue".
 */
import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({
  Toaster: () => null,
  toast: Object.assign(vi.fn(), {
    error: toastError,
    success: vi.fn(),
    message: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

import { ApiError, createApi, missingInputLines, unwrap } from "../../src/renderer/api/client";
import { notifySubmitError, ToastHost } from "../../src/renderer/ui/Toast";
import { AUTO_FIELD, buildConfig } from "../../src/renderer/pages/analyzer/buildConfig";
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
  const config = buildConfig({
    mode: "single", subjectId: "101", subjectIds: [], simulation: "L_Insula",
    space: "voxel", tissueType: "GM", field: AUTO_FIELD, analysisType: "cortical",
    coordinateSpace: "subject", sphere: { x: 0, y: 0, z: 0, radius: 5 },
    roiValue: { mode: "cortical", space: "subject", atlas: "DK40", regions: [{ id: 29, name: "insula", hemi: "lh" }] },
  });
  const result = await client.POST("/api/jobs", { body: { kind: "analyzer", config, subject_ids: ["101"] } });
  try {
    return unwrap(result, "/api/jobs");
  } catch (error) {
    return error;
  }
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function mountToastHost() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root!.render(React.createElement(ToastHost));
  });
}

afterEach(() => {
  if (root && container) {
    act(() => {
      root!.unmount();
    });
    container.remove();
  }
  root = null;
  container = null;
});

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

  it("notifySubmitError renders a short toast: title, the first input's `what`, and a Details action", async () => {
    toastError.mockClear();
    notifySubmitError("Could not queue the analysis.", await submitRefused());
    expect(toastError).toHaveBeenCalledTimes(1);
    const [message, options] = toastError.mock.calls[0] as [
      string,
      { duration: number; description: React.ReactElement; action: { label: string; onClick: () => void } },
    ];
    expect(message).toBe("Could not queue the analysis. Missing inputs:");
    expect(options.duration).toBe(4000);
    const html = renderToStaticMarkup(options.description);
    expect(html).toContain("volume parcellation for atlas");
    expect(options.action.label).toBe("Details");
  });

  it("Details opens the full list in the shared Dialog and dismisses the toast", async () => {
    toastError.mockClear();
    mountToastHost();
    notifySubmitError("Could not queue the analysis.", await submitRefused());
    const [, options] = toastError.mock.calls[0] as [string, { action: { onClick: () => void } }];
    act(() => {
      options.action.onClick();
    });
    // Radix Dialog portals into document.body, not into the mount container.
    const html = document.body.innerHTML;
    expect(html).toContain(MISSING[0]!.what);
    expect(html).toContain(MISSING[0]!.expected_path);
    expect(html).toContain(MISSING[0]!.how_to_fix);
    expect(html).toContain(MISSING[1]!.what);
    expect(html).toContain(MISSING[1]!.how_to_fix);
  });

  it("the toast auto-dismisses after its duration (sonner handles the timer itself)", async () => {
    toastError.mockClear();
    notifySubmitError("Could not queue the analysis.", await submitRefused());
    const [, options] = toastError.mock.calls[0] as [string, { duration: number }];
    // notify.blocked hands sonner a finite duration rather than Infinity, so the toast is not
    // pinned open; sonner itself owns dismissal (and hover-pause) on that timer.
    expect(options.duration).toBe(4000);
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
