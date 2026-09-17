/**
 * `<ScenePane mode="montage" | "target" | "inspect">` — the scene as a **form control** on the
 * three run pages (`docs/dev/DECISIONS.md § 2026-09-06 (Native panes, job rows and notebooks)`, N1–N4).
 *
 * `renderer/scene/` draws — our own WebGL2, no runtime dependency, no iframe, no protocol. This
 * file is everything between that renderer and a page's form: it fetches the packaged guide over
 * `/api/guide/*`, decodes TVSC1, and keeps the selection synchronised **in both directions**:
 *
 * | mode      | page      | a pick means                                      | the form writes back |
 * |-----------|-----------|---------------------------------------------------|----------------------|
 * | `montage` | Simulator | toggle that electrode into the active pair slot   | editing a pair re-colours its dots |
 * | `target`  | Optimizer | add/remove that atlas region from the ROI         | the ROI picker's region list IS the pane's selection |
 * | `target`  | Optimizer (Ex/mEx, **Electrodes** gesture) | toggle that electrode into the active bucket | editing a bucket re-colours its dots |
 * | `inspect` | Analyzer  | add/remove that atlas region from the analysis ROI | the analysis ROI is drawn where it will be measured |
 *
 * An Ex/mEx row names a leadfield, and a leadfield is an EEG net: the pane draws that net's cap on
 * the head exactly as the Simulator does, and a **Target | Electrodes** segmented control in the
 * atlas toolbar says which of the two a click edits. One gesture is live at a time, so the pane
 * can still state in one phrase what the next click will do — a pane where a click meant "region
 * or electrode, whichever you hit" is a pane that cannot.
 *
 * Four rules, each with the failure it prevents:
 *
 *  - **The pane never holds the selection.** `pairs` and `regions` are the page's state; a pick
 *    calls the page's writer and the new value comes back down through the same `toggleRegion` the
 *    form's own chips call. A pane with its own copy is a pane that can disagree with the form.
 *  - **What it draws is the head the row names.** Superseded 2026-09-06→2026-09-17: the pane used
 *    to draw the packaged guide and never the selected subject. It now draws the active row's own
 *    subject when the row's ROI is in subject space, and the packaged MNI152 guide when it is in
 *    MNI space, because the whole point of the pane is to show *what will be optimised* — and
 *    charm's islands, an atlas the subject does not have, and an MNI atlas warped into a different
 *    head are all invisible on a stand-in. The guide remains the fallback for a subject with no
 *    head model or a build still running, and the pane says which it is drawing in one sentence.
 *    A guide's space is `guide-ras`, so while one is drawn the pane still **never produces a
 *    coordinate**.
 *  - **An electrode's colour is its whole state** — neutral grey in no channel, its channel's
 *    Okabe-Ito hue when placed. No ring, no outline, no second glyph.
 *  - **Every failure is a sentence, not an error box** — the server's own `detail` verbatim, and a
 *    page that still works without the pane.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  SCENE_DEBUG,
  SceneCanvas,
  buildLabelColors,
  labelSwatchColor,
  type Bounds,
  type LegendEntry,
  type PickTarget,
  type ScenePick,
  type ScenePart,
  type SceneSelection,
  type Vec3,
} from "../../../scene";
import { usePageActive } from "../../../app/pageActivity";
import { Skeleton } from "../../../ui/Feedback";
import { Button } from "../../../ui/Button";
import { Select } from "../../../ui/Select";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { ChannelLegend } from "../../../ui/ChannelLegend";
import { SceneError, type GuideId, type GuideManifest, type SceneLegendRow, type SceneManifest } from "./api";
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
  useSceneElectrodes,
  useSceneLabels,
  useSceneManifest,
  useSceneRegions,
  useSceneSurfaceRequests,
  useSceneSurfaces,
} from "./queries";
import "./scene-pane.css";
import { capDisplacements } from "./displacements";

export type ScenePaneMode = "montage" | "target" | "inspect";

/** What a click does. Derived from the mode and from which writer the page supplied — one gesture
 *  is live at a time, so the pane can always say in one phrase what a click will do. */
