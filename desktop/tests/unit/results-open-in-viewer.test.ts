// @vitest-environment jsdom
/**
 * Results › an analysis › "Open in viewer", end to end through the hook (package p38, 2026-10-22).
 *
 * The bug: the button sent `POST /api/view/open {kind: "analysis", subject, simulation}` with no
 * analysis name; `tit/viewspec.py::build_view` returns None for that and the route answers 404
 * (`tests/test_viewspec_analysis_required.py`). p11 made `viewerLinkFor` open the analysis's own
 * scene file or overlay instead (`results-analysis-figures.test.ts` pins the link). This test pins
 * what then reaches the wire: the link `viewerLinkFor` builds for an analysis node, handed to
 * `useOpenInViewer`, either launches the scene file as is (no server call) or asks for a one-file
 * `custom` view of the overlay -- never a `kind: "analysis"` request.
 *
 * Expected paths are the hand-built analysis rows below, shaped like the mock fixture's
 * `desktop/tests/fixtures/analyses.json` entry for ernie / Thalamus.
 *
 * Reproduce: cd desktop && npx vitest run tests/unit/results-open-in-viewer.test.ts
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import type { components } from "../../src/renderer/api/schema";
import { useOpenInViewer, type ViewerLink } from "../../src/renderer/app/openInViewer";
import { outputsTreeFor, viewerLinkFor } from "../../src/renderer/pages/results/outputsTree";
import { notify } from "../../src/renderer/ui/Toast";

vi.mock("../../src/renderer/ui/Toast", () => ({ notify: { error: vi.fn() } }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Analysis = components["schemas"]["Analysis"];
const DIR = "/mnt/example/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Thalamus_DK40_TI_max";

function analysis(overrides: Partial<Analysis>): Analysis {
  return {
    name: "Thalamus_DK40_TI_max",
    space: "subject",
    analysis_space: "voxel",
    field: "TI_max",
    roi: "Thalamus",
    csv: `${DIR}/results.csv`,
    json: null,
    msh: null,
    nifti: `${DIR}/TI_max_masked.nii.gz`,
    pdf: null,
    figures: [],
    scene: null,
    ...overrides,
  } as Analysis;
}

function linkFor(a: Analysis): ViewerLink {
  const tree = outputsTreeFor("ernie", { simulations: [], flexRuns: [], exRuns: [], mexRuns: [], reports: [], analyses: { Thalamus: [a] } });
  const node = tree.groups.flatMap((g) => g.nodes).find((n) => n.kind === "analysis")!;
  const link = viewerLinkFor("ernie", node);
  expect(link, "an analysis with an overlay or scene offers the button").toBeDefined();
  return link!;
}

let root: Root;
let open: (link: ViewerLink) => void;
function Harness() {
  open = useOpenInViewer();
  return null;
}
beforeEach(async () => {
  root = createRoot(document.createElement("div"));
  await act(async () => root.render(React.createElement(Harness)));
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.restoreAllMocks();
  vi.clearAllMocks();
  delete window.tit;
});

describe("Open in viewer on an analysis", () => {
  it("asks the server for a one-file view of the analysis's overlay, not for kind=analysis", async () => {
    const a = analysis({});
    const request = vi.spyOn(api, "POST").mockResolvedValue({ data: { path: "/mnt/example/code/ti-toolbox/viewer/x.tetravox.json" }, response: new Response() } as never);
    const launch = vi.fn().mockResolvedValue({ ok: true });
    window.tit = { openNativeTetravox: launch } as never;
    await act(async () => open(linkFor(a)));
    expect(request).toHaveBeenCalledTimes(1);
    const [path, init] = request.mock.calls[0]! as unknown as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/api/view/open");
    expect(init.body).toMatchObject({ kind: "custom", subject: "ernie", path: a.nifti, files: [a.nifti] });
    expect(init.body.kind).not.toBe("analysis");
    expect(launch).toHaveBeenCalledWith("/mnt/example/code/ti-toolbox/viewer/x.tetravox.json");
    expect(notify.error).not.toHaveBeenCalled();
  });

  it("launches the analysis's own scene file as is, with no server round trip", async () => {
    const a = analysis({ scene: `${DIR}/scene.tetravox.json` });
    const request = vi.spyOn(api, "POST");
    const launch = vi.fn().mockResolvedValue({ ok: true });
    window.tit = { openNativeTetravox: launch } as never;
    await act(async () => open(linkFor(a)));
    expect(request).not.toHaveBeenCalled();
    expect(launch).toHaveBeenCalledWith(a.scene);
    expect(notify.error).not.toHaveBeenCalled();
  });
});
