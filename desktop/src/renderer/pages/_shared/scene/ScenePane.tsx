/**
 * `<ScenePane mode="montage" | "target" | "inspect">` — the scene as a **form control** on the
 * three run pages (`dev/notes/v3-native-panes-external-viewer-plan.md`, N1–N4).
 *
 * `renderer/scene/` draws — our own WebGL2, no runtime dependency, no iframe, no protocol. This
 * file is everything between that renderer and a page's form: it fetches the packaged guide over
 * `/api/guide/*`, decodes TVSC1, and keeps the selection synchronised **in both directions**:
 *
 * | mode      | page      | a pick means                                      | the form writes back |
 * |-----------|-----------|---------------------------------------------------|----------------------|
 * | `montage` | Simulator | toggle that electrode into the active pair slot   | editing a pair re-colours its dots |
 * | `target`  | Optimizer | add/remove that atlas region from the ROI         | the ROI picker's region list IS the pane's selection |
 * | `inspect` | Analyzer  | add/remove that atlas region from the analysis ROI | the analysis ROI is drawn where it will be measured |
 *
 * Four rules, each with the failure it prevents:
 *
 *  - **The pane never holds the selection.** `pairs` and `regions` are the page's state; a pick
 *    calls the page's writer and the new value comes back down through the same `toggleRegion` the
 *    form's own chips call. A pane with its own copy is a pane that can disagree with the form.
 *  - **What it draws is the fixed guide, never the selected subject.** No query is keyed on a
 *    subject, so ticking a second subject costs zero requests and zero remounts, and a pane on a
 *    project whose head models do not exist yet still shows anatomy. Its space is `guide-ras`: the
 *    pane names electrodes, nets and regions, and **never produces a coordinate**.
 *  - **An electrode's colour is its whole state** — neutral grey in no channel, its channel's
 *    Okabe-Ito hue when placed. No ring, no outline, no second glyph.
 *  - **Every failure is a sentence, not an error box** — the server's own `detail` verbatim, and a
 *    page that still works without the pane.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SCENE_DEBUG,
  SceneCanvas,
  type Bounds,
  type LegendEntry,
  type PickTarget,
  type ScenePart,
  type SceneSelection,
} from "../../../scene";
import { Skeleton } from "../../../ui/Feedback";
import { Button } from "../../../ui/Button";
import { Select } from "../../../ui/Select";
import { ChannelLegend } from "../../../ui/ChannelLegend";
import { SceneError, type SceneLegendRow } from "./api";
import {
  DEFAULT_OPACITY,
  SCENE_PALETTE,
  applyElectrodePick,
  channelByElectrode,
  firstEmptySlot,
  markerIndicesFor,
  markersFromElectrodes,
  placedElectrodes,
  regionsFromWireLabels,
  slotLabel,
  toggleRegion,
  wireLabelsFor,
  type Pair,
  type SceneMarker,
  type SceneRegionRef,
} from "./model";
import {
  useGuideElectrodes,
  useGuideLabels,
  useGuideManifest,
  useGuideRegions,
  useGuideSurfaceRequests,
  useGuideSurfaces,
} from "./queries";
import "./scene-pane.css";

export type ScenePaneMode = "montage" | "target" | "inspect";

/** What a click does. Derived from the mode and from which writer the page supplied — one gesture
 *  is live at a time, so the pane can always say in one phrase what a click will do. */
export type SceneGesture = "electrode" | "region" | "none";