export type SceneGesture = "electrode" | "region" | "place" | "none";

export interface ScenePaneProps {
  mode: ScenePaneMode;
  /** Rendered first in the atlas toolbar, on the same line as the atlas picker and Clear selection. */
  toolbarLead?: ReactNode;
  /**
   * Draw **this subject's own head** instead of the packaged guide.
   *
   * The guide is still the default and still the right answer for a page that only ever names
   * things (R4: a fresh project has no head model, ticking a second subject would start a
   * cache-cold extraction of a 184 MB mesh, and a coordinate picked off one subject's anatomy
   * could otherwise be written into a run on another). It stops being the right answer the moment
   * a page needs a **coordinate**: a free-hand placement is a millimetre in the subject's own head
   * mesh (`m2m_<id>/stim_configs/*.json`), and there is no way to produce one from `guide-ras`.
   *
   * So this prop and `onPlace` travel together: passing a subject is what makes placement possible,
   * and the pane refuses to emit a coordinate while it is drawing the guide. A subject with no
   * scene (no head model, or a build that failed) falls back to the guide and the pane says so in
   * its own hint rather than showing an error.
   */
  subject?: string | null;
  /**
   * Which packaged guide stands in when no subject is drawn: `"default"` (subject anatomy) or
   * `"mni"` (the MNI152 template). Passing `"mni"` also stops the pane from drawing a subject at
   * all — an MNI-space ROI is chosen on the template, and the run transforms it per subject.
   */
  guide?: GuideId;
  /**
   * A click on the anatomy reports the world point under the cursor, in the drawn subject's own
   * millimetres. Honoured **only** while a subject is being drawn (see `subject`).
   */
  onPlace?: (world: Vec3) => void;
  /** Page-supplied markers, drawn instead of an EEG net's — the free-hand positions being placed. */
  placedMarkers?: SceneMarker[];
  /** Optimized subject-space origins for the selected cap pairs. */
  originalPositions?: { x: number; y: number; z: number }[];
  /**
   * A click on one of `placedMarkers` reports its index instead of placing a new point.
   *
   * The failure it prevents: a user who clicks a dot to move it gets a *second* dot on top of the
   * first, and the table now claims an electrode nobody meant to add.
   */
  onPlacedPick?: (index: number) => void;
  /** Marker indices to draw as if hovered — how a hovered table row lights its own dot. */
  highlightMarkers?: number[];
  /** The placement marker the page has selected: ringed and enlarged, so "which electrode does the
   *  next click move" is answered on the scalp as well as in the table. */
  selectedMarkers?: number[];
  /** The dot the cursor is over, by index, or `null` — the other direction of the same link. */
  onPlacedHover?: (index: number | null) => void;
  /*
   * There is deliberately still no `unavailable`, `sphere` or `onSphereChange` prop.
   */
  /** `montage`: the EEG net file name the manifest lists (`"EEG10-10_UI_Jurak_2007.csv"`). */
  net?: string | null;
  /**
   * `target`: the EEG net whose cap is drawn ALONGSIDE the atlas — an Ex/mEx row's leadfield net.
   *
   * Spelled either way (`"<net>"` or `"<net>.csv"`): the leadfield catalog reports the bare name
   * and the scene manifest the cap filename (`pages/optimizer/nets.ts`), and a pane that compared
   * them for equality would draw no electrodes at all on the real project.
   */
  electrodeNet?: string | null;
  /** Electrode name → channel index, which is the marker's colour. Anything absent draws neutral
   *  grey. The page owns it — it is derived from the row's buckets, never held here. */
  electrodeChannels?: Record<string, number>;
  /** A click on an electrode while the **Electrodes** gesture is live. Supplying it (with
   *  `electrodeNet`) is what puts the Target | Electrodes control in the toolbar. */
  onElectrodePick?: (name: string) => void;
  /** The page's own legend for those colours, drawn above the stage — the bucket equivalent of
   *  `<ChannelLegend>`, which the page owns because the buckets are its form state. */
  electrodeLegend?: ReactNode;
  /** `target`/`inspect`: the cortical atlas id (`"DK40"`). Omitted, the pane picks the guide's
   *  first packaged atlas and its own selector chooses from there. */
  atlas?: string | null;
  /** Called when the user changes the atlas in the pane's own selector, so the form follows. When
   *  it is absent the selector still works and the choice stays local to the pane. */
  onAtlasChange?: (atlas: string, kind?: string) => void;
  /** `montage`: the pairs being edited. */
  pairs?: Pair[];
  onPairsChange?: (pairs: Pair[]) => void;
  /** Called when a pick arrives and the page has no montage draft open yet; the page opens one. */
  onRequestPairs?: (firstElectrode: string) => void;
  /** `target`/`inspect`: the form's region list. The same array `<RoiPicker>` holds. */
  regions?: SceneRegionRef[];
  onRegionsChange?: (regions: SceneRegionRef[], atlas?: string) => void;
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
  /** The research subject being drawn, or `null` when the pane is on the guide. */
  subject: string | null;
  net: string | null;
  atlas: string | null;
  state: "loading" | "ready" | "error";
  /** The guide the pane drew, e.g. `"ernie"`, or `null` when it drew a research subject. */
  guide: string | null;
  /** WHICH packaged guide that was — `"default"` or `"mni"` — or `null` for a research subject. */
  guideId: GuideId | null;
  /** The drawn manifest's own coordinate space: `"guide-ras"`, or `"subject-ras"` for a subject. */
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
  /** The channel each drawn marker is painted in, by electrode name — a marker with no channel is
   *  absent and draws neutral grey. What a spec reads instead of a pixel to check a bucket's hue. */
  markerChannels: Record<string, number>;
  /** The whole legend, so a spec can map a wire label back to its region without a second fetch. */
  legend: SceneLegendRow[];
}

