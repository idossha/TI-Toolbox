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
  /**
   * `?open=1` — build and show the scene immediately instead of only pre-filling the Menu.
   *
   * Results ▸ "Open in viewer" and Jobs ▸ "Open in Tetravox" both set it: a person who clicked a
   * result asked to *see* it, and landing them on a pre-filled Menu with an Open button still to
   * press was the gap the maintainer reported ("sends me to the Menu but doesn't actually select
   * the correct items"). The draft is still pre-filled, so going back to the Menu shows exactly
   * what is on screen.
   */
  open?: boolean;
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
    open: read("open") === "1" || read("open") === "true",
  };
}


// ------------------------------------------------------------------------------------------------
// Status bar formatting (DESIGN.md §10, §11) — the RAS and renderer cells' own small derivations,
// pulled out here so the unit test can assert them without a store or a DOM.
// ------------------------------------------------------------------------------------------------





// ------------------------------------------------------------------------------------------------
// R5 — explicit selection: the draft/loaded model's pure half.
//
// `docs/dev/HISTORY.md § 2026-09-05` R5: the Viewer separates what the source bar SHOWS
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
// VM2 — the file list is the scene.
//
// VM built a composition panel: per-layer cards, a layout, a camera, a background, extras. The
// maintainer's verdict on the screenshots was "too much", and the correction is the honest shape
// of what this page is for. There are two things now: **Source** (what to build from) and one
// editable **"what will open"** list — remove a row, add a file, drag to reorder. The list is the
// scene, and Open writes exactly those files, in that order.
//
// What the page deliberately does *not* offer is how each file should look. That is a judgement
// about the data — a percentile window on a TI field, a LUT and `nearest` on a label volume, a
// mesh hidden because the file is 64 MB — and it stays in `tit/viewspec.py`, where the rest of
// the scene's defaults already live. A client that mirrored those rules would drift from them,
// and every drift would show up as a picture that is subtly wrong with nothing on screen saying
// so. The server's overrides plumbing still exists and is still tested; nothing on this page
// sends it.
// =================================================================================================

/** One row of the list: a file that will open, with both path languages (VM2). */
export interface ViewerFile {
  name: string;
  /** The path written into the scene — host-facing, what a person can check. */
  path: string;
  /** The same file as the server sees it — what goes back in `files`. */
  container_path?: string | null;
  kind?: string | null;
  bytes?: number | null;
}

/** One offer in the "+ Add…" picker. */
export interface ViewerCandidate {
  name: string;
  path: string;
  kind: string;
  group: string;
  bytes?: number | null;
}

/** The container paths of a resolved list, in order — the `files` a request carries. */
export function containerPaths(files: ViewerFile[]): string[] {
  return files.map((file) => file.container_path ?? file.path);
}

/** *list* with the item at *from* moved to *to*. Out-of-range indices leave it alone. */
export function reorder<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = [...list];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved as T);
  return next;
}

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
// a preset is a selection someone chose to keep and put in the project; a recent is a footprint.
// Browser storage is therefore the right home for it, and losing it costs nothing.

const RECENTS_KEY = "tit.viewer.recents";
export const RECENTS_LIMIT = 8;

export interface ViewerRecent {
  key: string;
  label: string;
  selection: ViewerSelection;
  /** The edited list, or null when the view type's own set was opened. */
  files: string[] | null;
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

/**
 * The shape of one resolved scene layer, as far as the "what will open" summary needs it.
 *
 * A hand-written subset, not the generated `ViewSpec` type: `ViewerOpen.view` is the embed's own
 * document (`contracts/tetravox-viewspec-v2.schema.json`), whose layer union is wider than
 * anything this page reads. Narrowing it here keeps the summary honest about how little it
 * inspects, and every field is optional because the summary must degrade to "no summary" rather
 * than throw on a scene shape it does not recognise.
 */
export interface ViewSceneLayer {
  kind?: string;
  datasetId?: string;
  visible?: boolean;
  scale?: { kind?: string; min?: number; max?: number; lo?: number; hi?: number };
}

/**
 * One field value, at a precision a person can read back off the screen.
 *
 * Electric fields in this toolbox span roughly 1e-3 to 1e1 V/m, so a fixed number of decimals is
 * wrong at one end or the other: 2 decimals turns 0.0042 into "0.00", and 4 decimals turns 3.34
 * into "3.3401", which reads as a measurement far more precise than the percentile it came from.
 * Three significant figures says the same thing at both ends.
 */
export function formatFieldValue(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 100 || magnitude < 0.001) return value.toPrecision(3);
  return String(Number(value.toPrecision(3)));
}

