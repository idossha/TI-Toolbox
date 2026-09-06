import { useEffect, useMemo, useState } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { Checkbox } from "../../ui/Toggle";
import { AlertDialog } from "../../ui/Overlay";
import { Field, TextInput } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { ElectrodePairsEditor, type ElectrodePair } from "../../ui/ElectrodePairsEditor";
import { notify } from "../../ui/Toast";
import { NumberInput } from "../../ui/NumberInput";
import { deleteMontage, getEegNets, getMontages, putMontage } from "./api";
import { defaultCurrents, type SelectedRow } from "./types";

/** Minimum visible rows in the montage table (DESIGN.md §4.3 density + FXU1's fill rule). */
const MIN_MONTAGE_ROWS = 6;

/** One `NumberInput` per pair current (mA); `row.currents` stays the comma-joined wire string. */
function CurrentsCell({ rows, onChange }: { rows: SelectedRow[]; onChange: (currents: string) => void }) {
  const first = rows[0];
  if (!first) return <span className="field-help">—</span>;
  const values = first.currents.split(",").map((v) => Number(v.trim()));
  return (
    <div style={{ display: "flex", gap: "var(--space-1)" }}>
      {values.map((v, i) => (
        <NumberInput
          key={i}
          value={Number.isNaN(v) ? undefined : v}
          onValueChange={(next) => onChange(values.map((old, idx) => (idx === i ? (next ?? old) : old)).join(","))}
          step={0.1}
          min={0}
          unit="mA"
          style={{ width: 84 }}
          aria-label={`${first.name} pair ${i + 1} current`}
        />
      ))}
    </div>
  );
}

export type Kind = "uni_polar" | "multi_polar";

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
}

/** A fresh draft of the right shape: 2 pairs for uni-polar (TI), 4 for multi-polar (mTI). */
export function emptyDraft(kind: Kind): MontageDraft {
  return {
    name: "",
    pairs: kind === "multi_polar" ? [["", ""], ["", ""], ["", ""], ["", ""]] : [["", ""], ["", ""]],
  };
}

/** Matches `Montage.simulation_mode`: exactly 2 pairs (TI) or 4+ pairs (mTI); 1 or 3 is invalid. */
function isValidPairCount(n: number): boolean {
  return n === 2 || n >= 4;
}