declare global {
  interface Window {
    __scenePane?: ScenePaneDebug;
  }
}

/** `"#rrggbb"` -> the numeric triple a legend swatch and the shader both use. */
const hexToRgb = (hex: string): [number, number, number] => [
  parseInt(hex.slice(1, 3), 16) / 255,
  parseInt(hex.slice(3, 5), 16) / 255,
  parseInt(hex.slice(5, 7), 16) / 255,
];

/** `"EEG10-10_UI_Jurak_2007.csv"` and `"EEG10-10_UI_Jurak_2007"` are one net. */
const bareNet = (name: string): string => name.replace(/\.csv$/i, "");

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
  // `place` picks nothing selectable — the point of the click is WHERE it landed, which
  // `onPickAt` reports whatever the mode's rules say is pickable.
  place: "inspect",
  region: "target",
  none: "inspect",
};

export function ScenePane({
  mode,
  toolbarLead,
  subject = null,
  guide = "default",
  onPlace,
  placedMarkers,
  originalPositions,
  onPlacedPick,
  onPlacedHover,
  highlightMarkers,
  selectedMarkers,
  net = null,
  electrodeNet = null,
  electrodeChannels,
  onElectrodePick,
  electrodeLegend,
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
  // Three panes are mounted at once (one per retained run page). Only the visible one publishes the
  // `window.__scene` / `window.__scenePane` handles, so a spec never reads a hidden pane's state.
  const pageActive = usePageActive();

  /**
   * Which head is on screen. A subject is drawn only once its own manifest has arrived and is not
   * still building — until then, and for ever if the subject has no head model, the guide is what
   * the pane shows, so a page that asks for a subject is never left with an empty stage.
   */
  // In MNI space the template IS the anatomy the user is choosing on, so no subject is requested.
  const wantedSubject = guide === "mni" ? null : subject;
  const subjectManifest = useSceneManifest(wantedSubject);
  const guideManifest = useGuideManifest(guide);
  /**
   * A subject is drawn only once its manifest has arrived, is not still building — and **can draw
   * the atlas the form names**.
   *
   * The last clause is not a nicety. A subject's scene carries its cortical parcellations and no
   * subcortical atlas at all (`tit/server/routes/scene.py` builds `parts` from the head mesh and
   * `atlases` from the `.annot` files; `labeling.nii.gz` is a *volume*, and only the packaged guide
   * freezes a surface for it). Drawing the subject for a subcortical target would therefore show
   * plain grey cortex with nothing pickable on it, which is worse than the guide: the user's target
   * would have no anatomy at all. So the pane falls back, and says which head it is showing.
   */
  const subjectReady = !!wantedSubject && !!subjectManifest.data && !subjectManifest.data.building;
  const subjectHasAtlas =
    !subjectReady ||
    !atlas ||
    mode === "montage" ||
    (subjectManifest.data?.atlases ?? []).some((entry) => String(entry.id) === atlas);
  const drawnSubject = subjectReady && subjectHasAtlas ? wantedSubject : null;
  const manifest = drawnSubject ? subjectManifest : guideManifest;
  const manifestData = manifest.data as GuideManifest | SceneManifest | undefined;
  const guideId = drawnSubject ? null : (guideManifest.data?.guide?.id ?? null);

  /**
   * A placement gesture needs a real head to pick a millimetre off; on the guide it is refused.
   *
   * `placedMarkers` without `onPlace` is the read-only case — a saved free-hand set shown where it
   * will stimulate. It picks nothing: the dots are coordinates, not electrode names, so an
   * electrode gesture over them would write a millimetre's label into a montage pair.
   */
  const showingPlacements = !!placedMarkers;
  /**
   * Outside `montage`, a cap is drawn only when the page offers both a net and a writer for it:
   * the Optimizer's Ex/mEx rows. The user then chooses which of the two selections a click edits —
   * the target regions or the electrode buckets — and `region` stays the default, because the
   * target is what the page is otherwise for.
   */
  const capOffered = mode !== "montage" && !!electrodeNet && !!onElectrodePick;
  const [pickKind, setPickKind] = useState<"region" | "electrode">("region");
  const gesture: SceneGesture =
    onPlace && drawnSubject
      ? "place"
      : showingPlacements
        ? "none"
        : mode === "montage"
          ? "electrode"
          : capOffered && pickKind === "electrode"
            ? "electrode"
            : onRegionsChange
              ? "region"
              : "none";

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
      onAtlasChange?.(next, (manifestData?.atlases.find((entry) => entry.id === next) as { kind?: string } | undefined)?.kind);
    },
    [onAtlasChange, manifestData],
  );

  /**
   * Which surface part carries the drawn atlas' per-vertex labels.
   *
   * The manifest says so (`atlases[].aligned_to`), because an MNI guide packages one surface per
   * atlas volume — CIT168's regions are not Morel's geometry — and a hard-coded `"subcortical"`
   * would draw one atlas' anatomy with another's labels. `kind` is the fallback for the older
   * manifests that carry no `aligned_to`.
   */
  const atlasEntry = manifestData?.atlases.find((entry) => entry.id === effectiveAtlas) as
    | { kind?: string; aligned_to?: string }
    | undefined;
  const atlasPart = atlasEntry?.aligned_to ?? (atlasEntry?.kind === "subcortical" ? "subcortical" : "gm");

  // Both hook sets always run (a `useQueries` with an empty list issues nothing), so switching
  // between the guide and a subject never changes the hook order.
  const allGuideRequests = useGuideSurfaceRequests(drawnSubject ? undefined : guideManifest.data, guide);
  const guideRequests = useMemo(() => allGuideRequests.filter((part) => part.id === "skin" || part.id === atlasPart), [allGuideRequests, atlasPart]);
  const guideSurfaces = useGuideSurfaces(guideRequests);
  const subjectRequests = useSceneSurfaceRequests(drawnSubject, subjectManifest.data);
  const subjectSurfaces = useSceneSurfaces(drawnSubject, subjectRequests);
  const surfaceRequests = drawnSubject ? subjectRequests : guideRequests;
  const surfaces = drawnSubject ? subjectSurfaces : guideSurfaces;

  /** Only a net the MANIFEST lists is fetched; a catalog net the guide does not have is a note,
   *  not an error — the montage still works perfectly well from the form. */
  const wantedNet = mode === "montage" ? net : capOffered ? electrodeNet : null;
  /** The manifest's own spelling of the wanted net — the two catalogs disagree about the `.csv`
   *  suffix (`pages/optimizer/nets.ts`), and the fetch has to use the manifest's. */
  const listedNet =
    (wantedNet ? manifestData?.nets.find((entry) => bareNet(entry.name) === bareNet(wantedNet))?.name : undefined) ?? null;
  const netMissing = !!wantedNet && !!manifestData && !listedNet;
  const guideElectrodes = useGuideElectrodes(!drawnSubject ? listedNet : null, guide);
  const subjectElectrodes = useSceneElectrodes(drawnSubject, listedNet);
  const electrodes = drawnSubject ? subjectElectrodes : guideElectrodes;
  const guideRegionsQuery = useGuideRegions(drawnSubject ? null : effectiveAtlas, guide);
  const subjectRegionsQuery = useSceneRegions(drawnSubject, effectiveAtlas);
  const regionsQuery = drawnSubject ? subjectRegionsQuery : guideRegionsQuery;
  const legend = useMemo<SceneLegendRow[]>(
    () => (regionsQuery.data ? (regionsQuery.data.legend as SceneLegendRow[]) : []),
    [regionsQuery.data],
  );
  const guideLabels = useGuideLabels(drawnSubject ? null : effectiveAtlas, legend.length > 0, guide);
  const subjectLabels = useSceneLabels(drawnSubject, effectiveAtlas, legend.length > 0);
  const labels = drawnSubject ? subjectLabels : guideLabels;

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
  const gmData = surfaces[surfaceRequests.findIndex((part) => part.id === atlasPart)]?.data ?? null;
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
        id: atlasPart,
        label: atlasPart === "gm" ? "GM" : atlasPart === "subcortical" ? "Subcortical regions" : "Atlas regions",
        positions: gmData.positions,
        indices: gmData.indices,
        labels: alignment.aligned ? (labelData?.labels ?? null) : null,
        color: SCENE_PALETTE.gm,
        // Always fully opaque, with no slider: the cortex is the anatomy being aimed at, not a
        // veil over something behind it.
        opacity: 1,
        opacityLocked: true,
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
        // Opaque while electrodes are being read off it OR placed on it: a translucent scalp
        // hides the markers round the back, and a click has to land on the surface the user sees.
        opacity: gesture === "electrode" || gesture === "place" || showingPlacements ? 1 : (DEFAULT_OPACITY.skin ?? 0.22),
        order: 1,
      });
    }
    return out.length > 0 ? out : NO_PARTS;
  }, [gmData, skinData, labelData, alignment.aligned, gesture, showingPlacements, atlasPart]);

  const box6 = (box: number[] | null | undefined): Bounds | undefined =>
    box && box.length === 6 ? (box as Bounds) : undefined;
  const bounds = useMemo<Bounds | undefined>(() => box6(manifestData?.bbox), [manifestData]);
  /** What to FRAME when it is smaller than what to draw: the head with the neck cut off at the
   *  lowest grey-matter vertex. The server decides which millimetre that is — it has the mesh. */
  const focus = useMemo<Bounds | undefined>(() => box6(manifestData?.focus_bbox), [manifestData]);

  // ---- montage -------------------------------------------------------------------------------
  const activePairs = useMemo<Pair[]>(() => pairs ?? [], [pairs]);
  // The Simulator's channels come from its pairs; the Optimizer's come from its buckets, already
  // reduced to the same "name -> channel" shape by the page that owns them.
  const pairChannels = useMemo(() => channelByElectrode(activePairs), [activePairs]);
  const channels = mode === "montage" ? pairChannels : (electrodeChannels ?? {});
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

  /** When the page supplies markers they ARE the markers — the positions it is collecting, or the
   *  saved set it is showing — and the net's electrodes stand down. */
  // Never display subject coordinates on the packaged reference head while extraction is pending.
  const markers = placedMarkers ? (drawnSubject ? placedMarkers : NO_MARKERS) : (gesture === "electrode" ? electrodeMarkers : NO_MARKERS);
  const displacements = useMemo(() => drawnSubject && originalPositions
    ? capDisplacements(originalPositions, activePairs, electrodeMarkers) : undefined,
  [drawnSubject, originalPositions, activePairs, electrodeMarkers]);

  // ---- selection -----------------------------------------------------------------------------
  const formRegions = useMemo<SceneRegionRef[]>(() => regions ?? [], [regions]);
  const selection = useMemo<SceneSelection>(() => {
    if (gesture === "electrode") {
      // The Optimizer's buckets say everything through the hue (an electrode's colour is its whole
      // state), and the ROI stays painted so the target is still visible while the cap is picked.
      if (mode !== "montage") return { markers: [], regions: wireLabelsFor(legend, formRegions) };
      return { markers: markerIndicesFor(electrodeMarkers, placedElectrodes(activePairs)), regions: [] };
    }
    // In `place` the selection IS the answer to "which electrode does the next click move", so it
    // is exactly the page's selected marker — the renderer rings and enlarges it.
    if (gesture === "place") return { markers: selectedMarkers ?? [], regions: [] };
    return { markers: [], regions: wireLabelsFor(legend, formRegions) };
  }, [mode, gesture, electrodeMarkers, activePairs, legend, formRegions, selectedMarkers]);

  // ---- picking -------------------------------------------------------------------------------
  const onPick = useCallback(
    (target: PickTarget | null) => {
      if (!target) return;
      if (gesture === "place" && target.kind === "marker") {
        onPlacedPick?.(target.index);
        return;
      }
      if (gesture === "electrode" && target.kind === "marker") {
        const name = electrodeMarkers[target.index]?.id;
        if (!name) return;
        // The Optimizer: the row's ex/mEx form is the only owner of the buckets, so the pick is
        // handed straight to it and the new colours arrive back through `electrodeChannels`.
        if (mode !== "montage") {
          onElectrodePick?.(name);
          return;
        }
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
        if (picked) onRegionsChange?.(toggleRegion(formRegions, picked), effectiveAtlas ?? undefined);
      }
      // Deliberately nothing else. A pick on the guide names an electrode or a region; it can never
      // produce a coordinate, because these millimetres are `guide-ras`.
    },
    [mode, gesture, electrodeMarkers, onElectrodePick, onPairsChange, onRequestPairs, activePairs, cursor, legend, formRegions, onRegionsChange, onPlacedPick, effectiveAtlas],
  );

  /**
   * Where the click landed, not what it hit (`ScenePick.world`). The renderer reads the depth its
   * own pick pass rasterised, so this is a point ON the drawn anatomy — the skin, in practice,
   * because in `place` the skin is opaque and drawn in front of everything else.
   *
   * Guarded on `drawnSubject` a second time, deliberately: `gesture` already encodes it, and a
   * coordinate written into a run on the wrong head is wrong in a way nothing downstream can
   * detect, so the guard that prevents it is stated where the number is emitted.
   */
  const onPickAt = useCallback(
    (pick: ScenePick) => {
      if (gesture !== "place" || !drawnSubject || !pick.world) return;
      // A click that landed on an existing dot SELECTS it (`onPick` above); it must not also place
      // one, or every attempt to pick a dot up would drop a second one on top of it.
      if (pick.target?.kind === "marker") return;
      onPlace?.(pick.world);
    },
    [gesture, drawnSubject, onPlace],
  );

  const [hovered, setHovered] = useState<string | null>(null);
  const onHoverChange = useCallback(
    (target: PickTarget | null) => {
      if (gesture === "place") {
        onPlacedHover?.(target?.kind === "marker" ? target.index : null);
        return setHovered(target?.kind === "marker" ? (placedMarkers?.[target.index]?.label ?? null) : null);
      }
      if (!target) return setHovered(null);
      if (target.kind === "marker") return setHovered(electrodeMarkers[target.index]?.label ?? null);
      const row = legend.find((entry) => entry.label === target.index);
      setHovered(row ? `${row.name}${row.hemi ? ` · ${row.hemi}` : ""}` : null);
    },
    [gesture, onPlacedHover, placedMarkers, electrodeMarkers, legend],
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
    if (state === "loading")
      return drawnSubject
        ? `Loading ${drawnSubject}'s head model…`
        : guide === "mni"
          ? "Loading the MNI152 template…"
          : "Loading the guide head model…";
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
    () => formRegions.filter((region) => legend.some((row) => row.id === region.id && (row.hemi || undefined) === region.hemi)),
    [formRegions, legend],
  );

  /**
   * The per-label colour texture the canvas paints regions with: the `.annot` colour table's own
   * RGB for a cortical parcellation, `labeling_LUT.txt`'s for a subcortical volume label. Both
   * already arrive on `legend[].color` — the server has emitted them since the legend existed —
   * so this is only the packing, and it is memoised on the legend because it is an upload.
   */
  const labelColors = useMemo(() => buildLabelColors(legend), [legend]);

  const paneLegend = useMemo<LegendEntry[]>(() => {
    const rows: LegendEntry[] = [];
    if (gesture !== "electrode" && effectiveAtlas && legend.length > 0) {
      rows.push({ key: "atlas", label: effectiveAtlas, color: SCENE_PALETTE.dim, detail: `${legend.length} regions` });
      for (const region of selectedRegionRows) {
        // The swatch is the colour the region is actually painted in — its own, not one blue for
        // all of them. A legend whose swatches all match cannot tell a user which patch is which.
        const row = legend.find((entry) => entry.id === region.id && (entry.hemi || undefined) === region.hemi);
        const hex = row ? labelSwatchColor(legend, row.label) : null;
        rows.push({
          key: `roi-${region.hemi ?? ""}-${region.id}`,
          label: region.name,
          color: hex ? hexToRgb(hex) : SCENE_PALETTE.selected,
          detail: region.hemi ?? undefined,
        });
      }
    }
    return rows;
  }, [gesture, effectiveAtlas, legend, selectedRegionRows]);

  /** One phrase saying what a click does — the pane's own instruction, never a tooltip. */
  const hint = ((): string => {
    if (note) return note;
    if (netMissing)
      return mode === "montage"
        ? `The guide has no ${net} electrode positions — the montage still works from the form.`
        : `This head model has no ${electrodeNet} electrode positions — the buckets still work from the form.`;
    if (sideError) return sideError instanceof SceneError ? sideError.message : "Some of this scene could not be loaded.";
    if (gesture === "electrode" && mode !== "montage") return "Click an electrode to add or remove it from the active bucket.";
    if (gesture === "electrode") {
      return activePairs.length === 0
        ? "Click an electrode to start a montage."
        : `Click an electrode to fill ${slotLabel(activePairs, cursor)}.`;
    }
    if (gesture === "region") return "Click a region to add or remove it from the ROI.";
    // Deliberately nothing (maintainer, 2026-09-06: *"remove that 'E1 is selected place blah blah
    // blah' — these instructions are unnecessary"*). The selected row and its ringed dot say which
    // electrode a click moves; a sentence repeating it is copy the user reads once and then reads
    // past for ever.
    if (gesture === "place") return "";
    if (showingPlacements) return `${placedMarkers.length} placed positions${drawnSubject ? ` on ${drawnSubject}` : ""}.`;
    if (subjectReady && !subjectHasAtlas)
      return `${wantedSubject} has no ${atlas} of its own — showing the reference head, where that atlas is packaged.`;
    if (guide === "mni") return "MNI152 template — the ROI is chosen here and transformed into each subject before the job runs.";
    if (wantedSubject && !drawnSubject) {
      // Three states, each a sentence, never an error box: the server's own 404 detail names the
      // missing file, and a build in progress says so rather than looking broken.
      if (subjectManifest.error) {
        return subjectManifest.error instanceof SceneError
          ? `${subjectManifest.error.message} Showing the reference head instead.`
          : `${wantedSubject} has no head model to draw yet — showing the reference head instead.`;
      }
      return `Building ${wantedSubject}'s head model for the preview — showing the reference head meanwhile.`;
    }
    if (drawnSubject) return `${drawnSubject}'s own head model.`;
    return "Reference anatomy — a guide for choosing names, not this subject's head.";
  })();

  // ---- the debug handle ----------------------------------------------------------------------
  useEffect(() => {
    if (!SCENE_DEBUG || !pageActive) return;
    const handle: ScenePaneDebug = {
      mode,
      gesture,
      subject: drawnSubject,
      guide: guideId,
      guideId: drawnSubject ? null : guide,
      space: manifestData?.space ?? null,
      net: mode === "montage" ? net : (listedNet ?? electrodeNet),
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
      markerChannels: Object.fromEntries(
        markers.flatMap((marker) => (marker.channel === undefined ? [] : [[marker.id, marker.channel] as const])),
      ),
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
  }, [pageActive, mode, gesture, drawnSubject, guideId, guide, manifestData, net, effectiveAtlas, state, message, parts, markers, legend, selection, selectedRegionRows, hovered]);

  const atlasOptions = useMemo(
    () => (manifestData?.atlases ?? []).map((entry) => ({ value: String(entry.id), label: entry.id === "labeling.nii.gz" ? "Subcortical (labeling.nii.gz)" : String(entry.id) })),
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
      data-pick={capOffered ? pickKind : ""}
    >
      {showing || gesture === "electrode" ? (
        <div className="scene-pane-head">
          {showing ? (
            <p className="scene-pane-showing" data-testid="scene-pane-showing">
              Showing: <strong>{showing.montage}</strong> · {showing.net}
            </p>
          ) : null}
          {gesture === "electrode" ? (
            mode === "montage" ? (
              <ChannelLegend pairs={activePairs} activeChannel={activeChannel} onActivate={activateChannel} />
            ) : (
              electrodeLegend
            )
          ) : null}
        </div>
      ) : null}
      {wantsRegions && atlasOptions.length > 0 ? (
        <div className="scene-pane-atlas" data-testid="scene-pane-atlas">
          {toolbarLead}
          {/* Two selections on one pane, one gesture at a time: the pane can only state what the
              next click does if the user has said which of the two it edits. */}
          {capOffered ? (
            <SegmentedControl
              aria-label="What a click edits"
              value={pickKind}
              onValueChange={(value) => setPickKind(value === "electrode" ? "electrode" : "region")}
              options={[
                { value: "region", label: "Target" },
                { value: "electrode", label: "Electrodes" },
              ]}
            />
          ) : null}
          <Select
            aria-label="Atlas"
            value={effectiveAtlas ?? ""}
            onValueChange={chooseAtlas}
            options={atlasOptions}
          />
          {onRegionsChange ? (
            <Button
              disabled={formRegions.length === 0}
              onClick={() => onRegionsChange([], effectiveAtlas ?? undefined)}
            >
              Clear selection
            </Button>
          ) : null}
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
            connections={displacements}
            /*
             * Electrodes lie on the scalp, so the scalp hides the ones round the back — except the
             * page's own placements, which are never hidden.
             *
             * Measured 2026-09-06: a free-hand dot sits EXACTLY on the surface it was picked off,
             * and the occlusion pre-pass's 4 mm bias is not enough to keep it in front of an opaque
             * one — every dot the user placed was invisible. "The electrode I just put down is not
             * there" is a worse failure than "an electrode round the back shows through", and the
             * dots are four to eight, not 185.
             */
            markersOccluded={!placedMarkers}
            /* A placement dot is one of four to eight, carries a name and has to be aimed at; an
               EEG net's is one of 185. */
            markerScale={placedMarkers ? 1.5 : undefined}
            /* An electrode goes ON the skin — including a skin the user has turned down to 0.22 to
               see the cortex through. Without this the click reads through it and the electrode
               lands on the grey matter behind. */
            pickAnySurface={gesture === "place"}
            highlight={highlightMarkers}
            /* Four to eight dots the user has to tell apart by name — the fog a 185-electrode net's
               names would be is not this pane's state. */
            namesOn={gesture === "place" ? true : undefined}
            publishDebugHandle={pageActive}
            selection={selection}
            onPick={onPick}
            onPickAt={onPickAt}
            onHoverChange={onHoverChange}
            bounds={bounds}
            focus={focus}
            legend={paneLegend}
            labelColors={labelColors}
            label={`${drawnSubject ?? guideId ?? "guide"} head model`}
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
