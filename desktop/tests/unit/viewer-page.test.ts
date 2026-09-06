// @vitest-environment jsdom
/**
 * The Viewer page's pure derivations.
 *
 * These are the facts the page states on screen that no e2e against the mock server can reach: the
 * mock's simulation scene carries no mesh at all, so the "enable a mesh layer" hint has no true
 * positive there (the e2e asserts the true negative; the real-container run in
 * `dev/notes/v3-docker-streamline/fx2-viewer-pages-notes.md` covers the positive), the deep-link
 * reader has more branches than a spec can usefully click through, and the status bar's own
 * formatting (`formatRas`, `shortRenderer`) is easiest to prove without a store or a DOM.
 */
import { describe, expect, it } from "vitest";
import {
  controlsFor,
  formatRas,
  hasViewerDeepLink,
  hidden3DLayer,
  readDeepLink,
  requiredControls,
  selectionFromDeepLink,
  selectionKey,
  shortRenderer,
  validateSelection,
  viewQuery,
  type ViewerSelection,
} from "../../src/renderer/pages/viewer/lib";
import type { EmbedLayer } from "../../src/renderer/viewer";

const volume = (id: string, visible: boolean): EmbedLayer => ({ id, name: id, kind: "volume", visible });
const mesh = (id: string, visible: boolean): EmbedLayer => ({ id, name: id, kind: "mesh", visible });
const label = (id: string, visible: boolean): EmbedLayer => ({ id, name: id, kind: "volume", showIn3D: true, visible });

describe("hidden3DLayer", () => {
  it("names the hidden mesh when nothing else can draw into the 3D pane", () => {
    const hidden = hidden3DLayer([volume("T1", true), mesh("grey_Thalamus_TI", false)]);
    expect(hidden?.id).toBe("grey_Thalamus_TI");
  });

  it("says nothing when a mesh is already visible", () => {
    expect(hidden3DLayer([volume("T1", true), mesh("grey_Thalamus_TI", true)])).toBeNull();
  });

  it("says nothing for a scene of plain volumes — there would be nothing to enable", () => {
    expect(hidden3DLayer([volume("T1", true), volume("TI_max", true)])).toBeNull();
    expect(hidden3DLayer([volume("T1", false)])).toBeNull();
    expect(hidden3DLayer([])).toBeNull();
  });

  it("ignores a label volume the server marked showIn3D — the mesh is what fills that pane", () => {
    // A real simulation scene's electrode overlay is `showIn3D: true` and visible, and the 3D pane
    // still reads as empty to a researcher until the surface is on. Counting it would suppress the
    // one hint that matters.
    expect(hidden3DLayer([volume("T1", true), label("electrodes", true), mesh("grey", false)])?.id).toBe("grey");
    expect(hidden3DLayer([label("electrodes", false)])).toBeNull();
  });

  it("names the first hidden mesh when a scene carries more than one", () => {
    expect(hidden3DLayer([mesh("grey", false), mesh("white", false)])?.id).toBe("grey");
  });

  it("treats an absent `visible` as visible, matching the inspector's own switch", () => {
    expect(hidden3DLayer([{ id: "m", kind: "mesh" }])).toBeNull();
  });
});

describe("formatRas", () => {
  it("is undefined with no cursor, so the status cell is not rendered at all", () => {
    expect(formatRas(null)).toBeUndefined();
  });

  it("formats each axis to one decimal, two-space separated", () => {
    expect(formatRas([12, -18, 9])).toBe("12.0  -18.0  9.0");
  });
});

describe("shortRenderer", () => {
  it("pulls the useful middle out of an ANGLE wrapper", () => {
    expect(shortRenderer("ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)")).toBe("Apple M2 Pro");
  });

  it("falls back to the whole string when there is no parenthesised form", () => {
    expect(shortRenderer("SwiftShader")).toBe("SwiftShader");
  });
});

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
