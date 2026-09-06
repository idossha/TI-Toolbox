/**
 * `<ScenePane mode="montage" | "target" | "inspect">` — a Tetravox-backed scene as a **form
 * control** on the three run pages.
 *
 * The page owns the selection: picks write back to the Simulator/Optimizer/Analyzer form, and form
 * edits are mirrored into the embedded scene. Surfaces are GIfTI mesh datasets loaded by the
 * Tetravox iframe, electrodes are protocol-2 inline points, and clicks are protocol-2 `pick`
 * events.
 *
 * **What it draws is the fixed guide, never the selected research subject**
 * (`desktop/IMPLEMENTATION_PLAN.md` R4). Three failures that change prevents:
 *
 *  - a project whose subjects have no head model yet showed a "run charm first" sentence where the
 *    anatomy should be — on exactly the pages a user is configuring *before* charm has run;
 *  - every change of the selected subject re-keyed three queries and reloaded the embed, so
 *    ticking a second subject cost a cache-cold 184 MB mesh extraction and a remount;
 *  - and a click could turn one subject's anatomy into a subject-RAS coordinate written into a
 *    configuration that runs on a *different* subject.
 *
 * The last one is why the sphere gesture is gone from this pane: the guide's coordinates are
 * `guide-ras` and are never written into a configuration. Typed coordinates remain the way a
 * sphere centre is set; a picking mode for them needs an explicit space/transform contract first.
 *
 * `subject` and `unavailable` are still accepted so the pages keep compiling unchanged, and are
 * deliberately **ignored**: no request is keyed on them, so changing the selected subjects issues
 * no guide request and remounts no iframe. They are the props to delete once the pages are updated.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCapabilities } from "../../../api/client";
import { usePageSession } from "../../../app/pageSession";
import { usePageActive } from "../../../app/pageActivity";
import { Button } from "../../../ui/Button";
import { Skeleton } from "../../../ui/Feedback";
import { Slider } from "../../../ui/Toggle";
import { ChannelLegend } from "../../../ui/ChannelLegend";
import { EmbedFrame } from "../../../viewer/EmbedFrame";
import { HANDSHAKE_TIMEOUT_MS, createChannel, type EmbedChannel } from "../../../viewer/channel";
import { embedCan, embedShortfall, type EmbedCapability, type EmbedFeature } from "../../../viewer/embedProtocol";
import { normalizeLayers, type CameraMessage, type EmbedLayer, type EmbedMessage, type PickMessage } from "../../../viewer/protocol";
import { SceneError, type SceneLegendRow } from "./api";
import {
  POINTS_LAYER_NAME,
  buildPaneViewSpec,
  cameraPatchForScene,
  labelLayerPredicate,
  labelsForRegions,
  liveLayerId,
  pointLayerPredicate,
  pointsFromMarkers,
  regionFromPick,
} from "./embedScene";
import {
  applyElectrodePick,
  channelByElectrode,
  firstEmptySlot,
  markerIndicesFor,
  markersFromElectrodes,
  placedElectrodes,
  regionKey,
  slotLabel,
  wireLabelsFor,
  type Pair,
  type SceneMarker,
  type SceneRegionRef,
  type SceneSelection,
} from "./model";
import { useGuideElectrodes, useGuideManifest, useGuideRegions } from "./queries";
import "./scene-pane.css";

export type ScenePaneMode = "montage" | "target" | "inspect";

/** What a click does. Derived from the mode and from which writer the page supplied.
 *
 * `"sphere"` is retained in the union only because the ViewSpec builder and its unit tests still
 * name it; the guide pane never produces it (R4). */
export type SceneGesture = "electrode" | "region" | "sphere" | "none";

