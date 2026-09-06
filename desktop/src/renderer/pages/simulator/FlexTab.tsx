/**
 * "Flex result" — simulate a completed flex-search's optimised electrode set.
 *
 * Where the electrodes come from: **not** `flex_meta.json`. A flex run's manifest records the
 * goal, the ROI and the optimiser's score, and nothing at all about the electrodes it found — so
 * the earlier `manifest.electrodes` read here was always `undefined`, which disabled every row's
 * checkbox and made the whole tab unclickable (simulator PARITY.md #4, closed by this file).
 *
 * The electrodes live beside the manifest in the run directory, and `tit/catalog.py::flex_runs`
 * now surfaces both forms the toolbox can simulate:
 *
 *   - `run.mappings` — one entry per `electrode_mapping_<net>.json` the run has, i.e. the result
 *     already snapped onto that EEG cap's labels (`Montage.Mode.FLEX_MAPPED`);
 *   - `run.optimized` — the free XYZ pairs from `electrode_positions.json`, which every flex run
 *     writes (`Montage.Mode.FLEX_FREE`).
 *
 * A run therefore offers at least the free placement, and the per-row select is the choice between
 * them. Both are resolved here rather than at submit time because `POST /api/jobs`' `JobSpec` has
 * no `montage_sources` field: a submitted job carries a fully-resolved `Montage`.
 */
import { useQueries } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Waypoints } from "lucide-react";
import { Checkbox } from "../../ui/Toggle";
import { Select } from "../../ui/Select";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import { getFlexRuns, type FlexRun } from "./api";
import { defaultCurrents, type SelectedRow } from "./types";

function rowId(subject: string, run: string) {
  return `flex:${subject}:${run}`;
}

/** The free-XYZ placement's option value; anything else is an EEG-net filename. */
export const OPTIMIZED = "__optimized__";

export interface FlexPlacement {
  /** `OPTIMIZED`, or the EEG net whose mapping this is. */
  value: string;
  label: string;
  pairs?: [string, string][];
  xyzPairs?: [[number, number, number], [number, number, number]][];
}

/** Every placement a run can be simulated in: one per mapped net, then the free XYZ one. */
export function placementsFor(run: FlexRun): FlexPlacement[] {
  const out: FlexPlacement[] = [];
  for (const mapping of run.mappings ?? []) {
    const pairs = (mapping.pairs ?? [])
      .filter((p) => p.length === 2)
      .map((p) => [p[0], p[1]] as [string, string]);
    if (pairs.length === 0) continue;
    out.push({ value: mapping.eeg_net, label: mapping.eeg_net.replace(/\.csv$/, ""), pairs });
  }
  const optimized = (run.optimized ?? [])
    .filter((p) => p.length === 2 && p[0]?.length === 3 && p[1]?.length === 3)
    .map((p) => [p[0], p[1]] as [[number, number, number], [number, number, number]]);
  if (optimized.length > 0) out.push({ value: OPTIMIZED, label: "Optimised positions (XYZ)", xyzPairs: optimized });
  return out;
}

/** One row's electrode summary — labels when mapped, a coordinate count when free. */
export function placementSummary(placement: FlexPlacement): string {
  if (placement.pairs) return placement.pairs.map((p) => `${p[0]}→${p[1]}`).join(", ");
  const n = (placement.xyzPairs?.length ?? 0) * 2;
  return `${n} optimised coordinates`;
}

function rowFor(subject: string, run: FlexRun, placement: FlexPlacement): SelectedRow {
  const numPairs = placement.pairs?.length ?? placement.xyzPairs?.length ?? 0;
  return {
    id: rowId(subject, run.name),
    subjectId: subject,
    source: "flex",
    // A free-XYZ placement has no net, and that absence is what `buildSimulationConfig` reads to
    // pick `flex_free` over `flex_mapped` — the same distinction `Montage` itself makes.
    eegNet: placement.value === OPTIMIZED ? undefined : placement.value,
    name: run.name,
    pairs: placement.pairs,
    xyzPairs: placement.xyzPairs,
    currents: defaultCurrents(numPairs),
  };
}

