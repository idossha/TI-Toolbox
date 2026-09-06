/**
 * The Simulator's **Jobs table** — one row per job, and the row owns its inputs.
 *
 * Maintainer, 2026-09-06, against a 2.5.0 screenshot of the "Simulation Jobs" cards: *"it's hard
 * to separate users, montages, modes in different jobs. In 2.5.0, within a job users could
 * manipulate the subject, the mode, the montage, the current intensities, and so on. We need that
 * capability."* The v3 page had replaced those cards with a **global** subject set plus a montage
 * list fanned out across it, so a run was a cross-product the user had to hold in their head and
 * could not break: three subjects × two montages was six jobs, and there was no way to say "ernie
 * on F3_F4, 101 on the flex result".
 *
 * So the row is the job again. Its cells are, left to right:
 *
 *   Subject · Source · EEG net · Montage · Pairs · Currents (mA) · actions
 *
 * and the cells that mean different things under different sources change *inside their column*:
 * the widths come from `resolveColumnWidths` and a `<colgroup>`, so switching a row from Montage
 * to Flex result moves nothing anywhere else in the table (the same reservation rule the currents
 * column already used for the TI ↔ mTI switch).
 *
 * What is still global lives on the page: electrodes, conductivity and output fields are
 * properties of the *run*, not of a job, and 2.5.0 had them global too.
 *
 * This file also keeps the montage **editor** (the "New montage" draft card, whose state is lifted
 * to the page so the 3-D pane and the pairs form edit one draft) and the delete confirmation.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Pencil, Trash2, X, Copy } from "lucide-react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { AlertDialog } from "../../ui/Overlay";
import { Field, TextInput } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { SelectionPicker } from "../../ui/SelectionList";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { ElectrodePairsEditor, type ElectrodePair } from "../../ui/ElectrodePairsEditor";
import { notify } from "../../ui/Toast";
import { NumberInput } from "../../ui/NumberInput";
import { deleteMontage, getEegNets, getFlexRuns, getFreehand, getMontages, putMontage, type FlexRun, type FreehandConfig } from "./api";
import { OPTIMIZED, placementsFor, type FlexPlacement } from "./FlexTab";
import "./simulator-page.css";
import {
  SOURCE_OPTIONS,
  currentsCount,
  defaultCurrents,
  defaultCurrentsFor,
  emptyRow,
  inferMontageKind,
  isRunnableRow,
  newRowId,
  polarityLabel,
  rowPairCount,
  type MontageKind,
  type MontageSource,
  type SelectedRow,
} from "./types";

export type Kind = MontageKind;

/** A montage as the table addresses it: which net's bucket it lives in, and its pairs. */
export interface CatalogMontage {
  net: string;
  kind: MontageKind;
  name: string;
  pairs: [string, string][];
}

/** `${kind}:${name}` — the montage `Select`'s option value, since one name can exist in both
 *  buckets of the same net. */
export function montageOptionValue(kind: MontageKind, name: string): string {
  return `${kind}:${name}`;
}

export function parseMontageOptionValue(value: string): { kind: MontageKind; name: string } {
  const cut = value.indexOf(":");
  return { kind: value.slice(0, cut) as MontageKind, name: value.slice(cut + 1) };
}

/** `E1–E2 · E3–E4` — the read-only pairs cell for a label-based montage. */
export function formatPairs(pairs: [string, string][]): string {
  return pairs.map(([a, b]) => `${a}–${b}`).join(" · ");
}

/** The Pairs cell for any row, whichever form its electrodes came in. */
export function rowPairsText(row: SelectedRow): string {
  if (row.pairs && row.pairs.length > 0) return formatPairs(row.pairs);
  const n = row.xyzPairs?.length ?? 0;
  return n > 0 ? `${n * 2} XYZ coordinates` : "—";
}

/** The row's currents, normalised to the count its polarity requires (extra values dropped, a
 *  short list padded with 1.0). */
export function currentValues(currents: string, count: number): number[] {
  // A blank cell is an *unset* current, not zero — `Number("")` is 0, which is why the empty wire
  // string used to normalise to `[0, 1]` rather than the documented `[1, 1]`.
  const parsed = currents.split(",").map((v) => (v.trim() === "" ? Number.NaN : Number(v.trim())));
  return Array.from({ length: count }, (_, i) => {
    const v = parsed[i];
    return v === undefined || Number.isNaN(v) ? 1.0 : v;
  });
}

/**
 * How many current inputs a row shows: a catalog montage's polarity is the bucket it lives in; a
 * flex or free-hand row has none, so it follows the pair count (`inferMontageKind`).
 */
export function rowCurrentsCount(row: SelectedRow): number {
  const pairs = rowPairCount(row);
  return currentsCount(row.kind ?? inferMontageKind(pairs), pairs);
}

/**
 * The currents column's reserved width, in slots: the widest polarity the table can hold, never
 * fewer than 4 — so the common TI <-> mTI switch (2 <-> 4 currents) changes nothing but the
 * number of inputs *inside* the reserved cell, and no other cell moves.
 */
