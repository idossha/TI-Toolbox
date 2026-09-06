/**
 * The Viewer page's pure parts: the selection model, deep-link parsing and theme reading.
 *
 * Separate from `index.tsx` only so the unit test can import them without dragging in
 * `app/registry`'s eager page glob through `app/keyboard`. Nothing here touches the store, the API
 * or the DOM beyond `<html data-theme>`.
 */
import type { Space, ViewKind } from "./api";

export interface ViewerDeepLink {
  kind?: ViewKind;
  subject?: string;
  simulation?: string;
  analysis?: string;
  field?: string;
  atlas?: string;
  space?: Space;
  roi?: string;
  path?: string;
}

const VIEW_KINDS: ViewKind[] = ["subject", "simulation", "analysis", "group", "custom"];

/**
 * `?kind=&subject=&simulation=&field=` from wherever it actually is.
 *
 * The app runs a `MemoryRouter`, so there are two different query strings and they are both real:
 * the router's (what Results writes when it navigates here, and what `useSearchParams` sees) and
 * the document's (what a person gets when they open the served bundle at
 * `/?kind=simulation&subject=ernie`, which the router never sees). The router wins when it has an
 * answer, because it is the more recent act; the document is the fallback that makes an actual URL
 * work. Exported for the unit test — this is the only place either query is parsed.
 */
export function readDeepLink(routerSearch: string, documentSearch: string): ViewerDeepLink {
  const router = new URLSearchParams(routerSearch);
  const doc = new URLSearchParams(documentSearch);
  const read = (key: string): string | undefined => router.get(key) ?? doc.get(key) ?? undefined;
  const kind = read("kind");
  const space = read("space");
  return {
    kind: kind !== undefined && (VIEW_KINDS as string[]).includes(kind) ? (kind as ViewKind) : undefined,
    subject: read("subject"),
    simulation: read("simulation"),
    analysis: read("analysis"),
    field: read("field"),
    atlas: read("atlas"),
    space: space === "mni" || space === "subject" ? space : undefined,
    roi: read("roi"),
    path: read("path"),
  };
}


// ------------------------------------------------------------------------------------------------
// Status bar formatting (DESIGN.md §10, §11) — the RAS and renderer cells' own small derivations,
// pulled out here so the unit test can assert them without a store or a DOM.
// ------------------------------------------------------------------------------------------------





// ------------------------------------------------------------------------------------------------
// R5 — explicit selection: the draft/loaded model's pure half.
//
// `desktop/IMPLEMENTATION_PLAN.md` R5: the Viewer separates what the source bar SHOWS
// (`draftSelection`) from what the embed is CURRENTLY DRAWING (`loadedSelection`). Everything in
// this block is the part of that model with no store, no query client and no DOM: which selectors
// a view type needs, whether a draft is complete enough to ask the server for, the exact query
// that goes on the wire, and the stable key two selections are compared by.
//
// The whole point is that a selector edit is a pure state change with no side effect. Keeping the
// derivation here (rather than inline in the component) is what lets the unit test prove
// "changing the atlas changes the request that WOULD be issued" without rendering anything, and
// what stops a stray `useQuery({ enabled: true })` from creeping back into the page.
// ------------------------------------------------------------------------------------------------

/** Every selector the source bar can show. One id per control, used as its `data-testid` suffix. */
export type ViewerControl = "subject" | "simulation" | "analysis" | "field" | "atlas" | "space" | "roi" | "path";

export interface ViewerSelection {
  kind: ViewKind;
  subject?: string;
  simulation?: string;
  analysis?: string;
  field?: string;
  atlas?: string;
  space: Space;
  roi?: string;
  path?: string;
}

