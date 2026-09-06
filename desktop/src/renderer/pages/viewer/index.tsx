/**
 * Viewer screen — **a data selector, not a viewer** (V1,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * The maintainer's brief, verbatim: *"for the viewer, instead of embedding the web version of
 * Tetravox … the viewer tab only acts as the data selection and it actually opens up everything in
 * [an external window] like we have in 2.5.0."*
 *
 * So this page picks what to look at, says what would open, and opens it — in the **host-installed
 * Tetravox desktop app**, which is signed, notarised, auto-updating and not our problem. Nothing
 * here draws pixels and nothing here is an `<iframe>`. That is the whole point: the app that draws
 * the picture is a real application with its own window, its own file menu, its own release
 * cadence and its own bug tracker, and the coupling this page used to carry — an embed bundle
 * baked into the image, a protocol version, a runtime installer, an update channel and a toast —
 * is gone with it.
 *
 * **R5's draft → Load grammar survives unchanged**, because it was never about the embed. There
 * are two selections: `draft` (what the source bar shows) and `opened` (what was last handed to
 * Tetravox). Editing any selector edits the draft and nothing else — no request, no launch. The
 * command is now **Open in Tetravox**: it validates the draft, asks the server to write the scene
 * file for it (`POST /api/view/open`), and hands that one file to the Electron shell, which
 * spawns the app. A second Open is a second spawn; Tetravox's own single-instance handling
 * (verified in its repo at 0.3.11) routes it into the window already on screen rather than
 * opening a second one.
 *
 * **Browser mode** (the same bundle in a normal browser, no `window.tit`) cannot start an
 * application, so Open downloads the scene file and says to open it in Tetravox. That is a
 * complete answer, not a degraded one: the file is the interface.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Download, ExternalLink, Eye } from "lucide-react";
import { ApiError, getSubjects } from "../../api/client";
import type { PageDef } from "../../app/registry";
import { usePageSession } from "../../app/pageSession";
import { usePageActive } from "../../app/pageActivity";
import { SUBJECT_SYNC_STATE } from "../../app/subjectSpine";
import { useSubjectContext } from "../../app/subjectContext";
import { Button } from "../../ui/Button";
import { PageLayout } from "../../ui/Layout";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Select, type SelectOption } from "../../ui/Select";
import { getAnalyses, getAtlases, getSimulationsFor, getView, openView, type Space, type ViewKind, type ViewQuery } from "./api";
import {
  controlLabel,
  controlsFor,
  hasViewerDeepLink,
  readDeepLink,
  selectionFromDeepLink,
  selectionKey,
  validateSelection,
  viewQuery,
  type ViewerControl,
  type ViewerSelection,
} from "./lib";
import { useTetravox } from "../_shared/viewer/useTetravox";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import "./viewer-page.css";

export { readDeepLink } from "./lib";
export type { ViewerDeepLink, ViewerSelection } from "./lib";

const VIEW_KIND_OPTIONS: SelectOption[] = [
  { value: "subject", label: "Subject" },
  { value: "simulation", label: "Simulation" },
  { value: "analysis", label: "Analysis" },
  { value: "group", label: "Group" },
  { value: "custom", label: "Custom file" },
];

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

  // A later deep link (Results → "Open in viewer") re-prefills the draft. It still does not open:
  // the controls change, nothing launches, and the person presses Open when they mean it.
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
  // Menus. These are catalog reads: they populate options and never open anything.
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
  // "What will open": the layer list the server would build for this draft. A read, not a launch —
  // it is the one thing a selector page owes a person before they commit to a window opening on
  // top of their work. Debounced by react-query's own key, and a failure here is silent: it is a
  // preview, and an empty preview is not an error to shout about.
  // ---------------------------------------------------------------------------------------------
  const draftKey = selectionKey(draft);
  const complete = validateSelection(draft) === null;
  const summary = useQuery({
    queryKey: ["viewer-summary", draftKey],
    queryFn: () => getView(draft.kind, viewQuery(draft) as ViewQuery),
    enabled: complete,
    retry: false,
  });

  // ---------------------------------------------------------------------------------------------
  // Open: the one place a scene file is written and the one place the app is launched.
  // ---------------------------------------------------------------------------------------------
  const [opened, setOpened] = useState<{ key: string; hostPath: string | null; name: string } | null>(null);
  const [failure, setFailure] = useState<ViewerFailure | null>(null);
  const [busy, setBusy] = useState(false);

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
      const written = await openView(attempt.kind, viewQuery(attempt) as ViewQuery);
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
  }, [draft, tetravox]);

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

  const canOpen = tetravox.mode === "browser" || tetravox.info?.available === true;

  const sourceBar = (
    <div
      className="viewer-sourcebar"
      data-testid="viewer-source-bar"
      data-dirty={opened === null || opened.key !== draftKey ? "true" : "false"}
      data-draft-key={draftKey}
      data-opened-key={opened?.key ?? ""}
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
      <Button
        size="sm"
        variant="primary"
        onClick={() => void open()}
        disabled={busy || !canOpen}
        data-testid="viewer-open"
        icon={tetravox.mode === "browser" ? <Download size={14} /> : <ExternalLink size={14} />}
      >
        {busy ? "Opening…" : tetravox.mode === "browser" ? "Download scene" : "Open in Tetravox"}
      </Button>
    </div>
  );

  const showFailure = failure !== null && failure.key === draftKey;
  const layers = summary.data?.layers ?? [];

  return (
    <PageLayout variant="bleed" className="viewer-page">
      <div className="viewer-stage">
        {sourceBar}
        {showFailure && (
          <div className="viewer-load-error" role="alert" data-testid="viewer-view-error">
            <span className="viewer-load-error-title">{failure.title}</span>
            <span className="viewer-load-error-text">{failure.text}</span>
            <Button variant="secondary" size="sm" onClick={() => void open()} disabled={busy}>
              Retry
            </Button>
          </div>
        )}

        {/* "What will open" — the page's whole body. No canvas, no iframe: the picture is in
            another application's window, and pretending otherwise here is what V1 removes. */}
        <div className="viewer-plan" data-testid="viewer-plan">
          {!canOpen ? (
            <div className="viewer-plan-empty" data-testid="viewer-not-installed">
              <p className="viewer-plan-title">Tetravox is not installed on this computer</p>
              <p className="viewer-plan-text">
                The viewer is a separate desktop application. Install it once and this button opens every scene you build here; it updates
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
          ) : !complete ? (
            <p className="viewer-plan-hint" data-testid="viewer-nothing-selected">
              Choose what to look at above, then press {tetravox.mode === "browser" ? "Download scene" : "Open in Tetravox"}.
            </p>
          ) : (
            <div className="viewer-plan-body">
              <p className="viewer-plan-title">What will open</p>
              <ul className="viewer-plan-layers" data-testid="viewer-plan-layers">
                {layers.map((layer) => (
                  <li key={layer.path} className="viewer-plan-layer" title={layer.path}>
                    <span className="viewer-plan-layer-name">{layer.path.split("/").pop()}</span>
                    <span className="viewer-plan-layer-meta">{layer.colormap ?? "grayscale"}</span>
                  </li>
                ))}
                {layers.length === 0 && <li className="viewer-plan-layer-meta">Nothing yet — the server found no files for this selection.</li>}
              </ul>
              {opened !== null && (
                <p className="viewer-plan-text" data-testid="viewer-opened">
                  {tetravox.mode === "browser"
                    ? `Downloaded ${opened.name}. Open it in Tetravox (File ▸ Open Scene…).`
                    : `Opened ${opened.name}${opened.hostPath ? ` — ${opened.hostPath}` : ""}`}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "viewer",
  title: "Viewer",
  purpose: "Pick a subject, a simulation or an analysis and open it in the Tetravox desktop app.",
  navGroup: "explore",
  order: 60,
  icon: Eye,
  shortcut: "7",
  Component: ViewerPage,
  enabled: true,
  layout: "full-bleed",
};

export default page;
