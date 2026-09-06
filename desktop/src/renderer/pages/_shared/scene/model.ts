/**
 * The pure core of `<ScenePane>` — every mapping between what the *form* holds and what the
 * *scene* draws (plan of record §S6: "the pane is never the only way", both directions in sync).
 *
 * It is a separate, renderer-free, DOM-free module because the two directions of the sync are the
 * thing that can silently disagree, and a function that translates a montage pair list into marker
 * channels can be checked against arithmetic instead of against a screenshot. Nothing here imports
 * React, `fetch` or WebGL.
 */
import type { SceneElectrode, SceneLegendRow } from "./api";
import type { Rgb, SceneMarker } from "../../../scene/types";
import { SCENE_PALETTE } from "../../../scene/palette";

/** World millimetres. The renderer's `Rgb` and this are the same three-number tuple; naming both
 *  is what keeps a colour out of a coordinate slot at the type level. */
type Vec3 = Rgb;

/**
 * The renderer's own vocabulary, re-exported rather than re-declared.
 *
 * There is exactly ONE palette and ONE marker/selection shape in the app (`renderer/scene/`), and
 * this module is the seam the pages import it through. When these were two declarations that
 * happened to agree, the pane and the form chips drifted the day one of them changed — a "pair 2"
 * that was orange in the editor and green in the scene.
 */
export type { Rgb as Vec3, SceneMarker } from "../../../scene/types";
export type { SceneSelection } from "../../../scene/selection";
export { SCENE_PALETTE, DEFAULT_OPACITY, type ScenePalette } from "../../../scene/palette";

/** A region as the ROI picker holds it (`pages/_shared/roi/types.ts`'s `RoiRegion`). */
export interface SceneRegionRef {
  id: number;
  name: string;
  hemi?: "lh" | "rh";
}

/** `hemi:id` — the same key `RoiPicker` uses, so the two lists can be compared without a join. */
export function regionKey(region: { id: number; hemi?: string | null }): string {
  return region.hemi ? `${region.hemi}:${region.id}` : String(region.id);
}

/**
 * The `uint16` payload values for a form's region list.
 *
 * Regions the atlas does not contain are dropped rather than mapped to `0`: `0` means "no region"
 * in the payload, so mapping an unknown region onto it would highlight every unlabelled vertex —
 * the cerebellum and brainstem included (lane SCA's A1).
 */
export function wireLabelsFor(legend: SceneLegendRow[], regions: { id: number; hemi?: string | null }[]): number[] {
  const byKey = new Map(legend.map((row) => [regionKey(row), row.label]));
  const out: number[] = [];
  for (const region of regions) {
    const label = byKey.get(regionKey(region));
    if (label !== undefined && !out.includes(label)) out.push(label);
  }
  return out;
}

/**
 * **The one region-selection operation**, shared by `<ScenePane>` and `<RoiPicker>` (N3).
 *
 * A click in the 3D pane and a click on a chip in the form are the same edit of the same list, so
 * they run the same function: a region already in the list is removed, one that is not is
 * appended. Two toggles that merely looked alike is how a region ends up selected in the pane and
 * absent from the config that runs — the pane is a view of the form's list, never a second one.
 */
export function toggleRegion<T extends { id: number; hemi?: "lh" | "rh" }>(regions: T[], picked: T): T[] {
  const key = regionKey(picked);
  return regions.some((r) => regionKey(r) === key) ? regions.filter((r) => regionKey(r) !== key) : [...regions, picked];
}

/** The inverse: the form-shaped regions for a set of payload labels, in the order given. */
export function regionsFromWireLabels(legend: SceneLegendRow[], labels: number[]): SceneRegionRef[] {
  const byLabel = new Map(legend.map((row) => [row.label, row]));
  const out: SceneRegionRef[] = [];
  for (const label of labels) {
    const row = byLabel.get(label);
    if (row) out.push({ id: row.id, name: row.name, hemi: row.hemi });
  }
  return out;
}

// ---------------------------------------------------------------------------- montage mode

/** An electrode pair as the montage editor holds it (`ui/ElectrodePairsEditor.tsx`). */
export type Pair = [string, string];

/** Flattened slot index -> `pairs[Math.floor(i / 2)][i % 2]`. */
export function slotCount(pairs: Pair[]): number {
  return pairs.length * 2;
}