export function FlexTab({
  selectedSubjects,
  selectedRows,
  onAddRow,
  onRemoveRow,
  placement,
  onPlacementChange,
}: {
  selectedSubjects: string[];
  selectedRows: SelectedRow[];
  onAddRow: (row: SelectedRow) => void;
  onRemoveRow: (id: string) => void;
  /** Chosen placement per row id; a row absent from it uses the run's first placement. */
  placement: Record<string, string>;
  onPlacementChange: (id: string, value: string) => void;
}) {
  const navigate = useNavigate();
  const queries = useQueries({
    queries: selectedSubjects.map((subject) => ({
      queryKey: ["flex-runs", subject],
      queryFn: () => getFlexRuns(subject),
    })),
  });

  if (selectedSubjects.length === 0) {
    return <Callout kind="info">Pick at least one subject above to see its flex-search runs.</Callout>;
  }

  const isLoading = queries.some((q) => q.isPending);
  const failed = queries.some((q) => q.error);

  const rows: { subject: string; run: FlexRun }[] = [];
  selectedSubjects.forEach((subject, i) => {
    for (const run of queries[i]?.data ?? []) rows.push({ subject, run });
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <p className="field-help">
        Simulate a completed flex-search's best electrode placement — either mapped back onto an EEG cap's labels, or as the
        optimiser's own free coordinates.
      </p>
      {isLoading && <Skeleton height={120} />}
      {failed && <Callout kind="danger">Could not load flex-search runs for one or more subjects.</Callout>}
      {!isLoading && rows.length === 0 && (
        <EmptyState
          icon={<Waypoints size={24} />}
          message="No flex-search runs for the selected subjects yet."
          actionLabel="Go to Optimizer"
          onAction={() => navigate("/optimizer")}
        />
      )}
      {rows.length > 0 && (
        <div className="data-table-container scroll-x">
          <table className="data-table">
            <thead>
              <tr>
                <th />
                <th>Subject</th>
                <th>Run</th>
                <th>Goal</th>
                <th>Placement</th>
                <th>Electrodes</th>
                <th data-align="right">Best score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ subject, run }) => {
                const id = rowId(subject, run.name);
                const options = placementsFor(run);
                const chosen = options.find((o) => o.value === placement[id]) ?? options[0];
                const checked = selectedRows.some((r) => r.id === id);
                const bestScore = (run.manifest as { best_score?: unknown }).best_score;
                return (
                  <tr key={id} data-testid="flex-run-row" data-run={run.name}>
                    <td>
                      <Checkbox
                        checked={checked}
                        // The only reason a run cannot be picked: it wrote neither a mapping nor
                        // usable optimised positions, so there is no montage to simulate.
                        disabled={!chosen}
                        aria-label={`Select flex run ${run.name}`}
                        onCheckedChange={(on) => {
                          if (on && chosen) onAddRow(rowFor(subject, run, chosen));
                          else onRemoveRow(id);
                        }}
                      />
                    </td>
                    <td className="mono">{subject}</td>
                    <td className="mono">{run.name}</td>
                    <td>
                      <Chip kind="accent">{run.goal}</Chip>
                    </td>
                    <td>
                      {chosen ? (
                        <Select
                          value={chosen.value}
                          aria-label={`Placement for ${run.name}`}
                          options={options.map((o) => ({ value: o.value, label: o.label }))}
                          onValueChange={(value) => {
                            onPlacementChange(id, value);
                            // A picked row follows its placement: re-add it resolved the new way,
                            // rather than leaving the plan on electrodes no longer shown.
                            const next = options.find((o) => o.value === value);
                            if (checked && next) {
                              onRemoveRow(id);
                              onAddRow(rowFor(subject, run, next));
                            }
                          }}
                        />
                      ) : (
                        <span className="text-dense">—</span>
                      )}
                    </td>
                    <td className="text-dense">{chosen ? placementSummary(chosen) : "this run wrote no usable electrode positions"}</td>
                    <td data-align="right" className="tabular-nums">
                      {typeof bestScore === "number" ? bestScore.toFixed(3) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
