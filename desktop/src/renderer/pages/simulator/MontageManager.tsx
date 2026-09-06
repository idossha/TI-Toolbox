import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Pencil, Trash2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { AlertDialog } from "../../ui/Overlay";
import { Field, TextInput } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { ElectrodePairsEditor, type ElectrodePair } from "../../ui/ElectrodePairsEditor";
import { notify } from "../../ui/Toast";
import { NumberInput } from "../../ui/NumberInput";
import { deleteMontage, getEegNets, getMontages, putMontage } from "./api";
import "./simulator-page.css";
import {
  currentsCount,
  defaultCurrentsFor,
  inferMontageKind,
  polarityLabel,
  type MontageKind,
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

/** `E1–E2 · E3–E4` — the read-only pairs cell. */
export function formatPairs(pairs: [string, string][]): string {
  return pairs.map(([a, b]) => `${a}–${b}`).join(" · ");
}

/** The row's currents, normalised to the count its polarity requires (extra values dropped, a
 *  short list padded with 1.0) so the number of inputs always follows the montage. */
export function currentValues(currents: string, count: number): number[] {
  const parsed = currents.split(",").map((v) => (v.trim() === "" ? Number.NaN : Number(v.trim())));
  return Array.from({ length: count }, (_, i) => {
    const v = parsed[i];
    return v === undefined || Number.isNaN(v) ? 1.0 : v;
  });
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
 * which rules out the pixel colgroup it started with; percentages fixed that but spent the width
 * badly — "BioSemi-128" and "mTI_F3F4_P3P4 · mTI" were truncated in their selects while a band of
 * nothing sat in front of three 28px icons. So: the actions column is a fixed 96px (three icons
 * plus their gaps and the cell's padding, and not one pixel of slack), and the other four share
 * what is left, resolved to exact pixels that sum to the container. The user can drag any of the
 * first three boundaries; `currents` absorbs the remainder, and if it cannot the shrink walks back
 * up the row. The final proportional pass is what makes "sums to the container" true even when
 * every column is already at its minimum.
 * --------------------------------------------------------------------------------------------- */

export type ColumnKey = "net" | "montage" | "pairs";

/** The three widths a user can set. `null` = never dragged, so the fractional default applies. */
export type StoredColumns = Partial<Record<ColumnKey, number>>;

export interface ColumnWidths {
  net: number;
  montage: number;
  pairs: number;
  currents: number;
  actions: number;
}

/** Three 28px icon buttons, 2px apart, inside a cell with --space-1 of padding. No slack column. */
export const ACTIONS_W = 96;

/** Below these a column stops being a control and becomes a sliver. */
export const COLUMN_MIN: Record<keyof Omit<ColumnWidths, "actions">, number> = {
  net: 90,
  montage: 110,
  pairs: 48,
  currents: 96,
};

/** Shares of the resizable area when nothing is stored — sized so a net name and a montage name
 *  both fit at the 608px work column the run shape gives the Simulator at 1280. */
const COLUMN_DEFAULT_FRACTION = { net: 0.29, montage: 0.32, pairs: 0.08 } as const;

export const COLUMNS_STORAGE_KEY = "tit-montage-columns-v1";

/**
 * Exact pixel widths for a table `container` px wide. Total is always `container`, so a colgroup
 * built from it cannot overflow — that is the invariant, not an arithmetic coincidence.
 */
export function resolveColumnWidths(container: number, stored: StoredColumns): ColumnWidths {
  const avail = Math.max(0, Math.round(container) - ACTIONS_W);
  const pick = (k: ColumnKey) =>
    Math.max(COLUMN_MIN[k], Math.round(stored[k] ?? avail * COLUMN_DEFAULT_FRACTION[k]));
  const w = { net: pick("net"), montage: pick("montage"), pairs: pick("pairs"), currents: 0 };
  w.currents = avail - w.net - w.montage - w.pairs;

  // Not enough left for the currents inputs: take it back from the widest-first, never below a min.
  if (w.currents < COLUMN_MIN.currents) {
    let need = COLUMN_MIN.currents - w.currents;
    for (const k of ["pairs", "montage", "net"] as const) {
      const give = Math.min(w[k] - COLUMN_MIN[k], need);
      w[k] -= give;
      need -= give;
      if (need <= 0) break;
    }
    w.currents = avail - w.net - w.montage - w.pairs;
  }

  // Even the minimums may not fit a very narrow pane. Scale, then put the rounding residue on
  // `currents` so the four still add up to `avail` exactly.
  const total = w.net + w.montage + w.pairs + Math.max(0, w.currents);
  if (total > 0 && total !== avail) {
    const scale = avail / total;
    w.net = Math.max(1, Math.floor(w.net * scale));
    w.montage = Math.max(1, Math.floor(w.montage * scale));
    w.pairs = Math.max(1, Math.floor(w.pairs * scale));
  }
  w.currents = Math.max(0, avail - w.net - w.montage - w.pairs);
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
    for (const k of ["net", "montage", "pairs"] as const) {
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
  rows,
  count,
  slots,
  label,
  onChange,
}: {
  rows: SelectedRow[];
  count: number;
  /** Slots the column reserves — see `currentSlotsReserved`. */
  slots: number;
  label: string;
  onChange: (currents: string) => void;
}) {
  const first = rows[0];
  if (!first) return <span className="field-help">—</span>;
  const values = currentValues(first.currents, count);
  return (
    <div className="montage-currents" style={{ "--slots": slots } as React.CSSProperties}>
      {values.map((v, i) => (
        <NumberInput
          key={i}
          value={v}
          onValueChange={(next) => onChange(values.map((old, idx) => (idx === i ? (next ?? old) : old)).join(","))}
          step={0.1}
          min={0}
          aria-label={`${label} pair ${i + 1} current (mA)`}
        />
      ))}
    </div>
  );
}

/**
 * The montage being written — the editor's whole state, lifted to the page (SCC).
 *
 * It used to be `MontageManager`'s own `editing` state. The scene pane places electrodes into
 * exactly these pairs, and a pane that had to reach into a child component's private state could
 * only do it by duplicating them — which is the two-copies-of-the-truth failure decision S6 is
 * about. The page owns one draft; the table and the pane are two editors of it.
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

/** A row of the montage table that has no montage picked yet. */
interface PendingRow {
  key: string;
  net?: string;
}

let pendingSeq = 0;

export function MontageManager({
  selectedSubjects,
  subjectNets,
  selectedRows,
  onAddRow,
  onRemoveRow,
  onCurrentsChange,
  draft,
  onDraftChange,
  onNetChange,
  onPreviewChange,
}: {
  selectedSubjects: string[];
  /** subjectId -> eeg net names it has (from SubjectDetail.eeg_nets). */
  subjectNets: Record<string, string[]>;
  selectedRows: SelectedRow[];
  onAddRow: (row: SelectedRow) => void;
  onRemoveRow: (id: string) => void;
  /** The montage being written, owned by the page and shared with the scene pane. */
  draft: MontageDraft | null;
  onDraftChange: (draft: MontageDraft | null) => void;
  /** The resolved net, reported upward so the scene pane draws the same one's electrodes. */
  onNetChange?: (net: string | undefined) => void;
  /**
   * The row the user clicked, reported upward so the 3-D pane draws THAT montage (its net's
   * electrodes as idle dots, its own pairs coloured by channel) — visual confirmation of a row
   * that is already chosen, not an editor. `null` when no row is active.
   */
  onPreviewChange?: (preview: { net: string; name: string; pairs: [string, string][] } | null) => void;
  /**
   * Per-pair currents, edited in this table's own row (v3): the v2 page carried a second
   * "Selected jobs" card below the montage list that repeated every ticked row purely to hold
   * this control, which DESIGN.md v3 §6.2 removes. One row per montage, currents in it.
   */
  onCurrentsChange?: (id: string, currents: string) => void;
}) {
  const queryClient = useQueryClient();
  const montages = useQuery({ queryKey: ["montages"], queryFn: getMontages });

  const availableNets = useMemo(() => {
    const nets = new Set<string>();
    for (const list of Object.values(subjectNets)) for (const n of list) nets.add(n);
    if (montages.data) for (const n of Object.keys(montages.data.nets)) nets.add(n);
    return [...nets].sort();
  }, [subjectNets, montages.data]);

  /*
   * The net is a column of the table now, not a control above it (maintainer call): every row
   * carries its own, so one run can mix nets. `editorNet` is only the net a *new* row and the
   * montage editor start on — the last net the user touched, falling back to the first available.
   */
  const [netChoice, setNetChoice] = useState<string | undefined>(undefined);
  const editorNet = netChoice && availableNets.includes(netChoice) ? netChoice : availableNets[0];

  const [pendingRows, setPendingRows] = useState<PendingRow[]>([]);
  // An inline panel (Card), not a Dialog: a `Select` popover's z-index (60) sits below a Dialog's
  // own overlay/content (80/90) in ui/components.css, which makes the electrode-pair pickers
  // inside a modal montage editor unclickable (reported to F2 — see PARITY.md).
  const editing = draft;
  const setEditing = onDraftChange;
  const [deleteTarget, setDeleteTarget] = useState<CatalogMontage | null>(null);
  /** The row the 3-D pane is drawing. Click a row (not a control in it) to change it. */
  const [activeKey, setActiveKey] = useState<string | null>(null);

  // The scene pane draws the net the editor is on. Reported in an effect, not during render: it
  // is the parent's state.
  useEffect(() => {
    onNetChange?.(editorNet);
  }, [editorNet, onNetChange]);

  const netElectrodes = useQuery({
    queryKey: ["eeg-net-electrodes", editorNet, selectedSubjects[0]],
    queryFn: async () => {
      const subject = selectedSubjects.find((s) => subjectNets[s]?.includes(editorNet!)) ?? selectedSubjects[0];
      if (!subject || !editorNet) return [] as string[];
      const nets = await getEegNets(subject);
      return nets.find((n) => n.name === editorNet)?.electrodes ?? [];
    },
    enabled: !!editorNet && selectedSubjects.length > 0,
  });

  /** Every montage of one net, both buckets, in one list — the montage column's options. */
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
      dropSelection(m);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not delete the montage.", err instanceof Error ? err.message : undefined),
  });

  const eligibleSubjects = selectedSubjects.filter((s) => !editorNet || (subjectNets[s]?.includes(editorNet) ?? false));

  function eligibleFor(net: string): string[] {
    return selectedSubjects.filter((s) => subjectNets[s]?.includes(net) ?? false);
  }

  function rowId(m: { net: string; kind: MontageKind; name: string }) {
    return `montage:${m.net}:${m.kind}:${m.name}`;
  }

  /** The table's rows: one per montage the user has chosen, in the order they chose it. Rows and
   *  the plan are the same list — a row exists exactly when its (subject, montage) jobs do. */
  const chosen = useMemo(() => {
    const out: { key: string; montage: CatalogMontage; rows: SelectedRow[] }[] = [];
    const seen = new Map<string, number>();
    for (const r of selectedRows) {
      if (r.source !== "montage" || !r.eegNet || !r.kind) continue;
      const key = rowId({ net: r.eegNet, kind: r.kind, name: r.name });
      const at = seen.get(key);
      if (at === undefined) {
        seen.set(key, out.length);
        out.push({
          key,
          montage: { net: r.eegNet, kind: r.kind, name: r.name, pairs: r.pairs ?? [] },
          rows: [r],
        });
      } else {
        out[at]!.rows.push(r);
      }
    }
    return out;
  }, [selectedRows]);

  const activeRow = chosen.find((c) => c.key === activeKey) ?? null;
  const activeNet = activeRow?.montage.net;
  const activeName = activeRow?.montage.name;
  const activePairs = activeRow?.montage.pairs;
  // Reported in an effect, not during render: it is the page's state (which then hands it to the
  // shared scene pane exactly the way the montage draft is handed over).
  useEffect(() => {
    onPreviewChange?.(activeNet && activeName && activePairs ? { net: activeNet, name: activeName, pairs: activePairs } : null);
  }, [activeNet, activeName, activePairs, onPreviewChange]);

  function dropSelection(m: { net: string; kind: MontageKind; name: string }) {
    const id = rowId(m);
    if (activeKey === id) setActiveKey(null);
    for (const subject of selectedSubjects) onRemoveRow(`${id}:${subject}`);
    // Belt and braces: a subject that has since left the selection still owns rows with this id.
    for (const r of selectedRows) if (r.id.startsWith(`${id}:`)) onRemoveRow(r.id);
  }

  /** Fans one montage out to one job row per eligible subject (multi-subject fan-out). */
  function addSelection(m: CatalogMontage) {
    const id = rowId(m);
    const currents = defaultCurrentsFor(m.kind, m.pairs.length);
    for (const subject of eligibleFor(m.net)) {
      onAddRow({
        id: `${id}:${subject}`,
        subjectId: subject,
        source: "montage",
        kind: m.kind,
        eegNet: m.net,
        name: m.name,
        pairs: m.pairs,
        currents,
      });
    }
  }

  function pickMontage(rowKey: string | null, net: string, value: string) {
    const { kind, name } = parseMontageOptionValue(value);
    const montage = montagesOf(net).find((m) => m.kind === kind && m.name === name);
    if (!montage) return;
    // Replacing the montage of a filled row drops the old one's jobs first.
    const previous = chosen.find((c) => c.key === rowKey);
    if (previous) dropSelection(previous.montage);
    addSelection(montage);
    setPendingRows((prev) => prev.filter((p) => p.key !== rowKey));
    setNetChoice(net);
  }

  function changeNet(rowKey: string, net: string) {
    setNetChoice(net);
    const filled = chosen.find((c) => c.key === rowKey);
    if (filled) {
      // The montage belonged to the old net — the row goes back to "pick a montage", on the new one.
      dropSelection(filled.montage);
      setPendingRows((prev) => [...prev, { key: `pending-${pendingSeq++}`, net }]);
      return;
    }
    setPendingRows((prev) => prev.map((p) => (p.key === rowKey ? { ...p, net } : p)));
  }

  function addRow() {
    setPendingRows((prev) => [...prev, { key: `pending-${pendingSeq++}`, net: editorNet }]);
  }

  /** A brand-new montage always starts as a 2-pair draft; adding pairs makes it multi-polar. */
  function startNewMontage() {
    setEditing(emptyDraft());
  }

  const draftKind = editing ? inferMontageKind(editing.pairs.length) : "uni_polar";

  // The table always offers at least one row to fill in, without holding a pending row in state
  // for the empty case (nothing to clean up when it is used).
  const emptyRow: PendingRow[] = chosen.length === 0 && pendingRows.length === 0 ? [{ key: "row-1", net: editorNet }] : [];

  /** Reserved so a row switching TI <-> mTI never resizes the inputs already in the column: the
   *  cell is a grid of this many equal slots, whether or not every slot holds an input. */
  /* The table's own width, and the widths the user has set inside it. */
  const [tableWidth, setTableWidth] = useState(0);
  const [storedColumns, setStoredColumns] = useState<StoredColumns>(() =>
    readStoredColumns(typeof window === "undefined" ? undefined : window.localStorage),
  );
  // React 18: a ref callback cannot return a cleanup, so the observer lives in an effect.
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

  /** Rows whose net not every selected subject has — reported under the table, not in it. */
  const skipped = chosen
    .map(({ montage }) => ({ name: montage.name, net: montage.net, missing: selectedSubjects.length - eligibleFor(montage.net).length }))
    .filter((s) => s.missing > 0);

  const currentSlots = currentSlotsReserved(chosen.map((c) => currentsCount(c.montage.kind, c.montage.pairs.length)));

  /** Up/Down moves the active row — the one the 3-D pane is drawing. */
  function onTableKeyDown(e: React.KeyboardEvent<HTMLTableElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    if (chosen.length === 0) return;
    e.preventDefault();
    const at = chosen.findIndex((c) => c.key === activeKey);
    const next = e.key === "ArrowDown" ? Math.min(chosen.length - 1, at + 1) : Math.max(0, (at === -1 ? 0 : at) - 1);
    const key = chosen[next]?.key ?? null;
    setActiveKey(key);
    const row = e.currentTarget.querySelector<HTMLElement>(`tbody tr:nth-of-type(${next + 1})`);
    row?.focus();
  }

  function renderNetCell(rowKey: string, net: string | undefined, label: string) {
    return (
      <Select
        value={net}
        onValueChange={(v) => changeNet(rowKey, v)}
        options={availableNets.map((n) => ({ value: n, label: n }))}
        placeholder="EEG net"
        aria-label={`${label} EEG net`}
      />
    );
  }

  function montageOptions(net: string | undefined) {
    return montagesOf(net).map((m) => ({
      value: montageOptionValue(m.kind, m.name),
      label: `${m.name} · ${polarityLabel(m.kind)}`,
    }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {selectedSubjects.length === 0 && <Callout kind="info">Pick at least one subject above to add montages to the run.</Callout>}

      {montages.isPending && <Skeleton height={160} />}
      {montages.error && <Callout kind="danger">Could not load montages.</Callout>}
      {montages.data && availableNets.length === 0 && (
        <EmptyState icon={<Plus size={24} />} message="No EEG nets available for the selected subjects." />
      )}
      {montages.data && availableNets.length > 0 && (
        <div className="data-table-container" ref={tableBox} data-testid="montage-table-container">
          {/* Fixed geometry: an explicit `<colgroup>` plus `table-layout: fixed` (simulator-page.css).
              Nothing a user does to one ROW — net, montage, polarity — may move a cell in another;
              only a deliberate drag of a header boundary changes a COLUMN. The widths come from
              `resolveColumnWidths`, which always sums to the container, so the table cannot scroll
              sideways at any pane width (asserted in simulator.spec.ts). Before the first measure
              they are percentages of the same shape, so the first paint is not a 0px table. */}
          <table className="data-table montage-table" onKeyDown={onTableKeyDown}>
            <colgroup>
              <col style={{ width: tableWidth ? cols.net : "24%" }} />
              <col style={{ width: tableWidth ? cols.montage : "32%" }} />
              <col style={{ width: tableWidth ? cols.pairs : "14%" }} />
              <col style={{ width: tableWidth ? cols.currents : "20%" }} />
              <col style={{ width: tableWidth ? cols.actions : "10%" }} />
            </colgroup>
            <thead>
              <tr>
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
              {chosen.map(({ key, montage, rows }) => {
                const count = currentsCount(montage.kind, montage.pairs.length);
                const missing = selectedSubjects.length - eligibleFor(montage.net).length;
                return (
                  <tr
                    key={key}
                    data-montage-row={montage.name}
                    data-polarity={montage.kind}
                    data-active={activeKey === key ? "true" : undefined}
                    aria-selected={activeKey === key}
                    tabIndex={0}
                    onClick={(e) => {
                      // A click on a control in the row is that control's, not the row's.
                      if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
                      setActiveKey(key);
                    }}
                    onFocus={() => setActiveKey(key)}
                  >
                    <td>{renderNetCell(key, montage.net, montage.name)}</td>
                    <td>
                      <div
                        className="montage-cell"
                        title={missing > 0 ? `${missing} selected subject(s) do not have the "${montage.net}" net` : undefined}
                      >
                        <Select
                          value={montageOptionValue(montage.kind, montage.name)}
                          onValueChange={(v) => pickMontage(key, montage.net, v)}
                          options={montageOptions(montage.net)}
                          placeholder="Choose a montage"
                          aria-label={`Montage for ${montage.net}`}
                        />
                        {/* One fixed-width slot, drawn even when empty: the polarity chip changing
                            must not push the select beside it. The "N skipped" chip that used to
                            sit in a second reserved 76px slot is a footnote under the table now —
                            76px of permanently reserved width in a 608px table for a warning that
                            is usually absent is what made the row unable to fit. */}
                        <span className="montage-chip-slot" style={{ "--slot": "40px" } as React.CSSProperties}>
                          <span className="chip chip-neutral" title={montage.kind === "uni_polar" ? "Uni-polar (2 pairs)" : "Multi-polar (4+ pairs)"}>
                            {polarityLabel(montage.kind)}
                          </span>
                        </span>
                      </div>
                    </td>
                    <td className="mono text-dense">
                      <span className="montage-pairs" title={formatPairs(montage.pairs)}>
                        {formatPairs(montage.pairs)}
                      </span>
                    </td>
                    <td>
                      <CurrentsCell
                        rows={rows}
                        count={count}
                        slots={currentSlots}
                        label={montage.name}
                        onChange={(currents) => rows.forEach((r) => onCurrentsChange?.(r.id, currents))}
                      />
                    </td>
                    <td className="montage-actions">
                      <IconButton
                        aria-label={`Edit ${montage.name}`}
                        icon={<Pencil size={14} />}
                        onClick={() => {
                          setNetChoice(montage.net);
                          setEditing({ name: montage.name, pairs: montage.pairs.map((p) => [p[0], p[1]] as ElectrodePair), savedAs: montage.kind });
                        }}
                      />
                      <IconButton aria-label={`Delete ${montage.name}`} icon={<Trash2 size={14} />} onClick={() => setDeleteTarget(montage)} />
                      <IconButton aria-label={`Remove row ${montage.name}`} icon={<X size={14} />} onClick={() => dropSelection(montage)} />
                    </td>
                  </tr>
                );
              })}
              {[...pendingRows, ...emptyRow].map((p, i) => {
                const net = p.net && availableNets.includes(p.net) ? p.net : editorNet;
                const label = `row ${chosen.length + i + 1}`;
                return (
                  <tr key={p.key} data-montage-row="" data-polarity="">
                    <td>{renderNetCell(p.key, net, label)}</td>
                    <td>
                      <Select
                        value={undefined}
                        onValueChange={(v) => net && pickMontage(p.key, net, v)}
                        options={montageOptions(net)}
                        placeholder="Choose a montage"
                        aria-label={`Montage for ${label}`}
                      />
                    </td>
                    <td className="field-help">—</td>
                    <td className="field-help">—</td>
                    <td className="montage-actions">
                      {pendingRows.some((r) => r.key === p.key) && (
                        <IconButton
                          aria-label={`Remove ${label}`}
                          icon={<X size={14} />}
                          onClick={() => setPendingRows((prev) => prev.filter((r) => r.key !== p.key))}
                        />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* The "N skipped" warning, out of the table: it is rare, it is per row, and reserving a
          fixed slot for it in every row cost more width than the table had. */}
      {skipped.length > 0 && (
        <p className="field-help">
          {skipped.map((s) => `${s.name}: ${s.missing} selected subject(s) have no "${s.net}" net`).join(" · ")}
        </p>
      )}

      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={availableNets.length === 0} onClick={addRow}>
          Add row
        </Button>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={!editorNet} onClick={startNewMontage}>
          New montage
        </Button>
      </div>

      {eligibleSubjects.length === 0 && selectedSubjects.length > 0 && editorNet && (
        <Callout kind="warning">None of the selected subjects have the "{editorNet}" net.</Callout>
      )}

      {editing && (
        <Card>
          <CardHeader title={editing.name ? `Edit montage "${editing.name}"` : "New montage"} />
          <CardBody>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              {/* One label column: net, name and the polarity readout stack under each other in
                  the standard label-left `Field` grid, so their labels align with each other and
                  with the pair rows below. */}
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
              {/* Polarity is a readout, not a choice: it follows from the pairs picked. One line —
                  a chip and a short sentence, no storage detail and no (i). */}
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
                    // A montage is built in channels: two pairs (four electrodes) at a time, so
                    // "Add 2 pairs" / a remove that takes the whole group. 2 pairs is TI, 4+ mTI —
                    // an odd pair count is not reachable from the form at all.
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
                      dropSelection({ net: editorNet, kind: editing.savedAs, name: editing.name.trim() });
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
        onConfirm={() => deleteTarget && removeMontage.mutate(deleteTarget)}
      />
    </div>
  );
}
