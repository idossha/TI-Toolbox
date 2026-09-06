import { useEffect, useMemo, useState } from "react";
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

/** Minimum visible rows in the montage table (DESIGN.md §4.3 density + FXU1's fill rule). */
const MIN_MONTAGE_ROWS = 6;

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

/** One `NumberInput` per required current (mA); `row.currents` stays the comma-joined wire string. */
function CurrentsCell({
  rows,
  count,
  label,
  onChange,
}: {
  rows: SelectedRow[];
  count: number;
  label: string;
  onChange: (currents: string) => void;
}) {
  const first = rows[0];
  if (!first) return <span className="field-help">—</span>;
  const values = currentValues(first.currents, count);
  return (
    <div className="montage-currents">
      {values.map((v, i) => (
        <NumberInput
          key={i}
          value={v}
          onValueChange={(next) => onChange(values.map((old, idx) => (idx === i ? (next ?? old) : old)).join(","))}
          step={0.1}
          min={0}
          unit="mA"
          aria-label={`${label} pair ${i + 1} current`}
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
  onPreviewChange?: (preview: { net: string; pairs: [string, string][] } | null) => void;
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
  const activePairs = activeRow?.montage.pairs;
  // Reported in an effect, not during render: it is the page's state (which then hands it to the
  // shared scene pane exactly the way the montage draft is handed over).
  useEffect(() => {
    onPreviewChange?.(activeNet && activePairs ? { net: activeNet, pairs: activePairs } : null);
  }, [activeNet, activePairs, onPreviewChange]);

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
  const displayed = chosen.length + pendingRows.length + emptyRow.length;

  /** Reserved so a row switching TI <-> mTI never widens (or narrows) the column. */
  const currentsWidth = currentSlotsReserved(chosen.map((c) => currentsCount(c.montage.kind, c.montage.pairs.length))) * 100 + 24;

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
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {selectedSubjects.length === 0 && <Callout kind="info">Pick at least one subject above to add montages to the run.</Callout>}

      {montages.isPending && <Skeleton height={160} />}
      {montages.error && <Callout kind="danger">Could not load montages.</Callout>}
      {montages.data && availableNets.length === 0 && (
        <EmptyState icon={<Plus size={24} />} message="No EEG nets available for the selected subjects." />
      )}
      {montages.data && availableNets.length > 0 && (
        <div className="data-table-container scroll-x">
          {/* Fixed geometry: an explicit `<colgroup>` plus `table-layout: fixed` (simulator-page.css).
              Nothing a user does to one row — net, montage, polarity — may move a cell in another. */}
          <table className="data-table run-table-min-rows montage-table" onKeyDown={onTableKeyDown}>
            <colgroup>
              <col style={{ width: 210 }} />
              <col style={{ width: 300 }} />
              <col style={{ width: 300 }} />
              <col style={{ width: currentsWidth }} />
              <col style={{ width: 120 }} />
            </colgroup>
            <thead>
              <tr>
                <th>EEG net</th>
                <th>Montage</th>
                <th>Pairs</th>
                <th>Currents</th>
                <th />
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
                      <div className="montage-cell">
                        <Select
                          value={montageOptionValue(montage.kind, montage.name)}
                          onValueChange={(v) => pickMontage(key, montage.net, v)}
                          options={montageOptions(montage.net)}
                          placeholder="Choose a montage"
                          aria-label={`Montage for ${montage.net}`}
                        />
                        {/* Fixed-width slots, drawn even when empty: a chip appearing must not
                            push the select beside it. */}
                        <span className="montage-chip-slot" style={{ "--slot": "40px" } as React.CSSProperties}>
                          <span className="chip chip-neutral" title={montage.kind === "uni_polar" ? "Uni-polar (2 pairs)" : "Multi-polar (4+ pairs)"}>
                            {polarityLabel(montage.kind)}
                          </span>
                        </span>
                        <span className="montage-chip-slot" style={{ "--slot": "76px" } as React.CSSProperties}>
                          {missing > 0 && (
                            <span className="chip chip-warning" title={`${missing} selected subject(s) do not have the "${montage.net}" net`}>
                              {missing} skipped
                            </span>
                          )}
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
                        label={montage.name}
                        onChange={(currents) => rows.forEach((r) => onCurrentsChange?.(r.id, currents))}
                      />
                    </td>
                    <td style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
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
                    <td style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
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
              {/* A minimum of six visible rows (FXU1). The montage table is the Simulator's Tier-1
                  control and a two-row table left the pane looking unfinished; the filler rows are
                  drawn as ground (`--surface` + the same rule), not as blank page, so they read as
                  "room for more montages" rather than as a rendering fault. */}
              {Array.from({ length: Math.max(0, MIN_MONTAGE_ROWS - displayed) }, (_, i) => (
                <tr key={`filler-${i}`} className="run-table-filler" aria-hidden>
                  <td colSpan={5} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
