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
import { categoricalColor, rgbToHex, type Rgb, type SceneMarker } from "../../scene";
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
 * The colour that identifies one row — its dot on the scalp and its swatch in the table.
 *
 * Keyed on the row's **index**, not on its name: the name can be edited, and a colour that moved
 * when a user renamed an electrode would break the one thing this colour is for.
 */
export function positionColor(index: number): Rgb {
  return categoricalColor(index);
}

/** The same colour as the `#rrggbb` the table's swatch needs. One source, two renderings. */
export function positionSwatch(index: number): string {
  return rgbToHex(positionColor(index));
}

/**
 * One click on the scalp — **into the selected row, and only into the selected row**.
 *
 * Maintainer, 2026-09-06: *"in order to place an electrode let us enforce a selection of the
 * electrode from the table. And once that electrode is selected, the user can click on the scalp.
 * Once a different electrode is selected, then the user can select another position on the scalp —
 * that should streamline the user experience such that there is no confusion."*
 *
 * Four rules, each with the failure it prevents:
 *
 *  - **No selection, no placement.** An earlier version advanced to "the next empty row" by itself,
 *    which meant a click always did *something* and the user had to read the table afterwards to
 *    find out what. Now the pane says "Select an electrode in the table first" and nothing moves.
 *  - **The selected row is written whether it is empty or full**, so a re-click moves an electrode
 *    that is in the wrong place instead of needing it deleted and everything after it re-placed.
 *  - **The selection does not move afterwards.** Placing and then adjusting is one row's worth of
 *    work; a selection that jumped on would make the second click land on a different electrode.
 *  - **Nothing is appended.** Rows come from "Add electrode pair", because a montage's position
 *    count is 4 or 8+ (`isValidPositionCount`) and a click that grew the table past a valid count
 *    would leave Save disabled with nothing saying why.
 */
export function placeAt(
  positions: ElectrodePosition[],
  world: readonly [number, number, number],
  selected: number | null,
): { positions: ElectrodePosition[]; index: number } {
  if (selected === null || selected < 0 || selected >= positions.length) return { positions, index: -1 };
  const placed: ElectrodePosition = {
    label: positions[selected]?.label || autoLabel(selected),
    x: roundMm(world[0]),
    y: roundMm(world[1]),
    z: roundMm(world[2]),
  };
  return { positions: renumber(positions.map((p, i) => (i === selected ? placed : p))), index: selected };
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
      // The row's own colour, not its pair's: the question a dot answers here is "which row am I",
      // and the pair is already said by the name (`E1+`/`E1-`). See `SceneMarker.color`.
      color: positionColor(i),
    });
  });
  return markers;
}

/**
 * The marker index a row maps to, and back.
 *
 * They are NOT the same number: a blank row draws no dot, so row 3 can be dot 1. Every "hover this
 * row, light that dot" and "click that dot, select this row" goes through these two, because a
 * component that assumed they matched would highlight the wrong electrode exactly when some rows
 * were still empty — the state the editor spends most of its life in.
 */
export function markerIndexOfRow(positions: ElectrodePosition[], row: number): number {
  if (row < 0 || row >= positions.length || !isPlaced(positions[row] as ElectrodePosition)) return -1;
  return positions.slice(0, row).filter(isPlaced).length;
}

export function rowOfMarkerIndex(positions: ElectrodePosition[], marker: number): number {
  let seen = 0;
  for (let i = 0; i < positions.length; i += 1) {
    if (!isPlaced(positions[i] as ElectrodePosition)) continue;
    if (seen === marker) return i;
    seen += 1;
  }
  return -1;
}

/** The same dots for a SAVED configuration, so picking one in a job row shows it on the scalp. */
export function savedMarkers(positions: ElectrodePosition[]): SceneMarker[] {
  return placementMarkers(positions.map((p, i) => ({ ...p, label: p.label || autoLabel(i) })));
}

/**
 * Positions come in pairs, and the pair count is 2 or 4+ — `Montage.simulation_mode`, which is what
 * `FreehandEditor`'s own Save gate checks. "Add electrode" adds **two** rows for the same reason:
 * an odd row count is never a valid configuration, so offering it is offering a dead end.
 */
export const POSITIONS_PER_STEP = 2;