/**
 * The controls a given view type needs, in source-bar order.
 *
 * This is the ONLY place the shape of the bar is decided: the component renders this list, the
 * query builder strips everything not in it, and the unit test reads it. A type that does not take
 * a subject (`group`, `custom`) does not show one — the alternative, a disabled subject picker
 * whose value is still sent, is exactly the "the bar says one thing and the request says another"
 * failure R5 exists to remove.
 *
 * `analysis` is subject-space by construction on the server (`tit/viewspec.py::build_view` passes
 * `"subject"` regardless), so it shows no space control rather than a control that does nothing.
 */
export function controlsFor(kind: ViewKind): ViewerControl[] {
  switch (kind) {
    case "subject":
      return ["subject", "atlas", "space"];
    case "simulation":
      return ["subject", "simulation", "field", "space"];
    case "analysis":
      return ["subject", "simulation", "analysis", "roi"];
    case "group":
      return ["field", "roi"];
    case "custom":
      return ["path"];
  }
}

/** The selectors a type cannot be loaded without. A strict subset of {@link controlsFor}. */
export function requiredControls(kind: ViewKind): ViewerControl[] {
  switch (kind) {
    case "subject":
      return ["subject"];
    case "simulation":
      return ["subject", "simulation"];
    case "analysis":
      return ["subject", "simulation", "analysis"];
    case "group":
      return [];
    case "custom":
      return ["path"];
  }
}

const CONTROL_LABEL: Record<ViewerControl, string> = {
  subject: "Subject",
  simulation: "Simulation",
  analysis: "Analysis",
  field: "Field",
  atlas: "Atlas",
  space: "Space",
  roi: "ROI",
  path: "Path",
};

export function controlLabel(control: ViewerControl): string {
  return CONTROL_LABEL[control];
}

/**
 * `null` when the draft can be loaded, otherwise the sentence the bar shows instead of asking.
 *
 * Validation happens on **Load**, not on edit: an incomplete draft is a normal intermediate state
 * (a person picking a type before picking a subject), not an error to shout about, and the last
 * loaded scene stays on screen throughout.
 */
export function validateSelection(selection: ViewerSelection): string | null {
  const missing = requiredControls(selection.kind).filter((control) => {
    const value = selection[control];
    return value === undefined || value === "";
  });
  if (missing.length === 0) return null;
  const names = missing.map(controlLabel);
  return `Choose ${names.join(" and ")} before loading.`;
}

/**
 * The exact `GET /api/view/{kind}` query for a selection — only the params that type actually
 * takes, so a leftover simulation from a previous draft can never ride along on a `subject` view.
 */
export function viewQuery(selection: ViewerSelection): Record<string, string> {
  const controls = controlsFor(selection.kind);
  const query: Record<string, string> = {};
  for (const control of controls) {
    if (control === "space") continue;
    const value = selection[control];
    if (typeof value === "string" && value !== "") query[control] = value;
  }
  // Space is not a "control" on the wire — every kind that has one sends it, and the two that do
  // not (analysis, custom) inherit the server's own choice.
  if (controls.includes("space")) query.space = selection.space;
  return query;
}

/**
 * A stable, comparable identity for a selection — the dirty check, the `data-*` witnesses the e2e
 * asserts on, and the react-query-free memo key. Field order is the control order, so two keys
 * differing only in atlas differ only in that segment.
 */
export function selectionKey(selection: ViewerSelection): string {
  const query = viewQuery(selection);
  const parts = Object.keys(query)
    .sort()
    .map((key) => `${key}=${query[key]}`);
  return [selection.kind, ...parts].join("&");
}

export function sameSelection(a: ViewerSelection, b: ViewerSelection): boolean {
  return selectionKey(a) === selectionKey(b);
}

/**
 * The draft a deep link produces — **prefill only**, never a load (R5's fixed decision).
 *
 * `base` is what the page would otherwise show (the session's remembered draft, or the shell's
 * current subject): a link naming only `?subject=` must not silently reset the type or the space
 * a person had chosen. The kind falls back to `simulation` when the link names a simulation, so
 * the old Results → Viewer links keep meaning what they meant.
 */
