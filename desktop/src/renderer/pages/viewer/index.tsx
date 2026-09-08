/**
 * Viewer screen — **a source, a file list, and Open** (V1 · VM · VM2,
 * `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer){VX,VM,VM2}.md`).
 *
 * V1's brief: *"the viewer tab only acts as the data selection and it actually opens up everything
 * in [an external window] like we have in 2.5.0."* VM read that as room for a composition panel —
 * per-layer cards, a layout, a camera, a background, extras — and the maintainer's verdict on the
 * screenshots was **"too much"**. VM2 is the correction, and it is a better page than either:
 *
 *   **The list of files that will open is the whole scene, and it is editable.**
 *
 * Remove a row and that dataset is not in the scene. Add one — from everything the subject and
 * simulation offer, or any path in the project — and it is, at the end. Drag to reorder and that
 * is the layer order. Reset puts the view type's own set back. Open writes exactly those files,
 * in that order.
 *
 * **What this page deliberately does not offer is how each file should look.** Opacity, colormap,
 * threshold, layout, camera: all of that is a judgement about the data — a percentile window on a
 * TI field, a LUT and `nearest` on a label volume, a mesh hidden because the file is 64 MB — and
 * it lives in `tit/viewspec.py` with the rest of the scene's defaults. A file this page adds
 * arrives with the server's default for a file of that shape; a file the view type produced keeps
 * exactly the settings that view type gave it. Tetravox has an inspector, its own window and a
 * person's full attention; this page has a list.
 *
 * **The page is two rail sub-items** (VE, 2026-09-06). The maintainer: *"In the Viewer, the left
 * menu has two subsections: the Menu, and below it the actual Viewer. The user configures in the
 * Menu, hits Open, is moved to the Viewer where the Tetravox embed is; they can go back to the
 * Menu, tinker, and reload a different setup."*
 *
 *   **Menu** (`/viewer/menu`) — the source, the file list, presets and Recent. `Open in viewer`.
 *   **Tetravox** (`/viewer/tetravox`) — a full-bleed `<iframe src="/tetravox/">`
 *   (`renderer/viewer/TetravoxFrame`) with a slim strip above it: which scene is loaded, `Reload`.
 *
 * They are rows in the nav rail (`PageDef.subNav`, `app/NavRail.tsx`) and **one page**: two routes
 * under one `PageDef`, one mounted component, both panes always in the DOM with the inactive one
 * `display: none`. That is what makes the retention rule true by construction — moving between
 * them never unmounts the iframe, so the scene, the camera and the engine's wasm heap survive a
 * trip back to the Menu. Two `PageDef`s would have been two components and two iframes, and
 * "go back to the Menu, tinker, and reload a different setup" would have meant reloading the
 * engine every time.
 *
 * Going back is therefore just pressing **Menu** in the rail; the strip carries no Back button,
 * because a second control for a thing the rail already does is a second thing to keep in step.
 *
 * **R5's draft → command grammar is unchanged.** Editing anything — a selector, a row — edits the
 * draft. The only request drafting costs is the list's own `dry_run`, which writes no file and
 * shows nothing. Open is the one place a scene is committed: **one** `POST /api/view/open`, which
 * resolves the scene once and answers with both addressings of it — `view` (datasets as
 * `/api/files/raw/…` URLs) posted to the iframe as **one** `load` message, and `scene` (host
 * paths) written to `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json` for export. One
 * request, one message.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { Camera, Clock, Eye, GripVertical, Plus, RefreshCw, Save, X } from "lucide-react";
import { ApiError, getSubjects } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { usePageSession } from "../../app/pageSession";
import { usePageActive } from "../../app/pageActivity";
import { SUBJECT_SYNC_STATE } from "../../app/subjectSpine";
import { useSubjectContext } from "../../app/subjectContext";
import { Button } from "../../ui/Button";
import { PageLayout } from "../../ui/Layout";
import { Popover } from "../../ui/Overlay";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Select, type SelectOption } from "../../ui/Select";
import { TextInput } from "../../ui/Field";
import {
  deleteComposition,
  getCandidates,
  getCompositions,
  getTree,
  previewView,
  openView,
  saveComposition,
  saveScene,
  suggestSceneName,
  getSavedScenes,
  readSavedScene,
  type SavedScene,
  type Space,
  type ViewQuery,
} from "./api";
import {
  containerPaths,
  formatBytes,
  hasViewerDeepLink,
  pushRecent,
  readDeepLink,
  readRecents,
  reorder,
  selectionFromDeepLink,
  selectionKey,
  selectionLabel,
  validateSelection,
  viewQuery,
  windowSummary,
  type ViewerCandidate,
  type ViewerFile,
  type ViewerRecent,
  type ViewerSelection,
  type ViewSceneLayer,
} from "./lib";
import { CompositionTree } from "./Tree";
import { TetravoxFrame, useViewerStore } from "../../viewer";
import { getCapabilities } from "../settings/api";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import "./viewer-page.css";

export { readDeepLink } from "./lib";
export type { ViewerDeepLink, ViewerSelection } from "./lib";


/** The two rail sub-items. The id is the last path segment: `/viewer/menu`, `/viewer/tetravox`. */
type SubPage = "menu" | "tetravox";

/** What the rail draws under "Viewer". The first is where the page's own row and ⌘8 land. */
const SUB_NAV = [
  { id: "menu", title: "Menu" },
  { id: "tetravox", title: "Tetravox" },
] as const;

/** The scene the embed is showing, kept so the strip can name it and `Reload` can re-post it. */
interface LoadedScene {
  key: string;
  name: string;
  hostPath: string | null;
  view: Record<string, unknown>;
}

