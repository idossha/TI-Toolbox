/**
 * Viewer screen — the embed, and nothing else (DESIGN.md §10, program U5).
 *
 * The whole page is three things: pick what to look at (the source bar), ask the server to build a
 * scene for it (`GET /api/view/{kind}` → a Tetravox ViewSpec v2 whose datasets are origin-relative
 * `/api/files/raw/...` URLs), hand that scene to the embed. Nothing here renders anything: the
 * pixels are the embed's, in its own iframe, on its own CSP (D1/D3,
 * `dev/notes/v3-docker-streamline-plan.md`).
 *
 * R5 (`desktop/IMPLEMENTATION_PLAN.md`) — **selection is explicit and loading is a command.**
 *
 * There are two selections, not one. `draft` is what the source bar shows; `loaded` is what the
 * embed is currently drawing. Editing any selector edits the draft and nothing else: no view
 * request, no `load` message, no change on screen. **Load** validates the draft, snapshots it,
 * issues exactly one `GET /api/view/{kind}`, and posts exactly one scene to the retained iframe.
 *
 * Why that is worth the extra state: the v2 page derived its view query from the controls and let
 * react-query fetch whenever the key changed, so touching the subject switcher tore down a 400 MB
 * scene someone was reading and started fetching another one — and a failed fetch replaced the
 * picture with an error card, losing the thing they had. Here a failure keeps the last good scene
 * on screen and attaches the error to the *attempted* selection, which is the only selection the
 * error is about. Deep links prefill the draft and stop there (R5's fixed decision); Reload is
 * iframe/runtime recovery for the scene already loaded, not a way to load a new one.
 *
 * Catalog queries (subjects, simulations, analyses, atlases) still run on their own — they fill
 * menus. Populating a menu is not building a scene, and the gate counts `/api/view` requests.
 *
 * v2 drew a Layers / Cursor / Scene inspector down the right-hand side; v3 deletes it entirely.
 * Every one of those controls exists in the embed's own panels, drawn in the engine's theme
 * against the engine's state, and two copies of one control give two answers to "what is the
 * window" (DESIGN.md §10's ownership rule). What used to be an inspector block is now, at most, one
 * status-bar cell (`ras`, `space`, `renderer`, §11) or a hint drawn over the canvas itself.
 *
 * There is no Freeview, no Gmsh and no "Open externally" any more.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Eye, RotateCw } from "lucide-react";
import { ApiError, getCapabilities, getSubjects } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { usePageSession } from "../../app/pageSession";
import { usePageActive } from "../../app/pageActivity";
import { SUBJECT_SYNC_STATE } from "../../app/subjectSpine";
import { useSubjectContext } from "../../app/subjectContext";
import { useStatusCells } from "../../app/statusCells";
import { Button, IconButton } from "../../ui/Button";
import { PageLayout } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Select, type SelectOption } from "../../ui/Select";
import { TetravoxFrame, useViewerStore, type EmbedViewSpec } from "../../viewer";
import { getAnalyses, getAtlases, getSimulationsFor, getView, type Space, type ViewKind, type ViewQuery } from "./api";
import {
  controlLabel,
  controlsFor,
  formatRas,
  hasViewerDeepLink,
  hidden3DLayer,
  layerName,
  readDeepLink,
  readDocumentTheme,
  selectionFromDeepLink,
  selectionKey,
  shortRenderer,
  validateSelection,
  viewQuery,
  type ViewerControl,
  type ViewerSelection,
} from "./lib";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import "./viewer-page.css";

export { readDeepLink, hidden3DLayer } from "./lib";
export type { ViewerDeepLink, ViewerSelection } from "./lib";

const VIEW_KIND_OPTIONS: SelectOption[] = [
  { value: "subject", label: "Subject" },
  { value: "simulation", label: "Simulation" },
  { value: "analysis", label: "Analysis" },
  { value: "group", label: "Group" },
  { value: "custom", label: "Custom file" },
];

/** What a failed (or refused) Load left behind, tied to the selection that was attempted. */
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

  // ---------------------------------------------------------------------------------------------
  // The draft: session state, seeded from the deep link (prefill only) over the shell's subject.
  // Every selector below writes here and does nothing else.
  // ---------------------------------------------------------------------------------------------
  const [draft, setDraft] = usePageSession<ViewerSelection>("selection", () =>
    selectionFromDeepLink(deepLink, { kind: "subject", subject: subjectId ?? undefined, space: "subject" }),
  );
  const editDraft = useCallback(
    (patch: Partial<ViewerSelection>) => setDraft((current) => ({ ...current, ...patch })),
    [setDraft],
  );

  // A later deep link (Results → "Open in Viewer") re-prefills the draft. It still does not load:
  // the controls change, the picture does not, and the person presses Load when they mean it.
  const linkCarriesControls = hasViewerDeepLink(deepLink);
  useEffect(() => {
    if (!active || !linkCarriesControls || location.state?.[SUBJECT_SYNC_STATE]) return;
    setDraft((current) => selectionFromDeepLink(deepLink, current));
  }, [active, location.key, location.state, deepLink, linkCarriesControls, setDraft]);

  // The shell's subject switcher edits the draft's subject — a draft edit like any other, so it
  // does not fetch and does not disturb the scene on screen. Tracked through a ref rather than a
  // `draft.subject` dependency so a subject chosen *here* is not immediately overwritten.
  const lastShellSubject = useRef(subjectId);
  useEffect(() => {
    if (subjectId === lastShellSubject.current) return;
    lastShellSubject.current = subjectId;
    if (subjectId) editDraft({ subject: subjectId });
  }, [subjectId, editDraft]);

  // ---------------------------------------------------------------------------------------------
  // Menus. These are catalog reads: they populate options and never build a scene.
  // ---------------------------------------------------------------------------------------------
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: () => getCapabilities() });
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
  const fields = selectedSimulation?.fields ?? [];

  const layers = useViewerStore((s) => s.layers);
  const cursor = useViewerStore((s) => s.cursor);
  const storeSpace = useViewerStore((s) => s.space);
  const viewerStatus = useViewerStore((s) => s.status);
  const renderer = useViewerStore((s) => s.renderer);
  const embedReady = useViewerStore((s) => s.embedReady);
  const loadScene = useViewerStore((s) => s.loadScene);
  const setStoreSpace = useViewerStore((s) => s.setSpace);
  const setEmbedTheme = useViewerStore((s) => s.setTheme);

  // ---------------------------------------------------------------------------------------------
  // Reload: the source bar's own IconButton and the `no-embed` state's own button both bump this,
  // which remounts the iframe (TetravoxFrame's `key`) and re-runs the handshake. It re-sends the
  // scene that is already loaded — it never loads the draft. Recovering a runtime and adopting a
  // new selection are two different acts and R5 keeps them two different buttons.
  // ---------------------------------------------------------------------------------------------
  const [reloadToken, setReloadToken] = useState(0);
  const handleReload = useCallback(() => setReloadToken((t) => t + 1), []);

  // ---------------------------------------------------------------------------------------------
  // Load: the one place a view request is issued and the one place a scene reaches the embed.
  // ---------------------------------------------------------------------------------------------
  const [loaded, setLoaded] = useState<{ selection: ViewerSelection; key: string } | null>(null);
  const [failure, setFailure] = useState<ViewerFailure | null>(null);
  const [loading, setLoading] = useState(false);
  const loadedScene = useRef<EmbedViewSpec | null>(null);
  const draftKey = selectionKey(draft);
  const dirty = loaded === null || loaded.key !== draftKey;

  const load = useCallback(async () => {
    const attempt = draft;
    const key = selectionKey(attempt);
    const incomplete = validateSelection(attempt);
    if (incomplete !== null) {
      // Refused before the wire: an incomplete draft is not a server error and must not cost a
      // request. The previous scene stays exactly as it is.
      setFailure({ key, title: "This selection is incomplete", text: incomplete });
      return;
    }
    setFailure(null);
    setLoading(true);
    try {
      const result = await getView(attempt.kind, viewQuery(attempt) as ViewQuery);
      if (result.scene === null) throw new ApiError(404, `/api/view/${attempt.kind}`, "The server built no scene for this selection.");
      loadedScene.current = result.scene;
      setLoaded({ selection: attempt, key });
      setStoreSpace(result.space === "mni" ? "mni" : "subject");
      loadScene(result.scene);
    } catch (error) {
      const notFound = error instanceof ApiError && error.status === 404;
      setFailure({
        key,
        title: notFound ? "Nothing found for this selection" : "Could not build the view",
        text: notFound
          ? "The server has nothing to show for this selection. The scene on screen is the last one that loaded."
          : "GET /api/view could not build a scene for this selection. Check the server logs, or try again. The scene on screen is the last one that loaded.",
      });
    } finally {
      setLoading(false);
    }
  }, [draft, loadScene, setStoreSpace]);

  // A reload disconnects the old channel (clearing the store's `scene`) and the new frame has no
  // scene of its own to ask for, so the loaded scene is re-sent here. Guarded by the token's own
  // previous value so this is a reload handler, not a second load path.
  const lastReloadToken = useRef(reloadToken);
  useEffect(() => {
    if (reloadToken === lastReloadToken.current) return;
    lastReloadToken.current = reloadToken;
    if (loadedScene.current !== null) loadScene(loadedScene.current);
  }, [reloadToken, loadScene]);

  // ---------------------------------------------------------------------------------------------
  // Theme: the embed draws its own chrome, so it has to be told which palette to draw it in.
  //
  // DESIGN.md §10 says engine-drawn chrome is "in the engine's own theme, synchronised from the app
  // theme store". Sent on every `ready` — a reloaded frame boots back at its own default — and on
  // every repaint of the app, whether that came from the theme setting or from the OS changing
  // under `system`.
  // ---------------------------------------------------------------------------------------------
  const [embedTheme, setEmbedThemeValue] = useState(readDocumentTheme);
  useEffect(() => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    const update = (): void => setEmbedThemeValue(readDocumentTheme());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const query = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    query?.addEventListener("change", update);
    update();
    return () => {
      observer.disconnect();
      query?.removeEventListener("change", update);
    };
  }, []);
  useEffect(() => {
    if (embedReady) setEmbedTheme(embedTheme);
  }, [embedReady, embedTheme, setEmbedTheme]);

  // The 3D pane is empty until something that can draw into it is visible. That is a deliberate
  // default — `_grey_mesh_layer` hides 24-420 MB meshes so they are never fetched unasked — but the
  // pane itself says nothing, so a hint drawn over the canvas does.
  const hiddenMesh = hidden3DLayer(layers);

  const embedAvailable = capabilities.data?.tetravox_embed.available !== false;
  const embedVersion = capabilities.data?.tetravox_embed.version ?? null;

  // ---------------------------------------------------------------------------------------------
  // Status bar (DESIGN.md §11): exactly `ras`, `space`, `renderer`, registered only while this page
  // is mounted and only while there is something to say. None of the three exist when the server
  // has no viewer bundle at all — nothing was asked, so there is nothing to report. `space` is the
  // LOADED selection's, never the draft's: it labels the coordinates on screen.
  // ---------------------------------------------------------------------------------------------
  const noWebgl = viewerStatus === "no-webgl2";
  const rendererValue = !embedAvailable || viewerStatus === "no-embed" ? undefined : noWebgl ? "no WebGL2" : renderer ? shortRenderer(renderer) : undefined;
  useStatusCells([
    { id: "ras", label: "RAS", value: embedAvailable ? formatRas(cursor) : undefined, priority: 10, mono: true },
    { id: "space", label: "Space", value: embedAvailable && loaded !== null ? storeSpace : undefined, priority: 20 },
    { id: "renderer", label: "Renderer", value: rendererValue, priority: 30, tone: noWebgl ? "warning" : "default" },
  ]);

  const subjectOptions: SelectOption[] = (subjects.data ?? []).map((s) => ({ value: s.id, label: s.id }));
  const simulationOptions: SelectOption[] = (simulations.data ?? []).map((s) => ({ value: s.name, label: s.name }));
  const analysisOptions: SelectOption[] = (analyses.data ?? []).map((a) => ({ value: a.name, label: a.name }));
  const atlasOptions: SelectOption[] = (atlases.data ?? []).map((a) => ({ value: a.id, label: a.name || a.id }));
  const fieldOptions: SelectOption[] = fields.map((f) => ({ value: f, label: f }));

  /** One labelled selector; `data-testid` is its control id, so a spec names the control, not an index. */
  const selector = (control: ViewerControl, node: React.ReactNode) => (
    <label className="viewer-source-item" data-testid={`viewer-select-${control}`} key={control}>
      <span className="viewer-source-label">{controlLabel(control)}</span>
      {node}
    </label>
  );

  const sourceBar = (
    <div
      className="viewer-sourcebar"
      data-testid="viewer-source-bar"
      data-dirty={dirty ? "true" : "false"}
      data-draft-key={draftKey}
      data-loaded-key={loaded?.key ?? ""}
    >
      <label className="viewer-source-item" data-testid="viewer-select-kind">
        <span className="viewer-source-label">Type</span>
        <Select value={draft.kind} onValueChange={(v) => editDraft({ kind: v as ViewKind })} options={VIEW_KIND_OPTIONS} aria-label="Type" />
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
      <div className="viewer-source-spacer" />
      {shows("space") && (
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
      )}
      <Button size="sm" variant={dirty ? "primary" : "secondary"} onClick={() => void load()} disabled={loading} data-testid="viewer-load">
        {loading ? "Loading…" : "Load"}
      </Button>
      <IconButton icon={<RotateCw size={14} />} aria-label="Reload viewer" title="Reload viewer" size="sm" onClick={handleReload} data-testid="viewer-reload" />
    </div>
  );

  // The failure belongs to the selection that was attempted, and it is a strip above the canvas —
  // not a card instead of it. DESIGN.md §4.4's "failed load" row, corrected by R5: the last good
  // scene keeps the viewport, because throwing it away is the expensive mistake.
  const showFailure = failure !== null && failure.key === draftKey;
  const nothingLoaded = loaded === null;

  return (
    <PageLayout variant="bleed" className="viewer-page">
      <div className="viewer-stage">
        {embedAvailable && sourceBar}
        {embedAvailable && showFailure && (
          <div className="viewer-load-error" role="alert" data-testid="viewer-view-error">
            <span className="viewer-load-error-title">{failure.title}</span>
            <span className="viewer-load-error-text">{failure.text}</span>
            <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
              Retry
            </Button>
          </div>
        )}
        {!embedAvailable ? (
          <div className="viewer-unbundled" data-testid="viewer-not-bundled">
            <div className="viewer-unbundled-body">
              <p className="viewer-unbundled-title">This server has no viewer bundle</p>
              <p className="viewer-unbundled-text">
                {embedVersion
                  ? `GET /api/capabilities reports Tetravox embed ${embedVersion} but no bundle at /tetravox/.`
                  : "GET /api/capabilities reports no Tetravox embed at all."}{" "}
                The image was built without the Tetravox embed; pull or rebuild the image to get the viewer back. Everything else on this server
                works normally.
              </p>
            </div>
          </div>
        ) : (
          <div className="viewer-canvas-wrap">
            <TetravoxFrame embedVersion={embedVersion} reloadToken={reloadToken} onReload={handleReload} />
            {nothingLoaded && !showFailure && (
              <p className="viewer-hint" data-testid="viewer-nothing-loaded">
                Choose what to look at above, then press Load.
              </p>
            )}
            {!nothingLoaded && hiddenMesh !== null && (
              <p className="viewer-hint" data-testid="viewer-3d-hint">
                Enable a mesh layer to populate the 3D pane — {layerName(hiddenMesh)} is hidden.
              </p>
            )}
          </div>
        )}
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "viewer",
  title: "Viewer",
  purpose: "Look at a subject, a simulation or an analysis in the embedded Tetravox viewer.",
  navGroup: "explore",
  order: 60,
  icon: Eye,
  shortcut: "7",
  Component: ViewerPage,
  enabled: true,
  layout: "full-bleed",
  viewer: true,
};

export default page;