export interface ScenePaneProps {
  mode: ScenePaneMode;
  /*
   * There is deliberately no `subject`, `unavailable`, `sphere` or `onSphereChange` prop. The pane
   * draws the fixed guide (R4), so it is keyed on nothing a subject switch can change; and a
   * sphere centre is a subject-RAS coordinate that the guide is in no position to produce.
   */
  /** `montage`: the EEG net file name the manifest lists (`"EEG10-10_UI_Jurak_2007.csv"`). */
  net?: string | null;
  /** `target`/`inspect`: the cortical atlas id (`"DK40"`). */
  atlas?: string | null;
  /** `montage`: the pairs being edited. */
  pairs?: Pair[];
  onPairsChange?: (pairs: Pair[]) => void;
  /** Called when a pick arrives and the page has no montage draft open yet; the page opens one. */
  onRequestPairs?: (firstElectrode: string) => void;
  /** `target`/`inspect`: the form's region list. */
  regions?: SceneRegionRef[];
  onRegionsChange?: (regions: SceneRegionRef[]) => void;
  /** A page-supplied sentence for a target the pane cannot draw (subcortical, a saved ROI CSV). */
  note?: string;
  /**
   * What the pane is drawing, when the page can name it: the montage row the user picked in the
   * Simulator's table. Rendered as an accent chip above the stage in exactly the tokens that tint
   * that row (`--accent-soft` / `--accent`), so "the highlighted row" and "what the viewer shows"
   * are visibly the same claim rather than two things a user has to correlate.
   */
  showing?: { montage: string; net: string } | null;
  className?: string;
}

/** Everything the offscreen specs read. Stripped from production unless the scene hooks flag is on. */
export interface ScenePaneDebug {
  mode: ScenePaneMode;
  gesture: SceneGesture;
  subject: string | null;
  net: string | null;
  atlas: string | null;
  state: "no-subject" | "unavailable" | "building" | "loading" | "ready" | "error";
  /** The guide the pane drew, e.g. `"ernie"` — never a research subject id. */
  guide: string | null;
  /** The guide manifest's own coordinate space. Always `"guide-ras"`; never `"subject-ras"`. */
  space: string | null;
  message: string | null;
  parts: { id: string; triangles: number; vertices: number; labelled: boolean }[];
  markers: number;
  regions: number;
  selection: SceneSelection;
  /** Milliseconds from the pane first having a subject to Tetravox reporting `loaded`. */
  firstPaintMs: number | null;
  /** The whole legend, so a spec can map a wire label back to its region without a second fetch. */
  legend: SceneLegendRow[];
}

declare global {
  interface Window {
    __scenePane?: ScenePaneDebug;
  }
}

const SCENE_DEBUG = import.meta.env.DEV || import.meta.env.VITE_SCENE_HOOKS === "1";
const NO_MARKERS: SceneMarker[] = [];
const NO_LAYERS: EmbedLayer[] = [];
const EMPTY_SELECTION: SceneSelection = { markers: [], regions: [] };

interface EmbedPaneState {
  phase: "idle" | "loading" | "ready" | "error" | "no-webgl2" | "no-embed";
  message: string | null;
  renderer: string | null;
  layers: EmbedLayer[];
  pointsLayerId: string | null;
  labelsLayerId: string | null;
}

const EMPTY_EMBED_STATE: EmbedPaneState = {
  phase: "idle",
  message: null,
  renderer: null,
  layers: NO_LAYERS,
  pointsLayerId: null,
  labelsLayerId: null,
};

function firstMissingFeature(embed: EmbedCapability | null | undefined, required: EmbedFeature[]): EmbedFeature | null {
  for (const feature of required) if (!embedCan(embed, feature)) return feature;
  return null;
}