export function selectionFromDeepLink(link: ViewerDeepLink, base: ViewerSelection): ViewerSelection {
  const kind: ViewKind = link.kind ?? (link.analysis ? "analysis" : link.simulation ? "simulation" : link.path ? "custom" : base.kind);
  return {
    kind,
    subject: link.subject ?? base.subject,
    simulation: link.simulation ?? (link.kind !== undefined && link.kind !== base.kind ? undefined : base.simulation),
    analysis: link.analysis,
    field: link.field,
    atlas: link.atlas,
    space: link.space ?? base.space,
    roi: link.roi,
    path: link.path,
  };
}

/** True when a link carries at least one viewer control (as opposed to the shell's `?subject=`). */
export function hasViewerDeepLink(link: ViewerDeepLink): boolean {
  return (
    link.kind !== undefined ||
    link.simulation !== undefined ||
    link.analysis !== undefined ||
    link.field !== undefined ||
    link.atlas !== undefined ||
    link.space !== undefined ||
    link.roi !== undefined ||
    link.path !== undefined
  );
}

// =================================================================================================
// VM — the composition panel.
//
// The Viewer opens in another application's window, so this page has room to be a real menu rather
// than a bar over a black rectangle. What it may offer is decided by one rule: **every knob has to
// land in the scene file**. So the vocabulary below is the server's
// (`tit/viewspec.py::apply_scene_overrides`, `EXTRA_LAYERS`), which is in turn the engine's own
// ViewSpec v2 type. There is no electrode-*points* checkbox because ViewSpec v2 has no points
// layer; the electrode overlay *volume* exists, and that is what is offered.
// =================================================================================================

/** One layer of the scene the server resolved — the fields this page reads or edits. */
export interface SceneLayer {
  id: string;
  name: string;
  kind: "volume" | "mesh";
  visible: boolean;
  opacity: number;
  colormap: string;
  showIn3D?: boolean;
  colorMode?: string;
  threshold?: { lo: number | null; hi: number | null };
  clip?: { planes?: { enabled?: boolean }[] };
}

export interface LayerOverride {
  visible?: boolean;
  opacity?: number;
  colormap?: string;
  showIn3D?: boolean;
  colorMode?: string;
  clip?: boolean;
  threshold?: { lo?: number | null; hi?: number | null };
}

export type SceneLayout = "1x1" | "1+3" | "2x2" | "3d-only";
export type CameraPreset = "A" | "P" | "L" | "R" | "S" | "I";
export type SceneBackground = "dark" | "black" | "light";
export type ViewerExtra = "t1" | "atlas" | "electrodes" | "gm_mesh";

/** Exactly the `overrides` document `POST /api/view/open` accepts. */
export interface Composition {
  layers: Record<string, LayerOverride>;
  layout?: SceneLayout;
  camera?: CameraPreset;
  radiological?: boolean;
  background?: SceneBackground;
}

export const EMPTY_COMPOSITION: Composition = { layers: {} };

/**
 * The composition as the wire wants it, or `undefined` when nothing was touched.
 *
 * `undefined` is load-bearing, not tidiness: the server's guarantee is that an *absent* overrides
 * document produces byte-identical output, and sending `{layers:{}}` on every Open would quietly
 * step outside the guarantee this page's tests rest on.
 */
export function overridesPayload(composition: Composition): Composition | undefined {
  const layers = Object.fromEntries(Object.entries(composition.layers).filter(([, patch]) => Object.keys(patch).length > 0));
  const touched =
    Object.keys(layers).length > 0 ||
    composition.layout !== undefined ||
    composition.camera !== undefined ||
    composition.radiological !== undefined ||
    composition.background !== undefined;
  if (!touched) return undefined;
  return { ...composition, layers };
}

/** What a layer *is*, in the words the person reading the row uses. */
export function layerKindLabel(layer: SceneLayer): string {
  if (layer.kind === "mesh") return "mesh";
  if (layer.colormap === "lut") return "lut";
  if (layer.colormap === "gray" || layer.colormap === "grayscale") return "grayscale";
  return "colormap";
}

