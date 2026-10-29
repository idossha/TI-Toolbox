/**
 * What the Simulator's scene draws: one focus, and the scene as a pure function of it
 * (ARCHITECTURE §7.2, maintainer 2026-10-28: *"When the user interacts with an element, the state
 * must change to reflect what is happening"*).
 *
 * The focus is whatever the user last touched — a job row, the open montage form or the open
 * placement form — and nothing else feeds the scene: no "last net touched", no preview pushed up
 * by an effect. A row with no net draws no electrodes; the montage form draws its own net; closing
 * a form falls back to the row focused before it, because that row was never forgotten.
 */
import type { FlexRun } from "./api";
import { candidateOriginalPairs } from "./candidateHandoff";
import { OPTIMIZED, placementsFor } from "./FlexTab";
import type { MontageDraft } from "./MontageManager";
import type { SelectedRow } from "./types";

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
 * The stored state against what exists now: a form counts only while it is open (closing one needs
 * no bookkeeping), and a row that was removed gives way to the first row.
 */
export function resolveFocus(state: FocusState, rows: SelectedRow[], draftOpen: boolean, placementOpen: boolean): SceneFocus {
  const rowId = (rows.find((r) => r.id === state.rowId) ?? rows[0])?.id ?? null;
  if (state.form && draftOpen) return { on: "montage-form", rowId };
  if (state.form && placementOpen) return { on: "placement-form", rowId };
  return { on: "row", rowId };
}

type Xyz = { x: number; y: number; z: number };

/** Everything the scene shows, as the props `ScenePane` takes. */
export interface SceneView {
  /** The research subject whose head is drawn, or `null` for the packaged guide. */
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
  /** The focused row, whose own electrode settings size the drawn electrodes. */
  rowId?: string;
  note?: string;
}

export interface SceneData {
  rows: SelectedRow[];
  draft: MontageDraft | null;
  placementSubject: string | null;
  /** subject -> its flex runs, for a mapped row's optimised origins. */
  flexRuns: Record<string, FlexRun[]>;
  /** The packaged guide's net file names; `undefined` until the manifest arrives. */
  guideNets: string[] | undefined;
  subjectNets: Record<string, string[]>;
  /** Subjects that may draw a net the guide lacks, in order of preference. */
  subjects: (string | null | undefined)[];
}

const NO_NET = "Choose an EEG net to see its electrodes.";
const xyz = (pairs: NonNullable<SelectedRow["xyzPairs"]>): Xyz[] => pairs.flat().map(([x, y, z]) => ({ x, y, z }));

export function sceneFor(focus: SceneFocus, d: SceneData): SceneView {
  const headFor = (net: string | null, first?: string) => subjectForOffGuideNet(net, d.guideNets, [first, ...d.subjects], d.subjectNets);
  if (focus.on === "placement-form") return { subject: d.placementSubject, net: null, showing: null, edits: "placement" };
  if (focus.on === "montage-form") {
    const net = d.draft?.net ?? null;
    return { subject: headFor(net), net, pairs: d.draft?.pairs, showing: null, edits: "montage", note: net ? undefined : NO_NET };
  }
  const row = d.rows.find((r) => r.id === focus.rowId);
  if (!row) return { subject: null, net: null, showing: null, edits: null };
  const base = { rowId: row.id, edits: null };
  // Coordinates mean something only on the head they came from.
  if (row.xyzPairs?.length) {
    const positions = xyz(row.xyzPairs);
    return { ...base, subject: row.subjectId || null, net: null, positions, showing: row.name ? { montage: row.name, net: `${positions.length} placed positions` } : null };
  }
  const net = row.eegNet ?? null;
  if (!net) return { ...base, subject: null, net: null, showing: null, note: row.source === "montage" ? NO_NET : undefined };
  const pairs = row.pairs?.length ? row.pairs : undefined;
  const run = d.flexRuns[row.subjectId]?.find((r) => r.name === row.name);
  const origins = row.source === "flex" && pairs
    ? (candidateOriginalPairs(row) ?? (run ? placementsFor(run).find((p) => p.value === OPTIMIZED)?.xyzPairs : undefined))
    : undefined;
  const originalPositions = origins?.length ? xyz(origins) : undefined;
  return {
    ...base,
    // Named montages are browsed on the guide; snap displacements keep the subject's geometry.
    subject: originalPositions ? row.subjectId : headFor(net, row.subjectId),
    net,
    pairs,
    originalPositions,
    showing: pairs && row.name ? { montage: row.name, net } : null,
  };
}

/**
 * The subject whose own head draws `net` when the packaged guide does not carry it, else `null`.
 *
 * Named montages are drawn on the guide, which packages the standard caps only; a cap warped onto
 * a subject (BioSemi-64-10-10, GSN-HydroCel-128) is a file in that subject's `eeg_positions` and
 * nowhere else, so on the guide its electrodes were simply missing. The first of `candidates`
 * that has the net wins. `null` too while the guide's net list has not arrived, so the pane never
 * flips head on a guess.
 */
export function subjectForOffGuideNet(
  net: string | null,
  guideNets: string[] | undefined,
  candidates: (string | null | undefined)[],
  subjectNets: Record<string, string[]>,
): string | null {
  const bare = (name: string) => name.replace(/\.csv$/i, "");
  if (!net || !guideNets || guideNets.some((name) => bare(name) === bare(net))) return null;
  return candidates.find((id): id is string => !!id && (subjectNets[id] ?? []).some((name) => bare(name) === bare(net))) ?? null;
}