export function currentSlotsReserved(counts: number[]): number {
  return Math.max(4, ...counts, 0);
}

/* ------------------------------------------------------------------------------------------------
 * Column widths.
 *
 * The table must never scroll sideways (its container's scrollWidth == clientWidth is asserted),
 * which rules out a pixel colgroup: the actions column is fixed and the other five share what is
 * left, resolved to exact pixels that sum to the container. The user can drag the first four
 * boundaries; `currents` absorbs the remainder, and if it cannot the shrink walks back up the row.
 * The final proportional pass is what makes "sums to the container" true even when every column is
 * already at its minimum.
 *
 * The reservation is also what makes a **source switch** free of layout movement: a Flex row's
 * placement select and a Montage row's net select are two contents of one fixed-width column.
 * --------------------------------------------------------------------------------------------- */

export type ColumnKey = "subject" | "source" | "net" | "montage" | "pairs";

/** The four widths a user can set (`pairs` absorbs nothing; `currents` does). */
export type StoredColumns = Partial<Record<ColumnKey, number>>;

export interface ColumnWidths {
  subject: number;
  source: number;
  net: number;
  montage: number;
  pairs: number;
  currents: number;
  actions: number;
}

/**
 * Three 28px icon buttons (duplicate · edit · remove), 2px apart, inside a cell with --space-1 of
 * padding. No slack column.
 *
 * A fourth — "delete this montage from the catalog" — used to sit here and does not any more: six
 * content columns plus 124px of actions left every column pinned at its minimum in the 560px work
 * pane, which is a table nobody can resize. Deleting a *catalog entry* is also not an operation on
 * a job row; it lives in the montage editor the row's pencil opens.
 */
export const ACTIONS_W = 96;

/** Below these a column stops being a control and becomes a sliver. */
export const COLUMN_MIN: Record<keyof Omit<ColumnWidths, "actions">, number> = {
  subject: 56,
  source: 72,
  net: 64,
  montage: 80,
  pairs: 28,
  currents: 80,
};

/** Shares of the resizable area when nothing is stored — sized so a subject id, a source label, a
 *  net name and a montage name all fit at the 608px work column the run shape gives at 1280. */
const COLUMN_DEFAULT_FRACTION = { subject: 0.14, source: 0.16, net: 0.17, montage: 0.21, pairs: 0.07 } as const;

/** New key: the columns are not the ones `tit-montage-columns-v1` stored. */
export const COLUMNS_STORAGE_KEY = "tit-sim-jobs-columns-v1";

/**
 * Exact pixel widths for a table `container` px wide. Total is always `container`, so a colgroup
 * built from it cannot overflow — that is the invariant, not an arithmetic coincidence.
 */
export function resolveColumnWidths(container: number, stored: StoredColumns): ColumnWidths {
  const avail = Math.max(0, Math.round(container) - ACTIONS_W);
  const pick = (k: ColumnKey) =>
    Math.max(COLUMN_MIN[k], Math.round(stored[k] ?? avail * COLUMN_DEFAULT_FRACTION[k]));
  const w = {
    subject: pick("subject"),
    source: pick("source"),
    net: pick("net"),
    montage: pick("montage"),
    pairs: pick("pairs"),
    currents: 0,
  };
  const rest = () => avail - w.subject - w.source - w.net - w.montage - w.pairs;
  w.currents = rest();

  // Not enough left for the currents inputs: take it back widest-first, never below a min.
  if (w.currents < COLUMN_MIN.currents) {
    let need = COLUMN_MIN.currents - w.currents;
    for (const k of ["pairs", "montage", "net", "source", "subject"] as const) {
      const give = Math.min(w[k] - COLUMN_MIN[k], need);
      w[k] -= give;
      need -= give;
      if (need <= 0) break;
    }
    w.currents = rest();
  }

  // Even the minimums may not fit a very narrow pane. Scale, then put the rounding residue on
  // `currents` so the five still add up to `avail` exactly.
  const total = w.subject + w.source + w.net + w.montage + w.pairs + Math.max(0, w.currents);
  if (total > 0 && total !== avail) {
    const scale = avail / total;
    for (const k of ["subject", "source", "net", "montage", "pairs"] as const) {
      w[k] = Math.max(1, Math.floor(w[k] * scale));
    }
  }
  w.currents = Math.max(0, rest());
  return { ...w, actions: ACTIONS_W };
}

/** Reads the persisted widths; never throws (storage can be disabled or corrupt). */
export function readStoredColumns(storage: Pick<Storage, "getItem"> | undefined): StoredColumns {
  if (!storage) return {};
  try {
    const raw = storage.getItem(COLUMNS_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const rec = parsed as Record<string, unknown>;
    const out: StoredColumns = {};
    for (const k of ["subject", "source", "net", "montage", "pairs"] as const) {
      const v = rec[k];
      if (typeof v === "number" && Number.isFinite(v)) out[k] = Math.max(COLUMN_MIN[k], Math.round(v));
    }
    return out;
  } catch {
    return {};
  }
}

export function writeStoredColumns(storage: Pick<Storage, "setItem"> | undefined, cols: StoredColumns): void {
  if (!storage) return;
  try {
    storage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify(cols));
  } catch {
    /* storage disabled or full — the table still resizes, it just forgets. */
  }
}