export const LAYOUT_OPTIONS: { value: SceneLayout; label: string; title: string }[] = [
  { value: "1x1", label: "1×1", title: "One axial slice, full pane" },
  { value: "1+3", label: "1+3", title: "3D beside the three slice planes" },
  { value: "2x2", label: "2×2", title: "Three slice planes and 3D" },
  { value: "3d-only", label: "3D", title: "The 3D view alone" },
];

export const CAMERA_OPTIONS: { value: CameraPreset; label: string; title: string }[] = [
  { value: "A", label: "A", title: "Anterior — the engine's own default framing" },
  { value: "P", label: "P", title: "Posterior" },
  { value: "L", label: "L", title: "Left" },
  { value: "R", label: "R", title: "Right" },
  { value: "S", label: "S", title: "Superior" },
  { value: "I", label: "I", title: "Inferior" },
];

export const BACKGROUND_OPTIONS: { value: SceneBackground; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "black", label: "Black" },
  { value: "light", label: "Light" },
];

/**
 * The colormaps offered for a volume layer. A short list on purpose: these are the ones the
 * engine ships and the ones this server already emits, and a select of forty names is a worse
 * control than a select of seven.
 */
export const COLORMAP_OPTIONS = ["gray", "turbo", "jet", "hot", "viridis", "plasma", "lut"];

/**
 * "Also open". Each entry is a file the server already knows how to build a layer for; an extra
 * the chosen view type already opens is a no-op rather than a duplicate, so leaving one ticked is
 * safe across a change of type.
 */
export const EXTRA_OPTIONS: { value: ViewerExtra; label: string; help: string; needs?: "simulation" }[] = [
  { value: "t1", label: "Subject T1", help: "The head model's own T1, as the anatomical ground." },
  { value: "atlas", label: "Atlas labels", help: "The chosen atlas as a labelled volume with its LUT." },
  { value: "electrodes", label: "Electrode overlay", help: "The simulation's electrode overlay volume, where one has been generated.", needs: "simulation" },
  { value: "gm_mesh", label: "Grey-matter surface", help: "The grey-matter TI surface mesh (subject space only; large).", needs: "simulation" },
];

/** `4.2 MB` — one decimal, binary units, and "—" for a size the server could not read. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

// ── Recents ─────────────────────────────────────────────────────────────────────────────────────
//
// The last eight things actually opened. Local to this machine and this person, unlike a preset:
// a preset is a composition someone chose to keep and put in the project; a recent is a footprint.
// Browser storage is therefore the right home for it, and losing it costs nothing.

const RECENTS_KEY = "tit.viewer.recents";
export const RECENTS_LIMIT = 8;

export interface ViewerRecent {
  key: string;
  label: string;
  selection: ViewerSelection;
  extras: ViewerExtra[];
  overrides: Composition;
}

export function readRecents(): ViewerRecent[] {
  try {
    const raw = window.localStorage.getItem(RECENTS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed.slice(0, RECENTS_LIMIT) as ViewerRecent[]) : [];
  } catch {
    return [];
  }
}

/** *entry* first, its older twin dropped, eight kept. Returns the new list (storage may refuse). */
export function pushRecent(entry: ViewerRecent): ViewerRecent[] {
  const next = [entry, ...readRecents().filter((r) => r.key !== entry.key)].slice(0, RECENTS_LIMIT);
  try {
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    /* private mode, quota — a footprint is not worth an error */
  }
  return next;
}

/** `Simulation · ernie · Thalamus` — what a recent row reads. */
export function selectionLabel(selection: ViewerSelection): string {
  const type = { subject: "Subject", simulation: "Simulation", analysis: "Analysis", group: "Group", custom: "Custom" }[selection.kind];
  const parts = [selection.subject, selection.simulation, selection.analysis, selection.field, selection.path?.split("/").pop()].filter(Boolean);
  return [type, ...parts].join(" · ");
}
