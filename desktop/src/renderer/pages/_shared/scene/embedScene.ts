/**
 * Pure Tetravox ViewSpec builders for the run-page scene pane.
 *
 * The pane is still a form control — electrodes, atlas regions and sphere centres are owned by the
 * page — but the pixels are now the embedded Tetravox renderer's. This file is the narrow adapter:
 * it names the GIfTI scene-route URLs as mesh datasets, writes inline protocol-2 points, and maps
 * protocol-2 pick events back to the form's region/electrode identities.
 */
import type { Camera3D, EmbedLayer, EmbedPoint, EmbedViewSpec, PickMessage, ProbeResult, vec3, vec4 } from "../../../viewer/protocol";
import type { GuideManifest, GuideRegions, SceneLegendRow } from "./api";
import { SCENE_PALETTE, regionsFromWireLabels, wireLabelsFor, type SceneMarker, type SceneRegionRef, type SceneSelection, type Vec3 } from "./model";
import type { SceneGesture, ScenePaneMode } from "./ScenePane";

export const POINTS_LAYER_NAME = "TI pane points";
export const LABEL_FIELD_NAME = "regions";

const FOV_Y_DEG = 35;
const MIN_CAMERA_DISTANCE_MM = 160;
const DEFAULT_CAMERA: Camera3D = {
  target: [0, 0, 0],
  distance: 350,
  rotation: [0, 0, 0, 1],
  fovYDeg: FOV_Y_DEG,
  orthographic: false,
  near: 1,
  far: 1400,
};

export function labelLayerName(atlas: string): string {
  return `TI pane atlas · ${atlas}`;
}

/** Add or replace `format=gii` while preserving every other query parameter. */
export function sceneGiiUrl(url: string): string {
  const hashAt = url.indexOf("#");
  const hash = hashAt >= 0 ? url.slice(hashAt) : "";
  const withoutHash = hashAt >= 0 ? url.slice(0, hashAt) : url;
  const queryAt = withoutHash.indexOf("?");
  const path = queryAt >= 0 ? withoutHash.slice(0, queryAt) : withoutHash;
  const params = new URLSearchParams(queryAt >= 0 ? withoutHash.slice(queryAt + 1) : "");
  params.set("format", "gii");
  return `${path}?${params.toString()}${hash}`;
}

function rgba(rgb: readonly [number, number, number], alpha = 1): vec4 {
  return [rgb[0], rgb[1], rgb[2], alpha];
}

export function channelColor(channel: number | undefined): vec4 {
  if (channel === undefined) return rgba(SCENE_PALETTE.idle);
  return rgba(SCENE_PALETTE.channels[channel % SCENE_PALETTE.channels.length] ?? SCENE_PALETTE.marker);
}

/** Layer-level dot radius in device-independent pixels (plan B1). */
export const DOT_RADIUS_PX = 5;
/** What an active channel's dot would be, if the embed honoured a per-point dot radius. */
export const ACTIVE_DOT_RADIUS_PX = 7;

/**
 * Form markers -> protocol-2 inline points (plan §1-B, B1-B3).
 *
 * **Every point carries an explicit `color`**, including the idle ones, and that is not
 * redundancy. Measured against the live 0.4.0 bundle
 * (`assets/index-CdUrh5CF.js`, the `$b(point, stateColors)` normaliser):
 *
 * ```js
 * const t = n.state;
 * if (t === void 0 || t === "idle" || n.color !== void 0) return n;   // <- idle returns early
 * const s = e?.[t] ?? AL[t];
 * return { ...n, color: s };
 * ```
 *
 * so `stateColors.idle` is **never** consulted — an idle point with no `color` falls through to
 * the layer's `color`, and a layer-level `color` cannot also be the disabled colour. The layer
 * therefore keeps `stateColors.disabled` (which *is* consulted, because a point may not carry a
 * colour of its own) and the host writes idle grey and the channel hue per point.
 *
 * `state` is still set, because it is what the *pick* and the assertions read, and because a later
 * embed that honours `stateColors.idle` must not suddenly disagree with what is drawn.
 *
 * TODO(tetravox): the explicit idle `color` can go once the app runs against an embed built from
 * Tetravox 0.3.12 or later. Lane TX fixed `resolvePoint` upstream so an idle point with no colour
 * of its own now does take `stateColors.idle` (PR #35, commit `ebd814b`; see
 * `dev/notes/v3-tetravox-selection-pipeline/TX.md` §"Follow-up round"), but no release carries an
 * embed asset yet — the container still runs the hand-installed 0.4.0 this comment measures. Keep
 * writing the colour until `tit/tetravox/protocol.py`'s floor is a bundle that has the fix.
 */