export function slotAt(pairs: Pair[], slot: number): string {
  return pairs[Math.floor(slot / 2)]?.[slot % 2] ?? "";
}

export function withSlot(pairs: Pair[], slot: number, value: string): Pair[] {
  const row = Math.floor(slot / 2);
  const col = slot % 2;
  return pairs.map((pair, i) => (i === row ? ((col === 0 ? [value, pair[1]] : [pair[0], value]) as Pair) : pair));
}

/** The flattened slot an electrode already occupies, or `-1`. */
export function slotOf(pairs: Pair[], name: string): number {
  for (let i = 0; i < slotCount(pairs); i += 1) if (slotAt(pairs, i) === name) return i;
  return -1;
}

/**
 * The next slot the cursor should sit on after writing `from`: the next EMPTY slot, scanning
 * cyclically from `from + 1`, and simply `from + 1` (wrapped) when every slot is full.
 *
 * Cyclic rather than clamped so a user filling a 4-pair mTI montage never has to reach for the
 * form to get back to pair 1 after the last slot.
 */
export function advanceSlot(pairs: Pair[], from: number): number {
  const n = slotCount(pairs);
  if (n === 0) return 0;
  for (let step = 1; step <= n; step += 1) {
    const slot = (from + step) % n;
    if (slotAt(pairs, slot) === "") return slot;
  }
  return (from + 1) % n;
}

/** The first empty slot, or `0` when the montage is full — where a fresh cursor starts. */
export function firstEmptySlot(pairs: Pair[]): number {
  for (let i = 0; i < slotCount(pairs); i += 1) if (slotAt(pairs, i) === "") return i;
  return 0;
}

export interface PickResult {
  pairs: Pair[];
  cursor: number;
}

/**
 * What clicking electrode `name` in the pane means (plan §2.4, `montage`): **toggle it into the
 * current pair slot**.
 *
 * - already placed -> it is removed and the cursor moves to the slot it vacated, so a mis-click is
 *   undone by clicking the same electrode again and the next click refills that same slot;
 * - not placed -> it is written at the cursor, which then advances to the next empty slot.
 *
 * The cursor is explicit (and shown in the pane) rather than "the first empty slot" recomputed
 * every click: without it, replacing one electrode of a full montage would be impossible from the
 * scene — every click would find no empty slot and have nowhere to go.
 */
export function applyElectrodePick(pairs: Pair[], cursor: number, name: string): PickResult {
  if (slotCount(pairs) === 0) return { pairs, cursor: 0 };
  const existing = slotOf(pairs, name);
  if (existing >= 0) return { pairs: withSlot(pairs, existing, ""), cursor: existing };
  const slot = cursor % slotCount(pairs);
  const next = withSlot(pairs, slot, name);
  return { pairs: next, cursor: advanceSlot(next, slot) };
}

/** "Pair 2 · B" — what the pane's status line says the next click will fill. */
export function slotLabel(pairs: Pair[], cursor: number): string {
  if (slotCount(pairs) === 0) return "no pairs";
  const slot = cursor % slotCount(pairs);
  return `Pair ${Math.floor(slot / 2) + 1} · ${slot % 2 === 0 ? "A" : "B"}`;
}

/** Electrode name -> the pair (channel) index it belongs to. Later pairs win a duplicate. */
export function channelByElectrode(pairs: Pair[]): Record<string, number> {
  const out: Record<string, number> = {};
  pairs.forEach((pair, i) => {
    for (const name of pair) if (name) out[name] = i;
  });
  return out;
}

/**
 * The markers for one EEG net.
 *
 * `channel` is the pair index, which is what colours the marker per channel
 * (the shared channel palette above); an electrode in no pair has none and draws neutral.
 */
export function markersFromElectrodes(
  electrodes: SceneElectrode[],
  channels: Record<string, number> = {},
): SceneMarker[] {
  return electrodes.map((electrode) => {
    const channel = channels[electrode.name];
    return {
      id: electrode.name,
      label: electrode.name,
      world: electrode.world as Vec3,
      ...(channel === undefined ? {} : { channel }),
    };
  });
}

/** Indices into `markers` for a list of electrode names, skipping names the net does not have. */
export function markerIndicesFor(markers: SceneMarker[], names: string[]): number[] {
  const byId = new Map(markers.map((marker, i) => [marker.id, i]));
  const out: number[] = [];
  for (const name of names) {
    const index = byId.get(name);
    if (index !== undefined && !out.includes(index)) out.push(index);
  }
  return out;
}