/**
 * The window the field overlay will open at, in words — `p95–p99.9 · 0.25–3.34 V/m`, or `null`
 * when the scene has no field layer to describe (subject anatomy, a label-only view).
 *
 * The maintainer's complaint about the defaults (2026-09-07) was only visible *after* opening the
 * viewer, in another application's window. The numbers are decided at resolve time, so the "what
 * will open" card can say them before anyone opens anything — and a default a person can read is
 * one they can disagree with.
 *
 * Read off the **resolved scene** rather than recomputed from the selection: a summary derived by
 * different code from the thing it describes is a summary that can be wrong, which is the same
 * argument that made the file list share the Open endpoint.
 *
 * Only a *visible* heat layer counts. A scene carries the whole-head and WM copies of a field as
 * hidden layers, and describing a window nobody is looking at would be worse than saying nothing.
 */
export function windowSummary(
  layers: ViewSceneLayer[] | undefined,
  datasets?: { id: string; name: string }[],
  chosen?: string[],
): string | null {
  if (!layers) return null;

  // Which layer to describe. The preview is resolved for the *source*, not for the edited list —
  // that is deliberate, because re-resolving on every tick is what made the Menu slow. So once a
  // person has composed something, the visible layer of the source's own scene may not be the one
  // that will open, and describing it would put a window on screen for a layer they removed.
  //
  // A window is a property of the *file*, though, so the right layer is the one whose dataset is
  // in the list — found in data already fetched, at no extra request.
  const nameOf = new Map((datasets ?? []).map((d) => [d.id, d.name]));
  const wanted = new Set((chosen ?? []).map((p) => p.split("/").pop()));
  const heat = layers.filter((l) => l.kind === "volume" && l.scale?.kind === "heat");
  const field =
    (wanted.size > 0 ? heat.find((l) => wanted.has(nameOf.get(l.datasetId ?? "") ?? "")) : undefined) ??
    heat.find((l) => l.visible === true);

  const min = field?.scale?.min;
  const max = field?.scale?.max;
  if (typeof min !== "number" || typeof max !== "number") return null;
  return `p95–p99.9 · ${formatFieldValue(min)}–${formatFieldValue(max)} V/m`;
}

// ── the composition tree (2026-09-07) ──────────────────────────────────────────────────────────
//
// Maintainer: *"there is subject and then it kind of like shows two little branches with the
// anatomy and then there is a simulation section where they can choose the different simulations
// — they can potentially choose multiple — and then they choose analysis output ... It depends on
// what is available and what is selected, but it should be a continuous integrated thing instead
// of what we have right now."*
//
// **The tree does not own a selection of its own.** It is a second view onto the one list the page
// already has — the editable "what will open" rows. A checkbox is ticked when that path is in the
// list, ticking adds it, unticking removes it. That is what makes it "continuous": the branches and
// the list cannot disagree, because there is only one of them, and every mechanism already built on
// that list (Reset, drag-to-reorder, presets, deep links, Open) keeps working untouched.
//
// The alternative — a `selected: string[]` beside `files` — would have been two sources of truth
// for one question, and the first edit made in the list rather than the tree would have desynced
// them.

/** One node in a branch, as the tree API returns it. Narrowed to what the rows read. */
export interface TreeNode {
  id: string;
  name: string;
  label: string;
  path: string;
  kind: string;
  bytes?: number | null;
  default_on?: boolean;
  available?: boolean;
  reason?: string | null;
  /** A surface's `.annot` / morph / data-GIfTI files, matched to it by hemisphere. */
  attachments?: TreeNode[];
}

// ── what a file is, and how the tree says so ─────────────────────────────────
//
// Maintainer, 2026-09-07: *"Please distinguish between NIfTI, mesh, and a surface — a mesh is a
// tetrahedral FEM, a surface is just a triangular 2-D surface."* The server decides
// (`tit/catalog.py::classify_view_file`) and this half only renders the answer; nothing here
// re-derives a kind from a file extension, which is the mistake that produced the screenshot.