export function pointsFromMarkers(
  markers: SceneMarker[],
  selection: SceneSelection,
  activeChannel: number | null = null,
): EmbedPoint[] {
  const selected = new Set(selection.markers.map((index) => markers[index]?.id).filter((id): id is string => !!id));
  return markers.map((marker, index) => {
    const isSelected = selected.has(marker.id);
    return {
      id: marker.id,
      // Names for the selected points only: 185 labels over a head is not a legend, it is a fog.
      // (The embed has no per-point hover event — see the lane note — so "and on hover" is not
      // expressible against 0.4.0.)
      ...(isSelected ? { name: marker.label } : {}),
      position: marker.world as vec3,
      state: isSelected ? "selected" : "idle",
      color: isSelected ? channelColor(marker.channel) : rgba(SCENE_PALETTE.idle),
      // Inert in embed 0.4.0: the dot radius is read from the LAYER only (`p1(layer)`), never
      // from the point. Sent anyway because it is the exact field the upstream fix should honour,
      // and asserted in the unit test so it cannot silently drift.
      ...(activeChannel !== null && marker.channel === activeChannel ? { radiusPx: ACTIVE_DOT_RADIUS_PX } : {}),
      group: marker.channel === undefined ? "net" : `pair-${marker.channel + 1}`,
      ordinal: index + 1,
    };
  });
}

/** One surface part, as either manifest shapes it — they are the same shape by contract. */
type ScenePart = GuideManifest["parts"][number];

function partById(manifest: GuideManifest, id: string): ScenePart | null {
  return manifest.parts.find((part) => part.id === id) ?? null;
}

function box6(box: number[] | null | undefined): [number, number, number, number, number, number] | null {
  if (!Array.isArray(box) || box.length !== 6) return null;
  if (!box.every((v) => Number.isFinite(v))) return null;
  return box as [number, number, number, number, number, number];
}

export function cameraForBox(box: number[] | null | undefined): Camera3D {
  const b = box6(box);
  if (b === null) return { ...DEFAULT_CAMERA, target: [...DEFAULT_CAMERA.target] as vec3, rotation: [...DEFAULT_CAMERA.rotation] as vec4 };
  const target: vec3 = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
  const dx = b[3] - b[0];
  const dy = b[4] - b[1];
  const dz = b[5] - b[2];
  const radius = Math.max(1, Math.hypot(dx, dy, dz) / 2);
  const distance = Math.max(MIN_CAMERA_DISTANCE_MM, (radius / Math.tan((FOV_Y_DEG * Math.PI) / 360)) * 1.28);
  return {
    ...DEFAULT_CAMERA,
    target,
    distance: Math.round(distance * 10) / 10,
    near: Math.max(0.1, Math.round(distance / 200)),
    far: Math.round((distance + radius * 4) * 10) / 10,
    rotation: [...DEFAULT_CAMERA.rotation] as vec4,
  };
}

function meshLayerBase(id: string, datasetId: string, name: string, opacity: number, pickable: boolean): Record<string, unknown> {
  return {
    id,
    datasetId,
    kind: "mesh",
    name,
    visible: true,
    opacity,
    pickable,
    edges: { surface: false, caps: false },
    edgeColor: [0, 0, 0, 1],
    edgeWidthPx: 1,
    flatShading: false,
    faceMode: "both",
    clip: { planes: [], caps: true, capColorMode: "inherit" },
    contoursIn2D: false,
    fillIn2D: false,
  };
}