export interface ScenePaneProps {
  mode: ScenePaneMode;
  /*
   * There is deliberately no `subject`, `unavailable`, `sphere` or `onSphereChange` prop: the pane
   * draws the fixed guide, so nothing here is keyed on a subject, and a sphere centre is a
   * subject-RAS coordinate that `guide-ras` millimetres are in no position to produce.
   */
  /** `montage`: the EEG net file name the manifest lists (`"EEG10-10_UI_Jurak_2007.csv"`). */
  net?: string | null;
  /** `target`/`inspect`: the cortical atlas id (`"DK40"`). Omitted, the pane picks the guide's
   *  first packaged atlas and its own selector chooses from there. */
  atlas?: string | null;
  /** Called when the user changes the atlas in the pane's own selector, so the form follows. When
   *  it is absent the selector still works and the choice stays local to the pane. */
  onAtlasChange?: (atlas: string) => void;
  /** `montage`: the pairs being edited. */
  pairs?: Pair[];
  onPairsChange?: (pairs: Pair[]) => void;
  /** Called when a pick arrives and the page has no montage draft open yet; the page opens one. */
  onRequestPairs?: (firstElectrode: string) => void;
  /** `target`/`inspect`: the form's region list. The same array `<RoiPicker>` holds. */
  regions?: SceneRegionRef[];
  onRegionsChange?: (regions: SceneRegionRef[]) => void;
  /** A page-supplied sentence for a target the pane cannot draw (subcortical, a saved ROI CSV). */
  note?: string;
  /**
   * What the pane is drawing, when the page can name it: the montage row the user picked in the
   * Simulator's table. Rendered as an accent chip above the stage in exactly the tokens that tint
   * that row, so "the highlighted row" and "what the pane shows" are visibly one claim.
   */
  showing?: { montage: string; net: string } | null;
  className?: string;
}

/** Everything the offscreen specs read. Stripped from production unless the scene hooks flag is on. */
export interface ScenePaneDebug {
  mode: ScenePaneMode;
  gesture: SceneGesture;
  /** Always `null`: the pane draws no research subject. Kept so the specs' shape does not churn. */
  subject: string | null;
  net: string | null;
  atlas: string | null;
  state: "loading" | "ready" | "error";
  /** The guide the pane drew, e.g. `"ernie"` — never a research subject id. */
  guide: string | null;
  /** The guide manifest's own coordinate space. Always `"guide-ras"`; never `"subject-ras"`. */
  space: string | null;
  message: string | null;
  parts: { id: string; triangles: number; vertices: number; labelled: boolean }[];
  markers: number;
  regions: number;
  selection: SceneSelection;
  /** The form-shaped regions currently selected — what a spec compares against `RoiPicker`'s chips. */
  selectedRegions: SceneRegionRef[];
  /** The region under the cursor, by name, or `null`. */
  hovered: string | null;
  /** Milliseconds from the pane having a guide to the first frame the renderer drew. */
  firstPaintMs: number | null;
  /** The whole legend, so a spec can map a wire label back to its region without a second fetch. */
  legend: SceneLegendRow[];
}

declare global {
  interface Window {
    __scenePane?: ScenePaneDebug;
  }
}

const NO_PARTS: ScenePart[] = [];
const NO_MARKERS: SceneMarker[] = [];

/**
 * The renderer's rule set for a gesture (`scene/selection.ts::MODE_RULES`).
 *
 * Deliberately not the pane's own `mode`: the pane's mode says which page it is on, the canvas's
 * says what is pickable. The Analyzer is `inspect` and still picks regions, so it maps to
 * `target`.
 */
const CANVAS_MODE: Record<SceneGesture, "montage" | "target" | "inspect"> = {
  electrode: "montage",
  region: "target",
  none: "inspect",
};

