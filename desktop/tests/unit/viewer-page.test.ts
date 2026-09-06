// @vitest-environment jsdom
/**
 * The Viewer page's pure derivations.
 *
 * The selection model and the deep-link reader: more branches than a spec can usefully click
 * through, and none of them need a DOM.
 *
 * V1 (`dev/notes/v3-native-panes-external-viewer-plan.md`) removed the embed, and with it the
 * three derivations this file also used to cover — `hidden3DLayer` (a hint about the *embed's*
 * 3D pane), `formatRas` and `shortRenderer` (status-bar cells fed by the embed's cursor and its
 * WebGL renderer string). None of the three has a referent any more: the picture is in another
 * application's window, which reports its own cursor and its own renderer in its own status bar.
 */
import { describe, expect, it } from "vitest";
import {
  controlsFor,
  hasViewerDeepLink,
  readDeepLink,
  requiredControls,
  selectionFromDeepLink,
  selectionKey,
  validateSelection,
  viewQuery,
  type ViewerSelection,
} from "../../src/renderer/pages/viewer/lib";

describe("readDeepLink", () => {
  it("prefers the router's query and falls back to the document's", () => {
    expect(readDeepLink("kind=simulation&subject=ernie", "subject=bert&field=TI_max")).toEqual({
      kind: "simulation",
      subject: "ernie",
      simulation: undefined,
      analysis: undefined,
      field: "TI_max",
      atlas: undefined,
      space: undefined,
      roi: undefined,
      path: undefined,
    });
  });

  it("drops a kind or a space it does not know rather than passing it to the server", () => {
    expect(readDeepLink("kind=nonsense&space=talairach", "")).toEqual({
      kind: undefined,
      subject: undefined,
      simulation: undefined,
      analysis: undefined,
      field: undefined,
      atlas: undefined,
      space: undefined,
      roi: undefined,
      path: undefined,
    });
  });
});

// -------------------------------------------------------------------------------------------------
// R5 — the draft/loaded model's pure half (desktop/IMPLEMENTATION_PLAN.md).
//
// The e2e proves the *counts* (zero requests on an edit, exactly one on Load). What it cannot show
// cheaply is that the request a given draft WOULD produce carries the draft's own values and only
// those: that is `viewQuery`, and it is the thing an atlas selection has to reach.
// -------------------------------------------------------------------------------------------------

const selection = (patch: Partial<ViewerSelection> = {}): ViewerSelection => ({ kind: "subject", space: "subject", ...patch });

describe("controlsFor / requiredControls", () => {
  it("shows a subject picker only for the types that take a subject", () => {
    expect(controlsFor("subject")).toEqual(["subject", "atlas", "space"]);
    expect(controlsFor("simulation")).toContain("subject");
    expect(controlsFor("group")).not.toContain("subject");
    expect(controlsFor("custom")).toEqual(["path"]);
  });

  it("requires a strict subset of what it shows — an optional selector is never a blocker", () => {
    for (const kind of ["subject", "simulation", "analysis", "group", "custom"] as const) {
      for (const control of requiredControls(kind)) expect(controlsFor(kind)).toContain(control);
    }
  });
});

describe("validateSelection", () => {
  it("passes a complete draft", () => {
    expect(validateSelection(selection({ subject: "ernie" }))).toBeNull();
    expect(validateSelection(selection({ kind: "group" }))).toBeNull();
    expect(validateSelection(selection({ kind: "custom", path: "/data/T1.nii.gz" }))).toBeNull();
  });

  it("names every missing selector, so Load can refuse before spending a request", () => {
    expect(validateSelection(selection())).toBe("Choose Subject before loading.");
    expect(validateSelection(selection({ kind: "simulation" }))).toBe("Choose Subject and Simulation before loading.");
    expect(validateSelection(selection({ kind: "simulation", subject: "ernie", simulation: "" }))).toBe("Choose Simulation before loading.");
  });
});

describe("viewQuery", () => {
  it("sends the atlas the bar is showing", () => {
    expect(viewQuery(selection({ subject: "ernie", atlas: "DK40" }))).toEqual({ subject: "ernie", atlas: "DK40", space: "subject" });
  });

  it("gives two atlases two distinguishable requests — the R5 gate's A-vs-B claim", () => {
    const a = viewQuery(selection({ subject: "ernie", atlas: "DK40" }));
    const b = viewQuery(selection({ subject: "ernie", atlas: "HCP_MMP1" }));
    expect(a).not.toEqual(b);
    expect(selectionKey(selection({ subject: "ernie", atlas: "DK40" }))).not.toBe(selectionKey(selection({ subject: "ernie", atlas: "HCP_MMP1" })));
  });

  it("omits the atlas entirely when none is chosen, preserving the server's own choice", () => {
    expect(viewQuery(selection({ subject: "ernie" }))).toEqual({ subject: "ernie", space: "subject" });
  });

  it("drops values the chosen type does not take, so a stale simulation cannot ride along", () => {
    expect(viewQuery(selection({ subject: "ernie", simulation: "Thalamus", atlas: "DK40" }))).toEqual({
      subject: "ernie",
      atlas: "DK40",
      space: "subject",
    });
    expect(viewQuery(selection({ kind: "custom", path: "/data/T1.nii.gz", subject: "ernie" }))).toEqual({ path: "/data/T1.nii.gz" });
  });

  it("sends space only for the types that show a space control", () => {
    expect(viewQuery(selection({ kind: "simulation", subject: "ernie", simulation: "T", space: "mni" }))).toMatchObject({ space: "mni" });
    expect(viewQuery(selection({ kind: "analysis", subject: "ernie", simulation: "T", analysis: "a" })).space).toBeUndefined();
  });
});

describe("selectionKey", () => {
  it("is equal for two drafts that would issue the same request, and different otherwise", () => {
    expect(selectionKey(selection({ subject: "ernie" }))).toBe(selectionKey(selection({ subject: "ernie", simulation: "ignored" })));
    expect(selectionKey(selection({ subject: "ernie" }))).not.toBe(selectionKey(selection({ subject: "bert" })));
    expect(selectionKey(selection({ subject: "ernie" }))).not.toBe(selectionKey(selection({ subject: "ernie", space: "mni" })));
  });
});

describe("selectionFromDeepLink", () => {
  const base = selection({ kind: "simulation", subject: "bert", simulation: "Old", space: "mni" });

  it("prefills over the current draft rather than replacing it", () => {
    expect(selectionFromDeepLink({ subject: "ernie" }, base)).toMatchObject({ kind: "simulation", subject: "ernie", space: "mni" });
  });

  it("infers the type from what the link names, keeping old Results links meaning what they meant", () => {
    expect(selectionFromDeepLink({ subject: "ernie", simulation: "Thalamus" }, selection()).kind).toBe("simulation");
    expect(selectionFromDeepLink({ path: "/data/x.nii.gz" }, selection()).kind).toBe("custom");
  });

  it("distinguishes a viewer link from the shell's bare ?subject=", () => {
    expect(hasViewerDeepLink({ subject: "ernie" })).toBe(false);
    expect(hasViewerDeepLink({ subject: "ernie", atlas: "DK40" })).toBe(true);
  });
});
