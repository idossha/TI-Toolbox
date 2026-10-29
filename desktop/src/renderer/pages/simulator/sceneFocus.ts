/**
 * What the Simulator's scene draws: one focus, and the scene as a pure function of it
 * (ARCHITECTURE §7.2, maintainer 2026-10-28: *"When the user interacts with an element, the state
 * must change to reflect what is happening"*).
 *
 * The focus is whatever the user last touched — a job row, the open montage form or the open
 * placement form — and nothing else feeds the scene: no "last net touched", no preview pushed up
 * by an effect. The head is always that row's subject's (the form's row, the placement's subject),
 * the electrodes only what the row or form names, and the hint says what a click does there.
 */
import type { FlexRun } from "./api";
import { candidateOriginalPairs } from "./candidateHandoff";
import { OPTIMIZED, placementsFor } from "./FlexTab";
import type { MontageDraft } from "./MontageManager";
import type { MontageSource, SelectedRow } from "./types";

/** What the page stores: the row last touched, and whether an open form was touched after it. */
export interface FocusState {
  rowId: string | null;
  form: boolean;
}

/** The focus the scene draws. `rowId` is the focused row, or for a form the row it returns to. */
export interface SceneFocus {
  on: "row" | "montage-form" | "placement-form";
  rowId: string | null;
}

/**
 * The stored state against what is open now: a form counts only while it is shown (the placement
 * form covers a montage draft kept behind it), and a removed row gives way to the first row.
 */
export function resolveFocus(state: FocusState, rows: SelectedRow[], draftOpen: boolean, placementOpen: boolean): SceneFocus {
  const rowId = (rows.find((r) => r.id === state.rowId) ?? rows[0])?.id ?? null;
  if (state.form && placementOpen) return { on: "placement-form", rowId };
  if (state.form && draftOpen) return { on: "montage-form", rowId };
  return { on: "row", rowId };
}

type Xyz = { x: number; y: number; z: number };

/** Everything the scene shows, as the props `ScenePane` takes. */
export interface SceneView {
  /** The research subject whose head is drawn (the pane falls back to the guide, labelled, while
   *  it has none), or `null` for the guide. */
  subject: string | null;
  net: string | null;
  pairs?: [string, string][];
  /** A row's saved coordinates (free-hand, unmapped flex), drawn instead of a net. */
  positions?: Xyz[];
  /** A snapped flex row's optimised origins, for the displacement lines. */
  originalPositions?: Xyz[];
  showing: { montage: string; net: string } | null;
  /** Which draft a pick writes: the montage form's pairs, the placement's positions, or nothing. */
  edits: "montage" | "placement" | null;
  /** The focused row, or the form's row: its own electrode settings size the drawn electrodes. */
  rowId?: string;
  /** What a click does, or what to choose first — said whenever the pane's own hint would not fit. */
  note?: string;
}

export interface SceneData {
  rows: SelectedRow[];
  draft: MontageDraft | null;
  placementSubject: string | null;
  /** subject -> its flex runs, for a mapped row's optimised origins. */
  flexRuns: Record<string, FlexRun[]>;
  /** The form shown below the table, if any — a click on a row's net returns to it. */
  openForm: "montage" | "placement" | null;
}

const CHOOSE: Record<MontageSource, string> = {
  montage: "Choose an EEG net to see its electrodes.",
  flex: "Choose a flex run to see its electrodes.",
  freehand: "Choose a free-hand set to see its positions.",
};
const xyz = (pairs: NonNullable<SelectedRow["xyzPairs"]>): Xyz[] => pairs.flat().map(([x, y, z]) => ({ x, y, z }));

export function sceneFor(focus: SceneFocus, d: SceneData): SceneView {
  const row = d.rows.find((r) => r.id === focus.rowId);
  const rowId = row?.id;
  const subject = row?.subjectId || null;
  if (focus.on === "placement-form") return { rowId, subject: d.placementSubject, net: null, showing: null, edits: "placement" };
  if (focus.on === "montage-form") {
    const net = d.draft?.net ?? null;
    return { rowId, subject, net, pairs: d.draft?.pairs, showing: null, edits: "montage", note: net ? undefined : CHOOSE.montage };
  }
  if (!row) return { subject: null, net: null, showing: null, edits: null };
  const base = { rowId, subject, edits: null };
  if (row.xyzPairs?.length) {
    const positions = xyz(row.xyzPairs);
    return { ...base, net: null, positions, showing: row.name ? { montage: row.name, net: `${positions.length} placed positions` } : null };
  }
  // A net is drawn only where the row shows one: a montage row's net, a flex run's placement.
  const net = row.source === "montage" || (row.source === "flex" && row.name) ? (row.eegNet ?? null) : null;
  if (!net) return { ...base, net: null, showing: null, note: CHOOSE[row.source] };
  const pairs = row.pairs?.length ? row.pairs : undefined;
  const run = d.flexRuns[row.subjectId]?.find((r) => r.name === row.name);
  const origins = row.source === "flex" && pairs
    ? (candidateOriginalPairs(row) ?? (run ? placementsFor(run).find((p) => p.value === OPTIMIZED)?.xyzPairs : undefined))
    : undefined;
  return {
    ...base,
    net,
    pairs,
    originalPositions: origins?.length ? xyz(origins) : undefined,
    showing: pairs && row.name ? { montage: row.name, net } : null,
    // A click on a row's net starts a montage — or, with a form already open, goes back to it.
    note: d.openForm
      ? `Click an electrode to go back to the open ${d.openForm} form.`
      : "Click an electrode to start a new montage on this net.",
  };
}
