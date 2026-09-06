/**
 * Viewer screen — **a composition panel, not a viewer** (V1 + VM,
 * `dev/notes/v3-native-panes-external-viewer/{VX,VM}.md`).
 *
 * V1's brief, verbatim: *"the viewer tab only acts as the data selection and it actually opens up
 * everything in [an external window] like we have in 2.5.0."* VM's, on seeing what that produced —
 * a 40 px bar over a black rectangle with a ghost list in it: *"make the menu for the visualizer
 * much more extensive and centred — since the viewer opens in its own window, the page can be
 * graceful and let users enjoy an extensive menu experience."*
 *
 * Both are the same fact read twice. The picture belongs to the **Tetravox desktop app**, which is
 * signed, notarised, self-updating and not our problem; what is left here is the *composition* —
 * and a composition deserves a centred panel with room to think in, not a strip of selects over a
 * canvas that will never draw anything.
 *
 * **The rule that decides what this page may offer: every knob has to land in the scene file.**
 * A control whose value the server cannot write is a lie told to the person using it. So the
 * vocabulary is the server's (`tit/viewspec.py::apply_scene_overrides`, `EXTRA_LAYERS`), which is
 * in turn the engine's own ViewSpec v2 type — and the reason there is no electrode-*points*
 * checkbox is that ViewSpec v2 has no points layer. The electrode overlay *volume* exists, so
 * that is what "Also open" offers.
 *
 * **R5's draft → command grammar survives, and now covers the composition too.** Editing anything
 * — a selector, an opacity, a layout — edits the draft. The only request drafting costs is the
 * preview's own `dry_run`, which writes no file and launches nothing. **Open** is the one place a
 * scene file is written and the one place the app is launched: one `POST /api/view/open`, one
 * file, one spawn. Tetravox's single-instance lock routes a second Open into the window already
 * on screen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Clock, Download, ExternalLink, Eye, EyeOff, Save } from "lucide-react";
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
import { Checkbox, Slider } from "../../ui/Toggle";
import { NumberInput } from "../../ui/NumberInput";
import { TextInput } from "../../ui/Field";
import {
  deletePreset,
  getAnalyses,
  getAtlases,
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
  BACKGROUND_OPTIONS,
  CAMERA_OPTIONS,
  COLORMAP_OPTIONS,
  EMPTY_COMPOSITION,
  EXTRA_OPTIONS,
  LAYOUT_OPTIONS,
  controlLabel,
  controlsFor,
  formatBytes,
  hasViewerDeepLink,
  layerKindLabel,
  overridesPayload,
  pushRecent,
  readDeepLink,
  readRecents,
  selectionFromDeepLink,
  selectionKey,
  selectionLabel,
  validateSelection,
  viewQuery,
  type CameraPreset,
  type Composition,
  type LayerOverride,
  type SceneBackground,
  type SceneLayer,
  type SceneLayout,
  type ViewerControl,
  type ViewerExtra,
  type ViewerRecent,
  type ViewerSelection,
} from "./lib";
import { useTetravox } from "../_shared/viewer/useTetravox";
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

const COLORMAP_SELECT: SelectOption[] = COLORMAP_OPTIONS.map((c) => ({ value: c, label: c }));

/** What a failed (or refused) Open left behind, tied to the selection that was attempted. */
interface ViewerFailure {
  key: string;
  title: string;
  text: string;
}

/**
 * One section of the panel: an eyebrow title, one line saying what the section decides, a body.
 *
 * The one line is not decoration. This page is a menu a person meets once and then uses fast, and
 * a section whose heading is a noun with no verb ("Layers") makes them open it to find out what it
 * does. Saying it costs 16 px and is read once.
 */
