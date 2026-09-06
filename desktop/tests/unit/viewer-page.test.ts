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
import { beforeEach, describe, expect, it } from "vitest";
import {
  RECENTS_LIMIT,
  controlsFor,
  containerPaths,
  formatBytes,
  pushRecent,
  readRecents,
  reorder,
  selectionLabel,
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

// ── VM: the composition panel's pure parts ──────────────────────────────────────────────────────

describe("containerPaths", () => {
  it("prefers the container path, because that is the one the server jails", () => {
    // A row that handed back only its host path could not be re-resolved by a server that
    // resolves container paths — the whole list would come back empty, with no error anywhere.
    expect(
      containerPaths([
        { name: "a", path: "/Users/me/p/a.nii.gz", container_path: "/mnt/p/a.nii.gz" },
        { name: "b", path: "/mnt/p/b.nii.gz" },
      ]),
    ).toEqual(["/mnt/p/a.nii.gz", "/mnt/p/b.nii.gz"]);
  });
});

describe("reorder", () => {
  it("moves one item and leaves the rest in order", () => {
    expect(reorder(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(reorder(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
  });

  it("returns the list itself for a no-op or an impossible move", () => {
    const list = ["a", "b"];
    expect(reorder(list, 1, 1)).toBe(list);
    expect(reorder(list, 0, 5)).toBe(list);
    expect(reorder(list, -1, 0)).toBe(list);
  });
});

describe("formatBytes", () => {
  it("says '—' for a size the server could not read", () => {
    // Distinct from 0: "unknown" and "empty" are different answers and only one is a problem.
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(0)).toBe("0 B");
  });

  it("scales to binary units with one decimal", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(4 * 1024 * 1024)).toBe("4.0 MB");
    expect(formatBytes(420 * 1024 * 1024)).toBe("420 MB");
  });
});

describe("selectionLabel", () => {
  it("reads as the type and what it names", () => {
    expect(selectionLabel({ kind: "simulation", subject: "ernie", simulation: "Thalamus", space: "subject" })).toBe("Simulation · ernie · Thalamus");
    expect(selectionLabel({ kind: "custom", path: "/data/x.nii.gz", space: "subject" })).toBe("Custom · x.nii.gz");
  });
});

describe("recents", () => {
  const entry = (key: string) => ({
    key,
    label: key,
    selection: { kind: "subject" as const, space: "subject" as const },
    files: null,
  });

  // A tiny in-memory localStorage: this suite's jsdom environment provides the object but not a
  // working `clear()`, and a recents test that shares storage with its neighbours is a flake.
  beforeEach(() => {
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
        clear: () => store.clear(),
      },
    });
  });

  it("keeps the newest eight, most recent first, with no duplicate key", () => {
    for (let i = 0; i < 10; i += 1) pushRecent(entry(`k${i}`));
    const kept = readRecents();
    expect(kept).toHaveLength(RECENTS_LIMIT);
    expect(kept[0]!.key).toBe("k9");
    pushRecent(entry("k5"));
    const after = readRecents();
    expect(after[0]!.key).toBe("k5");
    expect(after.filter((r) => r.key === "k5")).toHaveLength(1);
  });

  it("survives unreadable storage rather than throwing", () => {
    window.localStorage.setItem("tit.viewer.recents", "{not json");
    expect(readRecents()).toEqual([]);
  });
});