/** The chip a row wears. Four words, because four are what a person is choosing between. */
export const KIND_CHIP: Record<string, string> = {
  volume: "VOLUME",
  "label-volume": "LABELS",
  surface: "SURFACE",
  mesh: "MESH",
  annotation: "ANNOT",
  morph: "MORPH",
  "surface-data": "DATA",
};

/**
 * A last-resort kind for a path nothing has described.
 *
 * Only reachable by typing a path into "+ Add…": every row that came from the tree or the
 * candidates list already carries the server's own answer, and this must never be used in
 * preference to that. It exists so such a row is not blank, and it uses the same vocabulary rather
 * than a second one — a row that said "mesh" for `lh.central.gii` here would reintroduce, in the
 * list, exactly the confusion the tree stopped making.
 */
export function kindFromName(path: string): string {
  const name = (path.split("/").pop() ?? path).toLowerCase();
  if (name.endsWith(".msh")) return "mesh";
  if (name.endsWith(".annot")) return "annotation";
  if (/\.(func|shape|time)\.gii$/.test(name)) return "surface-data";
  if (name.endsWith(".gii") || /\.(stl|ply|obj)$/.test(name)) return "surface";
  if (/^[lr]h\.(pial|white|central|inflated|sphere|smoothwm|orig)$/.test(name)) return "surface";
  if (/^[lr]h\.(thickness|curv|sulc|area)$/.test(name)) return "morph";
  return "volume";
}

export function kindChip(kind: string): string {
  return KIND_CHIP[kind] ?? kind.toUpperCase();
}

/**
 * The Anatomy branch's four groups, in the order they are drawn.
 *
 * Volumes first because a scene starts from one; label volumes next because they go on top of
 * one; then the two geometries, which are what the grouping exists to keep apart.
 */
export const ANATOMY_GROUPS: { key: string; title: string; kinds: string[] }[] = [
  { key: "volumes", title: "Volumes", kinds: ["volume"] },
  { key: "labels", title: "Label volumes (atlases)", kinds: ["label-volume"] },
  { key: "surfaces", title: "Surfaces", kinds: ["surface"] },
  { key: "meshes", title: "Meshes", kinds: ["mesh"] },
];

/** *nodes* split into {@link ANATOMY_GROUPS}, empty groups dropped. */
export function groupAnatomy(nodes: TreeNode[]): { key: string; title: string; nodes: TreeNode[] }[] {
  const groups = ANATOMY_GROUPS.map((group) => ({
    key: group.key,
    title: group.title,
    nodes: nodes.filter((node) => group.kinds.includes(node.kind)),
  })).filter((group) => group.nodes.length > 0);
  // A kind no group claims still has to appear — a row nobody drew is a file a person cannot
  // find, and silently dropping it is the failure mode this whole lane is fixing.
  const claimed = new Set(ANATOMY_GROUPS.flatMap((group) => group.kinds));
  const rest = nodes.filter((node) => !claimed.has(node.kind));
  return rest.length > 0 ? [...groups, { key: "other", title: "Other", nodes: rest }] : groups;
}

/**
 * The subject a container path belongs to, or `null` for a file that belongs to nobody.
 *
 * `null` is the bundled MNI template and the shared atlases, which an MNI scene is *supposed* to
 * mix in with a subject's own volumes — so they are never dropped by the rescoping below.
 */
export function subjectOfPath(path: string): string | null {
  const match = /\/derivatives\/SimNIBS\/sub-([^/]+)\//.exec(path);
  // The capture group is not optional, but `noUncheckedIndexedAccess` types every match index as
  // possibly undefined; `?? null` says so once rather than asserting it away.
  return match?.[1] ?? null;
}

/**
 * The rows of *files* that still belong, after the subject became *subject*.
 *
 * **Why this exists.** The "what will open" list survives a change of subject — it has to, since
 * it is also the list a person is editing — so picking 101 after ernie left ernie's rows in it,
 * and Open composed a scene spanning two people. That scene is not obviously wrong to look at:
 * two brains, both head-shaped, roughly aligned, one person's field over another's anatomy. The
 * real `viewer-open` spec passed for a while while measuring the wrong subject entirely.
 *
 * The server refuses such a scene outright (422, `tit/server/routes/viewers.py`). This is the
 * other half: rather than let a person hit that refusal, the list drops the rows that no longer
 * belong and the page says how many, so the removal is something they saw rather than something
 * they have to reconstruct.
 */