export function MontageManager({
  selectedSubjects,
  subjectNets,
  selectedRows,
  onAddRow,
  onRemoveRow,
  onCurrentsChange,
  kind,
  onKindChange,
  draft,
  onDraftChange,
  onNetChange,
}: {
  selectedSubjects: string[];
  /** subjectId -> eeg net names it has (from SubjectDetail.eeg_nets). */
  subjectNets: Record<string, string[]>;
  selectedRows: SelectedRow[];
  onAddRow: (row: SelectedRow) => void;
  onRemoveRow: (id: string) => void;
  /** Uni-/multi-polar, owned by the page so a scene-started draft has the right pair count. */
  kind: Kind;
  onKindChange: (kind: Kind) => void;
  /** The montage being written, owned by the page and shared with the scene pane. */
  draft: MontageDraft | null;
  onDraftChange: (draft: MontageDraft | null) => void;
  /** The resolved net, reported upward so the scene pane draws the same one's electrodes. */
  onNetChange?: (net: string | undefined) => void;
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

  // Derived, not effect-synced state: falls back to the first available net until the user picks
  // one explicitly, without an extra render (react-hooks/set-state-in-effect).
  const [netChoice, setNetChoice] = useState<string | undefined>(undefined);
  const net = netChoice && availableNets.includes(netChoice) ? netChoice : availableNets[0];
  const setNet = setNetChoice;

  const setKind = onKindChange;
  // An inline panel (Card), not a Dialog: a `Select` popover's z-index (60) sits below a Dialog's
  // own overlay/content (80/90) in ui/components.css, which makes the electrode-pair pickers
  // inside a modal montage editor unclickable (reported to F2 — see PARITY.md).
  const editing = draft;
  const setEditing = onDraftChange;
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // The net is derived (see above), so the page learns it from here rather than duplicating the
  // fallback rule. Reported in an effect, not during render: it is the parent's state.
  useEffect(() => {
    onNetChange?.(net);
  }, [net, onNetChange]);

  const netElectrodes = useQuery({
    queryKey: ["eeg-net-electrodes", net, selectedSubjects[0]],
    queryFn: async () => {
      const subject = selectedSubjects.find((s) => subjectNets[s]?.includes(net!)) ?? selectedSubjects[0];
      if (!subject || !net) return [] as string[];
      const nets = await getEegNets(subject);
      return nets.find((n) => n.name === net)?.electrodes ?? [];
    },
    enabled: !!net && selectedSubjects.length > 0,
  });

  const saveMontage = useMutation({
    mutationFn: ({ name, pairs }: { name: string; pairs: ElectrodePair[] }) =>
      putMontage(net!, kind, name, pairs.map((p) => [p[0], p[1]])),
    onSuccess: (_data, vars) => {
      notify.success(`Saved montage "${vars.name}".`);
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not save the montage.", err instanceof Error ? err.message : undefined),
  });

  const removeMontage = useMutation({
    mutationFn: (name: string) => deleteMontage(net!, kind, name),
    onSuccess: (_data, name) => {
      notify.success(`Deleted montage "${name}".`);
      setDeleteTarget(null);
      // Selected rows are keyed per-subject (`${id}:${subject}`) — drop every subject's copy.
      const id = rowId(net!, kind, name);
      for (const subject of selectedSubjects) onRemoveRow(`${id}:${subject}`);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not delete the montage.", err instanceof Error ? err.message : undefined),
  });

  const bucket = net ? (kind === "uni_polar" ? montages.data?.nets[net]?.uni_polar : montages.data?.nets[net]?.multi_polar) : undefined;
  const entries = Object.entries(bucket ?? {});

  function rowId(n: string, k: Kind, name: string) {
    return `montage:${n}:${k}:${name}`;
  }

  function toggle(name: string, pairs: string[][], checked: boolean) {
    if (!net) return;
    const id = rowId(net, kind, name);
    if (checked) {
      for (const subject of eligibleSubjects) {
        onAddRow({
          id: `${id}:${subject}`,
          subjectId: subject,
          source: "montage",
          kind,
          eegNet: net,
          name,
          pairs: pairs.map((p) => [p[0], p[1]] as [string, string]),
          currents: defaultCurrents(pairs.length),
        });
      }
    } else {
      for (const subject of selectedSubjects) onRemoveRow(`${id}:${subject}`);
    }
  }

  const eligibleSubjects = selectedSubjects.filter((s) => !net || (subjectNets[s]?.includes(net) ?? false));
  const ineligibleCount = selectedSubjects.length - eligibleSubjects.length;

  /** Every ticked (subject, montage) row for one montage name — they share one currents value,
   *  because the montage's pair count is what the currents are per. */
  function selectedRowsFor(name: string): SelectedRow[] {
    if (!net) return [];
    const id = rowId(net, kind, name);
    return selectedRows.filter((r) => r.id.startsWith(`${id}:`));
  }

  function isChecked(name: string): boolean {
    if (!net) return false;
    const id = rowId(net, kind, name);
    return eligibleSubjects.length > 0 && eligibleSubjects.every((s) => selectedRows.some((r) => r.id === `${id}:${s}`));
  }

  /** Matches `Montage.simulation_mode`: a uni-polar (TI) montage needs exactly 2 pairs, a
   *  multi-polar (mTI) montage needs 4 or more. */
  function startNewMontage() {
    setEditing(emptyDraft(kind));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label="EEG net">
          <Select value={net} onValueChange={setNet} options={availableNets.map((n) => ({ value: n, label: n }))} placeholder="Choose a net" />
        </Field>
        <Field label="Polarity">
          <Select
            value={kind}
            onValueChange={(v) => setKind(v as Kind)}
            options={[
              { value: "uni_polar", label: "Uni-polar (TI, 2 pairs)" },
              { value: "multi_polar", label: "Multi-polar (mTI, 4+ pairs)" },
            ]}
          />
        </Field>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={!net} onClick={startNewMontage}>
          New montage
        </Button>
      </div>

      {selectedSubjects.length === 0 && <Callout kind="info">Pick at least one subject above to add montages to the run.</Callout>}
      {ineligibleCount > 0 && net && (
        <Callout kind="warning">
          {ineligibleCount} of {selectedSubjects.length} selected subjects do not have the "{net}" net and will be skipped for this montage.
        </Callout>
      )}

      {montages.isPending && <Skeleton height={160} />}
      {montages.error && <Callout kind="danger">Could not load montages.</Callout>}
      {montages.data && entries.length === 0 && (
        <EmptyState
          icon={<Plus size={24} />}
          message={net ? `No ${kind === "uni_polar" ? "uni-polar" : "multi-polar"} montages for ${net} yet.` : "Choose a net to see its montages."}
          actionLabel={net ? "New montage" : undefined}
          onAction={net ? startNewMontage : undefined}
        />
      )}
      {montages.data && entries.length > 0 && (
        <div className="data-table-container scroll-x">
          <table className="data-table run-table-min-rows">
            <thead>
              <tr>
                <th />
                <th>Montage</th>
                <th>Pairs</th>
                <th>Currents</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {entries.map(([name, pairs]) => (
                <tr key={name}>
                  <td>
                    <Checkbox
                      checked={isChecked(name)}
                      onCheckedChange={(checked) => toggle(name, pairs, checked)}
                      disabled={eligibleSubjects.length === 0}
                    />
                  </td>
                  <td className="mono">{name}</td>
                  <td className="text-dense">{pairs.map((p) => `${p[0]}→${p[1]}`).join(", ")}</td>
                  <td>
                    <CurrentsCell
                      rows={selectedRowsFor(name)}
                      onChange={(currents) => selectedRowsFor(name).forEach((r) => onCurrentsChange?.(r.id, currents))}
                    />
                  </td>
                  <td style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                    <IconButton
                      aria-label={`Edit ${name}`}
                      icon={<Pencil size={14} />}
                      onClick={() => setEditing({ name, pairs: pairs.map((p) => [p[0], p[1]] as ElectrodePair) })}
                    />
                    <IconButton aria-label={`Delete ${name}`} icon={<Trash2 size={14} />} onClick={() => setDeleteTarget(name)} />
                  </td>
                </tr>
              ))}
              {/* A minimum of six visible rows (FXU1). The montage table is the Simulator's Tier-1
                  control and a two-row table left the pane looking unfinished; the filler rows are
                  drawn as ground (`--surface` + the same rule), not as blank page, so they read as
                  "room for more montages" rather than as a rendering fault. */}
              {Array.from({ length: Math.max(0, MIN_MONTAGE_ROWS - entries.length) }, (_, i) => (
                <tr key={`filler-${i}`} className="run-table-filler" aria-hidden>
                  <td colSpan={5} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <Card>
          <CardHeader title={editing.name ? `Edit montage "${editing.name}"` : "New montage"} />
          <CardBody>
            <p className="field-help" style={{ marginBottom: "var(--space-3)" }}>
              {kind === "uni_polar" ? "Uni-polar (2 electrode pairs)" : "Multi-polar (4 or more electrode pairs)"} montage on {net ?? "…"}.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <Field label="Montage name" required>
                <TextInput value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="e.g. F3_F4" />
              </Field>
              <Field label="Electrode pairs" help="Selected from the net's electrode labels.">
                {netElectrodes.isFetching && <Skeleton height={32} />}
                {!netElectrodes.isFetching && (
                  <ElectrodePairsEditor
                    mode="net"

                    electrodes={netElectrodes.data ?? []}
                    pairs={editing.pairs}
                    onPairsChange={(pairs) => setEditing({ ...editing, pairs })}
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
                  disabled={!editing.name.trim() || editing.pairs.some((p) => !p[0] || !p[1]) || !isValidPairCount(editing.pairs.length)}
                  onClick={() => saveMontage.mutate({ name: editing.name.trim(), pairs: editing.pairs })}
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
        title={`Delete montage "${deleteTarget}"?`}
        description="This removes the montage definition for this net. Simulations already run from it are unaffected."
        confirmLabel="Delete montage"
        onConfirm={() => deleteTarget && removeMontage.mutate(deleteTarget)}
      />
    </div>
  );
}
