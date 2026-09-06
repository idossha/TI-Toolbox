/**
 * "Flex result" as a job **source** — the placements a completed flex-search can be simulated in.
 *
 * The tab this file used to be is gone (2026-09-06 jobs rework): a job row picks its source in its
 * own Source cell, so what is left here is the pure model the row's EEG-net and Montage cells read
 * (`JobsTable`'s `renderNetCell` / `setRowFlexRun`).
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
import type { FlexRun } from "./api";

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

