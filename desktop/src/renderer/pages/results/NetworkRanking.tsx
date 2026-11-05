/**
 * Ranking an ex-search run's montages on a network: an explicit action, because it takes a job and
 * a run does not have to be about a network at all. Every statistic is a column and neither rank is
 * marked preferred; rows open sorted by montage name until the reader chooses a column.
 */
import { useMemo, useState } from "react";
import type { SortingState } from "@tanstack/react-table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Callout } from "../../ui/Feedback";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { notify } from "../../ui/Toast";
import { getTractMasks, getTractRankings, type TractMask, type TractRanking } from "../_shared/roi";
import { submitJobGroup } from "../_shared/run";
import { getCandidates } from "./candidates/api";

type Row = TractRanking["montages"][number];

/** `TargetConfig.top_n`'s default. */
const DEFAULT_TOP_N = 20;
/** Seconds per montage: 1,718 s over 14,535 on sub-CHN, emulated amd64 (2026-11-05). */
const SECONDS_PER_MONTAGE = 0.12;
/** Rows drawn at a time: a run's every montage is too many for one table in the DOM. */
const ROWS_SHOWN = 200;

/** `about 29 min`, or `under a minute` for a run that small. */
export function rankingEstimate(montages: number): string {
  const minutes = (montages * SECONDS_PER_MONTAGE) / 60;
  return minutes < 1 ? "under a minute" : `about ${Math.round(minutes)} min`;
}

const stat = (key: keyof Row, header: string): DataTableColumn<Row> => ({
  id: key,
  header,
  numeric: true,
  accessorFn: (row) => row[key],
  cell: ({ getValue }) => (getValue() as number).toFixed(4),
});
const rank = (key: keyof Row, header: string): DataTableColumn<Row> => ({ id: key, header, numeric: true, accessorFn: (row) => row[key] });

export const RANKING_COLUMNS: DataTableColumn<Row>[] = [
  { id: "montage", header: "Montage", accessorFn: (row) => row.montage.join(" ") },
  // First, so a 1440 px window shows them without scrolling past six wide statistics.
  rank("rank_by_ti_along", "Rank by ti_along"),
  rank("rank_by_ti_max", "Rank by ti_max"),
  stat("median_sl_mean_ti_along", "Median streamline mean ti_along (V/m)"),
  stat("pooled_mean_ti_along", "Pooled mean ti_along (V/m)"),
  stat("median_sl_mean_ti_max", "Median streamline mean ti_max (V/m)"),
  stat("pooled_mean_ti_max", "Pooled mean ti_max (V/m)"),
  stat("median_sl_mean_ti_avg", "Median streamline mean ti_avg (V/m)"),
  stat("pooled_mean_ti_avg", "Pooled mean ti_avg (V/m)"),
  stat("align_index", "Alignment index"),
];

/** The wire config of the ranking job: the mask's own selection, so it stays that mask. */
export function rankingConfig(subject: string, run: string, leadfield: string, mask: TractMask, topN: number | null) {
  return {
    _type: "TractConfig",
    subject_id: subject,
    stages: ["target"],
    target: {
      selection: { name: mask.name, kind: "edges", pairs: mask.pairs },
      min_count: mask.min_count,
      leadfield_hdf: leadfield,
      ex_run: run,
      top_n: topN,
    },
  };
}

/** One ranking, sorted here because it draws only the top of the sort. */
function RankingTable({ ranking }: { ranking: TractRanking }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [shown, setShown] = useState(ROWS_SHOWN);
  const rows = useMemo(() => {
    const by = sorting[0];
    const name = (row: Row) => row.montage.join(" ");
    if (!by || by.id === "montage") {
      const named = [...ranking.montages].sort((a, b) => name(a).localeCompare(name(b)));
      return by?.desc ? named.reverse() : named;
    }
    const key = by.id as keyof Row;
    const sign = by.desc ? -1 : 1;
    return [...ranking.montages].sort((a, b) => sign * (Number(a[key]) - Number(b[key])));
  }, [ranking, sorting]);
  return (
    <>
      <div className="scroll-x">
        <DataTable data={rows.slice(0, shown)} columns={RANKING_COLUMNS} getRowId={(row) => row.montage.join(" ")} sorting={sorting} onSortingChange={setSorting} />
      </div>
      {rows.length > shown && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <span className="field-help tabular" data-testid="network-ranking-shown">
            First {shown.toLocaleString("en-US")} of {rows.length.toLocaleString("en-US")} in this order. All are in ranking_{ranking.name}.csv.
          </span>
          <Button variant="secondary" size="sm" onClick={() => setShown(shown + ROWS_SHOWN)}>Show {ROWS_SHOWN} more</Button>
        </div>
      )}
    </>
  );
}

