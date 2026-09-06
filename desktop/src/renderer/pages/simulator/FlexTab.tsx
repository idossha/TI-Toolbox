import { useQueries } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Waypoints } from "lucide-react";
import { Checkbox } from "../../ui/Toggle";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Chip } from "../../ui/Status";
import { getFlexRuns, type FlexRun } from "./api";
import { defaultCurrents, type SelectedRow } from "./types";

function rowId(subject: string, run: string) {
  return `flex:${subject}:${run}`;
}

/** `manifest.electrodes` is a label-pair list from a mapped (EEG-net) flex-search result. */
function manifestPairs(run: FlexRun): [string, string][] {
  const electrodes = (run.manifest as { electrodes?: unknown }).electrodes;
  if (!Array.isArray(electrodes)) return [];
  return electrodes.filter((p): p is [string, string] => Array.isArray(p) && p.length === 2 && typeof p[0] === "string" && typeof p[1] === "string");
}

export function FlexTab({
  selectedSubjects,
  selectedRows,
  onAddRow,
  onRemoveRow,
}: {
  selectedSubjects: string[];
  selectedRows: SelectedRow[];
  onAddRow: (row: SelectedRow) => void;
  onRemoveRow: (id: string) => void;
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
        Simulate a completed flex-search's best electrode placement, mapped back onto EEG-cap labels. The resolved montage preview comes from the
        run's manifest.
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
                <th>Electrodes</th>
                <th data-align="right">Best score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ subject, run }) => {
                const pairs = manifestPairs(run);
                const id = rowId(subject, run.name);
                const checked = selectedRows.some((r) => r.id === id);
                const eegNet = String((run.manifest as { eeg_net?: unknown }).eeg_net ?? "");
                const bestScore = (run.manifest as { best_score?: unknown }).best_score;
                return (
                  <tr key={id}>
                    <td>
                      <Checkbox
                        checked={checked}
                        disabled={pairs.length === 0}
                        onCheckedChange={(on) => {
                          if (on) {
                            onAddRow({
                              id,
                              subjectId: subject,
                              source: "flex",
                              eegNet,
                              name: run.name,
                              pairs,
                              currents: defaultCurrents(pairs.length),
                            });
                          } else {
                            onRemoveRow(id);
                          }
                        }}
                      />
                    </td>
                    <td className="mono">{subject}</td>
                    <td className="mono">{run.name}</td>
                    <td>
                      <Chip kind="accent">{run.goal}</Chip>
                    </td>
                    <td className="text-dense">{pairs.length > 0 ? pairs.map((p) => `${p[0]}→${p[1]}`).join(", ") : "no mapped electrodes in manifest"}</td>
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