function selectedLabelsForLayer(selection: SceneSelection): { visibleLabels?: number[] } {
  return selection.regions.length > 0 ? { visibleLabels: selection.regions } : {};
}

export interface BuildPaneSceneArgs {
  manifest: GuideManifest;
  mode: ScenePaneMode;
  gesture: SceneGesture;
  atlas: string | null;
  regions: GuideRegions | null;
  selection: SceneSelection;
  includePointsLayer: boolean;
}

export function buildPaneViewSpec({
  manifest,
  gesture,
  atlas,
  regions,
  selection,
  includePointsLayer,
}: BuildPaneSceneArgs): EmbedViewSpec | null {
  const skin = partById(manifest, "skin");
  const gm = partById(manifest, "gm");
  if (skin === null && gm === null) return null;

  const datasets: EmbedViewSpec["datasets"] = [];
  const layers: Record<string, unknown>[] = [];

  const addSurface = (id: string, part: ScenePart, name: string): string => {
    const datasetId = `ds-${id}`;
    // Every URL comes from the manifest itself, so the same builder draws the guide's
    // `/api/guide/*` payloads and (should a subject-scoped pane ever return) a subject's.
    const url = sceneGiiUrl(part.url);
    datasets.push({ id: datasetId, kind: "mesh", name: `${name}.gii`, path: url, absPath: url, fingerprint: part.fingerprint ?? "" });
    return datasetId;
  };

  let carrierDatasetId: string | null = null;
  let labelLayerId: string | null = null;

  if (atlas && regions && gm !== null) {
    const datasetId = `ds-labels-${atlas}`;
    const url = sceneGiiUrl(regions.url);
    datasets.push({ id: datasetId, kind: "mesh", name: `${atlas}.label.gii`, path: url, absPath: url, fingerprint: "" });
    labelLayerId = "layer-labels";
    layers.push({
      ...meshLayerBase(labelLayerId, datasetId, labelLayerName(atlas), 0.92, gesture === "region" || gesture === "sphere"),
      colorMode: "label",
      colormap: "viridis",
      label: { name: LABEL_FIELD_NAME, mode: "fill", outlineWidthPx: 1, ...selectedLabelsForLayer(selection) },
      showColorbar: false,
    });
    carrierDatasetId = datasetId;
  } else if (gm !== null) {
    const datasetId = addSurface("gm", gm, "Grey matter");
    layers.push({
      ...meshLayerBase("layer-gm", datasetId, "Grey matter", 0.55, false),
      colorMode: "solid",
      solidColor: rgba(SCENE_PALETTE.gm, 1),
      showColorbar: false,
    });
    carrierDatasetId = datasetId;
  }

  if (skin !== null) {
    const datasetId = addSurface("skin", skin, "Skin");
    layers.push({
      ...meshLayerBase("layer-skin", datasetId, "Skin", gesture === "electrode" ? 1 : 0.22, false),
      colorMode: "solid",
      solidColor: rgba(SCENE_PALETTE.skin, 1),
      showColorbar: false,
    });
    carrierDatasetId = carrierDatasetId ?? datasetId;
  }

  if (includePointsLayer && carrierDatasetId !== null) {
    const dots = gesture === "electrode";
    layers.push({
      id: "layer-points",
      datasetId: carrierDatasetId,
      kind: "points",
      name: POINTS_LAYER_NAME,
      visible: true,
      opacity: 1,
      pickable: true,
      points: [],
      // Electrodes are DOTS, not spheres: a sphere is a ring of shading around a position the
      // user is trying to read as one thing, and it changes size with the camera, so "which
      // electrodes are in pair 2" became a question about perspective.
      shape: dots ? "dot" : "sphere",
      ...(dots ? { dotRadiusPx: DOT_RADIUS_PX } : {}),
      radiusMm: gesture === "sphere" ? 4.5 : 4,
      // The layer fallback for a point that carries no colour of its own.
      color: rgba(SCENE_PALETTE.idle, 1),
      // `idle` is here for the day the embed consults it (0.3.12+, TX PR #35); `selected`
      // deliberately is NOT, because
      // one layer-level selected colour cannot encode which channel a dot belongs to (B2).
      stateColors: { idle: rgba(SCENE_PALETTE.idle, 1), disabled: rgba(SCENE_PALETTE.disabled, 1) },
      labelMode: dots ? "names" : "none",
      showLabels: dots,
      labelSource: "names",
      // The label takes the dot's colour, so "Fp1 is in pair 2" reads once, not twice.
      labelColorSource: "points",
      offPlaneOpacity: dots ? 0.35 : 0,
    });
  }

  const camera = cameraForBox(manifest.focus_bbox ?? manifest.bbox);
  const activeLayerId = includePointsLayer ? "layer-points" : (labelLayerId ?? (layers[0]?.id as string | undefined) ?? null);
  return {
    version: 2,
    datasets,
    layers,
    activeLayerId,
    layout: { kind: "3d-only", cells: ["view3d"] },
    view3d: { id: "view3d", camera, showSlicePlanes: false },
    cursor: camera.target,
    radiological: false,
    background: [0.058823529411764705, 0.06666666666666667, 0.08627450980392157, 1],
    lighting: { ambient: 0.25, headlight: true },
    annotations: {
      orientationLabels: true,
      cornerInfo: false,
      conventionBadge: true,
      scaleBar: false,
      colorbars: false,
      crosshair: false,
      orientationCube: true,
    },
  };
}