/** Every electrode currently placed in the montage, in slot order — the pane's controlled
 *  selection, so unticking a pair in the form immediately un-highlights its markers. */
export function placedElectrodes(pairs: Pair[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < slotCount(pairs); i += 1) {
    const name = slotAt(pairs, i);
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

// ---------------------------------------------------------------------------- sphere mode

export interface RegionCentroid {
  label: number;
  id: number;
  hemi: "lh" | "rh";
  name: string;
  /** The served vertex NEAREST the region's centroid, never the centroid itself. */
  world: Vec3;
  vertices: number;
}

/**
 * One point per atlas region: the served `gm` vertex nearest that region's centroid.
 *
 * Snapped to a real vertex rather than left at the arithmetic centroid because a centroid of a
 * folded cortical region sits in white matter — up to a couple of centimetres off the surface for
 * a C-shaped region like the superior temporal gyrus — and a sphere centred there is not the
 * target the user clicked. Every served vertex is an untouched mesh vertex (lane SCA's A2), so the
 * snapped point is a coordinate the head model actually contains.
 */
export function regionCentroids(
  positions: Float32Array,
  labels: Uint16Array,
  legend: SceneLegendRow[],
  minVertices = 1,
): RegionCentroid[] {
  const sums = new Map<number, { x: number; y: number; z: number; n: number }>();
  for (let v = 0; v < labels.length; v += 1) {
    const label = labels[v] as number;
    if (label === 0) continue;
    let acc = sums.get(label);
    if (!acc) {
      acc = { x: 0, y: 0, z: 0, n: 0 };
      sums.set(label, acc);
    }
    acc.x += positions[v * 3] as number;
    acc.y += positions[v * 3 + 1] as number;
    acc.z += positions[v * 3 + 2] as number;
    acc.n += 1;
  }
  const best = new Map<number, { d2: number; world: Vec3 }>();
  for (let v = 0; v < labels.length; v += 1) {
    const label = labels[v] as number;
    const acc = sums.get(label);
    if (!acc) continue;
    const cx = acc.x / acc.n;
    const cy = acc.y / acc.n;
    const cz = acc.z / acc.n;
    const x = positions[v * 3] as number;
    const y = positions[v * 3 + 1] as number;
    const z = positions[v * 3 + 2] as number;
    const d2 = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2;
    const current = best.get(label);
    if (!current || d2 < current.d2) best.set(label, { d2, world: [x, y, z] });
  }
  const out: RegionCentroid[] = [];
  for (const row of legend) {
    const acc = sums.get(row.label);
    const hit = best.get(row.label);
    if (!acc || !hit || acc.n < minVertices) continue;
    out.push({ label: row.label, id: row.id, hemi: row.hemi, name: row.name, world: hit.world, vertices: acc.n });
  }
  return out;
}

/**
 * Markers for the sphere gesture: the current centre, and nothing else.
 *
 * It used to be one marker per atlas-region centroid as well, because a click could only name a
 * marker and the nearest centroid was the closest thing to "where you clicked" the old pick
 * contract allowed (lane SCC's C11). The embedded Tetravox picker reports the world point now, so
 * the centroids are gone and a click lands where it landed.
 */
export function sphereMarkers(centre: Vec3 | null): SceneMarker[] {
  return centre ? [{ id: "sphere-centre", label: "Sphere centre", world: centre, channel: 0 }] : [];
}

/** Rounded to 0.1 mm — a sphere centre typed into the form is a millimetre coordinate, and 15
 *  significant digits in an `x` field is noise the user then has to read past. */
export function roundCoord(world: Vec3): { x: number; y: number; z: number } {
  const r = (v: number): number => Math.round(v * 10) / 10;
  return { x: r(world[0]), y: r(world[1]), z: r(world[2]) };
}

/** The scene's own channel colour for a pair index, as a CSS colour — the form's pair rows use it
 *  so "pair 2 is orange" means the same thing in the editor and in the pane. */
export function channelCss(channel: number): string {
  const rgb = SCENE_PALETTE.channels[channel % SCENE_PALETTE.channels.length] ?? SCENE_PALETTE.marker;
  return `rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})`;
}