function samePoints(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function ScenePane({
  mode,
  net = null,
  atlas = null,
  pairs,
  onPairsChange,
  onRequestPairs,
  regions,
  onRegionsChange,
  note,
  showing = null,
  className,
}: ScenePaneProps) {
  const pageActive = usePageActive();
  const [reloadToken, setReloadToken] = useState(0);
  /**
   * A pick can name an electrode or a region — never a coordinate. `"sphere"` used to be a third
   * gesture here; on the fixed guide it would write guide millimetres into a research subject's
   * configuration, so it is gone rather than approximately transformed (R4).
   */
  const gesture: SceneGesture =
    mode === "montage" ? "electrode" : onRegionsChange && atlas ? "region" : "none";

  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: () => getCapabilities(), staleTime: 60_000 });
  const manifest = useGuideManifest();
  const manifestData = manifest.data;
  const guideId = manifestData?.guide?.id ?? null;

  /**
   * The atlas the pane actually draws. A page with no atlas control of its own falls back to the
   * guide's first packaged atlas, so the cortex still has regions to read.
   */
  // Always in `target`/`inspect`, even when the form has no atlas of its own: the guide's atlas
  // payloads are packaged and immutable, so cortical context costs one cached request rather than
  // a per-subject build, and a pane that showed plain grey cortex until the user picked an atlas
  // was the state most of these pages open in.
  const wantsRegions = mode !== "montage";
  const effectiveAtlas = wantsRegions ? (atlas ?? manifestData?.atlases[0]?.id ?? null) : null;

  /** Only a net the MANIFEST lists is fetched; a catalog net absent from this subject is a note. */
  const netListed = mode === "montage" && !!net && (manifestData?.nets.some((entry) => entry.name === net) ?? false);
  const netMissing = mode === "montage" && !!net && !!manifestData && !netListed;
  const electrodes = useGuideElectrodes(netListed ? net : null);
  const regionsQuery = useGuideRegions(effectiveAtlas);
  const legend = useMemo<SceneLegendRow[]>(
    () => (regionsQuery.data ? (regionsQuery.data.legend as SceneLegendRow[]) : []),
    [regionsQuery.data],
  );

  // ---- montage -------------------------------------------------------------------------------
  const activePairs = useMemo<Pair[]>(() => pairs ?? [], [pairs]);
  const channels = useMemo(() => channelByElectrode(activePairs), [activePairs]);
  const electrodeMarkers = useMemo(
    () => (electrodes.data ? markersFromElectrodes(electrodes.data.electrodes, channels) : NO_MARKERS),
    [electrodes.data, channels],
  );

  /** The slot the next electrode click fills. */
  const [cursor, setCursor] = useState(0);
  /** The pair the next click fills — what the legend highlights and what B1's larger dot means. */
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

  // ---- regions -------------------------------------------------------------------------------
  // No sphere-centre marker: the centre is a subject-RAS coordinate and this is not that subject's
  // head, so drawing it here would put it somewhere it is not (R4).
  const markers = gesture === "electrode" ? electrodeMarkers : NO_MARKERS;

  const selection = useMemo<SceneSelection>(() => {
    if (gesture === "electrode") {
      return { markers: markerIndicesFor(electrodeMarkers, placedElectrodes(activePairs)), regions: [] };
    }
    return { markers: [], regions: wireLabelsFor(legend, regions ?? []) };
  }, [gesture, electrodeMarkers, activePairs, legend, regions]);

  // The scene highlights the analysis/target ROI even when the pane is read-only.
  const shownSelection = useMemo<SceneSelection>(
    () =>
      gesture === "none" && legend.length > 0 && regions && regions.length > 0
        ? { markers: [], regions: wireLabelsFor(legend, regions) }
        : selection,
    [gesture, legend, regions, selection],
  );

  const requiredFeatures = useMemo<EmbedFeature[]>(() => {
    const out: EmbedFeature[] = ["meshes", "camera"];
    if (markers.length > 0 || gesture === "electrode") out.push("markers");
    if (gesture !== "none") out.push("pick");
    return out;
  }, [gesture, markers.length]);
  const embedCapability = capabilities.data?.tetravox_embed as EmbedCapability | undefined;
  const missingFeature = capabilities.data ? firstMissingFeature(embedCapability, requiredFeatures) : null;
  const capabilityShortfall = missingFeature ? embedShortfall(embedCapability, missingFeature) : null;

  // ---- embedded Tetravox channel -------------------------------------------------------------
  const [embedState, setEmbedState] = useState<EmbedPaneState>(EMPTY_EMBED_STATE);
  const [skinOpacity, setSkinOpacity] = usePageSession<number | null>("sceneSkinOpacity", null);
  const [gmOpacity, setGmOpacity] = usePageSession<number | null>("sceneGmOpacity", null);
  const opacityRef = useRef({ skin: skinOpacity, gm: gmOpacity });
  const channelRef = useRef<EmbedChannel | null>(null);
  const embedReadyRef = useRef(false);
  const pendingSceneRef = useRef<ReturnType<typeof buildPaneViewSpec> | null>(null);
  const liveLayersRef = useRef<EmbedLayer[]>(NO_LAYERS);
  const pickHandlerRef = useRef<(pick: PickMessage) => void>(() => undefined);
  const pointsRef = useRef<ReturnType<typeof pointsFromMarkers>>([]);
  const selectedLabelsRef = useRef<number[]>([]);
  const labelsLayerIdRef = useRef<string | null>(null);
  const cameraPatchRef = useRef<ReturnType<typeof cameraPatchForScene>>(null);
  const firstPaintRef = useRef<number | null>(null);
  const startedAt = useRef<number | null>(null);

  const syncOpacity = useCallback(() => {
    for (const layer of liveLayersRef.current) {
      if (layer.kind !== "mesh") continue;
      const part = layer.name === "Skin" ? "skin" : layer.name === "Grey matter" || layer.name?.startsWith("TI pane atlas · ") ? "gm" : null;
      const opacity = part ? opacityRef.current[part] : null;
      if (opacity !== null && opacity !== undefined && opacity !== layer.opacity) {
        channelRef.current?.post({ type: "setLayerOpacity", layerId: layer.id, opacity });
      }
    }
  }, []);

  useEffect(() => {
    opacityRef.current = { skin: skinOpacity, gm: gmOpacity };
    syncOpacity();
  }, [skinOpacity, gmOpacity, syncOpacity]);

  /**
   * The one write that draws the electrodes: a whole replacement of the layer's points (plan B3).
   *
   * Two messages this deliberately never sends, and the reasons are not stylistic:
   *
   *  - `setPointSelection` — the embed's selection is drawn as a **ring** around the point, and a
   *    ring around a dot is exactly the visual the maintainer asked to be rid of. Colour is the
   *    whole signal here, and the colour arrives in `points`.
   *  - `setPointTool` — a tool would let the embed mutate the layer itself; the form is the source
   *    of truth, so the embed is never given a way to write.
   *
   * Fire-and-forget: embed 0.4.0 answers `setPoints` with a `layers` **event** that carries no
   * correlation id, so a host that awaits a reply waits for ever (measured in
   * `tests/e2e/real/embed-occlusion.spec.ts`'s `sendAndSettle`). The upstream fix is in the TX
   * lane; until it ships, not awaiting is the correct behaviour, not a shortcut.
   */
  const syncPoints = useCallback((layerId: string | null) => {
    const channel = channelRef.current;
    if (!channel || !layerId) return;
    channel.post({ type: "setPoints", layerId, points: pointsRef.current });
  }, []);

  const syncLabels = useCallback((layerId: string | null) => {
    const channel = channelRef.current;
    if (!channel || !layerId) return;
    const layer = liveLayersRef.current.find((candidate) => candidate.id === layerId);
    const current = (layer?.label ?? null) as Record<string, unknown> | null;
    if (!current || typeof current !== "object") return;
    const rest = { ...current };
    delete rest.visibleLabels;
    channel.post({
      type: "updateLayer",
      layerId,
      patch: { label: selectedLabelsRef.current.length > 0 ? { ...rest, visibleLabels: selectedLabelsRef.current } : rest },
    });
  }, []);

  const sendCamera = useCallback(() => {
    const channel = channelRef.current;
    const patch = cameraPatchRef.current;
    if (!channel || !patch) return;
    void channel.request<CameraMessage>({ type: "setCamera", patch }, "camera").catch(() => undefined);
  }, []);
  const handleEmbedMessage = useCallback(
    (message: EmbedMessage) => {
      switch (message.type) {
        case "ready": {
          embedReadyRef.current = true;
          if (!message.caps.webgl2) {
            setEmbedState((s) => ({ ...s, phase: "no-webgl2", message: "This machine cannot run the 3D viewer: WebGL2 is unavailable.", renderer: message.caps.renderer ?? null }));
            return;
          }
          setEmbedState((s) => ({ ...s, renderer: message.caps.renderer ?? null, message: null, phase: pendingSceneRef.current ? "loading" : "idle" }));
          if (pendingSceneRef.current) channelRef.current?.post({ type: "load", scene: pendingSceneRef.current });
          return;
        }
        case "status": {
          if (message.phase === "error") setEmbedState((s) => ({ ...s, phase: "error", message: message.message ?? "The viewer reported an error." }));
          else if (message.phase === "no-webgl2") setEmbedState((s) => ({ ...s, phase: "no-webgl2", message: "This machine cannot run the 3D viewer: WebGL2 is unavailable." }));
          else setEmbedState((s) => ({ ...s, phase: message.phase === "ready" ? "ready" : message.phase, message: null }));
          return;
        }
        case "loaded": {
          const layers = normalizeLayers(message.layers);
          liveLayersRef.current = layers;
          const pointsLayerId = liveLayerId(layers, pointLayerPredicate);
          const labelsLayerId = liveLayerId(layers, labelLayerPredicate(effectiveAtlas));
          labelsLayerIdRef.current = labelsLayerId;
          setEmbedState((s) => ({ ...s, phase: "ready", message: null, layers, pointsLayerId, labelsLayerId }));
          if (startedAt.current !== null && firstPaintRef.current === null) firstPaintRef.current = Math.round(performance.now() - startedAt.current);
          channelRef.current?.post({ type: "setPickEvents", enabled: gesture !== "none" });
          syncPoints(pointsLayerId);
          syncLabels(labelsLayerId);
          syncOpacity();
          sendCamera();
          return;
        }
        case "layers": {
          const layers = normalizeLayers(message.layers);
          liveLayersRef.current = layers;
          const pointsLayerId = liveLayerId(layers, pointLayerPredicate);
          const labelsLayerId = liveLayerId(layers, labelLayerPredicate(effectiveAtlas));
          labelsLayerIdRef.current = labelsLayerId;
          setEmbedState((s) => ({ ...s, layers, pointsLayerId, labelsLayerId }));
          return;
        }
        case "pick":
          pickHandlerRef.current(message);
          return;
        case "camera":
          return;
        case "error":
          setEmbedState((s) => ({ ...s, phase: "error", message: message.message }));
          return;
        default:
          return;
      }
    },
    [effectiveAtlas, gesture, sendCamera, syncLabels, syncPoints, syncOpacity],
  );

  // A form edit can change the pick handler without changing the iframe. Reconnecting on callback
  // identity resets the renderer and camera even while the user stays on this tab.
  const messageHandlerRef = useRef(handleEmbedMessage);
  useEffect(() => {
    messageHandlerRef.current = handleEmbedMessage;
  }, [handleEmbedMessage]);

  const connect = useCallback(
    (frame: HTMLIFrameElement, embedOrigin: string, timeoutMs = HANDSHAKE_TIMEOUT_MS) => {
      channelRef.current?.dispose();
      embedReadyRef.current = false;
      setEmbedState((s) => ({ ...s, phase: pendingSceneRef.current ? "loading" : "idle", message: null }));
      channelRef.current = createChannel(frame, embedOrigin, (message) => messageHandlerRef.current(message), timeoutMs, () => {
        if (!embedReadyRef.current) setEmbedState((s) => ({ ...s, phase: "no-embed", message: "The viewer bundle mounted but did not answer." }));
      });
      channelRef.current.post({ type: "hello" });
    },
    [],
  );

  const disconnect = useCallback(() => {
    const channel = channelRef.current;
    if (channel) {
      channel.post({ type: "reset" });
      channel.dispose();
    }
    channelRef.current = null;
    embedReadyRef.current = false;
    liveLayersRef.current = NO_LAYERS;
    labelsLayerIdRef.current = null;
    setEmbedState(EMPTY_EMBED_STATE);
  }, []);

  // ---- pick handling -------------------------------------------------------------------------
  useEffect(() => {
    pickHandlerRef.current = (pick: PickMessage): void => {
      if (gesture === "electrode" && pick.kind === "point" && pick.pointId) {
        const name = pick.pointId;
        if (!electrodeMarkers.some((marker) => marker.id === name)) return;
        if (!onPairsChange || activePairs.length === 0) {
          onRequestPairs?.(name);
          return;
        }
        const next = applyElectrodePick(activePairs, cursor, name);
        setCursor(next.cursor);
        onPairsChange(next.pairs);
        return;
      }
      if (gesture === "region") {
        const picked = regionFromPick(pick, legend, labelsLayerIdRef.current);
        if (!picked) return;
        const current = regions ?? [];
        const key = regionKey(picked);
        const next = current.some((r) => regionKey(r) === key)
          ? current.filter((r) => regionKey(r) !== key)
          : [...current, picked];
        onRegionsChange?.(next);
        return;
      }
      // Deliberately nothing else. A pick on the guide can name an electrode or a region; it can
      // never produce a coordinate, because these millimetres are `guide-ras` (R4).
    };
  }, [gesture, electrodeMarkers, onPairsChange, onRequestPairs, activePairs, cursor, legend, regions, onRegionsChange]);

  // ---- ViewSpec and live point/label sync ----------------------------------------------------
  const includePointsLayer = gesture === "electrode";
  // A required atlas is part of the first scene, not a second asynchronous load over temporary
  // anatomy. Overlapping loads can leave duplicate skin/cortex layers in the same embed engine.
  const sceneSpec = useMemo(
    () =>
      manifestData && (!effectiveAtlas || regionsQuery.data) && !capabilityShortfall
        ? buildPaneViewSpec({
            manifest: manifestData,
            mode,
            gesture,
            atlas: effectiveAtlas,
            regions: effectiveAtlas && regionsQuery.data ? regionsQuery.data : null,
            selection: EMPTY_SELECTION,
            includePointsLayer,
          })
        : null,
    [manifestData, regionsQuery.data, capabilityShortfall, mode, gesture, effectiveAtlas, includePointsLayer],
  );

  // Keyed on the GUIDE, not on a subject: this is what makes "changing subjects remounts nothing"
  // true rather than merely intended — a subject change reaches no dependency here.
  useEffect(() => {
    startedAt.current = guideId ? performance.now() : null;
    firstPaintRef.current = null;
  }, [guideId, effectiveAtlas]);

  useEffect(() => {
    pendingSceneRef.current = sceneSpec;
    cameraPatchRef.current = sceneSpec ? cameraPatchForScene(sceneSpec) : null;
    if (!sceneSpec || capabilityShortfall) return;
    setEmbedState((s) => ({ ...s, phase: embedReadyRef.current ? "loading" : s.phase, message: null, pointsLayerId: null, labelsLayerId: null }));
    if (embedReadyRef.current) channelRef.current?.post({ type: "load", scene: sceneSpec });
  }, [sceneSpec, capabilityShortfall]);

  useEffect(() => {
    channelRef.current?.post({ type: "setPickEvents", enabled: gesture !== "none" });
  }, [gesture, embedState.pointsLayerId]);

  const points = useMemo(
    () => pointsFromMarkers(markers, shownSelection, gesture === "electrode" ? activeChannel : null),
    [markers, shownSelection, gesture, activeChannel],
  );
  useEffect(() => {
    if (!samePoints(pointsRef.current, points)) pointsRef.current = points;
    syncPoints(embedState.pointsLayerId);
  }, [points, embedState.pointsLayerId, syncPoints]);

  const selectedLabels = useMemo(() => labelsForRegions(legend, regions), [legend, regions]);
  useEffect(() => {
    selectedLabelsRef.current = selectedLabels;
    syncLabels(embedState.labelsLayerId);
  }, [selectedLabels, embedState.labelsLayerId, syncLabels]);

  // ---- states --------------------------------------------------------------------------------
  const error = (manifest.error ?? regionsQuery.error) as Error | null | undefined;
  const sideError = (regionsQuery.error ?? electrodes.error) as Error | null | undefined;
  // The guide ships built; nothing here can be "building". The state is kept in the union so the
  // debug shape and its specs do not churn while the pages still pass their old props.
  const building = false;
  const embedMessage = embedState.message;
  const embedFailed = embedState.phase === "error" || embedState.phase === "no-webgl2" || embedState.phase === "no-embed";

  const state: ScenePaneDebug["state"] = ((): ScenePaneDebug["state"] => {
    if (error || capabilityShortfall || embedFailed) return "error";
    if (building) return "building";
    return sceneSpec && embedState.phase === "ready" ? "ready" : "loading";
  })();

  const message = ((): string | null => {
    if (capabilityShortfall) return capabilityShortfall;
    if (embedFailed) return embedMessage ?? "The embedded viewer could not render this scene.";
    switch (state) {
      case "no-subject":
      case "unavailable":
        return null;
      case "error":
        return error instanceof SceneError ? error.message : (error?.message ?? "The scene could not be loaded.");
      case "building":
        return "Building the guide scene…";
      case "loading":
        return capabilities.isPending ? "Checking the viewer bundle…" : sceneSpec ? "Loading the embedded 3D scene…" : "Loading the guide head model…";
      default:
        return null;
    }
  })();

  // ---- legend / hint -------------------------------------------------------------------------
  const hint = ((): string => {
    if (note) return note;
    if (netMissing) return `The guide has no ${net} electrode positions — the montage still works from the form.`;
    if (sideError) return sideError instanceof SceneError ? sideError.message : "Some of this scene could not be loaded.";
    if (gesture === "electrode") {
      return activePairs.length === 0 ? "Click an electrode to start a montage." : `Click an electrode to fill ${slotLabel(activePairs, cursor)}.`;
    }
    if (gesture === "region") return "Click a region to add or remove it from the ROI.";
    return "Reference anatomy — a guide for choosing names, not this subject's head.";
  })();

  // ---- debug handle --------------------------------------------------------------------------
  useEffect(() => {
    if (!SCENE_DEBUG || !pageActive) return;
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
      parts: (manifestData?.parts ?? []).map((part) => ({
        id: part.id,
        triangles: part.triangles ?? 0,
        vertices: part.vertices ?? 0,
        labelled: part.id === "gm" && !!effectiveAtlas && legend.length > 0,
      })),
      markers: markers.length,
      regions: legend.length,
      selection: shownSelection,
      get firstPaintMs() {
        return firstPaintRef.current;
      },
      legend,
    };
    window.__scenePane = handle;
    return () => {
      if (window.__scenePane === handle) delete window.__scenePane;
    };
  }, [pageActive, mode, gesture, guideId, net, effectiveAtlas, state, message, manifestData, markers.length, legend, shownSelection]);

  // Keep failures visible until an explicit retry. Unmounting here calls disconnect(), which
  // clears the failure and otherwise creates an endless mount/timeout/reset loop.
  const showEmbed = !!sceneSpec && !capabilityShortfall;
  const hostClassName = `scene-pane-host ${className ?? ""}`.trim();

  return (
    <div className={hostClassName} data-testid="scene-pane-host" data-mode={mode} data-gesture={gesture} data-state={state} data-renderer="tetravox" data-active-channel={activeChannel ?? ""}>
      {showing ? (
        <p className="scene-pane-showing" data-testid="scene-pane-showing">
          Showing: <strong>{showing.montage}</strong> · {showing.net}
        </p>
      ) : null}
      {gesture === "electrode" ? (
        <ChannelLegend pairs={activePairs} activeChannel={activeChannel} onActivate={activateChannel} />
      ) : null}
      <div className="scene-pane-stage">
        {showEmbed ? (
          <EmbedFrame
            connect={connect}
            disconnect={disconnect}
            className="scene-pane-embed"
            testId="scene-pane-tetravox-frame"
            title={`${guideId ?? "guide"} 3D scene`}
            presentation="viewport"
            reloadToken={reloadToken}
          />
        ) : null}
        {(!showEmbed || state !== "ready") && (
          <div className={showEmbed ? "scene-pane-placeholder scene-pane-overlay" : "scene-pane-placeholder"} data-testid="scene-pane-placeholder">
            {state === "loading" && !capabilityShortfall && !embedFailed ? <Skeleton height={120} /> : null}
            <p className="scene-pane-message" data-testid="scene-pane-message">
              {message ?? ""}
            </p>
            {embedFailed || error ? (
              <Button
                className="scene-pane-retry"
                disabled={manifest.isFetching || regionsQuery.isFetching}
                onClick={() => {
                  if (manifest.error) void manifest.refetch();
                  if (regionsQuery.error) void regionsQuery.refetch();
                  if (embedFailed) setReloadToken((token) => token + 1);
                }}
              >Retry 3D preview</Button>
            ) : null}
          </div>
        )}
      </div>
      <div className="scene-pane-opacity" role="group" aria-label="Surface opacity" data-testid="scene-pane-opacity">
        <div className="scene-pane-opacity-row" data-testid="scene-skin-opacity">
          <span>Skin</span>
          <Slider
            aria-label="Skin opacity"
            value={Math.round((skinOpacity ?? (gesture === "electrode" ? 1 : 0.22)) * 100)}
            onValueChange={(value) => setSkinOpacity(value / 100)}
            unit="%"
            disabled={state !== "ready" || !manifestData?.parts.some((part) => part.id === "skin")}
          />
        </div>
        <div className="scene-pane-opacity-row" data-testid="scene-gm-opacity">
          <span>Grey matter</span>
          <Slider
            aria-label="Grey matter opacity"
            value={Math.round((gmOpacity ?? (effectiveAtlas ? 0.92 : 0.55)) * 100)}
            onValueChange={(value) => setGmOpacity(value / 100)}
            unit="%"
            disabled={state !== "ready" || !manifestData?.parts.some((part) => part.id === "gm")}
          />
        </div>
      </div>
      <p className="scene-pane-hint" data-testid="scene-pane-hint">
        {state === "ready" || state === "building" ? hint : ""}
      </p>
      {SCENE_DEBUG && embedState.renderer ? <span hidden data-testid="scene-pane-renderer">{embedState.renderer}</span> : null}
      {SCENE_DEBUG && embedState.pointsLayerId ? <span hidden data-testid="scene-pane-points-layer">{POINTS_LAYER_NAME}</span> : null}
    </div>
  );
}