export function liveLayerId(layers: EmbedLayer[], predicate: (layer: EmbedLayer) => boolean): string | null {
  return layers.find(predicate)?.id ?? null;
}

export function pickLabel(pick: PickMessage, labelsLayerId: string | null): number | null {
  if (pick.label && (labelsLayerId === null || pick.label.layerId === labelsLayerId)) return pick.label.id;
  const row = pick.probe.rows.find((r) => {
    if (labelsLayerId !== null && r.layerId !== labelsLayerId) return false;
    return typeof r.labelId === "number" || typeof r.value === "number";
  });
  const value = typeof row?.labelId === "number" ? row.labelId : typeof row?.value === "number" ? row.value : null;
  return value !== null && Number.isFinite(value) && value > 0 ? value : null;
}

export function regionFromPick(pick: PickMessage, legend: SceneLegendRow[], labelsLayerId: string | null): SceneRegionRef | null {
  const label = pickLabel(pick, labelsLayerId);
  if (label === null) return null;
  return regionsFromWireLabels(legend, [label])[0] ?? null;
}

export function labelsForRegions(legend: SceneLegendRow[], regions: SceneRegionRef[] | undefined): number[] {
  return wireLabelsFor(legend, regions ?? []);
}

export function cameraPatchForScene(scene: EmbedViewSpec): Partial<Camera3D> | null {
  const camera = ((scene.view3d as { camera?: Camera3D } | undefined)?.camera ?? null) as Camera3D | null;
  if (camera === null) return null;
  return { target: camera.target, distance: camera.distance, rotation: camera.rotation };
}

export function pointLayerPredicate(layer: EmbedLayer): boolean {
  return layer.kind === "points" || layer.name === POINTS_LAYER_NAME;
}

export function labelLayerPredicate(atlas: string | null): (layer: EmbedLayer) => boolean {
  const name = atlas ? labelLayerName(atlas) : null;
  return (layer) => layer.kind === "mesh" && (name === null || layer.name === name);
}

export function copyProbe(result: ProbeResult): ProbeResult {
  return { ...result, rows: result.rows.map((row) => ({ ...row })) };
}

export function vecFromCentre(centre: { x?: number; y?: number; z?: number } | null | undefined): Vec3 | null {
  return centre && centre.x !== undefined && centre.y !== undefined && centre.z !== undefined ? [centre.x, centre.y, centre.z] : null;
}