/** One header boundary. Pointer capture and arrow keys, the same gesture as the pane divider. */
function ColumnHandle({ label, width, onResize }: { label: string; width: number; onResize: (next: number) => void }) {
  return (
    <button
      type="button"
      className="montage-col-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      tabIndex={0}
      onPointerDown={(e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = width;
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        const onMove = (ev: PointerEvent) => onResize(startWidth + (ev.clientX - startX));
        const onUp = () => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      }}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        e.stopPropagation();
        onResize(width + (e.key === "ArrowRight" ? 16 : -16));
      }}
    />
  );
}

/** One `NumberInput` per required current (mA); `row.currents` stays the comma-joined wire string. */
function CurrentsCell({
  row,
  slots,
  onChange,
}: {
  row: SelectedRow;
  /** Slots the column reserves — see `currentSlotsReserved`. */
  slots: number;
  onChange: (currents: string) => void;
}) {
  const count = rowCurrentsCount(row);
  if (count === 0 || !row.name) return <span className="field-help">—</span>;
  const values = currentValues(row.currents, count);
  return (
    <div className="montage-currents" style={{ "--slots": slots } as React.CSSProperties}>
      {values.map((v, i) => (
        <NumberInput
          key={i}
          value={v}
          onValueChange={(next) => onChange(values.map((old, idx) => (idx === i ? (next ?? old) : old)).join(","))}
          step={0.1}
          min={0}
          aria-label={`${row.name || "row"} pair ${i + 1} current (mA)`}
        />
      ))}
    </div>
  );
}

/**
 * The montage being written — the editor's whole state, lifted to the page (SCC).
 *
 * The scene pane places electrodes into exactly these pairs, and a pane that had to reach into a
 * child component's private state could only do it by duplicating them. The page owns one draft;
 * the table and the pane are two editors of it.
 */
export interface MontageDraft {
  name: string;
  pairs: ElectrodePair[];
  /** The bucket an *existing* montage was opened from — a new draft has none and infers it. */
  savedAs?: MontageKind;
}

/** A fresh draft: two empty pairs, the smallest real montage (TI). Its polarity is not a choice —
 *  it follows from how many pairs the user ends up filling in (`inferMontageKind`). */
export function emptyDraft(): MontageDraft {
  return { name: "", pairs: [["", ""], ["", ""]] };
}

/** Matches `Montage.simulation_mode`: exactly 2 pairs (TI) or 4+ pairs (mTI); 1 or 3 is invalid. */
function isValidPairCount(n: number): boolean {
  return n === 2 || n >= 4;
}

/** A subject as the Subject cell addresses it: its id and whether a simulation can run on it. */
export interface JobSubject {
  id: string;
  /** `undefined` when the subject is usable; otherwise the reason it is not (J3 wording). */
  blockedReason?: string;
}

export interface JobsTableProps {
  /** Every subject in the project, with this page's own readiness verdict. */
  subjects: JobSubject[];
  /** subjectId -> eeg net names it has (from SubjectDetail.eeg_nets). */
  subjectNets: Record<string, string[]>;
  rows: SelectedRow[];
  onRowsChange: (next: SelectedRow[]) => void;
  /** The montage being written, owned by the page and shared with the scene pane. */
  draft: MontageDraft | null;
  onDraftChange: (draft: MontageDraft | null) => void;
  /** The resolved net, reported upward so the scene pane draws the same one's electrodes. */
  onNetChange?: (net: string | undefined) => void;
  /**
   * The row the user clicked, reported upward so the 3-D pane draws THAT job (its net's electrodes
   * as idle dots, its own pairs coloured by channel) — visual confirmation of a job that is
   * already configured, not an editor. `null` when no row is active or the row has no net.
   */
  onPreviewChange?: (preview: { net: string; name: string; pairs: [string, string][] } | null) => void;
  /** The source of the active row, so the page can note that flex/free-hand carry their own
   *  coordinates rather than the previewed net's. */
  onActiveSourceChange?: (source: MontageSource | null) => void;
}