export function NetworkRanking({ subject, run, runConfig }: { subject: string; run: string; runConfig: string | undefined }) {
  const queryClient = useQueryClient();
  const masks = useQuery({ queryKey: ["tract-masks", subject], queryFn: () => getTractMasks(subject) });
  const rankings = useQuery({ queryKey: ["tract-rankings", subject, run], queryFn: () => getTractRankings(subject, run) });
  const { leadfield, targetMask } = useMemo(() => {
    try {
      const parsed = JSON.parse(runConfig ?? "{}") as { leadfield_hdf?: string; roi_atlas?: { atlas_path?: string }[] };
      return { leadfield: parsed.leadfield_hdf, targetMask: parsed.roi_atlas?.[0]?.atlas_path };
    } catch {
      return { leadfield: undefined, targetMask: undefined };
    }
  }, [runConfig]);
  const usable = useMemo(() => (masks.data ?? []).filter((mask) => !mask.stale), [masks.data]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [scope, setScope] = useState<"all" | "top">("all");
  const [topN, setTopN] = useState(DEFAULT_TOP_N);
  const total = useQuery({
    queryKey: ["ex-run-montages", subject, run],
    queryFn: async () => (await getCandidates({ subject, kind: "ex", run }, 0, "Composite_Index", true, 1)).total,
    retry: false,
  });
  const mask = usable.find((m) => m.name === chosen) ?? usable.find((m) => m.path === targetMask) ?? usable[0];
  const rank = useMutation({
    mutationFn: () => submitJobGroup("tract", rankingConfig(subject, run, leadfield as string, mask as TractMask, scope === "all" ? null : topN), [subject], { overwrite: true }),
    onSuccess: () => {
      notify.success("Queued the ranking.");
      void queryClient.invalidateQueries({ queryKey: ["tract-rankings"] });
    },
    onError: (error) => notify.error(error.message),
  });

  const allLabel = total.data === undefined ? "All montages in the run" : `All montages in the run (${total.data.toLocaleString("en-US")}, ${rankingEstimate(total.data)})`;
  return (
    <div data-testid="network-ranking" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {usable.length === 0 ? (
        <p className="field-help" data-testid="network-ranking-empty">
          No current network mask for sub-{subject}. Create one in the Optimizer&rsquo;s Network target, then rank this run&rsquo;s montages on it.
        </p>
      ) : (
        <div className="form-grid">
          <Field label="Network">
            <Select aria-label="Network mask" value={mask?.name ?? ""} onValueChange={setChosen} options={usable.map((m) => ({ value: m.name, label: `${m.name} · ${m.n_edges} edge${m.n_edges === 1 ? "" : "s"}` }))} />
          </Field>
          <Field label="Montages" help="A montage strong on the composite index need not be strong along the fibres, so a top-N can leave out what this ranking would put first.">
            <Select aria-label="Montages to rank" value={scope} onValueChange={(v) => setScope(v === "top" ? "top" : "all")} options={[{ value: "all", label: allLabel }, { value: "top", label: "Top N by composite index" }]} />
          </Field>
          {scope === "top" && (
            <Field label="N" help={rankingEstimate(topN)}>
              <NumberInput value={topN} min={1} step={1} onValueChange={(v) => setTopN(Math.max(1, Math.round(v ?? DEFAULT_TOP_N)))} />
            </Field>
          )}
          <Button variant="secondary" size="sm" disabled={!mask || !leadfield || rank.isPending} onClick={() => rank.mutate()} data-testid="network-rank">
            {rank.isPending ? "Queueing…" : "Rank montages"}
          </Button>
        </div>
      )}
      {rankings.error && <Callout kind="danger">{rankings.error.message}</Callout>}
      {(rankings.data ?? []).map((ranking) => (
        <section key={ranking.name} data-testid="network-ranking-table" data-network={ranking.name}>
          <p className="field-help">
            {ranking.name} · {ranking.n_streamlines.toLocaleString("en-US")} streamlines · {ranking.current_mA.join(" : ")} mA ·{" "}
            {ranking.n_points_in_leadfield_mesh.toLocaleString("en-US")} of {ranking.n_points.toLocaleString("en-US")} points inside the leadfield mesh. Field descriptors, not activation predictions. Select a column to sort.
          </p>
          <RankingTable ranking={ranking} />
        </section>
      ))}
    </div>
  );
}