export function ScenePane({
  mode,
  net = null,
  atlas = null,
  onAtlasChange,
  pairs,
  onPairsChange,
  onRequestPairs,
  regions,
  onRegionsChange,
  note,
  showing = null,
  className,
}: ScenePaneProps) {
  const gesture: SceneGesture = mode === "montage" ? "electrode" : onRegionsChange ? "region" : "none";

  const manifest = useGuideManifest();
  const manifestData = manifest.data;
  const guideId = manifestData?.guide?.id ?? null;

  /**
   * The atlas the pane draws. Always one in `target`/`inspect`, even when the form has no atlas of
   * its own: the guide's atlas payloads are packaged and immutable, so cortical context costs one
   * cached request, and a pane showing plain grey cortex until the user picks an atlas was the
   * state most of these pages open in.
   */
  const wantsRegions = mode !== "montage";
  const [localAtlas, setLocalAtlas] = useState<string | null>(null);
  const effectiveAtlas = wantsRegions ? (atlas ?? localAtlas ?? manifestData?.atlases[0]?.id ?? null) : null;
  const chooseAtlas = useCallback(
    (next: string) => {
      setLocalAtlas(next);
      onAtlasChange?.(next);
    },
    [onAtlasChange],
  );

  const surfaceRequests = useGuideSurfaceRequests(manifestData);
  const surfaces = useGuideSurfaces(surfaceRequests);

  /** Only a net the MANIFEST lists is fetched; a catalog net the guide does not have is a note,
   *  not an error — the montage still works perfectly well from the form. */
  const netListed = mode === "montage" && !!net && (manifestData?.nets.some((entry) => entry.name === net) ?? false);
  const netMissing = mode === "montage" && !!net && !!manifestData && !netListed;
  const electrodes = useGuideElectrodes(netListed ? net : null);
  const regionsQuery = useGuideRegions(effectiveAtlas);
  const legend = useMemo<SceneLegendRow[]>(
    () => (regionsQuery.data ? (regionsQuery.data.legend as SceneLegendRow[]) : []),
    [regionsQuery.data],
  );
  const labels = useGuideLabels(effectiveAtlas, legend.length > 0);

  // ---- geometry ------------------------------------------------------------------------------
  /**
   * The decoded payloads, pulled out of the query array by hand.
   *
   * `useQueries` returns a NEW array every render, so a `useMemo` listing it as a dependency
   * recomputes every render — and `parts` is `SceneCanvas`'s upload trigger. Measured once
   * already: that pair is an infinite render loop that re-uploads 145 k triangles per frame and
   * starves every `setTimeout` on the page. React Query hands back the same `data` object while it
   * is cached, so these three references are the honest dependencies.
   */
  const skinData = surfaces[surfaceRequests.findIndex((part) => part.id === "skin")]?.data ?? null;
  const gmData = surfaces[surfaceRequests.findIndex((part) => part.id === "gm")]?.data ?? null;
  const labelData = labels.data ?? null;

  /**
   * The labels are applied only when their vertex count AND their first and last positions match
   * the `gm` surface's. Both come from the same packaged build, so this can only fail on a
   * half-regenerated guide — and checking it here makes that show as "labels not applied" rather
   * than as a region highlighted centimetres from the one that was clicked, which no test in the
   * browser would see.
   */
  const alignment = useMemo(() => {
    if (!gmData || !labelData?.labels) return { aligned: false, reason: null as string | null };
    if (labelData.vertexCount !== gmData.vertexCount) {
      return {
        aligned: false,
        reason: `labels are for ${labelData.vertexCount} vertices, the surface has ${gmData.vertexCount}`,
      };
    }
    const last = (gmData.vertexCount - 1) * 3;
    const same = [0, 1, 2, last, last + 1, last + 2].every((i) => gmData.positions[i] === labelData.positions[i]);
    return { aligned: same, reason: same ? null : "the labels payload's vertices are not the surface's" };
  }, [gmData, labelData]);

  const parts = useMemo<ScenePart[]>(() => {
    const out: ScenePart[] = [];
    // Grey matter first: it is inside the skin, so it is drawn first with depth writes off — the
    // other way round the skin's translucent fragments reject the brain behind them and the brain
    // disappears inside the head.
    if (gmData?.indices) {
      out.push({
        id: "gm",
        label: "Grey matter",
        positions: gmData.positions,
        indices: gmData.indices,
        labels: alignment.aligned ? (labelData?.labels ?? null) : null,
        color: SCENE_PALETTE.gm,
        opacity: effectiveAtlas ? 0.92 : (DEFAULT_OPACITY.gm ?? 0.55),
        order: 0,
      });
    }
    if (skinData?.indices) {
      out.push({
        id: "skin",
        label: "Skin",
        positions: skinData.positions,
        indices: skinData.indices,
        labels: null,
        color: SCENE_PALETTE.skin,
        // Opaque under the electrodes (they sit ON it and one round the back must be hidden by
        // it); faint when the cortex is what the user is aiming at.
        opacity: gesture === "electrode" ? 1 : (DEFAULT_OPACITY.skin ?? 0.22),
        order: 1,
      });
    }
    return out.length > 0 ? out : NO_PARTS;
  }, [gmData, skinData, labelData, alignment.aligned, effectiveAtlas, gesture]);

  const box6 = (box: number[] | null | undefined): Bounds | undefined =>
    box && box.length === 6 ? (box as Bounds) : undefined;
  const bounds = useMemo<Bounds | undefined>(() => box6(manifestData?.bbox), [manifestData]);
  /** What to FRAME when it is smaller than what to draw: the head with the neck cut off at the
   *  lowest grey-matter vertex. The server decides which millimetre that is — it has the mesh. */
  const focus = useMemo<Bounds | undefined>(() => box6(manifestData?.focus_bbox), [manifestData]);

  // ---- montage -------------------------------------------------------------------------------
  const activePairs = useMemo<Pair[]>(() => pairs ?? [], [pairs]);
  const channels = useMemo(() => channelByElectrode(activePairs), [activePairs]);
  const electrodeMarkers = useMemo(
    () => (electrodes.data ? markersFromElectrodes(electrodes.data.electrodes, channels) : NO_MARKERS),
    [electrodes.data, channels],
  );

  /**
   * The slot the next electrode click fills. Re-seeded to the first EMPTY slot whenever the montage
   * gains or loses a pair — not to 0: a first click with no draft open creates one with that
   * electrode already in pair 1 A, and a reset to 0 would send the very next click back over it.
   */
  const [cursor, setCursor] = useState(0);
  const activeChannel = activePairs.length === 0 ? null : Math.floor((cursor % (activePairs.length * 2)) / 2);
  /** A legend chip click parks the cursor on that pair's first empty slot, or on its A slot when
   *  the pair is full — "make this the pair I am editing", not "clear it". */
  const activateChannel = useCallback(
    (channel: number) => {
      const base = channel * 2;
      setCursor(activePairs[channel]?.[0] === "" ? base : activePairs[channel]?.[1] === "" ? base + 1 : base);
    },
    [activePairs],
  );
  const pairCount = activePairs.length;
  const [lastPairCount, setLastPairCount] = useState(pairCount);
  if (pairCount !== lastPairCount) {
    setLastPairCount(pairCount);
    setCursor(firstEmptySlot(activePairs));
  }

  const markers = gesture === "electrode" ? electrodeMarkers : NO_MARKERS;

  // ---- selection -----------------------------------------------------------------------------
  const formRegions = useMemo<SceneRegionRef[]>(() => regions ?? [], [regions]);
  const selection = useMemo<SceneSelection>(() => {
    if (gesture === "electrode") {
      return { markers: markerIndicesFor(electrodeMarkers, placedElectrodes(activePairs)), regions: [] };
    }
    return { markers: [], regions: wireLabelsFor(legend, formRegions) };
  }, [gesture, electrodeMarkers, activePairs, legend, formRegions]);

  // ---- picking -------------------------------------------------------------------------------
  const onPick = useCallback(
    (target: PickTarget | null) => {
      if (!target) return;
      if (gesture === "electrode" && target.kind === "marker") {
        const name = electrodeMarkers[target.index]?.id;
        if (!name) return;
        if (!onPairsChange || activePairs.length === 0) {
          onRequestPairs?.(name);
          return;
        }
        const next = applyElectrodePick(activePairs, cursor, name);
        setCursor(next.cursor);
        onPairsChange(next.pairs);
        return;
      }
      if (gesture === "region" && target.kind === "region") {
        const picked = regionsFromWireLabels(legend, [target.index])[0];
        // The same toggle the form's own chips run — one selection model, not two that agree.
        if (picked) onRegionsChange?.(toggleRegion(formRegions, picked));
      }
      // Deliberately nothing else. A pick on the guide names an electrode or a region; it can never
      // produce a coordinate, because these millimetres are `guide-ras`.
    },
    [gesture, electrodeMarkers, onPairsChange, onRequestPairs, activePairs, cursor, legend, formRegions, onRegionsChange],
  );

  const [hovered, setHovered] = useState<string | null>(null);
  const onHoverChange = useCallback(
    (target: PickTarget | null) => {
      if (!target) return setHovered(null);
      if (target.kind === "marker") return setHovered(electrodeMarkers[target.index]?.label ?? null);
      const row = legend.find((entry) => entry.label === target.index);
      setHovered(row ? `${row.name}${row.hemi ? ` · ${row.hemi}` : ""}` : null);
    },
    [electrodeMarkers, legend],
  );

  // ---- states --------------------------------------------------------------------------------
  // An atlas or a net the guide does not have is a NOTE, not an error state: the anatomy is still
  // worth drawing and the form is still usable. Only the manifest or a surface payload empties it.
  const error = (manifest.error ?? surfaces.find((s) => s.error)?.error) as Error | null | undefined;
  const sideError = (regionsQuery.error ?? electrodes.error) as Error | null | undefined;
  const state: ScenePaneDebug["state"] = error ? "error" : parts.length === 0 ? "loading" : "ready";

  const message = ((): string | null => {
    if (state === "error") {
      // The server's own `detail` verbatim: it names the missing file, which a sentence written
      // here could not.
      return error instanceof SceneError ? error.message : (error?.message ?? "The scene could not be loaded.");
    }
    if (state === "loading") return "Loading the guide head model…";
    return null;
  })();

  // ---- first paint ---------------------------------------------------------------------------
  // Refs, not state: this number is read through the debug handle and by nothing that renders, and
  // putting it in state would re-render the pane purely to record a measurement.
  const startedAt = useRef<number | null>(null);
  const firstPaintRef = useRef<number | null>(null);
  useEffect(() => {
    startedAt.current = performance.now();
    firstPaintRef.current = null;
  }, []);
  useEffect(() => {
    if (parts.length === 0 || startedAt.current === null || firstPaintRef.current !== null) return;
    // Two frames: the first is the render React just scheduled, the second is after the canvas has
    // drawn in it — a single rAF fires before the renderer's own loop has run.
    let raf = requestAnimationFrame(() => {
      raf = requestAnimationFrame(() => {
        const started = startedAt.current;
        if (started !== null && firstPaintRef.current === null) {
          firstPaintRef.current = Math.round(performance.now() - started);
        }
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [parts.length]);

  // ---- legend --------------------------------------------------------------------------------
  const selectedRegionRows = useMemo(
    () => formRegions.filter((region) => legend.some((row) => row.id === region.id && row.hemi === region.hemi)),
    [formRegions, legend],
  );

  const paneLegend = useMemo<LegendEntry[]>(() => {
    const rows: LegendEntry[] = [];
    if (gesture !== "electrode" && effectiveAtlas && legend.length > 0) {
      rows.push({ key: "atlas", label: effectiveAtlas, color: SCENE_PALETTE.dim, detail: `${legend.length} regions` });
      for (const region of selectedRegionRows) {
        rows.push({
          key: `roi-${region.hemi ?? ""}-${region.id}`,
          label: region.name,
          color: SCENE_PALETTE.selected,
          detail: region.hemi ?? undefined,
        });
      }
    }
    return rows;
  }, [gesture, effectiveAtlas, legend.length, selectedRegionRows]);

  /** One phrase saying what a click does — the pane's own instruction, never a tooltip. */
  const hint = ((): string => {
    if (note) return note;
    if (netMissing) return `The guide has no ${net} electrode positions — the montage still works from the form.`;
    if (sideError) return sideError instanceof SceneError ? sideError.message : "Some of this scene could not be loaded.";
    if (gesture === "electrode") {
      return activePairs.length === 0
        ? "Click an electrode to start a montage."
        : `Click an electrode to fill ${slotLabel(activePairs, cursor)}.`;
    }
    if (gesture === "region") return "Click a region to add or remove it from the ROI.";
    return "Reference anatomy — a guide for choosing names, not this subject's head.";
  })();

  // ---- the debug handle ----------------------------------------------------------------------
  useEffect(() => {
    if (!SCENE_DEBUG) return;
    const handle: ScenePaneDebug = {
      mode,
      gesture,
      subject: null,
      guide: guideId,
      space: manifestData?.space ?? null,
      net: mode === "montage" ? net : null,
      atlas: effectiveAtlas,
      state,
      message,
      parts: parts.map((part) => ({
        id: part.id,
        triangles: part.indices.length / 3,
        vertices: part.positions.length / 3,
        labelled: !!part.labels,
      })),
      markers: markers.length,
      regions: legend.length,
      selection,
      selectedRegions: selectedRegionRows,
      hovered,
      get firstPaintMs() {
        return firstPaintRef.current;
      },
      legend,
    };
    window.__scenePane = handle;
    return () => {
      if (window.__scenePane === handle) delete window.__scenePane;
    };
  }, [mode, gesture, guideId, manifestData, net, effectiveAtlas, state, message, parts, markers.length, legend, selection, selectedRegionRows, hovered]);

  const atlasOptions = useMemo(
    () => (manifestData?.atlases ?? []).map((entry) => ({ value: String(entry.id), label: String(entry.id) })),
    [manifestData],
  );

  return (
    <div
      className={`scene-pane-host ${className ?? ""}`.trim()}
      data-testid="scene-pane-host"
      data-mode={mode}
      data-gesture={gesture}
      data-state={state}
      data-renderer="native"
      data-active-channel={activeChannel ?? ""}
    >
      {showing ? (
        <p className="scene-pane-showing" data-testid="scene-pane-showing">
          Showing: <strong>{showing.montage}</strong> · {showing.net}
        </p>
      ) : null}
      {gesture === "electrode" ? (
        <ChannelLegend pairs={activePairs} activeChannel={activeChannel} onActivate={activateChannel} />
      ) : null}
      {wantsRegions && atlasOptions.length > 0 ? (
        <div className="scene-pane-atlas" data-testid="scene-pane-atlas">
          <Select
            aria-label="Atlas"
            value={effectiveAtlas ?? ""}
            onValueChange={chooseAtlas}
            options={atlasOptions}
          />
          <span className="scene-pane-hovered" data-testid="scene-pane-hovered">
            {hovered ?? ""}
          </span>
        </div>
      ) : null}
      <div className="scene-pane-stage">
        {state === "ready" ? (
          <SceneCanvas
            mode={CANVAS_MODE[gesture]}
            parts={parts}
            markers={markers}
            /* Electrodes lie on the scalp, so the scalp hides the ones round the back. */
            markersOccluded
            selection={selection}
            onPick={onPick}
            onHoverChange={onHoverChange}
            bounds={bounds}
            focus={focus}
            legend={paneLegend}
            label={`${guideId ?? "guide"} head model`}
          />
        ) : (
          <div className="scene-pane-placeholder" data-testid="scene-pane-placeholder">
            {state === "loading" ? <Skeleton height={120} /> : null}
            <p className="scene-pane-message" data-testid="scene-pane-message">
              {message ?? ""}
            </p>
            {state === "error" ? (
              <Button
                className="scene-pane-retry"
                disabled={manifest.isFetching}
                onClick={() => {
                  if (manifest.error) void manifest.refetch();
                  for (const surface of surfaces) if (surface.error) void surface.refetch();
                }}
              >
                Retry 3D preview
              </Button>
            ) : null}
          </div>
        )}
      </div>
      <p className="scene-pane-hint" data-testid="scene-pane-hint">
        {state === "ready" ? hint : ""}
      </p>
    </div>
  );
}