export function JobsTable({
  subjects,
  subjectNets,
  rows,
  onRowsChange,
  draft,
  onDraftChange,
  onNetChange,
  onPreviewChange,
  onActiveSourceChange,
}: JobsTableProps) {
  const queryClient = useQueryClient();
  const montages = useQuery({ queryKey: ["montages"], queryFn: getMontages });

  const usable = useMemo(() => subjects.filter((s) => !s.blockedReason).map((s) => s.id), [subjects]);

  // Flex runs and free-hand configs, per usable subject: a row's Montage cell needs the catalog for
  // *its own* subject, so this is one query each rather than one for the page's "current" subject.
  const flexQueries = useQueries({
    queries: usable.map((id) => ({ queryKey: ["flex-runs", id], queryFn: () => getFlexRuns(id), staleTime: 60_000 })),
  });
  const freehandQueries = useQueries({
    queries: usable.map((id) => ({ queryKey: ["freehand", id], queryFn: () => getFreehand(id), staleTime: 60_000 })),
  });
  /* Derived on every render rather than memoized, the precedent `RunControls.tsx`'s `useSimPlan`
     set: `useQueries` hands back a fresh array each render, so a `useMemo` over it can only be
     keyed on a serialisation — which React Compiler correctly refuses to treat as preserved
     memoization. Both are maps over a project's few subjects. */
  const flexBySubject: Record<string, FlexRun[]> = {};
  const freehandBySubject: Record<string, FreehandConfig[]> = {};
  usable.forEach((id, i) => {
    flexBySubject[id] = flexQueries[i]?.data ?? [];
    freehandBySubject[id] = freehandQueries[i]?.data ?? [];
  });

  const availableNets = useMemo(() => {
    const nets = new Set<string>();
    for (const list of Object.values(subjectNets)) for (const n of list) nets.add(n);
    if (montages.data) for (const n of Object.keys(montages.data.nets)) nets.add(n);
    return [...nets].sort();
  }, [subjectNets, montages.data]);

  /*
   * The net is a cell of the row, not a control above the table. `editorNet` is only the net a
   * *new* row and the montage editor start on — the last net the user touched, falling back to the
   * first available.
   */
  const [netChoice, setNetChoice] = useState<string | undefined>(undefined);
  const editorNet = netChoice && availableNets.includes(netChoice) ? netChoice : availableNets[0];

  const editing = draft;
  const setEditing = onDraftChange;
  const [deleteTarget, setDeleteTarget] = useState<CatalogMontage | null>(null);
  /** The row the 3-D pane is drawing. Click a row (not a control in it) to change it. */
  const [activeId, setActiveId] = useState<string | null>(null);

  // The scene pane draws the net the editor is on. Reported in an effect, not during render: it
  // is the parent's state.
  useEffect(() => {
    onNetChange?.(editorNet);
  }, [editorNet, onNetChange]);

  const netElectrodes = useQuery({
    queryKey: ["eeg-net-electrodes", editorNet, usable[0]],
    queryFn: async () => {
      const subject = usable.find((s) => subjectNets[s]?.includes(editorNet!)) ?? usable[0];
      if (!subject || !editorNet) return [] as string[];
      const nets = await getEegNets(subject);
      return nets.find((n) => n.name === editorNet)?.electrodes ?? [];
    },
    enabled: !!editorNet && usable.length > 0,
  });

  /** Every montage of one net, both buckets, in one list — the Montage cell's options. */
  const montagesOf = useMemo(() => {
    return (net: string | undefined): CatalogMontage[] => {
      if (!net) return [];
      const entry = montages.data?.nets[net];
      if (!entry) return [];
      const of = (kind: MontageKind, bucket: Record<string, string[][]> | undefined) =>
        Object.entries(bucket ?? {}).map(([name, pairs]) => ({
          net,
          kind,
          name,
          pairs: pairs.map((p) => [p[0], p[1]] as [string, string]),
        }));
      return [...of("uni_polar", entry.uni_polar), ...of("multi_polar", entry.multi_polar)];
    };
  }, [montages.data]);

  const saveMontage = useMutation({
    mutationFn: ({ net, kind, name, pairs }: { net: string; kind: MontageKind; name: string; pairs: ElectrodePair[] }) =>
      putMontage(net, kind, name, pairs.map((p) => [p[0], p[1]])),
    onSuccess: (_data, vars) => {
      notify.success(`Saved montage "${vars.name}".`);
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not save the montage.", err instanceof Error ? err.message : undefined),
  });

  const removeMontage = useMutation({
    mutationFn: (m: CatalogMontage) => deleteMontage(m.net, m.kind, m.name),
    onSuccess: (_data, m) => {
      notify.success(`Deleted montage "${m.name}".`);
      setDeleteTarget(null);
      // Every row that pointed at it goes back to "pick a montage" rather than silently planning a
      // montage that no longer exists.
      onRowsChange(
        rows.map((r) =>
          r.source === "montage" && r.eegNet === m.net && r.kind === m.kind && r.name === m.name
            ? { ...r, name: "", kind: undefined, pairs: undefined }
            : r,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not delete the montage.", err instanceof Error ? err.message : undefined),
  });

  const patch = useCallback(
    (id: string, next: Partial<SelectedRow>) => onRowsChange(rows.map((r) => (r.id === id ? { ...r, ...next } : r))),
    [rows, onRowsChange],
  );

  /* ------------------------------------------------------------------ Row edits */

  function setRowSubject(row: SelectedRow, subjectId: string) {
    // A montage/net the new subject does not have is not a job — clear back to "pick one" rather
    // than carrying an unrunnable row forward.
    const keepsNet = row.source !== "montage" || !row.eegNet || (subjectNets[subjectId]?.includes(row.eegNet) ?? false);
    patch(row.id, keepsNet && row.source === "montage" ? { subjectId } : { subjectId, name: "", kind: undefined, pairs: undefined, xyzPairs: undefined, eegNet: row.source === "montage" ? row.eegNet : undefined });
  }

  function setRowSource(row: SelectedRow, source: MontageSource) {
    setActiveId(row.id);
    patch(row.id, {
      source,
      name: "",
      kind: undefined,
      pairs: undefined,
      xyzPairs: undefined,
      eegNet: source === "montage" ? (row.eegNet ?? editorNet) : undefined,
      currents: "1.0,1.0",
    });
  }

  function setRowNet(row: SelectedRow, net: string) {
    setNetChoice(net);
    // The montage belonged to the old net.
    patch(row.id, { eegNet: net, name: "", kind: undefined, pairs: undefined });
  }

  function setRowMontage(row: SelectedRow, value: string) {
    const { kind, name } = parseMontageOptionValue(value);
    const montage = montagesOf(row.eegNet).find((m) => m.kind === kind && m.name === name);
    if (!montage) return;
    setNetChoice(montage.net);
    patch(row.id, {
      kind: montage.kind,
      name: montage.name,
      pairs: montage.pairs,
      xyzPairs: undefined,
      currents: defaultCurrentsFor(montage.kind, montage.pairs.length),
    });
  }

  /** The placements a flex row can be simulated in, for the row's own subject and run. */
  function placementsForRow(row: SelectedRow): FlexPlacement[] {
    const run = (flexBySubject[row.subjectId] ?? []).find((r) => r.name === row.name);
    return run ? placementsFor(run) : [];
  }

  function applyFlexPlacement(row: SelectedRow, placement: FlexPlacement) {
    const numPairs = placement.pairs?.length ?? placement.xyzPairs?.length ?? 0;
    patch(row.id, {
      eegNet: placement.value === OPTIMIZED ? undefined : placement.value,
      pairs: placement.pairs,
      xyzPairs: placement.xyzPairs,
      currents: defaultCurrents(numPairs),
    });
  }

  function setRowFlexRun(row: SelectedRow, name: string) {
    const run = (flexBySubject[row.subjectId] ?? []).find((r) => r.name === name);
    const first = run ? placementsFor(run)[0] : undefined;
    const numPairs = first?.pairs?.length ?? first?.xyzPairs?.length ?? 0;
    patch(row.id, {
      name,
      kind: undefined,
      eegNet: first && first.value !== OPTIMIZED ? first.value : undefined,
      pairs: first?.pairs,
      xyzPairs: first?.xyzPairs,
      currents: defaultCurrents(numPairs),
    });
  }

  function setRowFreehand(row: SelectedRow, name: string) {
    const config = (freehandBySubject[row.subjectId] ?? []).find((c) => c.name === name);
    const pairs: [[number, number, number], [number, number, number]][] = [];
    for (let i = 0; config && i + 1 < config.electrode_positions.length; i += 2) {
      const a = config.electrode_positions[i]!;
      const b = config.electrode_positions[i + 1]!;
      pairs.push([[a.x, a.y, a.z], [b.x, b.y, b.z]]);
    }
    patch(row.id, { name, kind: undefined, eegNet: undefined, pairs: undefined, xyzPairs: pairs, currents: defaultCurrents(pairs.length) });
  }

  function addRow() {
    const last = rows[rows.length - 1];
    const seedSubject = last?.subjectId || usable[0] || "";
    onRowsChange([...rows, emptyRow(seedSubject, "montage", editorNet)]);
  }

  function duplicateRow(row: SelectedRow) {
    const at = rows.findIndex((r) => r.id === row.id);
    const copy = { ...row, id: newRowId() };
    onRowsChange([...rows.slice(0, at + 1), copy, ...rows.slice(at + 1)]);
    setActiveId(copy.id);
  }

  function removeRow(id: string) {
    if (activeId === id) setActiveId(null);
    onRowsChange(rows.filter((r) => r.id !== id));
  }

  /** A brand-new montage always starts as a 2-pair draft; adding pairs makes it multi-polar. */
  function startNewMontage() {
    setEditing(emptyDraft());
  }

  const draftKind = editing ? inferMontageKind(editing.pairs.length) : "uni_polar";

  /* ------------------------------------------------------------------ Preview */

  const activeRow = rows.find((r) => r.id === activeId) ?? null;
  const activeNet = activeRow?.eegNet;
  const activeName = activeRow?.name;
  const activePairs = activeRow?.pairs;
  const activeSource = activeRow?.source ?? null;
  useEffect(() => {
    onPreviewChange?.(activeNet && activeName && activePairs?.length ? { net: activeNet, name: activeName, pairs: activePairs } : null);
  }, [activeNet, activeName, activePairs, onPreviewChange]);
  useEffect(() => {
    onActiveSourceChange?.(activeSource);
  }, [activeSource, onActiveSourceChange]);

  /* ------------------------------------------------------------------ Geometry */

  const [tableWidth, setTableWidth] = useState(0);
  const [storedColumns, setStoredColumns] = useState<StoredColumns>(() =>
    readStoredColumns(typeof window === "undefined" ? undefined : window.localStorage),
  );
  const tableBox = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = tableBox.current;
    if (!node) return;
    setTableWidth(node.clientWidth);
    const ro = new ResizeObserver(() => setTableWidth(node.clientWidth));
    ro.observe(node);
    return () => ro.disconnect();
  }, [montages.data, availableNets.length]);
  const cols = useMemo(() => resolveColumnWidths(tableWidth, storedColumns), [tableWidth, storedColumns]);
  const setColumn = useCallback((key: ColumnKey, next: number) => {
    setStoredColumns((prev) => {
      const merged = { ...prev, [key]: Math.max(COLUMN_MIN[key], Math.round(next)) };
      writeStoredColumns(typeof window === "undefined" ? undefined : window.localStorage, merged);
      return merged;
    });
  }, []);

  const currentSlots = currentSlotsReserved(rows.map(rowCurrentsCount));

  /** Up/Down moves the active row — the one the 3-D pane is drawing. */
  function onTableKeyDown(e: React.KeyboardEvent<HTMLTableElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    if (rows.length === 0) return;
    e.preventDefault();
    const at = rows.findIndex((r) => r.id === activeId);
    const next = e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : Math.max(0, (at === -1 ? 0 : at) - 1);
    setActiveId(rows[next]?.id ?? null);
    const row = e.currentTarget.querySelector<HTMLElement>(`tbody tr:nth-of-type(${next + 1})`);
    row?.focus();
  }

  /* ------------------------------------------------------------------ Cells */

  const subjectItems = useMemo(
    () =>
      subjects.map((s) => ({
        id: s.id,
        label: s.id,
        reason: s.blockedReason,
        // Blocked subjects are LISTED with their reason and cannot be picked — the row's own
        // version of the subject grammar's J3 rule, which is why this is a `SelectionPicker` and
        // not a `Select` whose options carry no explanation.
        disabled: !!s.blockedReason,
      })),
    [subjects],
  );

  function montageOptions(net: string | undefined) {
    return montagesOf(net).map((m) => ({
      value: montageOptionValue(m.kind, m.name),
      label: `${m.name} · ${polarityLabel(m.kind)}`,
    }));
  }

  function netsForSubject(subjectId: string): string[] {
    const own = subjectNets[subjectId] ?? [];
    return own.length > 0 ? own : availableNets;
  }

  /** The EEG net column: a net for a montage row, the placement for a flex row, nothing else. */
  function renderNetCell(row: SelectedRow) {
    if (row.source === "montage") {
      const nets = netsForSubject(row.subjectId);
      return (
        <Select
          value={row.eegNet && nets.includes(row.eegNet) ? row.eegNet : undefined}
          onValueChange={(v) => setRowNet(row, v)}
          options={nets.map((n) => ({ value: n, label: n }))}
          placeholder="EEG net"
          aria-label="EEG net"
        />
      );
    }
    if (row.source === "flex") {
      const options = placementsForRow(row);
      if (options.length === 0) return <span className="field-help">—</span>;
      const current = row.eegNet ?? OPTIMIZED;
      return (
        <Select
          value={options.some((o) => o.value === current) ? current : options[0]!.value}
          onValueChange={(v) => {
            const next = options.find((o) => o.value === v);
            if (next) applyFlexPlacement(row, next);
          }}
          options={options.map((o) => ({ value: o.value, label: o.label }))}
          aria-label="Placement"
        />
      );
    }
    return <span className="field-help">own XYZ</span>;
  }

  /** The Montage column: catalog montage, flex run, or saved free-hand configuration. */
  function renderMontageCell(row: SelectedRow) {
    if (row.source === "montage") {
      return (
        <div className="montage-cell">
          <Select
            value={row.name && row.kind ? montageOptionValue(row.kind, row.name) : undefined}
            onValueChange={(v) => setRowMontage(row, v)}
            options={montageOptions(row.eegNet)}
            placeholder="Choose a montage"
            aria-label="Montage"
          />
          <span className="montage-chip-slot" style={{ "--slot": "40px" } as React.CSSProperties}>
            {row.kind && (
              <span className="chip chip-neutral" title={row.kind === "uni_polar" ? "Uni-polar (2 pairs)" : "Multi-polar (4+ pairs)"}>
                {polarityLabel(row.kind)}
              </span>
            )}
          </span>
        </div>
      );
    }
    if (row.source === "flex") {
      const runs = flexBySubject[row.subjectId] ?? [];
      return (
        <Select
          value={runs.some((r) => r.name === row.name) ? row.name : undefined}
          onValueChange={(v) => setRowFlexRun(row, v)}
          options={runs.map((r) => ({ value: r.name, label: r.name }))}
          placeholder={runs.length === 0 ? "No flex runs" : "Choose a run"}
          disabled={runs.length === 0}
          aria-label="Flex run"
        />
      );
    }
    const configs = freehandBySubject[row.subjectId] ?? [];
    return (
      <Select
        value={configs.some((c) => c.name === row.name) ? row.name : undefined}
        onValueChange={(v) => setRowFreehand(row, v)}
        options={configs.map((c) => ({ value: c.name, label: c.name }))}
        placeholder={configs.length === 0 ? "No free-hand sets" : "Choose a set"}
        disabled={configs.length === 0}
        aria-label="Free-hand configuration"
      />
    );
  }

  const catalogMontageOf = (row: SelectedRow): CatalogMontage | null =>
    row.source === "montage" && row.eegNet && row.kind && row.name
      ? { net: row.eegNet, kind: row.kind, name: row.name, pairs: row.pairs ?? [] }
      : null;

  const loading = montages.isPending;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {usable.length === 0 && subjects.length > 0 && (
        <Callout kind="warning">No subject in this project has a head model — a simulation cannot run yet.</Callout>
      )}
      {loading && <Skeleton height={160} />}
      {montages.error && <Callout kind="danger">Could not load montages.</Callout>}
      {montages.data && availableNets.length === 0 && (
        <EmptyState icon={<Plus size={24} />} message="No EEG nets available in this project." />
      )}
      {montages.data && availableNets.length > 0 && (
        <div className="data-table-container" ref={tableBox} data-testid="sim-jobs-table-container">
          {/* Fixed geometry: an explicit `<colgroup>` plus `table-layout: fixed` (simulator-page.css).
              Nothing a user does to one ROW — its subject, its source, its montage, its polarity —
              may move a cell in another; only a deliberate drag of a header boundary changes a
              COLUMN. The widths come from `resolveColumnWidths`, which always sums to the
              container, so the table cannot scroll sideways at any pane width. */}
          <table className="data-table montage-table sim-jobs-table" onKeyDown={onTableKeyDown} data-testid="sim-jobs-table">
            <colgroup>
              <col style={{ width: tableWidth ? cols.subject : "14%" }} />
              <col style={{ width: tableWidth ? cols.source : "15%" }} />
              <col style={{ width: tableWidth ? cols.net : "17%" }} />
              <col style={{ width: tableWidth ? cols.montage : "21%" }} />
              <col style={{ width: tableWidth ? cols.pairs : "7%" }} />
              <col style={{ width: tableWidth ? cols.currents : "16%" }} />
              <col style={{ width: tableWidth ? cols.actions : "10%" }} />
            </colgroup>
            <thead>
              <tr>
                <th data-column="subject">
                  Subject
                  <ColumnHandle label="Subject" width={cols.subject} onResize={(w) => setColumn("subject", w)} />
                </th>
                <th data-column="source">
                  Source
                  <ColumnHandle label="Source" width={cols.source} onResize={(w) => setColumn("source", w)} />
                </th>
                <th data-column="net">
                  EEG net
                  <ColumnHandle label="EEG net" width={cols.net} onResize={(w) => setColumn("net", w)} />
                </th>
                <th data-column="montage">
                  Montage
                  <ColumnHandle label="Montage" width={cols.montage} onResize={(w) => setColumn("montage", w)} />
                </th>
                <th data-column="pairs">
                  Pairs
                  <ColumnHandle label="Pairs" width={cols.pairs} onResize={(w) => setColumn("pairs", w)} />
                </th>
                <th data-column="currents">
                  Currents <span className="montage-unit">mA</span>
                </th>
                <th data-column="actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const montage = catalogMontageOf(row);
                return (
                  <tr
                    key={row.id}
                    data-job-row={row.id}
                    data-subject={row.subjectId || undefined}
                    data-source={row.source}
                    data-montage-row={row.name || ""}
                    data-polarity={row.kind ?? ""}
                    data-runnable={isRunnableRow(row) ? "true" : "false"}
                    data-active={activeId === row.id ? "true" : undefined}
                    aria-selected={activeId === row.id}
                    tabIndex={0}
                    onClick={(e) => {
                      // A click on a control in the row is that control's, not the row's.
                      if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
                      setActiveId(row.id);
                    }}
                    onFocus={() => setActiveId(row.id)}
                  >
                    <td data-cell="subject">
                      <SelectionPicker
                        mode="single"
                        label="Subject"
                        items={subjectItems}
                        value={row.subjectId ? [row.subjectId] : []}
                        onChange={(v) => v[0] && setRowSubject(row, v[0])}
                        placeholder="Subject"
                        headers={{ label: "Subject", reason: "Why not" }}
                        hideBulk
                        idPrefix={`job-subject-${row.id}`}
                        triggerTestId={`job-subject-${row.id}`}
                      />
                    </td>
                    <td data-cell="source">
                      <Select
                        value={row.source}
                        onValueChange={(v) => setRowSource(row, v as MontageSource)}
                        options={SOURCE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                        aria-label="Source"
                      />
                    </td>
                    <td data-cell="net">{renderNetCell(row)}</td>
                    <td data-cell="montage">{renderMontageCell(row)}</td>
                    <td data-cell="pairs" className="mono text-dense">
                      <span className="montage-pairs" title={rowPairsText(row)}>
                        {rowPairsText(row)}
                      </span>
                    </td>
                    <td data-cell="currents">
                      <CurrentsCell row={row} slots={currentSlots} onChange={(currents) => patch(row.id, { currents })} />
                    </td>
                    <td data-cell="actions" className="montage-actions">
                      <IconButton
                        aria-label={`Duplicate job ${rows.indexOf(row) + 1}`}
                        icon={<Copy size={14} />}
                        onClick={() => duplicateRow(row)}
                      />
                      {montage && (
                        <IconButton
                          aria-label={`Edit ${montage.name}`}
                          icon={<Pencil size={14} />}
                          onClick={() => {
                            setNetChoice(montage.net);
                            setEditing({ name: montage.name, pairs: montage.pairs.map((p) => [p[0], p[1]] as ElectrodePair), savedAs: montage.kind });
                          }}
                        />
                      )}
                      <IconButton aria-label={`Remove job ${rows.indexOf(row) + 1}`} icon={<X size={14} />} onClick={() => removeRow(row.id)} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={availableNets.length === 0} onClick={addRow}>
          Add job
        </Button>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={!editorNet} onClick={startNewMontage}>
          New montage
        </Button>
      </div>

      {editing && (
        <Card>
          <CardHeader title={editing.name ? `Edit montage "${editing.name}"` : "New montage"} />
          <CardBody>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <Field label="EEG net">
                <Select
                  value={editorNet}
                  onValueChange={setNetChoice}
                  options={availableNets.map((n) => ({ value: n, label: n }))}
                  placeholder="Choose a net"
                />
              </Field>
              <Field label="Montage name" required>
                <TextInput value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="e.g. F3_F4" />
              </Field>
              {/* Polarity is a readout, not a choice: it follows from the pairs picked. */}
              <Field label="Polarity">
                <div data-testid="montage-draft-polarity" className="montage-cell" style={{ minHeight: 28 }}>
                  <span className="montage-chip-slot" style={{ "--slot": "40px" } as React.CSSProperties}>
                    <span className="chip chip-neutral">{polarityLabel(draftKind)}</span>
                  </span>
                  <span className="field-help">
                    {editing.pairs.length} pairs · {draftKind === "uni_polar" ? "uni-polar" : "multi-polar"}
                  </span>
                </div>
              </Field>
              <Field label="Electrode pairs" help="Selected from the net's electrode labels.">
                {netElectrodes.isFetching && <Skeleton height={32} />}
                {!netElectrodes.isFetching && (
                  <ElectrodePairsEditor
                    mode="net"
                    electrodes={netElectrodes.data ?? []}
                    pairs={editing.pairs}
                    onPairsChange={(pairs) => setEditing({ ...editing, pairs })}
                    pairStep={2}
                    freehandPairs={[]}
                    onFreehandPairsChange={() => {}}
                  />
                )}
                {!isValidPairCount(editing.pairs.length) && (
                  <span className="field-error">Use exactly 2 pairs (standard TI) or 4 or more pairs (multi-channel mTI).</span>
                )}
              </Field>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)" }}>
                {/* Deleting a catalog entry is an act on the CATALOG, so it lives with the editor
                    rather than in a job row's actions. Only offered for a montage that exists. */}
                {editing.savedAs && editorNet && (
                  <Button
                    variant="secondary"
                    icon={<Trash2 size={14} />}
                    style={{ marginRight: "auto" }}
                    onClick={() => setDeleteTarget({ net: editorNet, kind: editing.savedAs as MontageKind, name: editing.name.trim(), pairs: [] })}
                  >
                    Delete montage
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setEditing(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saveMontage.isPending}
                  disabled={
                    !editorNet ||
                    !editing.name.trim() ||
                    editing.pairs.some((p) => !p[0] || !p[1]) ||
                    !isValidPairCount(editing.pairs.length)
                  }
                  onClick={() => {
                    if (!editorNet) return;
                    // An edit that changed a montage's polarity moves buckets: delete the old
                    // entry so the same name cannot exist in both.
                    if (editing.savedAs && editing.savedAs !== draftKind) {
                      void deleteMontage(editorNet, editing.savedAs, editing.name.trim()).catch(() => undefined);
                    }
                    saveMontage.mutate({ net: editorNet, kind: draftKind, name: editing.name.trim(), pairs: editing.pairs });
                  }}
                >
                  Save montage
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={`Delete montage "${deleteTarget?.name ?? ""}"?`}
        description="This removes the montage definition for this net. Simulations already run from it are unaffected."
        confirmLabel="Delete montage"
        onConfirm={() => {
          if (!deleteTarget) return;
          setEditing(null);
          removeMontage.mutate(deleteTarget);
        }}
      />
    </div>
  );
}
