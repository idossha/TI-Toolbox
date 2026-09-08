// @vitest-environment jsdom
/**
 * The Viewer page's pure derivations.
 *
 * The selection model and the deep-link reader: more branches than a spec can usefully click
 * through, and none of them need a DOM.
 *
 * V1 (`docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`) removed the embed, and with it the
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
  branchCount,
  branchState,
  fieldOfNode,
  formatFieldValue,
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
  simulationNodeIds,
  toggleId,
  toggleMany,
  viewQuery,
  windowSummary,
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
// R5 — the draft/loaded model's pure half (docs/dev/HISTORY.md § 2026-09-05).
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

describe("formatFieldValue", () => {
  it("keeps three significant figures across the range a TI field actually spans", () => {
    // Fixed decimals are wrong at one end or the other: 2 turns 0.0042 into "0.00", and 4 turns
    // 3.34 into "3.3401", which reads as a measurement far more precise than the percentile it
    // came from.
    expect(formatFieldValue(3.3401404163837958)).toBe("3.34");
    expect(formatFieldValue(0.25388869643211365)).toBe("0.254");
    expect(formatFieldValue(0.0042)).toBe("0.0042");
    expect(formatFieldValue(0)).toBe("0");
  });

  it("says so rather than printing NaN", () => {
    expect(formatFieldValue(Number.NaN)).toBe("—");
    expect(formatFieldValue(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("windowSummary", () => {
  const heat = (min: number, max: number, visible = true) => ({
    kind: "volume",
    visible,
    scale: { kind: "heat", min, max },
  });

  it("names the window the overlay will open at, before anything is opened", () => {
    // The maintainer could only see the defaults after the viewer had opened, in another
    // application's window. This is the card saying them first.
    expect(windowSummary([heat(0.25388869643211365, 3.3401404163837958)])).toBe("p95–p99.9 · 0.254–3.34 V/m");
  });

  it("describes the field that is in the list, not the source's own visible one", () => {
    // The preview is resolved for the *source*, not the edited list (re-resolving on every tick is
    // what made the Menu slow), so once someone has composed something the source's visible layer
    // may not be the one that will open. A window is a property of the file, so the layer to
    // describe is the one whose dataset is in the list.
    const layers = [
      { ...heat(0.1, 1.5, true), datasetId: "d1" },
      { ...heat(0.0868, 0.139, false), datasetId: "d2" },
    ];
    const datasets = [
      { id: "d1", name: "L_Insula_TI_subject_TI_max.nii.gz" },
      { id: "d2", name: "grey_L_Insula_TI_subject_TI_max.nii.gz" },
    ];
    expect(windowSummary(layers, datasets, ["/p/grey_L_Insula_TI_subject_TI_max.nii.gz"])).toBe(
      "p95–p99.9 · 0.0868–0.139 V/m",
    );
    // Nothing composed yet: fall back to what the source itself shows.
    expect(windowSummary(layers, datasets, [])).toBe("p95–p99.9 · 0.1–1.5 V/m");
  });

  it("describes the layer a person is actually looking at, not a hidden one", () => {
    // A simulation scene carries the whole-head and WM copies of the field as hidden layers.
    // Summarising one of those would describe a window nobody can see.
    const layers = [heat(9.9, 99.9, false), heat(0.1, 1.5, true)];
    expect(windowSummary(layers)).toBe("p95–p99.9 · 0.1–1.5 V/m");
  });

  it("says nothing when the scene has no field overlay to describe", () => {
    // Subject anatomy: a grey T1 and a label volume. A "window" line here would be noise.
    expect(windowSummary([{ kind: "volume", visible: true, scale: { kind: "linear", lo: 1, hi: 715 } }])).toBeNull();
    expect(windowSummary([])).toBeNull();
    expect(windowSummary(undefined)).toBeNull();
  });

  it("degrades to no summary on a scene shape it does not recognise", () => {
    // `ViewerOpen.view` is the embed's document, whose layer union is wider than this reads.
    expect(windowSummary([{ kind: "mesh", visible: true }])).toBeNull();
    expect(windowSummary([{ kind: "volume", visible: true, scale: { kind: "heat" } }])).toBeNull();
  });
});

// ── the composition tree (2026-09-07) ─────────────────────────────────────────────────────────
//
// The tree owns no selection: a row is ticked when its path is in the page's one editable list.
// That is what makes these rules pure, and it is why they are tested here rather than by rendering
// — the component is a function of (tree, chosen) and nothing else.

describe("toggleId / toggleMany", () => {
  it("appends rather than guessing where a newly ticked file belongs", () => {
    // Layer order is the list's order and the person can drag it, so inserting at a "natural"
    // position would be overriding a choice they have a control for.
    expect(toggleId(["a", "b"], "c", true)).toEqual(["a", "b", "c"]);
    expect(toggleId(["a", "b"], "a", true)).toEqual(["a", "b"]);
  });

  it("removes without disturbing the order of what is left", () => {
    expect(toggleId(["a", "b", "c"], "b", false)).toEqual(["a", "c"]);
    expect(toggleId(["a"], "zzz", false)).toEqual(["a"]);
  });

  it("takes a whole branch on or off in one edit", () => {
    expect(toggleMany(["a"], ["b", "c"], true)).toEqual(["a", "b", "c"]);
    // Already-present ids are not duplicated — ticking a branch whose parts are partly in is the
    // normal case, and a duplicate row would be a duplicate layer.
    expect(toggleMany(["a", "b"], ["b", "c"], true)).toEqual(["a", "b", "c"]);
    expect(toggleMany(["a", "b", "c"], ["b", "c"], false)).toEqual(["a"]);
  });
});

describe("branchState", () => {
  it("is the tri-state a branch checkbox needs", () => {
    // "some" is the one that earns its keep: it says part of this simulation is in the scene
    // without making a person expand it to find out.
    const chosen = new Set(["a", "b"]);
    expect(branchState(["a", "b"], chosen)).toBe("all");
    expect(branchState(["a", "z"], chosen)).toBe("some");
    expect(branchState(["y", "z"], chosen)).toBe("none");
    expect(branchState([], chosen)).toBe("none");
  });
});

describe("branchCount", () => {
  it("says how much of a collapsed branch is in the scene", () => {
    expect(branchCount(3, 2, "simulation")).toBe("3 simulations · 2 selected");
    expect(branchCount(1, 0, "simulation")).toBe("1 simulation");
    expect(branchCount(0, 0, "run")).toBe("0 runs");
  });
});

describe("fieldOfNode", () => {
  it("reads the field off the last token, so three outputs are three fields", () => {
    // The server had the same defect: `L_Insula_TI_subject_hf_peak.nii.gz` contains "ti" twice,
    // and a substring match called it TI_max.
    expect(fieldOfNode("L_Insula_TI_subject_TI_max.nii.gz")).toBe("TI_max");
    expect(fieldOfNode("L_Insula_TI_subject_hf_peak.nii.gz")).toBe("hf_peak");
    expect(fieldOfNode("grey_L_Insula_TI_subject_TI_normal.nii.gz")).toBe("TI_normal");
    expect(fieldOfNode("101_TDCS_1_scalar_subject_magnE.nii.gz")).toBe("magnE");
  });

  it("invents no field for a file that names none", () => {
    // A caller uses this to set `draft.field`; guessing here would put a window on screen for a
    // layer that has no field at all.
    expect(fieldOfNode("T1.nii.gz")).toBeNull();
    expect(fieldOfNode("final_tissues.nii.gz")).toBeNull();
    expect(fieldOfNode("roi_mask.nii.gz")).toBeNull();
  });
});

describe("simulationNodeIds", () => {
  it("is every output a simulation offers, across its three buckets", () => {
    expect(
      simulationNodeIds({
        fields: [{ id: "f1" }, { id: "f2" }] as never,
        meshes: [{ id: "m1" }] as never,
        electrodes: [{ id: "e1" }] as never,
      }),
    ).toEqual(["f1", "f2", "m1", "e1"]);
    expect(simulationNodeIds({})).toEqual([]);
  });
});