function Section({
  id,
  title,
  description,
  actions,
  children,
}: {
  id: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="viewer-section" data-testid={`viewer-section-${id}`}>
      <div className="viewer-section-head">
        <div className="viewer-section-heading">
          <h2 className="viewer-section-title text-eyebrow">{title}</h2>
          <p className="viewer-section-desc">{description}</p>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

/** A label-left row, the density the rest of the app is tuned to (DESIGN.md §3). */
function Row({ label, htmlFor, testId, children }: { label: string; htmlFor?: string; testId?: string; children: React.ReactNode }) {
  return (
    <div className="viewer-row" data-testid={testId}>
      <label className="viewer-row-label" htmlFor={htmlFor}>
        {label}
      </label>
      <div className="viewer-row-control">{children}</div>
    </div>
  );
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
  // The draft: the selection, the extras and the composition. Every control below writes here and
  // does nothing else.
  // ---------------------------------------------------------------------------------------------
  const [draft, setDraft] = usePageSession<ViewerSelection>("selection", () =>
    selectionFromDeepLink(deepLink, { kind: "subject", subject: subjectId ?? undefined, space: "subject" }),
  );
  const [extras, setExtras] = usePageSession<ViewerExtra[]>("extras", () => []);
  const [composition, setComposition] = usePageSession<Composition>("composition", () => EMPTY_COMPOSITION);

  const editDraft = useCallback(
    (patch: Partial<ViewerSelection>) => setDraft((current) => ({ ...current, ...patch })),
    [setDraft],
  );
  const editComposition = useCallback(
    (patch: Partial<Composition>) => setComposition((current) => ({ ...current, ...patch })),
    [setComposition],
  );
  const editLayer = useCallback(
    (id: string, patch: LayerOverride) =>
      setComposition((current) => ({ ...current, layers: { ...current.layers, [id]: { ...current.layers[id], ...patch } } })),
    [setComposition],
  );

  // A later deep link (Results → "Open in viewer") re-prefills the draft. It still does not open.
  const linkCarriesControls = hasViewerDeepLink(deepLink);
  useEffect(() => {
    if (!active || !linkCarriesControls || location.state?.[SUBJECT_SYNC_STATE]) return;
    setDraft((current) => selectionFromDeepLink(deepLink, current));
  }, [active, location.key, location.state, deepLink, linkCarriesControls, setDraft]);

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
  const fields = selectedSimulation?.fields ?? [];
  const tetravox = useTetravox();

  // ---------------------------------------------------------------------------------------------
  // The resolution: what this selection *is*, from the endpoint that would open it, in dry-run.
  //
  // Deliberately the same route Open uses. A preview built by different code from the thing it
  // previews is a preview that can be wrong, and the one moment this page must not be wrong is the
  // moment before another application's window covers someone's work.
  //
  // The overrides are **not** sent here: the layer rows are built from the *unedited* scene and
  // the edits are held locally, so dragging an opacity slider costs no request and cannot make the
  // list it is editing re-resolve underneath the hand doing the dragging.
  // ---------------------------------------------------------------------------------------------
  const draftKey = selectionKey(draft);
  const extrasKey = [...extras].sort().join(",");
  const complete = validateSelection(draft) === null;
  const resolution = useQuery({
    queryKey: ["viewer-resolution", draftKey, extrasKey],
    queryFn: () => previewView(draft.kind, viewQuery(draft) as ViewQuery, extras),
    enabled: complete,
    retry: false,
  });

  const scene = resolution.data?.scene as { layers?: SceneLayer[] } | undefined;
  const sceneLayers = useMemo<SceneLayer[]>(() => scene?.layers ?? [], [scene]);
  const files = resolution.data?.files ?? [];

  // A different resolution is a different set of layer ids, so the edits held against the old ones
  // are meaningless — kept, they would silently apply to whatever layer inherited the id.
  const resolutionKey = `${draftKey}|${extrasKey}`;
  const lastResolution = useRef(resolutionKey);
  useEffect(() => {
    if (lastResolution.current === resolutionKey) return;
    lastResolution.current = resolutionKey;
    setComposition((current) => ({ ...current, layers: {} }));
  }, [resolutionKey, setComposition]);

  /** A layer's value as the scene will carry it: the local edit if there is one, else the server's. */
  const layerValue = useCallback(
    <K extends keyof SceneLayer & keyof LayerOverride>(layer: SceneLayer, key: K): SceneLayer[K] => {
      const patch = composition.layers[layer.id];
      const edited = patch?.[key as keyof LayerOverride];
      return (edited === undefined ? layer[key] : edited) as SceneLayer[K];
    },
    [composition.layers],
  );

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
      // request, let alone a window.
      setFailure({ key, title: "This selection is incomplete", text: incomplete });
      return;
    }
    setFailure(null);
    setBusy(true);
    try {
      const written = await openView(attempt.kind, viewQuery(attempt) as ViewQuery, {
        extras,
        overrides: overridesPayload(composition) as Record<string, unknown> | undefined,
      });
      setRecents(pushRecent({ key: `${key}|${extrasKey}`, label: selectionLabel(attempt), selection: attempt, extras, overrides: composition }));
      if (tetravox.mode === "browser") {
        // No main process to spawn anything: hand the person the file. `written.scene` is the
        // exact bytes the server put on disk, so the download and the file are the same document.
        const blob = new Blob([JSON.stringify(written.scene, null, 1)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = written.name;
        anchor.click();
        URL.revokeObjectURL(url);
        setOpened({ key, hostPath: written.host_path, name: written.name });
        return;
      }
      const launched = await tetravox.open(written.path);
      if (!launched.ok) {
        setFailure({ key, title: "Could not open Tetravox", text: launched.reason });
        return;
      }
      setOpened({ key, hostPath: written.host_path, name: written.name });
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
  }, [composition, draft, extras, extrasKey, tetravox]);

  // ---------------------------------------------------------------------------------------------
  // Presets and recents. A preset is a composition someone chose to keep, and it lives in the
  // project (`code/ti-toolbox/viewer/presets/`) because the project is the unit people copy and
  // share. A recent is a footprint, and lives in this machine's browser storage, where losing it
  // costs nothing.
  // ---------------------------------------------------------------------------------------------
  const presets = useQuery({ queryKey: ["viewer-presets"], queryFn: () => getPresets(), retry: false });
  const [presetName, setPresetName] = useState("");
  const [presetOpen, setPresetOpen] = useState(false);
  const saving = useMutation({
    mutationFn: (name: string) =>
      savePreset({
        name,
        selection: draft as unknown as Record<string, never>,
        extras,
        overrides: composition as unknown as Record<string, never>,
      }),
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
    (entry: { selection?: unknown; extras?: unknown; overrides?: unknown }) => {
      if (entry.selection) setDraft(entry.selection as ViewerSelection);
      setExtras(Array.isArray(entry.extras) ? (entry.extras as ViewerExtra[]) : []);
      const overrides = (entry.overrides as Composition | undefined) ?? EMPTY_COMPOSITION;
      setComposition({ ...EMPTY_COMPOSITION, ...overrides, layers: overrides.layers ?? {} });
      // Restoring is not opening. The panel fills in; the person presses Open when they mean it.
      lastResolution.current = `${selectionKey(entry.selection as ViewerSelection)}|${[...((entry.extras as string[]) ?? [])].sort().join(",")}`;
    },
    [setComposition, setDraft, setExtras],
  );

  // ---------------------------------------------------------------------------------------------
  // Options
  // ---------------------------------------------------------------------------------------------
  const subjectOptions: SelectOption[] = (subjects.data ?? []).map((s) => ({ value: s.id, label: s.id }));
  const simulationOptions: SelectOption[] = (simulations.data ?? []).map((s) => ({ value: s.name, label: s.name }));
  const analysisOptions: SelectOption[] = (analyses.data ?? []).map((a) => ({ value: a.name, label: a.name }));
  const atlasOptions: SelectOption[] = (atlases.data ?? []).map((a) => ({ value: a.id, label: a.name || a.id }));
  const fieldOptions: SelectOption[] = fields.map((f) => ({ value: f, label: f }));

  const selector = (control: ViewerControl, node: React.ReactNode) => (
    <label className="viewer-source-item viewer-row" data-testid={`viewer-select-${control}`} key={control}>
      <span className="viewer-row-label viewer-source-label">{controlLabel(control)}</span>
      <span className="viewer-row-control">{node}</span>
    </label>
  );

  const canOpen = tetravox.mode === "browser" || tetravox.info?.available === true;
  const showFailure = failure !== null && failure.key === draftKey;
  const openLabel = tetravox.mode === "browser" ? "Download scene" : "Open in Tetravox";
  const openTitle = !canOpen
    ? "Tetravox is not installed on this computer"
    : !complete
      ? (validateSelection(draft) ?? undefined)
      : undefined;

  // ---------------------------------------------------------------------------------------------
  // The panel
  // ---------------------------------------------------------------------------------------------
  return (
    <PageLayout variant="bleed" className="viewer-page">
      <div className="viewer-scroll">
        <div className="viewer-panel" data-testid="viewer-panel">
          <header className="viewer-panel-head">
            <h1 className="viewer-panel-title">Compose a scene</h1>
            <p className="viewer-panel-lede">
              Pick what to look at and how it should look; <strong>Open</strong> writes the scene and hands it to the Tetravox desktop app,
              which draws it in its own window.
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

          {!canOpen && (
            <div className="viewer-callout" data-testid="viewer-not-installed">
              <p className="viewer-callout-title">Tetravox is not installed on this computer</p>
              <p className="viewer-callout-text">
                The viewer is a separate desktop application. Install it once and this panel opens every scene you compose here; it updates
                itself from then on.
              </p>
              <Button
                variant="primary"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => void window.tit?.openExternal(tetravox.info?.downloadUrl ?? "https://github.com/idossha/tetravox/releases/latest")}
                data-testid="viewer-download-tetravox"
              >
                Download Tetravox
              </Button>
            </div>
          )}

          {/* ── Source ─────────────────────────────────────────────────────────────────────── */}
          <Section id="source" title="Source" description="What the scene is built from. The type decides which of the fields below it needs.">
            <div
              className="viewer-source-grid"
              data-testid="viewer-source-bar"
              data-dirty={opened === null || opened.key !== draftKey ? "true" : "false"}
              data-draft-key={draftKey}
              data-opened-key={opened?.key ?? ""}
            >
              <label className="viewer-source-item viewer-row" data-testid="viewer-select-kind">
                <span className="viewer-row-label viewer-source-label">Type</span>
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
                <Row label="Space">
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
                </Row>
              )}
            </div>
          </Section>

          {/* ── Layers ─────────────────────────────────────────────────────────────────────── */}
          <Section
            id="layers"
            title="Layers"
            description="The layers this selection resolves to, with the server's own defaults. Anything changed here is written into the scene."
            actions={
              Object.keys(composition.layers).length > 0 ? (
                <Button variant="ghost" size="sm" onClick={() => editComposition({ layers: {} })} data-testid="viewer-layers-reset">
                  Reset
                </Button>
              ) : undefined
            }
          >
            {!complete ? (
              <p className="viewer-empty" data-testid="viewer-nothing-selected">
                Choose a source above and the layers it resolves to appear here.
              </p>
            ) : resolution.isPending ? (
              <p className="viewer-empty">Resolving…</p>
            ) : sceneLayers.length === 0 ? (
              <p className="viewer-empty">The server found no files for this selection.</p>
            ) : (
              <ul className="viewer-layers" data-testid="viewer-layers">
                {sceneLayers.map((layer) => {
                  const visible = layerValue(layer, "visible") as boolean;
                  const opacity = layerValue(layer, "opacity") as number;
                  const isMesh = layer.kind === "mesh";
                  const threshold = composition.layers[layer.id]?.threshold ?? layer.threshold ?? { lo: null, hi: null };
                  const clipEnabled = composition.layers[layer.id]?.clip ?? layer.clip?.planes?.[0]?.enabled ?? false;
                  return (
                    <li className="viewer-layer" key={layer.id} data-testid={`viewer-layer-${layer.id}`} data-visible={visible ? "true" : "false"}>
                      <div className="viewer-layer-head">
                        <button
                          type="button"
                          className="viewer-layer-eye"
                          aria-label={`${visible ? "Hide" : "Show"} ${layer.name}`}
                          aria-pressed={visible}
                          data-testid={`viewer-layer-visible-${layer.id}`}
                          onClick={() => editLayer(layer.id, { visible: !visible })}
                        >
                          {visible ? <Eye size={14} /> : <EyeOff size={14} />}
                        </button>
                        <span className="viewer-layer-name" title={layer.name}>
                          {layer.name}
                        </span>
                        <span className="viewer-layer-kind">{layerKindLabel(layer)}</span>
                      </div>
                      <div className="viewer-layer-controls">
                        <Row label="Opacity">
                          <Slider
                            value={Math.round(opacity * 100)}
                            onValueChange={(v) => editLayer(layer.id, { opacity: v / 100 })}
                            min={0}
                            max={100}
                            step={1}
                            unit="%"
                            aria-label={`${layer.name} opacity`}
                            data-testid={`viewer-layer-opacity-${layer.id}`}
                          />
                        </Row>
                        {!isMesh && (
                          <Row label="Colormap">
                            <Select
                              value={layerValue(layer, "colormap") as string}
                              onValueChange={(v) => editLayer(layer.id, { colormap: v })}
                              options={COLORMAP_SELECT}
                              aria-label={`${layer.name} colormap`}
                            />
                          </Row>
                        )}
                        <Row label="Threshold" testId={`viewer-layer-threshold-${layer.id}`}>
                          <div className="viewer-threshold">
                            <NumberInput
                              value={threshold.lo ?? undefined}
                              onValueChange={(v) => editLayer(layer.id, { threshold: { ...threshold, lo: v ?? null } })}
                              placeholder="lo"
                              aria-label={`${layer.name} threshold low`}
                            />
                            <NumberInput
                              value={threshold.hi ?? undefined}
                              onValueChange={(v) => editLayer(layer.id, { threshold: { ...threshold, hi: v ?? null } })}
                              placeholder="hi"
                              aria-label={`${layer.name} threshold high`}
                            />
                          </div>
                        </Row>
                        {isMesh ? (
                          <>
                            <Row label="Colour by">
                              <Select
                                value={(layerValue(layer, "colorMode") as string) ?? "solid"}
                                onValueChange={(v) => editLayer(layer.id, { colorMode: v })}
                                options={[
                                  { value: "field", label: "Field on the surface" },
                                  { value: "tag", label: "Tissue tag" },
                                  { value: "solid", label: "One colour" },
                                ]}
                                aria-label={`${layer.name} colour mode`}
                              />
                            </Row>
                            <Row label="Clip plane">
                              <Checkbox
                                checked={clipEnabled}
                                onCheckedChange={(v) => editLayer(layer.id, { clip: v })}
                                label="Cut the surface at the cursor"
                                aria-label={`${layer.name} clip plane`}
                              />
                            </Row>
                          </>
                        ) : (
                          <Row label="In 3D">
                            <Checkbox
                              checked={(layerValue(layer, "showIn3D") as boolean) ?? false}
                              onCheckedChange={(v) => editLayer(layer.id, { showIn3D: v })}
                              label="Render this volume in the 3D pane"
                              aria-label={`${layer.name} in 3D`}
                            />
                          </Row>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          {/* ── Layout & camera ────────────────────────────────────────────────────────────── */}
          <Section id="layout" title="Layout &amp; camera" description="How the window is divided, where the 3D camera starts, and which way is left.">
            <Row label="Panes" testId="viewer-layout">
              <SegmentedControl<SceneLayout>
                aria-label="Panes"
                size="sm"
                value={composition.layout ?? ((scene as { layout?: { kind?: SceneLayout } } | undefined)?.layout?.kind ?? "2x2")}
                onValueChange={(v) => editComposition({ layout: v })}
                options={LAYOUT_OPTIONS}
              />
            </Row>
            <Row label="Camera" testId="viewer-camera">
              <SegmentedControl<CameraPreset>
                aria-label="Camera"
                size="sm"
                value={composition.camera ?? "A"}
                onValueChange={(v) => editComposition({ camera: v })}
                options={CAMERA_OPTIONS}
              />
            </Row>
            <Row label="Background" testId="viewer-background">
              <SegmentedControl<SceneBackground>
                aria-label="Background"
                size="sm"
                value={composition.background ?? "dark"}
                onValueChange={(v) => editComposition({ background: v })}
                options={BACKGROUND_OPTIONS}
              />
            </Row>
            <Row label="Convention" testId="viewer-radiological">
              <Checkbox
                checked={composition.radiological ?? false}
                onCheckedChange={(v) => editComposition({ radiological: v })}
                label="Radiological (the subject's left on screen right)"
                aria-label="Radiological convention"
              />
            </Row>
          </Section>

          {/* ── Also open ──────────────────────────────────────────────────────────────────── */}
          <Section
            id="extras"
            title="Also open"
            description="Extra files to add to the scene. One this source already opens is a no-op, so a tick is safe to leave on."
          >
            <div className="viewer-extras">
              {EXTRA_OPTIONS.map((extra) => {
                const unavailable = extra.needs === "simulation" && !draft.simulation;
                return (
                  <div className="viewer-extra" key={extra.value} data-testid={`viewer-extra-${extra.value}`}>
                    <Checkbox
                      checked={extras.includes(extra.value)}
                      disabled={unavailable}
                      onCheckedChange={(v) => setExtras((current) => (v ? [...current, extra.value] : current.filter((e) => e !== extra.value)))}
                      label={extra.label}
                      aria-label={extra.label}
                    />
                    <p className="viewer-extra-help">{unavailable ? "Needs a simulation." : extra.help}</p>
                  </div>
                );
              })}
            </div>
          </Section>

          {/* ── The preview card ───────────────────────────────────────────────────────────── */}
          <div className="viewer-preview" data-testid="viewer-plan">
            <div className="viewer-preview-head">
              <span className="viewer-preview-title text-eyebrow">What will open</span>
              <span className="viewer-preview-count">{files.length === 0 ? "nothing yet" : `${files.length} file${files.length === 1 ? "" : "s"}`}</span>
            </div>
            {files.length === 0 ? (
              <p className="viewer-empty">
                {complete ? "The server found no files for this selection." : `Choose a source, then press ${openLabel}.`}
              </p>
            ) : (
              <ul className="viewer-preview-files" data-testid="viewer-preview-files">
                {files.map((file) => (
                  <li className="viewer-preview-file" key={file.path} title={file.path}>
                    <span className="viewer-preview-file-name">{file.name}</span>
                    <span className="viewer-preview-file-kind">{file.kind}</span>
                    <span className="viewer-preview-file-size">{formatBytes(file.bytes)}</span>
                  </li>
                ))}
              </ul>
            )}
            {opened !== null && (
              <p className="viewer-preview-opened" data-testid="viewer-opened">
                {tetravox.mode === "browser"
                  ? `Downloaded ${opened.name}. Open it in Tetravox (File ▸ Open Scene…).`
                  : `Opened ${opened.name}${opened.hostPath ? ` — ${opened.hostPath}` : ""}`}
              </p>
            )}
          </div>

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
                <p className="viewer-popover-title">Save this composition</p>
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
              icon={tetravox.mode === "browser" ? <Download size={14} /> : <ExternalLink size={14} />}
            >
              {busy ? "Opening…" : openLabel}
            </Button>
          </footer>
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "viewer",
  title: "Viewer",
  purpose: "Compose a scene from a subject, a simulation or an analysis and open it in the Tetravox desktop app.",
  navGroup: "explore",
  order: 60,
  icon: Eye,
  shortcut: "7",
  Component: ViewerPage,
  enabled: true,
  layout: "full-bleed",
};

export default page;
