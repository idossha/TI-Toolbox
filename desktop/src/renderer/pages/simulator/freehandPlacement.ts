/**
 * Clicking the subject's scalp fills the next free-hand position row — the model, with no React
 * and no WebGL in it (the same split `renderer/scene/`'s pure modules follow, and the reason this
 * behaviour can be tested without a GPU).
 *
 * This is v2.5.0's `tit/gui/extensions/electrode_placement.py` in one file's worth of rules:
 *
 *  - `onMarkerPlaced` named a marker `E<n><polarity>` from its **row index**, `+` on even rows and
 *    `−` on odd ones, so rows 0..3 are `E1+ E1− E2+ E2−` — the pairs the simulation runs;
 *  - `deleteChecked` **renumbered every remaining marker** afterwards, because a table reading
 *    `E1+ E2− E3+` would claim pairs that do not exist;
 *  - and a marker was a point on the skin surface in the head mesh's own millimetres, which is the
 *    frame `m2m_<id>/stim_configs/*.json` stores and `tit/catalog.py::_read_freehand_file` reads.
 *
 * The one thing v3 changes: the Qt widget appended a row per click and nothing else, while the v3
 * editor opens with four blank rows (its own "4 positions = 2 pairs" default). A click therefore
 * fills the first **blank** row and only appends once they are used up — otherwise the first four
 * clicks would leave four empty rows above the four they wrote, and the Save button would stay
 * disabled with no visible reason.
 */
import type { SceneMarker } from "../../scene";
import type { ElectrodePosition } from "./api";

/** Millimetres, to the same 0.1 mm step the editor's `NumberInput`s use. A pick carries float
 *  noise from the depth buffer that no user typed and no user can reproduce. */
export function roundMm(value: number): number {
  return Math.round(value * 10) / 10;
}

/** `E1+`, `E1-`, `E2+`, … from a row index. The `-` is ASCII, not a minus sign: it goes into a
 *  JSON key that SimNIBS reads back. */
export function autoLabel(index: number): string {
  return `E${Math.floor(index / 2) + 1}${index % 2 === 0 ? "+" : "-"}`;
}

/** A label this module owns, and may therefore renumber. A name the user typed is left alone. */
const AUTO_LABEL = /^E\d+[+-]$/;

/**
 * A row nothing has been placed into: the origin, and no name of the user's own.
 *
 * The auto label counts as blank on purpose. `renumber` names every row so the empty table already
 * reads `E1+ E1− E2+ E2−` — the plan, before any click — and a rule that treated a name as a
 * placement would then find no free row to write into and append a fifth on the first click.
 * The origin is inside the head, so no real scalp pick can land there.
 */
export function isBlankPosition(p: ElectrodePosition): boolean {
  const label = p.label?.trim() ?? "";
  return !p.x && !p.y && !p.z && (label === "" || AUTO_LABEL.test(label));
}

/** Has anything been placed here — the test for "draw a dot for this row". */
export function isPlaced(p: ElectrodePosition): boolean {
  return !isBlankPosition(p);
}

/**
 * Qt's `deleteChecked` renumbering: every auto-named row takes the name its **current index**
 * gives it, so the table always reads `E1+ E1− E2+ E2−` however rows were added or removed.
 * A row the user renamed keeps its name — it was a deliberate act, and silently overwriting it
 * would lose the only thing the user typed.
 */
export function renumber(positions: ElectrodePosition[]): ElectrodePosition[] {
  return positions.map((p, i) => (!p.label || AUTO_LABEL.test(p.label) ? { ...p, label: autoLabel(i) } : p));
}

/**
 * One click on the scalp. Returns the new rows and the index that was written, so a caller can
 * scroll to it or say which electrode it just placed.
 */
export function placeAt(
  positions: ElectrodePosition[],
  world: readonly [number, number, number],
): { positions: ElectrodePosition[]; index: number } {
  const blank = positions.findIndex(isBlankPosition);
  const index = blank >= 0 ? blank : positions.length;
  const placed: ElectrodePosition = {
    label: autoLabel(index),
    x: roundMm(world[0]),
    y: roundMm(world[1]),
    z: roundMm(world[2]),
  };
  const next = blank >= 0 ? positions.map((p, i) => (i === index ? placed : p)) : [...positions, placed];
  return { positions: renumber(next), index };
}

/** Remove one row, then renumber — the two halves of Qt's delete, which were never separate. */
export function removeAt(positions: ElectrodePosition[], index: number): ElectrodePosition[] {
  return renumber(positions.filter((_, i) => i !== index));
}

/**
 * The dots the pane draws: one per **placed** row, coloured by its pair.
 *
 * `channel` is the pair index, which is what `scene/palette.ts` turns into the Okabe-Ito hue the
 * `ChannelLegend` uses — so `E1+`/`E1−` are visibly one channel, exactly as the Qt widget's
 * per-pair colouring said. A blank row draws nothing: a dot at the origin is a dot inside the
 * subject's head, and it would look like a placement nobody made.
 */
export function placementMarkers(positions: ElectrodePosition[]): SceneMarker[] {
  const markers: SceneMarker[] = [];
  positions.forEach((p, i) => {
    if (!isPlaced(p)) return;
    markers.push({
      id: p.label || autoLabel(i),
      label: p.label || autoLabel(i),
      world: [p.x, p.y, p.z],
      channel: Math.floor(i / 2),
    });
  });
  return markers;
}

/** The same dots for a SAVED configuration, so picking one in a job row shows it on the scalp. */
export function savedMarkers(positions: ElectrodePosition[]): SceneMarker[] {
  return placementMarkers(positions.map((p, i) => ({ ...p, label: p.label || autoLabel(i) })));
}