export function rescopeToSubject(files: string[], subject: string | undefined): { kept: string[]; dropped: string[] } {
  if (!subject) return { kept: files, dropped: [] };
  const kept: string[] = [];
  const dropped: string[] = [];
  for (const path of files) {
    const owner = subjectOfPath(path);
    (owner === null || owner === subject ? kept : dropped).push(path);
  }
  return { kept, dropped };
}

/** `2 files from another subject were removed` — the notice, or `null` when nothing went. */
export function rescopeNotice(dropped: string[]): string | null {
  if (dropped.length === 0) return null;
  const which = dropped.length === 1 ? "file" : "files";
  return `${dropped.length} ${which} from another subject ${dropped.length === 1 ? "was" : "were"} removed from what will open.`;
}

/**
 * `TI_max` for `grey_L_Insula_TI_subject_TI_max.nii.gz` — which physical field a node carries.
 *
 * Used to keep `draft.field` in step when someone ticks a field row, which is what keeps the
 * window chip ("p95–p99.9 · …") describing the layer they just chose. Deliberately the same
 * vocabulary `tit/viewspec.py::_scene_field_name` guesses from, and `null` when the name says
 * nothing — a caller must not invent a field for an anatomy file.
 */
export function fieldOfNode(name: string): string | null {
  const stem = name.replace(/\.(nii\.gz|nii|mgz|msh|gii)$/i, "");
  for (const field of ["mTI_max", "TI_normal", "TI_max", "hf_peak", "hf_sar", "magnE", "normE"]) {
    if (stem.endsWith(`_${field}`) || stem === field) return field;
  }
  return null;
}

/**
 * Every id a simulation branch offers, across its buckets.
 *
 * Attachments are **not** included: "select all of this simulation" means its outputs, and
 * sweeping in every parcellation would tick things whose surfaces may not even be in the scene.
 */
export function simulationNodeIds(sim: {
  fields?: TreeNode[];
  meshes?: TreeNode[];
  surfaces?: TreeNode[];
  electrodes?: TreeNode[];
}): string[] {
  return [...(sim.fields ?? []), ...(sim.meshes ?? []), ...(sim.surfaces ?? []), ...(sim.electrodes ?? [])].map((n) => n.id);
}

/**
 * `"none" | "some" | "all"` for a branch, given what is currently in the list.
 *
 * Drives the branch checkbox's `indeterminate`, which is the only affordance that can say "part of
 * this simulation is in the scene" without making a person expand it to find out.
 */
export function branchState(ids: string[], chosen: ReadonlySet<string>): "none" | "some" | "all" {
  if (ids.length === 0) return "none";
  const hits = ids.filter((id) => chosen.has(id)).length;
  if (hits === 0) return "none";
  return hits === ids.length ? "all" : "some";
}

/** `3 simulations · 2 selected` — what a collapsed branch says about itself. */
export function branchCount(total: number, selected: number, noun: string): string {
  const plural = `${total} ${noun}${total === 1 ? "" : "s"}`;
  return selected === 0 ? plural : `${plural} · ${selected} selected`;
}

/**
 * Add or remove *id*, preserving the order of everything else.
 *
 * Appends rather than inserting at a "natural" position: layer order is the list's order and the
 * person can drag it, so guessing where a newly ticked file belongs would be overriding a choice
 * they have a control for.
 */
export function toggleId(current: string[], id: string, on: boolean): string[] {
  if (on) return current.includes(id) ? current : [...current, id];
  return current.filter((entry) => entry !== id);
}

/** Add or remove a whole branch at once, without disturbing the rest of the list. */
export function toggleMany(current: string[], ids: string[], on: boolean): string[] {
  if (!on) {
    const drop = new Set(ids);
    return current.filter((entry) => !drop.has(entry));
  }
  const have = new Set(current);
  return [...current, ...ids.filter((id) => !have.has(id))];
}
