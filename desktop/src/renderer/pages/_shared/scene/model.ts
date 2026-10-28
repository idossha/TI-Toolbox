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
import type { ElectrodePad } from "../../../scene/electrodePose";
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
    if (row) out.push({ id: row.id, name: row.name, ...(row.hemi ? { hemi: row.hemi } : {}) });
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
  /** The montage's electrode size, for the Actual size view: the electrodes in a channel are drawn
   *  at that size with their gel, and the rest of the net is hidden. Absent, every electrode is the
   *  small cap marker. */
  pad?: ElectrodePad,
): SceneMarker[] {
  return electrodes.map((electrode) => {
    const channel = channels[electrode.name];
    return {
      id: electrode.name,
      label: electrode.name,
      world: electrode.world as Vec3,
      ...(channel === undefined ? {} : { channel }),
      ...(pad ? (channel === undefined ? { hidden: true } : { pad }) : {}),
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

/** The scene's own channel colour for a pair index, as a CSS colour — the form's pair rows use it
 *  so "pair 2 is orange" means the same thing in the editor and in the pane. */
export function channelCss(channel: number): string {
  const rgb = SCENE_PALETTE.channels[channel % SCENE_PALETTE.channels.length] ?? SCENE_PALETTE.marker;
  return `rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})`;
}

/**
 * Whether a labels payload belongs to the surface it is about to colour: same vertex count and the
 * same first and last positions. Both come from one packaged build, so this fails only on a
 * half-regenerated guide — and failing here shows "labels not applied" instead of a region
 * highlighted centimetres from the one clicked.
 */
export function labelsAlignment(
  surface: { vertexCount: number; positions: Float32Array },
  labels: { vertexCount: number; positions: Float32Array },
): { aligned: boolean; reason: string | null } {
  if (labels.vertexCount !== surface.vertexCount) {
    return { aligned: false, reason: `labels are for ${labels.vertexCount} vertices, the surface has ${surface.vertexCount}` };
  }
  const last = (surface.vertexCount - 1) * 3;
  const same = [0, 1, 2, last, last + 1, last + 2].every((i) => surface.positions[i] === labels.positions[i]);
  return { aligned: same, reason: same ? null : "the labels payload's vertices are not the surface's" };
}

/**
 * Whether the pane offers **Explode**: only on the MNI template (never a subject's own head, whose
 * atlases are cortical surfaces with nothing buried), and only once an atlas' labels are on the
 * drawn surface — there is nothing to pull apart before that.
 */
export function explodeOffered(guide: string, drawnSubject: string | null, atlasLabelled: boolean): boolean {
  return guide === "mni" && drawnSubject === null && atlasLabelled;
}
