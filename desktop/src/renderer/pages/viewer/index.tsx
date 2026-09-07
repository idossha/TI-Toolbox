/**
 * Viewer screen — **a source, a file list, and Open** (V1 · VM · VM2,
 * `dev/notes/v3-native-panes-external-viewer/{VX,VM,VM2}.md`).
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { Clock, Eye, GripVertical, Plus, RefreshCw, Save, X } from "lucide-react";
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
  deletePreset,
  getAnalyses,
  getAtlases,
  getCandidates,
  getPresets,
  getSimulationsFor,
  previewView,
  openView,
  savePreset,
  type Space,
  type ViewKind,
  type ViewQuery,
} from "./api";
import {
  containerPaths,
  controlLabel,
  controlsFor,
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
  type ViewerCandidate,
  type ViewerControl,
  type ViewerFile,
  type ViewerRecent,
  type ViewerSelection,
} from "./lib";
import { TetravoxFrame, useViewerStore } from "../../viewer";
import { getCapabilities } from "../settings/api";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import "./viewer-page.css";

export { readDeepLink } from "./lib";
export type { ViewerDeepLink, ViewerSelection } from "./lib";

const VIEW_KIND_OPTIONS: SelectOption[] = [
  { value: "subject", label: "Subject anatomy" },
  { value: "simulation", label: "Simulation" },
  { value: "analysis", label: "Analysis" },
  { value: "group", label: "Group result" },
  { value: "custom", label: "Custom files" },
];

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
  const controls = controlsFor(draft.kind);
  const shows = (control: ViewerControl): boolean => controls.includes(control);
  const simulations = useQuery({
    queryKey: ["viewer-simulations", draft.subject],
    queryFn: () => getSimulationsFor(draft.subject as string),
    enabled: !!draft.subject && shows("simulation"),
  });
  const analyses = useQuery({
    queryKey: ["viewer-analyses", draft.subject, draft.simulation],
    queryFn: () => getAnalyses(draft.subject as string, draft.simulation as string),
    enabled: !!draft.subject && !!draft.simulation && shows("analysis"),
  });
  const atlases = useQuery({
    queryKey: ["viewer-atlases", draft.subject, draft.space],
    queryFn: () => getAtlases(draft.subject as string, draft.space),
    enabled: !!draft.subject && shows("atlas"),
  });

  const selectedSimulation = (simulations.data ?? []).find((s) => s.name === draft.simulation);
  const fieldsAvailable = selectedSimulation?.fields ?? [];

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
  const [reloadToken, setReloadToken] = useState(0);
  // The bundle's version, for the `no-embed` state's sentence only. A read; never gates Open.
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: getCapabilities, retry: false });
  const embedVersion = caps.data?.tetravox_embed?.version ?? null;

  // ---------------------------------------------------------------------------------------------
  // The list: what this selection resolves to, from the endpoint that would open it, in dry run.
  //
  // The same route Open uses, and with the same `files`, so what the list shows and what Open
  // writes cannot disagree. Editing a row therefore re-resolves — which is the point: the server
  // is the one that knows a path is jailed out, missing, or a duplicate, and the row disappearing
  // is a truer answer than a row the client kept and the scene did not.
  // ---------------------------------------------------------------------------------------------
  const draftKey = selectionKey(draft);
  const complete = validateSelection(draft) === null;
  const resolution = useQuery({
    queryKey: ["viewer-resolution", draftKey, files],
    queryFn: () => previewView(draft.kind, viewQuery(draft) as ViewQuery, files ?? undefined),
    enabled: complete,
    retry: false,
  });
  const rows: ViewerFile[] = useMemo(() => resolution.data?.files ?? [], [resolution.data]);

  const candidates = useQuery({
    queryKey: ["viewer-candidates", draft.subject, draft.simulation, draft.space],
    queryFn: () => getCandidates(draft.subject, draft.simulation, draft.space),
    enabled: !!draft.subject,
  });

  /** Edit the list. Always through the *resolved* rows, so an edit never invents a path. */
  const editFiles = useCallback((next: string[]) => setFiles(next), [setFiles]);
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
  // Presets and recents. A preset is a selection someone chose to keep, and it lives in the
  // project (`code/ti-toolbox/viewer/presets/`) because the project is the unit people copy and
  // share. A recent is a footprint, and lives in this machine's browser storage.
  // ---------------------------------------------------------------------------------------------
  const presets = useQuery({ queryKey: ["viewer-presets"], queryFn: () => getPresets(), retry: false });
  const [presetName, setPresetName] = useState("");
  const [presetOpen, setPresetOpen] = useState(false);
  const saving = useMutation({
    mutationFn: (name: string) => savePreset({ name, selection: draft as unknown as Record<string, never>, files }),
    onSuccess: () => {
      setPresetOpen(false);
      setPresetName("");
      void queryClient.invalidateQueries({ queryKey: ["viewer-presets"] });
    },
  });
  const forgetting = useMutation({
    mutationFn: (name: string) => deletePreset(name),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["viewer-presets"] }),
  });

  const restore = useCallback(
    (entry: { selection?: unknown; files?: unknown }) => {
      // Restoring is not opening. The page fills in; the person presses Open when they mean it.
      if (entry.selection) setDraft(entry.selection as ViewerSelection);
      setFiles(Array.isArray(entry.files) ? (entry.files as string[]) : null);
    },
    [setDraft, setFiles],
  );

  // ---------------------------------------------------------------------------------------------
  // Options
  // ---------------------------------------------------------------------------------------------
  const subjectOptions: SelectOption[] = (subjects.data ?? []).map((s) => ({ value: s.id, label: s.id }));
  const simulationOptions: SelectOption[] = (simulations.data ?? []).map((s) => ({ value: s.name, label: s.name }));
  const analysisOptions: SelectOption[] = (analyses.data ?? []).map((a) => ({ value: a.name, label: a.name }));
  const atlasOptions: SelectOption[] = (atlases.data ?? []).map((a) => ({ value: a.id, label: a.name || a.id }));
  const fieldOptions: SelectOption[] = fieldsAvailable.map((f) => ({ value: f, label: f }));

  const selector = (control: ViewerControl, node: React.ReactNode) => (
    <label className="viewer-row viewer-source-item" data-testid={`viewer-select-${control}`} key={control}>
      <span className="viewer-row-label">{controlLabel(control)}</span>
      <span className="viewer-row-control">{node}</span>
    </label>
  );

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
              Pick a source, edit the list of files it resolves to, and <strong>Open in viewer</strong> — the scene is drawn in the{" "}
              <strong>Viewer</strong> tab above, by the Tetravox engine that ships inside the toolbox image. Nothing to install.
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

          {/* ── Source ─────────────────────────────────────────────────────────────────────── */}
          <section className="viewer-card" data-testid="viewer-section-source">
            <div className="viewer-card-head">
              <span className="viewer-card-title text-eyebrow">Source</span>
              <span className="viewer-card-note">The type decides which of the fields it needs.</span>
            </div>
            <div
              className="viewer-source-grid"
              data-testid="viewer-source-bar"
              data-dirty={opened === null || opened.key !== draftKey ? "true" : "false"}
              data-draft-key={draftKey}
              data-opened-key={opened?.key ?? ""}
            >
              <label className="viewer-row viewer-source-item" data-testid="viewer-select-kind">
                <span className="viewer-row-label">Type</span>
                <span className="viewer-row-control">
                  <Select value={draft.kind} onValueChange={(v) => editDraft({ kind: v as ViewKind })} options={VIEW_KIND_OPTIONS} aria-label="Type" />
                </span>
              </label>
              {shows("subject") &&
                selector(
                  "subject",
                  <Select
                    value={draft.subject}
                    onValueChange={(v) => editDraft({ subject: v, simulation: undefined, analysis: undefined, field: undefined, atlas: undefined })}
                    options={subjectOptions}
                    placeholder="Subject…"
                    aria-label="Subject"
                  />,
                )}
              {shows("simulation") &&
                selector(
                  "simulation",
                  <Select
                    value={draft.simulation}
                    onValueChange={(v) => editDraft({ simulation: v, analysis: undefined, field: undefined })}
                    options={simulationOptions}
                    placeholder={simulationOptions.length === 0 ? "None" : "Simulation…"}
                    disabled={simulationOptions.length === 0}
                    aria-label="Simulation"
                  />,
                )}
              {shows("analysis") &&
                selector(
                  "analysis",
                  <Select
                    value={draft.analysis}
                    onValueChange={(v) => editDraft({ analysis: v })}
                    options={analysisOptions}
                    placeholder={analysisOptions.length === 0 ? "None" : "Analysis…"}
                    disabled={analysisOptions.length === 0}
                    aria-label="Analysis"
                  />,
                )}
              {shows("field") &&
                selector(
                  "field",
                  <Select
                    value={draft.field}
                    onValueChange={(v) => editDraft({ field: v })}
                    options={fieldOptions}
                    placeholder={fieldOptions.length === 0 ? "None" : "Field…"}
                    disabled={fieldOptions.length === 0}
                    aria-label="Field"
                  />,
                )}
              {shows("atlas") &&
                selector(
                  "atlas",
                  <Select
                    value={draft.atlas}
                    onValueChange={(v) => editDraft({ atlas: v })}
                    options={atlasOptions}
                    placeholder={atlasOptions.length === 0 ? "Server default" : "Atlas…"}
                    disabled={atlasOptions.length === 0}
                    aria-label="Atlas"
                  />,
                )}
              {shows("roi") &&
                selector(
                  "roi",
                  <Select
                    value={draft.roi}
                    onValueChange={(v) => editDraft({ roi: v })}
                    options={atlasOptions}
                    placeholder={atlasOptions.length === 0 ? "None" : "ROI…"}
                    disabled={atlasOptions.length === 0}
                    aria-label="ROI"
                  />,
                )}
              {shows("path") &&
                selector(
                  "path",
                  <input
                    className="input viewer-source-path"
                    type="text"
                    value={draft.path ?? ""}
                    onChange={(e) => editDraft({ path: e.target.value })}
                    placeholder="/path/to/volume.nii.gz"
                    aria-label="Path"
                    data-testid="viewer-path-input"
                  />,
                )}
              {shows("space") && (
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
              )}
            </div>
          </section>

          {/* ── What will open ─────────────────────────────────────────────────────────────── */}
          <section className="viewer-card" data-testid="viewer-plan">
            <div className="viewer-card-head">
              <span className="viewer-card-title text-eyebrow">What will open</span>
              <span className="viewer-card-note">{rows.length === 0 ? "nothing yet" : `${rows.length} file${rows.length === 1 ? "" : "s"}, in this order`}</span>
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
            ) : resolution.isPending ? (
              <p className="viewer-empty">Resolving…</p>
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
                  Save as preset…
                </Button>
              }
            >
              <div className="viewer-popover">
                <p className="viewer-popover-title">Save this selection</p>
                <TextInput
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  placeholder="Name"
                  aria-label="Preset name"
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
              Build a scene in the <strong>Menu</strong> and press <strong>Open in viewer</strong>. It appears here, in this window — there is
              nothing to install.
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