/** What a failed (or refused) Open left behind, tied to the selection that was attempted. */
interface ViewerFailure {
  key: string;
  title: string;
  text: string;
}

/**
 * *value*, but no more often than once per *delayMs* of quiet.
 *
 * Page-local, like the copies in `pages/optimizer` and `pages/panels/*`: the convention in this
 * renderer is that a page owns its own small hooks rather than a shared module every lane edits.
 */
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

function ViewerPage() {
  const active = usePageActive();
  const location = useLocation();
  const [initialLocationKey] = useState(location.key);
  const deepLink = useMemo(
    () => readDeepLink(location.search, location.key === initialLocationKey && typeof window !== "undefined" ? window.location.search : ""),
    [initialLocationKey, location.key, location.search],
  );

  const subjectId = useSubjectContext((s) => s.subjectId);
  usePageScrollMemory();
  const queryClient = useQueryClient();

  // ---------------------------------------------------------------------------------------------
  // The draft: the source, and the edited file list. `files === null` means "the view type's own
  // set" — not an empty list, and not a copy of it either: a copy would go stale the moment the
  // source changed, and the page would be showing yesterday's answer with today's selector values.
  // ---------------------------------------------------------------------------------------------
  const [draft, setDraft] = usePageSession<ViewerSelection>("selection", () =>
    selectionFromDeepLink(deepLink, { kind: "subject", subject: subjectId ?? undefined, space: "subject" }),
  );
  const [files, setFiles] = usePageSession<string[] | null>("files", () => null);

  const editDraft = useCallback(
    (patch: Partial<ViewerSelection>) => {
      // A different source resolves to a different set of files, so an edit to the source is an
      // edit to the list: keeping the old rows would silently open the previous subject's data.
      setFiles(null);
      setDraft((current) => ({ ...current, ...patch }));
    },
    [setDraft, setFiles],
  );

  // A later deep link (Results → "Open in viewer") re-prefills the draft. It still does not open.
  const linkCarriesControls = hasViewerDeepLink(deepLink);
  useEffect(() => {
    if (!active || !linkCarriesControls || location.state?.[SUBJECT_SYNC_STATE]) return;
    setFiles(null);
    setDraft((current) => selectionFromDeepLink(deepLink, current));
  }, [active, location.key, location.state, deepLink, linkCarriesControls, setDraft, setFiles]);

  // The shell's subject switcher edits the draft's subject — a draft edit like any other.
  const lastShellSubject = useRef(subjectId);
  useEffect(() => {
    if (subjectId === lastShellSubject.current) return;
    lastShellSubject.current = subjectId;
    if (subjectId) editDraft({ subject: subjectId });
  }, [subjectId, editDraft]);

  // ---------------------------------------------------------------------------------------------
  // Menus. Catalog reads: they populate options and open nothing.
  // ---------------------------------------------------------------------------------------------
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });

  // Which sub-page is on screen is the *route*, not state: the rail rows are real links, so the
  // rail's highlight and what is on screen are the same fact rather than two that can drift. A
  // path that names neither sub-item (a bare `/viewer`, or a `/viewer?...` deep link) is the Menu.
  const navigate = useNavigate();
  const sub: SubPage = location.pathname.endsWith("/tetravox") ? "tetravox" : "menu";
  const setSub = useCallback((next: SubPage) => navigate(`/viewer/${next}`), [navigate]);
  // What the embed is actually showing, so the Viewer strip can name it and `Reload` can re-post
  // it. Held here rather than read back off the store because the store's `scene` is the document
  // *after* the embed rewrote its layer ids on load.
  const [loaded, setLoaded] = useState<LoadedScene | null>(null);
  const loadScene = useViewerStore((s) => s.loadScene);
  const serializeScene = useViewerStore((s) => s.serializeScene);
  const screenshot = useViewerStore((s) => s.screenshot);
  const embedStatus = useViewerStore((s) => s.status);
  const [reloadToken, setReloadToken] = useState(0);
  // The bundle's version, for the `no-embed` state's sentence only. A read; never gates Open.
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: getCapabilities, retry: false });
  const embedVersion = caps.data?.tetravox_embed?.version ?? null;

  // ---------------------------------------------------------------------------------------------
  // The list.
  //
  // **One request per source, and none per edit** (VE, 2026-09-06; maintainer: *"the menu acts way
  // too slow — it looks like it does computation when I add or remove things"*). It did: the list
  // re-resolved through `POST /api/view/open?dry_run` on every add, remove and reorder, and that
  // route reads every volume in the scene to compute its percentile window — ~150 ms warm, 860 ms
  // cold, for a click that changes the order of two array elements.
  //
  // So the server is asked exactly two questions, both keyed on the *source* and cached forever
  // (`staleTime: Infinity` — a file's name, kind and size do not change under a fixed selection,
  // and a job that writes new files changes the selection or the catalog query that feeds it):
  //
  //   `baseline`   what this view type resolves to on its own — the list when nothing is edited,
  //                and the metadata for every row that came from the view type.
  //   `candidates` everything the subject and simulation offer "+ Add…", with the same
  //                name/kind/bytes on every row.
  //
  // An edited list is then those rows, in the order the person put them, looked up locally. No
  // request, no thread, no volume read: an add or a remove is one array operation.
  //
  // What that gives up, stated honestly: VM2 had the server drop a row it could not resolve, and
  // called a disappearing row a truer answer than one the client kept. That is still true for the
  // *one* path the client can invent — a hand-typed container path in "+ Add…". Every other row
  // came from the server's own catalogue, so it resolves by construction. The invented one now
  // appears in the list and is dropped by the server at Open, which is a worse moment to learn it
  // and a fair trade for a menu that does not stall on every click.
  // ---------------------------------------------------------------------------------------------
  const draftKey = selectionKey(draft);
  const complete = validateSelection(draft) === null;
  // Three things, all of them about the same complaint (maintainer, 2026-09-07: "there is still a
  // lot of loading time once the user starts manipulating the input data"):
  //
  // 1. **Debounced.** Every keystroke and every step through a `<select>`'s values used to start
  //    its own resolve. 150 ms is long enough to swallow the intermediate values of a selection
  //    someone is still making and short enough that a finished one feels immediate.
  // 2. **Abortable.** React Query hands `queryFn` a signal it aborts when the query is superseded
  //    or unmounted, and it now reaches `fetch` — so a resolve for an abandoned selection stops
  //    at the server rather than racing the current one to repaint the card.
  // 3. **`keepPreviousData`.** While the next selection resolves, the card keeps showing the
  //    previous list (greyed, see `data-stale`) instead of blanking to "Resolving…". Changing
  //    Field is a small edit to a list that is mostly the same afterwards; emptying the card for
  //    it made a fast resolve look like a reload.
  const debouncedKey = useDebounced(draftKey, 150);
  const debounceSettled = debouncedKey === draftKey;
  const baseline = useQuery({
    queryKey: ["viewer-resolution", draftKey],
    queryFn: ({ signal }) => previewView(draft.kind, viewQuery(draft) as ViewQuery, undefined, signal),
    enabled: complete && debounceSettled,
    retry: false,
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });
  /**
   * True while the rows on screen do not (yet) belong to the current selection.
   *
   * Four ways that can be so, and all four are needed. `isFetching` alone leaves a gap: in the
   * render where the debounce catches up but React Query has not started the request yet, nothing
   * is in flight and the data is still the previous key's — a spec that waited on `isFetching`
   * proceeded there and then attributed the resolve to whatever it did next.
   * `isPlaceholderData` is React Query's own answer to "is this the previous key's data", and
   * `isPending` covers the first resolve of a sitting, which has no previous key to show.
   */
  const resolving =
    complete && (!debounceSettled || baseline.isFetching || baseline.isPlaceholderData || baseline.isPending);
  const stale = resolving && baseline.data !== undefined;

  const candidates = useQuery({
    queryKey: ["viewer-candidates", draft.subject, draft.simulation, draft.space],
    queryFn: () => getCandidates(draft.subject, draft.simulation, draft.space),
    enabled: !!draft.subject,
    staleTime: Infinity,
  });

  // ---------------------------------------------------------------------------------------------
  // The composition tree (2026-09-07). Anatomy / Simulations / Analyses for this subject, from
  // `GET /api/viewer/tree` — `listdir` and `stat` on the server, so it is cheap enough to redraw
  // as a person clicks. `expandedSims` is sent with it because analyses are listed only for the
  // simulations someone has opened: a subject with a dozen simulations has a dozen Analyses
  // directories, and listing all of them turns a menu into a file browser.
  // ---------------------------------------------------------------------------------------------
  const [expandedSims, setExpandedSims] = useState<string[]>([]);
  const tree = useQuery({
    queryKey: ["viewer-tree", draft.subject, draft.space, expandedSims.join(",")],
    queryFn: () => getTree(draft.subject, draft.space, expandedSims),
    enabled: !!draft.subject,
    retry: false,
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });

  /** Every file this source knows about, by container path. Both queries, one index. */
  const known = useMemo(() => {
    const index = new Map<string, ViewerFile>();
    for (const c of candidates.data ?? []) {
      index.set(c.path, { kind: c.kind, name: c.name, path: c.path, container_path: c.path, bytes: c.bytes });
    }
    // Baseline rows win: they carry the host-facing `path` the row's tooltip shows, and a file can
    // be both a candidate and part of the view type's own set.
    for (const f of baseline.data?.files ?? []) {
      const key = f.container_path ?? f.path;
      index.set(key, f);
    }
    return index;
  }, [candidates.data, baseline.data]);

  const rows: ViewerFile[] = useMemo(() => {
    if (files === null) return baseline.data?.files ?? [];
    return files.map(
      (path) =>
        known.get(path) ?? {
          // A path nothing has described — only reachable by typing one into "+ Add…". Shown with
          // what can be known from the string itself, so the row is never blank.
          kind: /\.(msh|gii)$/i.test(path) ? "mesh" : "volume",
          name: path.split("/").pop() ?? path,
          path,
          container_path: path,
          bytes: null,
        },
    );
  }, [files, baseline.data, known]);

  /** The window the overlay will open at, shown on the card. See `lib.ts::windowSummary`. */
  const summary = useMemo(
    () =>
      windowSummary(
        baseline.data?.view?.layers as ViewSceneLayer[] | undefined,
        baseline.data?.view?.datasets as { id: string; name: string }[] | undefined,
        containerPaths(rows),
      ),
    [baseline.data, rows],
  );

  /** Edit the list. Always through the *resolved* rows, so an edit never invents a path. */
  const editFiles = useCallback((next: string[]) => setFiles(next), [setFiles]);

  /**
   * A *field* row was ticked in the tree, so bring the draft with it.
   *
   * Ticking anything else is a pure list edit and costs the server nothing — that property is
   * asserted, and it is why the Menu stopped feeling slow. A field is the exception because it is
   * not only a file: it decides which layer the window chip ("p95–p99.9 · …") describes and which
   * simulation the scene's cursor and per-layer defaults come from. Letting that go stale would
   * put a number on screen that belongs to a layer the person has just replaced.
   */
  const pickField = useCallback(
    (simulation: string, field: string | null) => {
      // `setDraft`, deliberately **not** `editDraft`. `editDraft` clears the list, because a
      // different *source* resolves to a different set of files and keeping the old rows would
      // silently open the previous subject's data. That is right for the subject picker and wrong
      // here: the person is editing the list, and the draft is only following along so the window
      // chip and the scene's per-layer defaults describe the field they just ticked. Routing this
      // through `editDraft` threw away the tick that caused it — the row went in and came straight
      // back out, replaced by the view type's own set.
      setDraft((current) => ({ ...current, kind: "simulation", simulation, ...(field === null ? {} : { field }) }));
    },
    [setDraft],
  );
  const removeRow = useCallback(
    (index: number) => editFiles(containerPaths(rows).filter((_, i) => i !== index)),
    [editFiles, rows],
  );
  const addFile = useCallback((path: string) => editFiles([...containerPaths(rows), path]), [editFiles, rows]);
  const moveRow = useCallback((from: number, to: number) => editFiles(reorder(containerPaths(rows), from, to)), [editFiles, rows]);

  const [dragging, setDragging] = useState<number | null>(null);

  // The picker: everything on offer, minus what is already in the list, grouped as the server
  // grouped it. A picker that offered a file already in the scene would be offering a no-op.
  const [addQuery, setAddQuery] = useState("");
  const [addPath, setAddPath] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const inList = new Set(containerPaths(rows));
  const offered = (candidates.data ?? []).filter(
    (c) => !inList.has(c.path) && (addQuery.trim() === "" || c.name.toLowerCase().includes(addQuery.trim().toLowerCase())),
  );
  const grouped = offered.reduce<Record<string, ViewerCandidate[]>>((acc, c) => {
    (acc[c.group] ??= []).push(c);
    return acc;
  }, {});

  // ---------------------------------------------------------------------------------------------
  // Open: the one place a scene file is written and the one place the app is launched.
  // ---------------------------------------------------------------------------------------------
  const [opened, setOpened] = useState<{ key: string; hostPath: string | null; name: string } | null>(null);
  const [failure, setFailure] = useState<ViewerFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [recents, setRecents] = useState<ViewerRecent[]>(() => readRecents());

  const open = useCallback(async () => {
    const attempt = draft;
    const key = selectionKey(attempt);
    const incomplete = validateSelection(attempt);
    if (incomplete !== null) {
      // Refused before the wire: an incomplete draft is not a server error and must not cost a
      // request, let alone a scene the person did not ask for.
      setFailure({ key, title: "This selection is incomplete", text: incomplete });
      return;
    }
    setFailure(null);
    setBusy(true);
    try {
      const written = await openView(attempt.kind, viewQuery(attempt) as ViewQuery, { files: files ?? undefined });
      setRecents(pushRecent({ key: `${key}|${(files ?? []).join(",")}`, label: selectionLabel(attempt), selection: attempt, files }));
      // One message. `written.view` is the embed's addressing of the same resolution that produced
      // the file on disk, so what the iframe draws and what the scene file describes cannot
      // disagree. The store holds it until the frame says `ready`, which is what lets Open work on
      // the very first visit, before the iframe has finished its handshake.
      loadScene(written.view as never);
      setLoaded({ key, name: written.name, hostPath: written.host_path, view: written.view });
      setOpened({ key, hostPath: written.host_path, name: written.name });
      setSub("tetravox");
    } catch (error) {
      const notFound = error instanceof ApiError && error.status === 404;
      setFailure({
        key,
        title: notFound ? "Nothing found for this selection" : "Could not build the scene",
        text: notFound
          ? "The server has nothing to show for this selection."
          : "POST /api/view/open could not build a scene for this selection. Check the server logs, or try again.",
      });
    } finally {
      setBusy(false);
    }
  }, [draft, files, loadScene, setSub]);

  /** Re-post the scene that is already loaded. Not a new resolution and not a new request. */
  const reloadScene = useCallback(() => {
    if (loaded === null) return;
    loadScene(loaded.view as never);
  }, [loadScene, loaded]);

  // ---------------------------------------------------------------------------------------------
  // Save scene (2026-09-07). The maintainer: *"we should be integrating scene saving where users
  // can essentially save scenes — not only the input selection but also the scene for the user —
  // and we should be very opinionated about that and save it in the Tetravox [scene format]."*
  //
  // Opinionated is the operative word, and it decides three things:
  //
  //  * **What is saved is what the embed has**, not the document the server built. Everything
  //    worth saving about a scene is what changed after it loaded — the camera someone flew to,
  //    the window they widened. So this asks the embed to `serialize` and stores that verbatim.
  //  * **A picture comes with it.** A list of scene names is a list a person cannot choose from;
  //    the embed's `screenshot` is one message and makes the list browsable. If it fails the save
  //    still happens, because a scene is worth keeping without its thumbnail.
  //  * **No dialog beyond a name.** The name is pre-filled by the server
  //    (`<subject>_<sim>_<field>_<date>`) so the common case is press-and-done.
  // ---------------------------------------------------------------------------------------------
  const savedScenes = useQuery({ queryKey: ["viewer-saved-scenes"], queryFn: getSavedScenes, retry: false });
  const [sceneName, setSceneName] = useState("");
  const [sceneSaveOpen, setSceneSaveOpen] = useState(false);
  const [sceneSaved, setSceneSaved] = useState<string | null>(null);

  // Pre-fill from the server when the popover opens, so the date is the project's clock rather
  // than this browser's and two machines saving the same view agree on what to call it.
  useEffect(() => {
    if (!sceneSaveOpen || sceneName !== "") return;
    let cancelled = false;
    void suggestSceneName(draft.subject, draft.simulation, draft.field).then((name) => {
      if (!cancelled) setSceneName(name);
    });
    return () => {
      cancelled = true;
    };
  }, [sceneSaveOpen, sceneName, draft.subject, draft.simulation, draft.field]);

  const saveSceneMutation = useMutation({
    mutationFn: async (name: string) => {
      const scene = await serializeScene();
      if (scene === null) {
        // A plain Error, not an ApiError: nothing failed over HTTP. The embed did not answer, and
        // saying so is more use to the person than a status code that would have to be invented.
        throw new Error("The viewer did not answer with its scene, so there is nothing to save.");
      }
      const thumbnail = await screenshot({ width: 480, height: 320 });
      return saveScene(name, {
        scene: scene as unknown as Record<string, unknown>,
        thumbnail,
        subject: draft.subject ?? null,
        simulation: draft.simulation ?? null,
        field: draft.field ?? null,
        space: draft.space ?? null,
      });
    },
    onSuccess: (saved) => {
      setSceneSaveOpen(false);
      setSceneName("");
      setSceneSaved(saved.name);
      void queryClient.invalidateQueries({ queryKey: ["viewer-saved-scenes"] });
    },
  });

  /** Re-open a scene someone saved: the document, straight into the embed. */
  const openSavedScene = useCallback(
    async (row: SavedScene) => {
      const scene = await readSavedScene(row.name);
      setLoaded({ key: `saved:${row.slug}`, name: `${row.slug}.tetravox.json`, hostPath: row.host_path ?? null, view: scene });
      loadScene(scene as never);
      setSub("tetravox");
    },
    [loadScene, setSub],
  );

  // ---------------------------------------------------------------------------------------------
  // Presets and recents. A preset is a selection someone chose to keep, and it lives in the
  // project (`code/ti-toolbox/viewer/presets/`) because the project is the unit people copy and
  // share. A recent is a footprint, and lives in this machine's browser storage.
  // ---------------------------------------------------------------------------------------------
  const presets = useQuery({ queryKey: ["viewer-compositions"], queryFn: getCompositions, retry: false });
  const [presetName, setPresetName] = useState("");
  const [presetOpen, setPresetOpen] = useState(false);
  const saving = useMutation({
    // A **composition**, not a scene: ids, not resolved layers. It records what was chosen, so
    // loading it next month re-resolves those choices against whatever is in the project then and
    // reports what has gone missing — "show me the same thing, from the current data". The scene
    // (what it looked like) is the other artefact, saved from the Tetravox sub-page.
    //
    // `selection` rides along beside `inputs` so a load can restore the draft exactly — which
    // field the window chip describes, which simulations were expanded. The server keeps keys it
    // does not know precisely so this page can carry what it needs without a contract change.
    mutationFn: (name: string) =>
      saveComposition(name, {
        name,
        subject: draft.subject ?? null,
        space: draft.space ?? null,
        inputs: containerPaths(rows),
        simulations: expandedSims,
        selection: draft as unknown as Record<string, never>,
      } as never),
    onSuccess: () => {
      setPresetOpen(false);
      setPresetName("");
      void queryClient.invalidateQueries({ queryKey: ["viewer-compositions"] });
    },
  });
  const forgetting = useMutation({
    mutationFn: (name: string) => deleteComposition(name),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["viewer-compositions"] }),
  });

  const restore = useCallback(
    (entry: { selection?: unknown; files?: unknown; inputs?: unknown; simulations?: unknown }) => {
      // Restoring is not opening. The page fills in; the person presses Open when they mean it.
      if (entry.selection) setDraft(entry.selection as ViewerSelection);
      // `inputs` is a composition's word for the list; `files` is a recent's. Both are the same
      // thing — the paths that make the scene — and reading either keeps Recent working unchanged.
      const list = Array.isArray(entry.inputs) ? entry.inputs : entry.files;
      setFiles(Array.isArray(list) ? (list as string[]) : null);
      // Expanding the same simulations puts the tree back the way it was left, which is most of
      // what "restore" means once the branches, not a dropdown, are how a scene is described.
      if (Array.isArray(entry.simulations)) setExpandedSims(entry.simulations as string[]);
    },
    [setDraft, setFiles],
  );

  // ---------------------------------------------------------------------------------------------
  // Options
  // ---------------------------------------------------------------------------------------------
  const subjectOptions: SelectOption[] = (subjects.data ?? []).map((s) => ({ value: s.id, label: s.id }));


  // Nothing to install and nothing to find: the viewer is served by the same origin that served
  // this page. The only thing that can stop an Open is an incomplete selection or an empty list.
  const showFailure = failure !== null && failure.key === draftKey;
  const openTitle = !complete
    ? (validateSelection(draft) ?? undefined)
    : rows.length === 0
      ? "Nothing to open — add a file first"
      : undefined;
  const canOpen = complete && rows.length > 0;

  return (
    <PageLayout variant="bleed" className="viewer-page" data-sub={sub}>
      {/* Two routes, one page. Both panes are always mounted: hiding the inactive one with
          `display:none` (viewer-page.css) keeps the iframe's document, its wasm heap and its
          camera exactly as the person left them, which is what "go back to the Menu, tinker, and
          reload a different setup" requires. Unmounting would silently reload the engine. */}
      <div className="viewer-sub" data-testid="viewer-sub-menu" data-active={sub === "menu" ? "true" : "false"}>
      <div className="viewer-scroll">
        <div className="viewer-panel" data-testid="viewer-panel">
          <header className="viewer-panel-head">
            <h1 className="viewer-panel-title">Open in viewer</h1>
            <p className="viewer-panel-lede">
              Tick what belongs in the scene — anatomy, a simulation’s outputs, an analysis — then <strong>Open in viewer</strong>. The
              scene is drawn under <strong>Tetravox</strong> in the rail, by the engine that ships inside the toolbox image. Nothing to
              install.
            </p>
          </header>

          {showFailure && (
            <div className="viewer-load-error" role="alert" data-testid="viewer-view-error">
              <span className="viewer-load-error-title">{failure.title}</span>
              <span className="viewer-load-error-text">{failure.text}</span>
              <Button variant="secondary" size="sm" onClick={() => void open()} disabled={busy}>
                Retry
              </Button>
            </div>
          )}

          {/* ── Compose ────────────────────────────────────────────────────────────────────
              Replaces the `Type / Subject / Simulation / Field / Space` card (2026-09-07). See
              `Tree.tsx` for why the type went away and why the tree owns no selection of its own. */}
          <section className="viewer-card" data-testid="viewer-section-source">
            <div className="viewer-card-head">
              <span className="viewer-card-title text-eyebrow">Compose</span>
              <span className="viewer-card-note">Tick what belongs in the scene. Everything here is a file this subject already has.</span>
            </div>

            {/* Subject and space are the two facts every branch below depends on, so they sit
                above the tree rather than inside it. */}
            <div
              className="viewer-compose-head"
              data-testid="viewer-source-bar"
              data-dirty={opened === null || opened.key !== draftKey ? "true" : "false"}
              data-draft-key={draftKey}
              data-opened-key={opened?.key ?? ""}
            >
              <label className="viewer-row viewer-source-item" data-testid="viewer-select-subject">
                <span className="viewer-row-label">Subject</span>
                <span className="viewer-row-control">
                  <Select
                    value={draft.subject}
                    onValueChange={(v) =>
                      editDraft({ kind: "subject", subject: v, simulation: undefined, analysis: undefined, field: undefined, atlas: undefined })
                    }
                    options={subjectOptions}
                    placeholder="Subject…"
                    aria-label="Subject"
                  />
                </span>
              </label>
              <label className="viewer-row viewer-source-item">
                <span className="viewer-row-label">Space</span>
                <span className="viewer-row-control">
                  <SegmentedControl<Space>
                    aria-label="Space"
                    size="sm"
                    value={draft.space}
                    onValueChange={(v) => editDraft({ space: v, atlas: undefined })}
                    options={[
                      { value: "subject", label: "Subject" },
                      { value: "mni", label: "MNI", title: "The scene the server builds in MNI space" },
                    ]}
                  />
                </span>
              </label>
            </div>

            <CompositionTree
              tree={tree.data}
              loading={tree.isFetching}
              chosen={containerPaths(rows)}
              onChange={editFiles}
              expanded={expandedSims}
              onExpandedChange={setExpandedSims}
              onFieldPicked={pickField}
            />
          </section>

          {/* ── What will open ─────────────────────────────────────────────────────────────── */}
          <section
            className="viewer-card"
            data-testid="viewer-plan"
            /* The list on screen belongs to an earlier selection (kept, greyed) — drives the CSS. */
            data-stale={stale ? "true" : undefined}
            /* A resolve is pending or in flight, whether or not there are rows to keep. What a
               test must wait on before it can attribute a request to what it does next. */
            data-resolving={resolving ? "true" : undefined}
          >
            <div className="viewer-card-head">
              <span className="viewer-card-title text-eyebrow">What will open</span>
              <span className="viewer-card-note" data-testid="viewer-plan-note">
                {rows.length === 0 ? "nothing yet" : `${rows.length} file${rows.length === 1 ? "" : "s"}, in this order`}
              </span>
              {summary !== null && (
                <span className="viewer-card-window" data-testid="viewer-window-summary" title="The window the field overlay opens at">
                  {summary}
                </span>
              )}
              <div className="viewer-card-actions">
                {files !== null && (
                  <button type="button" className="viewer-link" onClick={() => setFiles(null)} data-testid="viewer-files-reset">
                    Reset
                  </button>
                )}
                <Popover
                  open={addOpen}
                  onOpenChange={setAddOpen}
                  trigger={
                    <Button variant="secondary" size="sm" icon={<Plus size={14} />} disabled={!draft.subject} data-testid="viewer-add">
                      Add…
                    </Button>
                  }
                >
                  <div className="viewer-popover viewer-add">
                    <p className="viewer-popover-title">Add a file to the scene</p>
                    <TextInput value={addQuery} onChange={(e) => setAddQuery(e.target.value)} placeholder="Filter…" aria-label="Filter files" data-testid="viewer-add-filter" />
                    <div className="viewer-add-list" data-testid="viewer-add-list">
                      {Object.keys(grouped).length === 0 && <p className="viewer-empty">Nothing left to add for this subject.</p>}
                      {Object.entries(grouped).map(([group, entries]) => (
                        <div className="viewer-add-group" key={group}>
                          <p className="viewer-add-group-title">{group}</p>
                          {entries.map((candidate) => (
                            <button
                              type="button"
                              className="viewer-add-item"
                              key={candidate.path}
                              title={candidate.path}
                              data-testid={`viewer-add-${candidate.name}`}
                              onClick={() => {
                                addFile(candidate.path);
                                setAddOpen(false);
                                setAddQuery("");
                              }}
                            >
                              <span className="viewer-add-item-name">{candidate.name}</span>
                              <span className="viewer-add-item-meta">
                                {candidate.kind} · {formatBytes(candidate.bytes)}
                              </span>
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                    {/* Anything else in the project. No host picker is wired in this app yet, so
                        this is the container path a person types or pastes — the same field
                        `kind: custom` uses, and the same jail check on the far end. */}
                    <div className="viewer-add-path">
                      <TextInput
                        value={addPath}
                        onChange={(e) => setAddPath(e.target.value)}
                        placeholder="/path/inside/the/project.nii.gz"
                        aria-label="Add by path"
                        data-testid="viewer-add-path"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={addPath.trim() === ""}
                        data-testid="viewer-add-path-go"
                        onClick={() => {
                          addFile(addPath.trim());
                          setAddPath("");
                          setAddOpen(false);
                        }}
                      >
                        Add
                      </Button>
                    </div>
                  </div>
                </Popover>
              </div>
            </div>

            {!complete ? (
              <p className="viewer-empty" data-testid="viewer-nothing-selected">
                Choose a source above and the files it resolves to appear here.
              </p>
            ) : rows.length === 0 && resolving ? (
              // Only the **first** resolve of a sitting can reach this: with `keepPreviousData`
              // every later one still has the previous selection's rows to show, greyed, so
              // changing Field no longer blanks the card and then refills it. An edited list is
              // local and never resolves at all.
              <p className="viewer-empty" data-testid="viewer-resolving">
                Resolving…
              </p>
            ) : rows.length === 0 ? (
              <p className="viewer-empty">Nothing yet — the server found no files for this selection. Add one, or reset the list.</p>
            ) : (
              <ul className="viewer-files" data-testid="viewer-preview-files">
                {rows.map((file, index) => (
                  <li
                    className="viewer-file"
                    key={file.container_path ?? file.path}
                    data-testid={`viewer-file-${file.name}`}
                    data-index={index}
                    data-dragging={dragging === index ? "true" : undefined}
                    draggable
                    onDragStart={() => setDragging(index)}
                    onDragEnd={() => setDragging(null)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragging !== null) moveRow(dragging, index);
                      setDragging(null);
                    }}
                  >
                    <span className="viewer-file-grip" aria-hidden>
                      <GripVertical size={13} />
                    </span>
                    <span className="viewer-file-name" title={file.path}>
                      {file.name}
                    </span>
                    <span className="viewer-file-kind">{file.kind}</span>
                    <span className="viewer-file-size">{formatBytes(file.bytes)}</span>
                    {/* Keyboard reordering: drag is a mouse gesture, and a list you can only
                        reorder with a mouse is a list some people cannot reorder. */}
                    <button
                      type="button"
                      className="viewer-file-move"
                      aria-label={`Move ${file.name} up`}
                      disabled={index === 0}
                      onClick={() => moveRow(index, index - 1)}
                      data-testid={`viewer-file-up-${file.name}`}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="viewer-file-move"
                      aria-label={`Move ${file.name} down`}
                      disabled={index === rows.length - 1}
                      onClick={() => moveRow(index, index + 1)}
                      data-testid={`viewer-file-down-${file.name}`}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="viewer-file-remove"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => removeRow(index)}
                      data-testid={`viewer-file-remove-${file.name}`}
                    >
                      <X size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {opened !== null && (
              <p className="viewer-opened" data-testid="viewer-opened">
                {`Open in the Viewer tab. The scene was also written to ${opened.hostPath ?? opened.name}.`}
              </p>
            )}
          </section>

          {/* ── Footer ─────────────────────────────────────────────────────────────────────── */}
          <footer className="viewer-panel-foot">
            <Popover
              open={presetOpen}
              onOpenChange={setPresetOpen}
              trigger={
                <Button variant="secondary" size="sm" icon={<Save size={14} />} disabled={!complete} data-testid="viewer-save-preset">
                  Save selection…
                </Button>
              }
            >
              <div className="viewer-popover">
                <p className="viewer-popover-title">Save this selection</p>
                <p className="viewer-popover-text">
                  Writes the subject, the space and the inputs you ticked to the project as JSON. Loading it later re-resolves those
                  choices against the data as it is then — so a re-run simulation comes back with its new outputs.
                </p>
                <TextInput
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  placeholder="Name"
                  aria-label="Composition name"
                  data-testid="viewer-preset-name"
                />
                <Button
                  variant="primary"
                  size="sm"
                  disabled={presetName.trim().length === 0 || saving.isPending}
                  onClick={() => saving.mutate(presetName.trim())}
                  data-testid="viewer-preset-save"
                >
                  Save
                </Button>
                {(presets.data ?? []).length > 0 && (
                  <ul className="viewer-preset-list" data-testid="viewer-presets">
                    {(presets.data ?? []).map((preset) => (
                      <li className="viewer-preset" key={preset.name}>
                        <button
                          type="button"
                          className="viewer-preset-restore"
                          data-testid={`viewer-preset-${preset.name}`}
                          onClick={() => {
                            restore(preset);
                            setPresetOpen(false);
                          }}
                        >
                          {preset.name}
                        </button>
                        <button
                          type="button"
                          className="viewer-preset-forget"
                          aria-label={`Forget ${preset.name}`}
                          onClick={() => forgetting.mutate(preset.name)}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Popover>

            <Popover
              trigger={
                <Button variant="secondary" size="sm" icon={<Clock size={14} />} disabled={recents.length === 0} data-testid="viewer-recent">
                  Recent
                </Button>
              }
            >
              <div className="viewer-popover">
                <p className="viewer-popover-title">Last opened</p>
                <ul className="viewer-recent-list" data-testid="viewer-recents">
                  {recents.map((entry, index) => (
                    <li key={entry.key}>
                      <button type="button" className="viewer-recent-item" data-testid={`viewer-recent-${index}`} onClick={() => restore(entry)}>
                        {entry.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </Popover>

            {/* Saved scenes — a picture someone kept, reopened in one click. Distinct from
                Recent (a footprint of what was opened) and from a preset (a selection): this is
                the scene as it looked, camera and windows included. */}
            <Popover
              trigger={
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Camera size={14} />}
                  disabled={(savedScenes.data ?? []).length === 0}
                  data-testid="viewer-saved-scenes-open"
                >
                  Saved scenes
                </Button>
              }
            >
              <div className="viewer-popover">
                <p className="viewer-popover-title">Saved scenes</p>
                <ul className="viewer-scene-list" data-testid="viewer-saved-scenes">
                  {(savedScenes.data ?? []).map((row) => (
                    <li key={row.slug}>
                      <button
                        type="button"
                        className="viewer-scene-item"
                        data-testid={`viewer-saved-scene-${row.slug}`}
                        onClick={() => void openSavedScene(row)}
                        title={row.path}
                      >
                        {row.has_thumbnail ? (
                          <img
                            className="viewer-scene-thumb"
                            /* Served by the same jailed file route every dataset comes through. */
                            src={`/api/files/raw${row.path.replace(/\.tetravox\.json$/, ".png")}`}
                            alt=""
                          />
                        ) : (
                          <span className="viewer-scene-thumb viewer-scene-thumb-empty" aria-hidden />
                        )}
                        <span className="viewer-scene-text">
                          <span className="viewer-scene-name">{row.name}</span>
                          <span className="viewer-scene-meta">
                            {[row.subject, row.simulation, row.field].filter(Boolean).join(" · ") || "scene"}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </Popover>

            <div className="viewer-foot-spacer" />

            <Button
              size="sm"
              variant="primary"
              onClick={() => void open()}
              disabled={busy || !canOpen}
              title={openTitle}
              data-testid="viewer-open"
              icon={<Eye size={14} />}
            >
              {busy ? "Opening…" : "Open in viewer"}
            </Button>
          </footer>
        </div>
      </div>
      </div>

      {/* ── Viewer ───────────────────────────────────────────────────────────────────────────
          Full-bleed, and deliberately almost empty of chrome: layer appearance, the camera and
          the crosshair belong to the embed's own inspector, which has the whole surface and the
          reader's attention. What is left here is the three things the embed cannot answer —
          which scene this is, put it back the way it was, and go edit it. */}
      <div className="viewer-sub viewer-sub-frame" data-testid="viewer-sub-viewer" data-active={sub === "tetravox" ? "true" : "false"}>
        <div className="viewer-strip" data-testid="viewer-strip">
          <span className="viewer-strip-name" data-testid="viewer-strip-name" title={loaded?.hostPath ?? undefined}>
            {loaded === null ? "No scene open" : loaded.name}
          </span>
          <div className="viewer-strip-spacer" />
          {sceneSaved !== null && (
            <span className="viewer-strip-saved" data-testid="viewer-scene-saved">
              Saved {sceneSaved}.tetravox.json
            </span>
          )}
          <Popover
            open={sceneSaveOpen}
            onOpenChange={(open) => {
              setSceneSaveOpen(open);
              if (open) setSceneSaved(null);
            }}
            trigger={
              <Button
                variant="secondary"
                size="sm"
                icon={<Camera size={14} />}
                /* The embed has to be showing something before there is a scene to serialize. */
                disabled={loaded === null || embedStatus !== "ready"}
                data-testid="viewer-scene-save-open"
                title="Save the camera, layout and windows exactly as they are now"
              >
                Save scene
              </Button>
            }
          >
            <div className="viewer-popover">
              <p className="viewer-popover-title">Save this scene</p>
              <p className="viewer-popover-text">
                Keeps the picture as it is now — camera, layout, and every layer’s window — as a Tetravox scene in the project, with a
                thumbnail. The standalone Tetravox app opens it directly.
              </p>
              <TextInput
                value={sceneName}
                onChange={(e) => setSceneName(e.target.value)}
                placeholder="Scene name"
                aria-label="Scene name"
                data-testid="viewer-scene-name"
              />
              {saveSceneMutation.isError && (
                <p className="viewer-popover-error" data-testid="viewer-scene-save-error">
                  {(saveSceneMutation.error as Error).message}
                </p>
              )}
              <div className="viewer-popover-actions">
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Save size={14} />}
                  disabled={sceneName.trim() === "" || saveSceneMutation.isPending}
                  onClick={() => saveSceneMutation.mutate(sceneName.trim())}
                  data-testid="viewer-scene-save"
                >
                  {saveSceneMutation.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>
          </Popover>
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={reloadScene}
            disabled={loaded === null}
            data-testid="viewer-reload"
            title="Re-send this scene to the viewer"
          >
            Reload
          </Button>
        </div>

        {loaded === null ? (
          <div className="viewer-empty" data-testid="viewer-empty">
            <p className="viewer-empty-title">Nothing is open yet</p>
            <p className="viewer-empty-text">
              Build a scene under <strong>Menu</strong> and press <strong>Open in viewer</strong>. It appears here, in this window — there
              is nothing to install.
            </p>
            <Button variant="primary" size="sm" onClick={() => setSub("menu")} data-testid="viewer-empty-menu">
              Go to the menu
            </Button>
          </div>
        ) : (
          <TetravoxFrame
            className="viewer-embed"
            embedVersion={embedVersion}
            reloadToken={reloadToken}
            onReload={() => {
              // A full remount of the iframe, then the scene again — the recovery path for a frame
              // that mounted and never answered. `Reload` in the strip is the cheap one (re-post
              // only); this is the expensive one, and only the `no-embed` state offers it.
              setReloadToken((t) => t + 1);
              reloadScene();
            }}
          />
        )}
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "viewer",
  title: "Viewer",
  purpose: "Build a scene from the subject's files, then view it in the app's own Tetravox.",
  navGroup: "explore",
  order: 60,
  icon: Eye,
  shortcut: "7",
  Component: ViewerPage,
  enabled: true,
  layout: "full-bleed",
  subNav: SUB_NAV,
};

export default page;
